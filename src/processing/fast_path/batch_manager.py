# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Batch manager for accumulating events before writing.

Manages batching logic: size-based and time-based flushing.
"""

import time
import threading
from typing import Dict, List, Any, Optional
from collections import deque

import logging

logger = logging.getLogger(__name__)


class BatchManager:
    """
    Manages event batching for efficient writes.
    
    Features:
    - Size-based batching (flush when batch_size reached)
    - Time-based batching (flush after timeout)
    - Thread-safe operations
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
        self._events: deque = deque()
        self._lock = threading.Lock()
        self._first_event_time: Optional[float] = None

    def add_event(self, event: Dict[str, Any]) -> bool:
        """
        Add event to batch.

        Args:
            event: Event dictionary

        Returns:
            True if batch is ready to flush, False otherwise
        """
        with self._lock:
            if len(self._events) == 0:
                self._first_event_time = time.time()

            self._events.append(event)

            # Check if batch is full
            if len(self._events) >= self.batch_size:
                return True

            return False

    def get_batch(self) -> List[Dict[str, Any]]:
        """
        Get current batch and clear it.

        Returns:
            List of events in batch
        """
        with self._lock:
            batch = list(self._events)
            self._events.clear()
            self._first_event_time = None
            return batch

    def clear(self) -> None:
        """Clear current batch."""
        with self._lock:
            self._events.clear()
            self._first_event_time = None

    def should_flush(self) -> bool:
        """
        Check if batch should be flushed based on timeout.

        Returns:
            True if timeout exceeded, False otherwise
        """
        with self._lock:
            if len(self._events) == 0:
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
            return len(self._events)

    def is_empty(self) -> bool:
        """
        Check if batch is empty.

        Returns:
            True if batch is empty
        """
        return self.size() == 0

