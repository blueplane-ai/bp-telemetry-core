# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Worker pool manager for orchestrating slow path workers.

Manages lifecycle of multiple worker instances with:
- Dynamic worker scaling
- Health monitoring
- Backpressure detection
- Graceful shutdown
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import redis

from .worker_base import WorkerBase
from .metrics_worker import MetricsWorker
from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class WorkerPoolManager:
    """
    Manages pools of async workers for different processing types.

    Worker Types:
    - Metrics workers: Calculate and store metrics (priority 1-3)
    - Conversation workers: Build conversation structure (priority 1-2) [Future]
    - AI workers: Generate insights (priority 4-5) [Future]
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: SQLiteClient,
        stream_name: str = "cdc:events",
        consumer_group: str = "workers",
        worker_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize worker pool manager.

        Args:
            redis_client: Redis client instance
            sqlite_client: SQLite client instance
            stream_name: CDC stream name
            consumer_group: Consumer group name
            worker_config: Worker configuration dict (from config/redis.yaml)
                          If None, uses default configuration
        """
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group

        self.workers: List[WorkerBase] = []
        self.worker_tasks: List[asyncio.Task] = []
        self.running = False

        # Worker configuration (use provided config or defaults)
        self.worker_config = worker_config or {
            'metrics': {
                'count': 2,  # Number of metrics workers
                'enabled': True,
            },
            # Future: conversation, ai_insights workers
        }

        logger.info("Initialized worker pool manager")

    async def start(self) -> None:
        """Start all worker pools."""
        if self.running:
            logger.warning("Worker pool already running")
            return

        logger.info("Starting worker pool...")

        # Ensure consumer group exists
        self._ensure_consumer_group()

        # Start metrics workers
        if self.worker_config['metrics']['enabled']:
            await self._start_metrics_workers()

        # Start backpressure monitor
        self.worker_tasks.append(
            asyncio.create_task(self._monitor_backpressure())
        )

        self.running = True
        logger.info(f"Worker pool started with {len(self.workers)} workers")

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        if not self.running:
            return

        logger.info("Stopping worker pool...")
        self.running = False

        # Stop all workers
        for worker in self.workers:
            await worker.stop()

        # Cancel all tasks
        for task in self.worker_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.workers.clear()
        self.worker_tasks.clear()

        logger.info("Worker pool stopped")

    async def _start_metrics_workers(self) -> None:
        """Start metrics worker instances."""
        worker_count = self.worker_config['metrics']['count']

        logger.info(f"Starting {worker_count} metrics workers...")

        for i in range(worker_count):
            worker = MetricsWorker(
                redis_client=self.redis_client,
                sqlite_client=self.sqlite_client,
                stream_name=self.stream_name,
                consumer_group=self.consumer_group,
                consumer_name=f"metrics-worker-{i+1}",
                block_ms=1000,
                count=1,
            )

            self.workers.append(worker)

            # Start worker in background task
            task = asyncio.create_task(self._run_worker(worker, 'metrics'))
            self.worker_tasks.append(task)

        logger.info(f"Started {worker_count} metrics workers")

    async def _run_worker(self, worker: WorkerBase, worker_type: str) -> None:
        """
        Run a single worker with error handling.

        Args:
            worker: Worker instance
            worker_type: Type of worker ('metrics', 'conversation', etc.)
        """
        try:
            await worker.start()
        except asyncio.CancelledError:
            logger.info(f"Worker {worker.consumer_name} cancelled")
        except Exception as e:
            logger.error(f"Worker {worker.consumer_name} failed: {e}")

            # TODO: Implement restart logic with exponential backoff
            # For now, just log the error

    async def _monitor_backpressure(self) -> None:
        """
        Monitor CDC queue depth and log warnings if backpressure builds up.

        Checks:
        - Stream length (number of pending messages)
        - Oldest message age (lag)
        - Consumer group pending entries
        """
        logger.info("Starting backpressure monitor")

        while self.running:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds

                stats = self._get_queue_stats()

                # Log warnings based on queue depth
                if stats['stream_length'] > 50000:
                    logger.critical(
                        f"CDC queue critically high: {stats['stream_length']} messages. "
                        f"Consider scaling workers or reducing ingestion rate."
                    )
                elif stats['stream_length'] > 10000:
                    logger.warning(
                        f"CDC queue depth high: {stats['stream_length']} messages. "
                        f"Processing lag: {stats.get('lag_seconds', 0):.1f}s"
                    )

                # Log pending entries (unacknowledged messages)
                if stats['pending_count'] > 1000:
                    logger.warning(
                        f"High pending count: {stats['pending_count']} unacknowledged messages"
                    )

            except Exception as e:
                logger.error(f"Error in backpressure monitor: {e}")

        logger.info("Backpressure monitor stopped")

    def _get_queue_stats(self) -> Dict[str, Any]:
        """
        Get CDC queue statistics.

        Returns:
            Dictionary with queue stats
        """
        try:
            # Get stream info
            stream_info = self.redis_client.xinfo_stream(self.stream_name)
            stream_length = stream_info.get(b'length', 0)

            # Get pending entries for consumer group
            pending_info = self.redis_client.xpending(self.stream_name, self.consumer_group)
            pending_count = pending_info.get('pending', 0) if pending_info else 0

            # Calculate lag from oldest message
            lag_seconds = 0
            if stream_length > 0:
                # Get first message to calculate age
                messages = self.redis_client.xrange(self.stream_name, count=1)
                if messages:
                    message_id = messages[0][0]
                    # Message ID format: timestamp-sequence
                    timestamp_ms = int(message_id.decode('utf-8').split('-')[0])
                    import time
                    current_ms = int(time.time() * 1000)
                    lag_seconds = (current_ms - timestamp_ms) / 1000.0

            return {
                'stream_length': stream_length,
                'pending_count': pending_count,
                'lag_seconds': lag_seconds,
            }

        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {
                'stream_length': 0,
                'pending_count': 0,
                'lag_seconds': 0,
            }

    def _ensure_consumer_group(self) -> None:
        """Ensure the consumer group exists, create if not."""
        try:
            self.redis_client.xgroup_create(
                name=self.stream_name,
                groupname=self.consumer_group,
                id='0',
                mkstream=True
            )
            logger.info(f"Created consumer group: {self.consumer_group}")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists, this is fine
                logger.debug(f"Consumer group {self.consumer_group} already exists")
            else:
                raise

    def get_worker_stats(self) -> List[Dict[str, Any]]:
        """
        Get statistics for all workers.

        Returns:
            List of worker stat dictionaries
        """
        stats = []
        for worker in self.workers:
            worker_stats = worker.get_stats()

            # Add calculator stats for metrics workers
            if isinstance(worker, MetricsWorker):
                worker_stats['calculator'] = worker.get_calculator_stats()

            stats.append(worker_stats)

        return stats

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get overall pool statistics.

        Returns:
            Dictionary with pool stats
        """
        queue_stats = self._get_queue_stats()

        total_processed = sum(w.stats['processed'] for w in self.workers)
        total_failed = sum(w.stats['failed'] for w in self.workers)

        return {
            'running': self.running,
            'total_workers': len(self.workers),
            'active_workers': sum(1 for w in self.workers if w.running),
            'total_processed': total_processed,
            'total_failed': total_failed,
            'queue_stats': queue_stats,
        }
