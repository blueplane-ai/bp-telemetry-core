# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Main server for Blueplane Telemetry Core processing layer.

Orchestrates fast path consumer, database initialization, and graceful shutdown.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import redis

from .database.sqlite_client import SQLiteClient
from .database.schema import create_schema
from .database.writer import SQLiteBatchWriter
from .fast_path.consumer import FastPathConsumer
from .fast_path.cdc_publisher import CDCPublisher
from .slow_path.worker_pool import WorkerPoolManager
from .cursor.session_monitor import SessionMonitor
from .cursor.database_monitor import CursorDatabaseMonitor
from .claude_code.transcript_monitor import ClaudeCodeTranscriptMonitor
from .metrics.shared_state import SharedMetricsState
from .metrics.calculator import MetricsCalculator
from .metrics.redis_metrics import RedisMetricsStorage
from ..capture.shared.config import Config

logger = logging.getLogger(__name__)


class TelemetryServer:
    """
    Main server for telemetry processing.

    Manages:
    - SQLite database initialization
    - Redis connection
    - Fast path consumer
    - Slow path worker pool
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
        self.worker_pool: Optional[WorkerPoolManager] = None
        self.session_monitor: Optional[SessionMonitor] = None
        self.cursor_monitor: Optional[CursorDatabaseMonitor] = None
        self.claude_code_monitor: Optional[ClaudeCodeTranscriptMonitor] = None
        self.composite_metrics_task: Optional[asyncio.Task] = None
        self.shared_state: Optional[SharedMetricsState] = None
        self.metrics_calculator: Optional[MetricsCalculator] = None
        self.metrics_storage: Optional[RedisMetricsStorage] = None
        self.running = False

    def _initialize_database(self) -> None:
        """Initialize SQLite database and schema."""
        logger.info(f"Initializing database: {self.db_path}")
        
        self.sqlite_client = SQLiteClient(self.db_path)
        
        # Initialize database with optimal settings
        self.sqlite_client.initialize_database()
        
        # Create schema
        create_schema(self.sqlite_client)
        
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
        # Check if cursor monitoring is enabled (default: True)
        # For now, we'll enable it by default. Can be made configurable later.
        enabled = True  # TODO: Load from config

        if not enabled:
            logger.info("Cursor database monitoring is disabled")
            return

        logger.info("Initializing Cursor database monitor")

        # Create session monitor
        self.session_monitor = SessionMonitor(self.redis_client)

        # Create database monitor
        self.cursor_monitor = CursorDatabaseMonitor(
            redis_client=self.redis_client,
            session_monitor=self.session_monitor,
            poll_interval=30.0,
            sync_window_hours=24,
            query_timeout=1.5,
            max_retries=3,
        )

        logger.info("Cursor database monitor initialized")

    def _initialize_claude_code_monitor(self) -> None:
        """Initialize Claude Code transcript monitor."""
        # Check if claude code monitoring is enabled (default: True)
        enabled = True  # TODO: Load from config

        if not enabled:
            logger.info("Claude Code transcript monitoring is disabled")
            return

        logger.info("Initializing Claude Code transcript monitor")

        stream_config = self.config.get_stream_config("message_queue")

        # Create transcript monitor
        self.claude_code_monitor = ClaudeCodeTranscriptMonitor(
            redis_client=self.redis_client,
            stream_name=stream_config.name,
            consumer_group="transcript_processors",
            consumer_name="transcript_monitor-1",
            poll_interval=1.0,
        )

        logger.info("Claude Code transcript monitor initialized")

    def _initialize_worker_pool(self) -> None:
        """Initialize slow path worker pool."""
        logger.info("Initializing worker pool")

        cdc_config = self.config.get_stream_config("cdc")

        self.worker_pool = WorkerPoolManager(
            redis_client=self.redis_client,
            sqlite_client=self.sqlite_client,
            stream_name=cdc_config.name,
            consumer_group="workers",
        )

        logger.info("Worker pool initialized")

    def _initialize_metrics(self) -> None:
        """Initialize metrics components for composite metrics calculation."""
        logger.info("Initializing metrics components")

        # Create shared state and calculator
        self.shared_state = SharedMetricsState(self.redis_client)
        self.metrics_calculator = MetricsCalculator(self.shared_state)
        self.metrics_storage = RedisMetricsStorage(self.redis_client)
        self.metrics_storage.initialize()

        logger.info("Metrics components initialized")

    async def _composite_metrics_updater(self) -> None:
        """
        Background task that updates composite metrics every 30 seconds.

        This runs independently of event processing to avoid performance overhead
        and worker coordination issues. Composite metrics (productivity score)
        are global aggregates that don't need per-event calculation.
        """
        logger.info("Starting composite metrics updater (30 second interval)")

        while self.running:
            try:
                # Calculate composite metrics
                # Note: session_id is empty string since productivity score is global
                metrics = self.metrics_calculator._calculate_composite_metrics("")

                # Record to Redis
                for metric in metrics:
                    self.metrics_storage.record_metric(
                        metric['category'],
                        metric['name'],
                        metric['value']
                    )

                logger.debug(f"Updated composite metrics: {len(metrics)} metrics recorded")

            except Exception as e:
                logger.error(f"Failed to update composite metrics: {e}")

            # Wait 30 seconds before next update
            await asyncio.sleep(30)

        logger.info("Composite metrics updater stopped")

    async def start(self) -> None:
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
            self._initialize_worker_pool()
            self._initialize_cursor_monitor()
            self._initialize_claude_code_monitor()
            self._initialize_metrics()

            # Mark as running before starting background tasks
            self.running = True

            # Start composite metrics updater
            self.composite_metrics_task = asyncio.create_task(
                self._composite_metrics_updater()
            )

            # Start monitors (if enabled) - runs concurrently
            if self.session_monitor and self.cursor_monitor:
                await self.session_monitor.start()
                await self.cursor_monitor.start()

            if self.claude_code_monitor:
                await self.claude_code_monitor.start()

            # Start worker pool
            if self.worker_pool:
                await self.worker_pool.start()

            # Start consumer (this blocks)
            await self.consumer.run()

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if not self.running:
            return

        logger.info("Stopping server...")
        self.running = False

        # Stop composite metrics updater
        if self.composite_metrics_task:
            self.composite_metrics_task.cancel()
            try:
                await self.composite_metrics_task
            except asyncio.CancelledError:
                logger.info("Composite metrics updater cancelled")

        if self.claude_code_monitor:
            await self.claude_code_monitor.stop()

        if self.cursor_monitor:
            await self.cursor_monitor.stop()

        if self.session_monitor:
            await self.session_monitor.stop()

        if self.worker_pool:
            await self.worker_pool.stop()

        if self.consumer:
            self.consumer.stop()

        if self.redis_client:
            self.redis_client.close()

        logger.info("Server stopped")

    async def run(self) -> None:
        """Run the server (alias for start)."""
        await self.start()


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def main() -> None:
    """Main entry point."""
    setup_logging()

    # Create server
    server = TelemetryServer()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(server.stop())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())

