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

            # Start consumer
            self.running = True
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

