# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Main server for Blueplane Telemetry Core processing layer.

Orchestrates fast path consumer, database initialization, and graceful shutdown.
"""

import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

import redis

from .database.sqlite_client import SQLiteClient
from .database.schema import create_schema
from .database.writer import SQLiteBatchWriter
from .fast_path.consumer import FastPathConsumer
from .fast_path.cdc_publisher import CDCPublisher
from .cursor.session_monitor import SessionMonitor
from .cursor.database_monitor import CursorDatabaseMonitor
from .cursor.markdown_monitor import CursorMarkdownMonitor
from .cursor.session_timeout import CursorSessionTimeoutManager
from .cursor.metrics import get_metrics
from .claude_code.transcript_monitor import ClaudeCodeTranscriptMonitor
from .claude_code.session_monitor import ClaudeCodeSessionMonitor
from .claude_code.jsonl_monitor import ClaudeCodeJSONLMonitor
from .claude_code.session_timeout import SessionTimeoutManager
from ..capture.shared.config import Config

logger = logging.getLogger(__name__)


class TelemetryServer:
    """
    Main server for telemetry processing.
    
    Manages:
    - SQLite database initialization
    - Redis connection
    - Fast path consumer
    - Graceful shutdown
    """

    def __init__(self, config: Optional[Config] = None, db_path: Optional[str] = None):
        """
        Initialize telemetry server.

        Args:
            config: Configuration instance (creates default if not provided)
            db_path: Database path (uses default from config if not provided)
        """
        self.config = config or Config()
        self.db_path = db_path or str(Path.home() / ".blueplane" / "telemetry.db")
        
        self.sqlite_client: Optional[SQLiteClient] = None
        self.sqlite_writer: Optional[SQLiteBatchWriter] = None
        self.redis_client: Optional[redis.Redis] = None
        self.cdc_publisher: Optional[CDCPublisher] = None
        self.consumer: Optional[FastPathConsumer] = None
        self.session_monitor: Optional[SessionMonitor] = None
        self.cursor_timeout_manager: Optional[CursorSessionTimeoutManager] = None
        self.cursor_monitor: Optional[CursorDatabaseMonitor] = None
        self.markdown_monitor: Optional[CursorMarkdownMonitor] = None
        self.claude_code_monitor: Optional[ClaudeCodeTranscriptMonitor] = None
        self.claude_session_monitor: Optional[ClaudeCodeSessionMonitor] = None
        self.claude_jsonl_monitor: Optional[ClaudeCodeJSONLMonitor] = None
        self.claude_timeout_manager: Optional[SessionTimeoutManager] = None
        self.running = False
        self.monitor_threads: list[threading.Thread] = []

    def _initialize_database(self) -> None:
        """Initialize SQLite database and schema."""
        logger.info(f"Initializing database: {self.db_path}")
        
        self.sqlite_client = SQLiteClient(self.db_path)
        
        # Initialize database with optimal settings
        self.sqlite_client.initialize_database()
        
        # Check schema version and migrate if needed
        from src.processing.database.schema import (
            create_schema, get_schema_version, migrate_schema, 
            SCHEMA_VERSION, detect_schema_version
        )
        
        current_version = detect_schema_version(self.sqlite_client)
        
        if current_version is None:
            # First time setup - create schema
            logger.info("Creating database schema...")
            create_schema(self.sqlite_client)
            
            # Set schema version
            self.sqlite_client.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
            )
            self.sqlite_client.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )
            logger.info(f"Database schema created (version {SCHEMA_VERSION})")
        elif current_version < SCHEMA_VERSION:
            # Migration needed
            logger.info(f"Migrating schema from version {current_version} to {SCHEMA_VERSION}")
            migrate_schema(self.sqlite_client, current_version, SCHEMA_VERSION)
        else:
            # Ensure schema exists (for new tables)
            create_schema(self.sqlite_client)
            logger.info(f"Database schema is up to date (version {current_version})")
        
        # Create writer
        self.sqlite_writer = SQLiteBatchWriter(self.sqlite_client)
        
        logger.info("Database initialized successfully")

    def _initialize_redis(self) -> None:
        """Initialize Redis connection."""
        logger.info("Initializing Redis connection")
        
        redis_config = self.config.redis
        
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            socket_timeout=redis_config.socket_timeout,
            socket_connect_timeout=redis_config.socket_connect_timeout,
            decode_responses=False,  # We handle encoding/decoding
        )
        
        # Test connection
        try:
            self.redis_client.ping()
            logger.info("Redis connection established")
        except redis.ConnectionError as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}") from e

    def _initialize_consumer(self) -> None:
        """Initialize fast path consumer."""
        logger.info("Initializing fast path consumer")
        
        stream_config = self.config.get_stream_config("message_queue")
        cdc_config = self.config.get_stream_config("cdc")
        
        # Create CDC publisher
        self.cdc_publisher = CDCPublisher(
            self.redis_client,
            stream_name=cdc_config.name,
            max_length=cdc_config.max_length
        )
        
        # Create consumer
        self.consumer = FastPathConsumer(
            redis_client=self.redis_client,
            sqlite_writer=self.sqlite_writer,
            cdc_publisher=self.cdc_publisher,
            stream_name=stream_config.name,
            consumer_group=stream_config.consumer_group,
            consumer_name=f"{stream_config.consumer_group}-1",
            batch_size=stream_config.count,
            batch_timeout=stream_config.block_ms / 1000.0,
            block_ms=stream_config.block_ms,
        )
        
        logger.info("Fast path consumer initialized")

    def _initialize_cursor_monitor(self) -> None:
        """Initialize Cursor database monitor."""
        # Load cursor config
        cursor_config = self.config.get_cursor_config("database_monitor")
        enabled = cursor_config.get("enabled", True)

        if not enabled:
            logger.info("Cursor database monitoring is disabled")
            return

        logger.info("Initializing Cursor database monitor")

        # Create session monitor (with database persistence)
        self.session_monitor = SessionMonitor(
            redis_client=self.redis_client,
            sqlite_client=self.sqlite_client
        )

        # Create timeout manager for abandoned sessions
        self.cursor_timeout_manager = CursorSessionTimeoutManager(
            session_monitor=self.session_monitor,
            sqlite_client=self.sqlite_client,
            timeout_hours=24,
            cleanup_interval=3600.0
        )

        # Create database monitor
        self.cursor_monitor = CursorDatabaseMonitor(
            redis_client=self.redis_client,
            session_monitor=self.session_monitor,
            poll_interval=cursor_config.get("poll_interval_seconds", 30.0),
            sync_window_hours=cursor_config.get("sync_window_hours", 24),
            query_timeout=cursor_config.get("query_timeout_seconds", 1.5),
            max_retries=cursor_config.get("max_retries", 3),
        )

        logger.info("Cursor database monitor initialized")

    def _initialize_markdown_monitor(self) -> None:
        """Initialize Cursor Markdown History monitor."""
        # Load cursor config
        markdown_config = self.config.get_cursor_config("markdown_monitor")
        duckdb_config = self.config.get_cursor_config("duckdb_sink")
        
        enabled = markdown_config.get("enabled", True)

        if not enabled:
            logger.info("Cursor Markdown History monitoring is disabled")
            return

        # Require session monitor to be initialized
        if not self.session_monitor:
            logger.warning("Session monitor not initialized, cannot start Markdown monitor")
            return

        logger.info("Initializing Cursor Markdown History monitor")

        # Get output directory from config
        output_dir = markdown_config.get("output_dir")
        if output_dir:
            output_dir = Path(output_dir)
        
        # Get DuckDB settings
        enable_duckdb = duckdb_config.get("enabled", False)
        duckdb_path = duckdb_config.get("database_path")
        if duckdb_path:
            duckdb_path = Path(duckdb_path)
        
        # Create markdown monitor
        self.markdown_monitor = CursorMarkdownMonitor(
            session_monitor=self.session_monitor,
            output_dir=output_dir,
            poll_interval=markdown_config.get("poll_interval_seconds", 120.0),
            debounce_delay=markdown_config.get("debounce_delay_seconds", 10.0),
            query_timeout=markdown_config.get("query_timeout_seconds", 1.5),
            enable_duckdb=enable_duckdb,
            duckdb_path=duckdb_path,
        )

        logger.info(
            f"Cursor Markdown History monitor initialized "
            f"(output_dir={output_dir or 'workspace/.history/'}, "
            f"poll_interval={markdown_config.get('poll_interval_seconds', 120)}s, "
            f"debounce={markdown_config.get('debounce_delay_seconds', 10)}s, "
            f"duckdb_enabled={enable_duckdb})"
        )

    def _initialize_claude_code_monitor(self) -> None:
        """Initialize Claude Code monitors (session, JSONL, transcript)."""
        # Check if claude code monitoring is enabled (default: True)
        enabled = True  # TODO: Load from config

        if not enabled:
            logger.info("Claude Code monitoring is disabled")
            return

        logger.info("Initializing Claude Code monitors")

        stream_config = self.config.get_stream_config("message_queue")

        # Create session monitor (tracks active sessions via Redis events)
        # Pass sqlite_client for database persistence
        self.claude_session_monitor = ClaudeCodeSessionMonitor(
            redis_client=self.redis_client,
            sqlite_client=self.sqlite_client
        )
        
        # Create timeout manager for abandoned sessions
        self.claude_timeout_manager = SessionTimeoutManager(
            session_monitor=self.claude_session_monitor,
            sqlite_client=self.sqlite_client,
            timeout_hours=24,
            cleanup_interval=3600.0
        )

        # Create JSONL monitor (watches JSONL files for active sessions)
        self.claude_jsonl_monitor = ClaudeCodeJSONLMonitor(
            redis_client=self.redis_client,
            session_monitor=self.claude_session_monitor,
            sqlite_client=self.sqlite_client,
            poll_interval=30.0,
        )

        # Create transcript monitor (existing implementation)
        self.claude_code_monitor = ClaudeCodeTranscriptMonitor(
            redis_client=self.redis_client,
            stream_name=stream_config.name,
            consumer_group="transcript_processors",
            consumer_name="transcript_monitor-1",
            poll_interval=1.0,
        )

        logger.info("Claude Code monitors initialized")

    async def _log_metrics_periodically(self):
        """Log metrics periodically."""
        import asyncio
        while self.running:
            await asyncio.sleep(300)  # Every 5 minutes
            try:
                metrics = get_metrics()
                stats = metrics.get_stats()
                if stats:
                    logger.info(f"Session metrics: {stats}")
            except Exception as e:
                logger.debug(f"Error logging metrics: {e}")

    def start(self) -> None:
        """Start the server."""
        if self.running:
            logger.warning("Server already running")
            return

        logger.info("Starting Blueplane Telemetry Server...")

        try:
            # Initialize components
            self._initialize_database()
            self._initialize_redis()
            self._initialize_consumer()
            self._initialize_cursor_monitor()
            self._initialize_markdown_monitor()
            self._initialize_claude_code_monitor()

            # Start monitors in background threads (if enabled)
            if self.session_monitor:
                def run_session_monitor():
                    import asyncio
                    import logging
                    logger = logging.getLogger(__name__)
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.session_monitor.start())
                    except Exception as e:
                        logger.error(f"Cursor session monitor thread crashed: {e}", exc_info=True)
                
                session_thread = threading.Thread(target=run_session_monitor, daemon=True)
                session_thread.start()
                self.monitor_threads.append(session_thread)
                logger.info("Cursor session monitor started")
            
            if self.cursor_monitor:
                def run_cursor_monitor():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.cursor_monitor.start())
                
                cursor_thread = threading.Thread(target=run_cursor_monitor, daemon=True)
                cursor_thread.start()
                self.monitor_threads.append(cursor_thread)
                logger.info("Cursor database monitor started")
            
            if self.cursor_timeout_manager:
                def run_cursor_timeout_manager():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.cursor_timeout_manager.start())
                
                cursor_timeout_thread = threading.Thread(target=run_cursor_timeout_manager, daemon=True)
                cursor_timeout_thread.start()
                self.monitor_threads.append(cursor_timeout_thread)
                logger.info("Cursor session timeout manager started")

            # Start metrics logging task (if Cursor monitoring enabled)
            if self.session_monitor:
                def run_metrics_logger():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._log_metrics_periodically())
                
                metrics_thread = threading.Thread(target=run_metrics_logger, daemon=True)
                metrics_thread.start()
                self.monitor_threads.append(metrics_thread)
                logger.info("Session metrics logger started")

            # Start markdown monitor (if enabled)
            if self.markdown_monitor:
                def run_markdown_monitor():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.markdown_monitor.start())
                
                markdown_thread = threading.Thread(target=run_markdown_monitor, daemon=True)
                markdown_thread.start()
                self.monitor_threads.append(markdown_thread)
                logger.info("Cursor Markdown History monitor started")

            # Start Claude Code monitors (if enabled)
            if self.claude_session_monitor and self.claude_jsonl_monitor:
                def run_claude_session_monitor():
                    import asyncio
                    import logging
                    logger = logging.getLogger(__name__)
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.claude_session_monitor.start())
                    except Exception as e:
                        logger.error(f"Claude Code session monitor thread crashed: {e}", exc_info=True)

                def run_claude_jsonl_monitor():
                    import asyncio
                    import logging
                    logger = logging.getLogger(__name__)
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.claude_jsonl_monitor.start())
                    except Exception as e:
                        logger.error(f"Claude Code JSONL monitor thread crashed: {e}", exc_info=True)
                
                def run_claude_timeout_manager():
                    import asyncio
                    import logging
                    logger = logging.getLogger(__name__)
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.claude_timeout_manager.start())
                    except Exception as e:
                        logger.error(f"Claude Code timeout manager thread crashed: {e}", exc_info=True)

                claude_session_thread = threading.Thread(target=run_claude_session_monitor, daemon=True)
                claude_jsonl_thread = threading.Thread(target=run_claude_jsonl_monitor, daemon=True)
                claude_timeout_thread = threading.Thread(target=run_claude_timeout_manager, daemon=True)
                claude_session_thread.start()
                claude_jsonl_thread.start()
                claude_timeout_thread.start()
                self.monitor_threads.extend([claude_session_thread, claude_jsonl_thread, claude_timeout_thread])
                logger.info("Claude Code session, JSONL monitors, and timeout manager started")

            if self.claude_code_monitor:
                def run_claude_code_monitor():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.claude_code_monitor._monitor_loop())

                # Set running flag
                self.claude_code_monitor.running = True
                # Ensure consumer group exists
                try:
                    self.redis_client.xgroup_create(
                        self.claude_code_monitor.stream_name,
                        self.claude_code_monitor.consumer_group,
                        id='0',
                        mkstream=True
                    )
                    logger.info("Created consumer group: %s", self.claude_code_monitor.consumer_group)
                except redis.exceptions.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        logger.error("Failed to create consumer group: %s", e)
                        raise
                    logger.debug("Consumer group already exists: %s", self.claude_code_monitor.consumer_group)

                claude_thread = threading.Thread(target=run_claude_code_monitor, daemon=True)
                claude_thread.start()
                self.monitor_threads.append(claude_thread)
                logger.info("Claude Code transcript monitor started")

            # Start consumer (this blocks)
            self.running = True
            self.consumer.run()

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    def stop(self) -> None:
        """Stop the server gracefully."""
        if not self.running:
            return

        logger.info("Stopping server...")
        
        # Log final metrics before shutdown
        try:
            metrics = get_metrics()
            stats = metrics.get_stats()
            if stats:
                logger.info(f"Final session metrics: {stats}")
        except Exception as e:
            logger.debug(f"Error logging final metrics: {e}")
        self.running = False

        # Stop Cursor timeout manager
        if self.cursor_timeout_manager:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.cursor_timeout_manager.stop())

        # Stop Claude Code monitors
        if self.claude_timeout_manager:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.claude_timeout_manager.stop())

        if self.claude_jsonl_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.claude_jsonl_monitor.stop())

        if self.claude_session_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.claude_session_monitor.stop())

        if self.claude_code_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.claude_code_monitor.stop())

        if self.markdown_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.markdown_monitor.stop())

        # Stop Cursor monitors
        if self.cursor_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.cursor_monitor.stop())

        if self.session_monitor:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.session_monitor.stop())

        # Stop consumer
        if self.consumer:
            self.consumer.stop()

        # Close Redis connection
        if self.redis_client:
            self.redis_client.close()

        logger.info("Server stopped")

    def run(self) -> None:
        """Run the server (alias for start)."""
        self.start()


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main() -> None:
    """Main entry point."""
    setup_logging()

    # Create server
    server = TelemetryServer()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        server.stop()


if __name__ == "__main__":
    main()
