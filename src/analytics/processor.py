# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Analytics Processor for Blueplane Telemetry Core.

Embedded processor that reads from SQLite and writes to DuckDB for analytics.
Runs on a configurable schedule, separate from the real-time capture pipeline.

See also:
- Architecture: docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md
- Testing: docs/ANALYTICS_TESTING_PLAN.md
- ADR: docs/adr/0001-analytics-service-architecture-decisions.md
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.capture.shared.config import Config
from .workers.sqlite_reader import SQLiteReader
from .workers.duckdb_writer import DuckDBWriter

logger = logging.getLogger(__name__)


class AnalyticsProcessor:
    """
    Analytics processor that processes SQLite traces into DuckDB analytics.
    
    Runs independently from the capture pipeline, reading processed data
    from SQLite and writing structured analytics to DuckDB.
    
    Architecture:
    - Reads from SQLite: docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md
    - Writes to DuckDB: src/analytics/workers/duckdb_writer.py
    - State tracking: Uses analytics_processing_state table in DuckDB
    
    See also:
    - Configuration: config/config.yaml (analytics section)
    - Materialized views design: docs/ANALYTICS_MATERIALIZED_VIEWS.md
    - API endpoints design: docs/ANALYTICS_API_ENDPOINTS.md
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize analytics processor.

        Args:
            config: Configuration instance (creates default if not provided)
        """
        self.config = config or Config()
        
        # Get analytics configuration
        analytics_config = self.config.get("analytics", {})
        if isinstance(analytics_config, dict):
            self.enabled = analytics_config.get("enabled", False)
            self.processing_interval = analytics_config.get("processing_interval", 300)  # 5 minutes default
            self.batch_size = analytics_config.get("batch_size", 1000)
            
            # Get DuckDB path from config
            duckdb_config = analytics_config.get("duckdb", {})
            if isinstance(duckdb_config, dict):
                duckdb_path = duckdb_config.get("db_path")
            else:
                duckdb_path = None
        else:
            self.enabled = False
            self.processing_interval = 300
            self.batch_size = 1000
            duckdb_path = None
        
        # Get database paths
        sqlite_path = self.config.get_path("paths.database.telemetry_db")
        
        if duckdb_path:
            duckdb_path = Path(duckdb_path).expanduser()
        else:
            duckdb_path = Path.home() / ".blueplane" / "analytics.duckdb"
        
        # Initialize state variables (always, even if disabled)
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        if not self.enabled:
            logger.info("Analytics processor is disabled")
            return

        # Initialize readers and writers (only if enabled)
        self.duckdb_writer = DuckDBWriter(duckdb_path)
        self.sqlite_reader = SQLiteReader(sqlite_path, duckdb_writer=self.duckdb_writer)

    async def start(self) -> None:
        """Start the analytics processor."""
        if not self.enabled:
            logger.info("Analytics processor is disabled, not starting")
            return
        
        if self.running:
            logger.warning("Analytics processor already running")
            return
        
        logger.info(f"Starting analytics processor (interval={self.processing_interval}s, batch_size={self.batch_size})")
        
        self.running = True
        self.duckdb_writer.connect()
        
        # Start processing loop
        self._task = asyncio.create_task(self.run())
        
        logger.info("Analytics processor started")

    async def stop(self) -> None:
        """Stop the analytics processor gracefully."""
        if not self.running:
            return
        
        logger.info("Stopping analytics processor...")
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self.duckdb_writer:
            self.duckdb_writer.close()
        
        logger.info("Analytics processor stopped")

    async def run(self) -> None:
        """Main processing loop."""
        while self.running:
            try:
                await self.process_once()
            except asyncio.CancelledError:
                logger.info("Analytics processor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in analytics processing loop: {e}", exc_info=True)
            
            # Wait for next processing interval
            try:
                await asyncio.sleep(self.processing_interval)
            except asyncio.CancelledError:
                break

    async def process_once(self) -> None:
        """
        Process a single batch of traces.
        
        Reads new traces from SQLite since last processed sequence,
        transforms them, and writes to DuckDB.
        """
        logger.debug("Starting analytics processing cycle")
        
        try:
            # Process Cursor traces
            await self._process_platform('cursor')
            
            # Process Claude Code traces
            await self._process_platform('claude_code')
            
            logger.debug("Completed analytics processing cycle")
        
        except Exception as e:
            logger.error(f"Error in analytics processing: {e}", exc_info=True)
            raise

    async def _process_platform(self, platform: str) -> None:
        """
        Process traces for a specific platform.

        Args:
            platform: Platform name ('cursor' or 'claude_code')
        """
        # Run in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._process_platform_sync, platform)

    def _process_platform_sync(self, platform: str) -> None:
        """
        Synchronous processing for a platform (runs in executor).

        Args:
            platform: Platform name ('cursor' or 'claude_code')
        """
        try:
            # Get last processed sequence
            last_sequence = self.sqlite_reader.get_last_processed_sequence(platform)
            
            # Read new traces
            traces = self.sqlite_reader.get_new_traces(
                platform=platform,
                since_sequence=last_sequence,
                limit=self.batch_size
            )
            
            if not traces:
                logger.debug(f"No new traces for {platform} (last_sequence={last_sequence})")
                return
            
            logger.info(f"Processing {len(traces)} new traces for {platform} (sequence {last_sequence + 1} to {traces[-1]['sequence']})")
            
            # Write to DuckDB
            self.duckdb_writer.write_traces(traces)
            
            # Update processing state
            if traces:
                last_trace = traces[-1]
                last_timestamp = last_trace.get('timestamp')
                if isinstance(last_timestamp, str):
                    try:
                        last_timestamp = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        last_timestamp = None
                
                self.sqlite_reader.update_last_processed(
                    platform=platform,
                    sequence=last_trace['sequence'],
                    timestamp=last_timestamp
                )
            
            logger.info(f"Processed {len(traces)} traces for {platform}")
        
        except Exception as e:
            logger.error(f"Error processing {platform} traces: {e}", exc_info=True)
            raise

