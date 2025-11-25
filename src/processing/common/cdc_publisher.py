# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
CDC (Change Data Capture) publisher for slow path coordination.

Publishes events to Redis Streams for async worker processing.
"""

import json
import logging
from typing import Dict, Any, Optional
import redis

from ...capture.shared.redis_streams import CDC_EVENTS_STREAM

logger = logging.getLogger(__name__)


class CDCPublisher:
    """
    Publishes change data capture events to Redis Streams.
    
    Features:
    - Fire-and-forget pattern (doesn't block fast path)
    - Priority-based routing for workers
    - Auto-trim stream to prevent unbounded growth
    """

    def __init__(self, redis_client: redis.Redis, stream_name: str = CDC_EVENTS_STREAM, max_length: int = 100000):
        """
        Initialize CDC publisher.

        Args:
            redis_client: Redis client instance
            stream_name: Name of CDC stream
            max_length: Maximum stream length before trimming
        """
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.max_length = max_length

    def _calculate_priority(self, event: Dict[str, Any]) -> int:
        """
        Calculate priority level for event.

        Priority levels (1=highest):
        1 - user_prompt, acceptance_decision
        2 - tool_use, completion
        3 - performance, latency
        4 - session_start, session_end
        5 - debug/trace events

        Args:
            event: Event dictionary

        Returns:
            Priority level (1-5)
        """
        event_type = event.get('event_type', '')

        if event_type in ('user_prompt', 'acceptance_decision'):
            return 1
        elif event_type in ('tool_use', 'mcp_execution', 'assistant_response'):
            return 2
        elif event_type in ('file_edit', 'shell_execution'):
            return 3
        elif event_type in ('session_start', 'session_end'):
            return 4
        else:
            return 5

    def publish(self, sequence: int, event: Dict[str, Any], priority: Optional[int] = None) -> None:
        """
        Publish CDC event to Redis Stream (fire-and-forget).

        Args:
            sequence: Sequence number from SQLite
            event: Event dictionary
            priority: Priority level (calculated if not provided)
        """
        if priority is None:
            priority = self._calculate_priority(event)

        try:
            # Build CDC event
            cdc_event = {
                'sequence': sequence,
                'event_id': event.get('event_id', ''),
                'session_id': event.get('session_id', ''),
                'event_type': event.get('event_type', ''),
                'platform': event.get('platform', ''),
                'timestamp': event.get('timestamp', ''),
                'priority': priority,
            }

            # Publish to stream with auto-trim
            self.redis_client.xadd(
                self.stream_name,
                cdc_event,
                maxlen=self.max_length,
                approximate=True
            )

            logger.debug(f"Published CDC event: sequence={sequence}, priority={priority}")

        except Exception as e:
            # Log but don't block - CDC failures don't affect fast path
            logger.warning(f"Failed to publish CDC event: {e}")

