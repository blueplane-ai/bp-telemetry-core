# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Batch manager for accumulating events before writing.

Manages batching logic: size-based and time-based flushing.
"""

import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, Iterable
from collections import deque

import logging

logger = logging.getLogger(__name__)


@dataclass
class BatchItem:
    event: Dict[str, Any]
    message_id: str
    added_at: float


class BatchManager:
    """
    Manages event batching for efficient writes.
    
    Features:
    - Size-based batching (flush when batch_size reached)
    - Time-based batching (flush after timeout)
    - Thread-safe operations
    - Tracks message IDs alongside events for proper ACK handling
    """

    def __init__(self, batch_size: int = 100, batch_timeout: float = 0.1):
        """
        Initialize batch manager.

        Args:
            batch_size: Maximum number of events per batch
            batch_timeout: Maximum time (seconds) to wait before flushing
        """
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        # Store BatchItem entries to preserve metadata for ACK handling
        self._batch_items: deque[BatchItem] = deque()
        self._lock = threading.Lock()
        self._first_event_time: Optional[float] = None

    def add_event(self, event: Dict[str, Any], message_id: str) -> bool:
        """
        Add event to batch with its message ID.

        Args:
            event: Event dictionary
            message_id: Redis Stream message ID (required for ACK)

        Returns:
            True if batch is ready to flush, False otherwise
        """
        with self._lock:
            now = time.time()
            if len(self._batch_items) == 0:
                self._first_event_time = now

            self._batch_items.append(BatchItem(event=event, message_id=message_id, added_at=now))

            # Check if batch is full
            if len(self._batch_items) >= self.batch_size:
                return True

            return False

    def get_batch(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Get current batch and clear it.

        Returns:
            Tuple of (events, message_ids) - both lists in same order
        """
        with self._lock:
            events = []
            message_ids = []
            while self._batch_items:
                item = self._batch_items.popleft()
                events.append(item.event)
                message_ids.append(item.message_id)
            
            self._batch_items.clear()
            self._first_event_time = None
            return events, message_ids

    def clear(self) -> None:
        """Clear current batch."""
        with self._lock:
            self._batch_items.clear()
            self._first_event_time = None

    def remove_message_ids(self, message_ids: Iterable[str]) -> None:
        """
        Remove specific message IDs from the current batch.

        Args:
            message_ids: Iterable of message IDs to remove
        """
        ids = set(message_ids)
        if not ids:
            return

        with self._lock:
            if not self._batch_items:
                return

            filtered_items = deque(item for item in self._batch_items if item.message_id not in ids)
            self._batch_items = filtered_items

            if self._batch_items:
                self._first_event_time = self._batch_items[0].added_at
            else:
                self._first_event_time = None

    def should_flush(self) -> bool:
        """
        Check if batch should be flushed based on timeout.

        Returns:
            True if timeout exceeded, False otherwise
        """
        with self._lock:
            if len(self._batch_items) == 0:
                return False

            if self._first_event_time is None:
                return False

            elapsed = time.time() - self._first_event_time
            return elapsed >= self.batch_timeout

    def size(self) -> int:
        """
        Get current batch size.

        Returns:
            Number of events in current batch
        """
        with self._lock:
            return len(self._batch_items)

    def is_empty(self) -> bool:
        """
        Check if batch is empty.

        Returns:
            True if batch is empty
        """
        return self.size() == 0

