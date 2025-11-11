# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Metrics worker for async metrics calculation.

Consumes CDC events, fetches full event data from SQLite,
calculates metrics, and stores them in Redis.
"""

import json
import zlib
import logging
from typing import Dict, Any, Optional
import redis

from .worker_base import WorkerBase
from ..metrics.calculator import MetricsCalculator
from ..metrics.redis_metrics import RedisMetricsStorage
from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class MetricsWorker(WorkerBase):
    """
    Worker for calculating and storing metrics.

    Processes CDC events to:
    - Fetch full event from SQLite raw_traces
    - Calculate relevant metrics
    - Store metrics in Redis
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: SQLiteClient,
        stream_name: str = "cdc:events",
        consumer_group: str = "workers",
        consumer_name: str = "metrics-worker-1",
        block_ms: int = 1000,
        count: int = 1,
    ):
        """
        Initialize metrics worker.

        Args:
            redis_client: Redis client instance
            sqlite_client: SQLite client instance
            stream_name: CDC stream name
            consumer_group: Consumer group name
            consumer_name: Unique consumer name
            block_ms: Milliseconds to block when waiting for messages
            count: Number of messages to read per batch
        """
        # Initialize with priority filter for metrics-relevant events
        # Priority 1-3: user prompts, tool use, file edits
        super().__init__(
            redis_client=redis_client,
            stream_name=stream_name,
            consumer_group=consumer_group,
            consumer_name=consumer_name,
            block_ms=block_ms,
            count=count,
            priorities=[1, 2, 3],  # High and medium priority events
        )

        self.sqlite_client = sqlite_client
        self.metrics_storage = RedisMetricsStorage(redis_client)

        # CRITICAL FIX: Use SharedMetricsState instead of in-memory state
        # This ensures accurate metrics across multiple workers
        from ..metrics.shared_state import SharedMetricsState
        self.shared_state = SharedMetricsState(redis_client)
        self.calculator = MetricsCalculator(self.shared_state)

        # Initialize metrics storage
        self.metrics_storage.initialize()

        logger.info(f"Initialized metrics worker: {consumer_name}")

    async def process_event(self, cdc_event: Dict[str, Any]) -> None:
        """
        Process a CDC event to calculate and store metrics.

        Args:
            cdc_event: CDC event dictionary with:
                - sequence: Sequence number in SQLite
                - event_id: Event ID
                - session_id: Session ID
                - event_type: Event type
                - platform: Platform name
                - timestamp: Event timestamp
                - priority: Priority level
        """
        try:
            sequence = int(cdc_event.get('sequence', 0))
            if sequence == 0:
                logger.warning("CDC event missing sequence number")
                return

            # Fetch full event from SQLite
            full_event = self._fetch_event_from_sqlite(sequence)
            if not full_event:
                logger.warning(f"Could not fetch event for sequence {sequence}")
                return

            # Calculate metrics for this event
            metrics = self.calculator.calculate_metrics_for_event(full_event)

            # Store each metric in Redis
            for metric in metrics:
                self.metrics_storage.record_metric(
                    category=metric['category'],
                    name=metric['name'],
                    value=metric['value'],
                    labels=metric.get('labels')
                )

            logger.debug(f"Processed metrics for event {sequence}: {len(metrics)} metrics calculated")

        except Exception as e:
            logger.error(f"Error processing event in metrics worker: {e}")
            raise

    def _fetch_event_from_sqlite(self, sequence: int) -> Optional[Dict[str, Any]]:
        """
        Fetch full event from SQLite by sequence number.

        Args:
            sequence: Sequence number

        Returns:
            Full event dictionary or None if not found
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        event_id,
                        session_id,
                        event_type,
                        platform,
                        timestamp,
                        workspace_hash,
                        model,
                        tool_name,
                        duration_ms,
                        tokens_used,
                        lines_added,
                        lines_removed,
                        event_data
                    FROM raw_traces
                    WHERE sequence = ?
                    """,
                    (sequence,)
                )

                row = cursor.fetchone()
                if not row:
                    return None

                # Decompress event_data
                compressed_data = row[12]
                decompressed_data = zlib.decompress(compressed_data)
                event_data = json.loads(decompressed_data)

                # Build full event with indexed fields and payload
                full_event = {
                    'event_id': row[0],
                    'session_id': row[1],
                    'event_type': row[2],
                    'platform': row[3],
                    'timestamp': row[4],
                    'workspace_hash': row[5],
                    'model': row[6],
                    'tool_name': row[7],
                    'duration_ms': row[8],
                    'tokens_used': row[9],
                    'lines_added': row[10],
                    'lines_removed': row[11],
                    'payload': event_data.get('payload', {}),
                }

                return full_event

        except Exception as e:
            logger.error(f"Failed to fetch event {sequence} from SQLite: {e}")
            return None

    def get_calculator_stats(self) -> Dict[str, Any]:
        """Get current calculator statistics."""
        return self.calculator.get_current_stats()
