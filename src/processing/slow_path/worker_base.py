# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Base class for slow path workers.

Workers consume CDC events from Redis Streams and process them asynchronously.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import redis

logger = logging.getLogger(__name__)


class WorkerBase(ABC):
    """
    Base class for slow path workers.

    Workers process CDC events asynchronously with:
    - Automatic retry via PEL (Pending Entries List)
    - Error handling and logging
    - Graceful shutdown
    - Health monitoring
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream_name: str = "cdc:events",
        consumer_group: str = "workers",
        consumer_name: str = "worker-1",
        block_ms: int = 1000,
        count: int = 1,
        priorities: Optional[List[int]] = None,
    ):
        """
        Initialize worker.

        Args:
            redis_client: Redis client instance
            stream_name: Name of CDC stream to consume from
            consumer_group: Consumer group name
            consumer_name: Unique consumer name
            block_ms: Milliseconds to block when waiting for messages
            count: Number of messages to read per batch
            priorities: List of priority levels this worker should process (None = all)
        """
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.block_ms = block_ms
        self.count = count
        self.priorities = priorities

        self.running = False
        self.stats = {
            'processed': 0,
            'failed': 0,
            'errors': [],
        }

    async def start(self) -> None:
        """Start the worker."""
        if self.running:
            logger.warning(f"{self.consumer_name} already running")
            return

        logger.info(f"Starting worker: {self.consumer_name}")

        # Ensure consumer group exists
        self._ensure_consumer_group()

        self.running = True
        await self._run()

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        if not self.running:
            return

        logger.info(f"Stopping worker: {self.consumer_name}")
        self.running = False

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
                pass
            else:
                raise

    async def _run(self) -> None:
        """Main worker loop."""
        logger.info(f"Worker {self.consumer_name} entering main loop")

        while self.running:
            try:
                # Read from stream using consumer group
                messages = self.redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.stream_name: '>'},
                    count=self.count,
                    block=self.block_ms,
                )

                if not messages:
                    # No messages available
                    await asyncio.sleep(0.1)
                    continue

                # Process each message
                for stream_name, message_list in messages:
                    for message_id, message_data in message_list:
                        await self._process_message(message_id, message_data)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                self.stats['errors'].append(str(e))
                await asyncio.sleep(1)  # Back off on error

        logger.info(f"Worker {self.consumer_name} exited main loop")

    async def _process_message(self, message_id: bytes, message_data: Dict[bytes, bytes]) -> None:
        """
        Process a single CDC message.

        Args:
            message_id: Redis stream message ID
            message_data: Message data dictionary
        """
        try:
            # Decode message data
            event = self._decode_message(message_data)

            # Check priority filter
            if self.priorities is not None:
                priority = event.get('priority', 5)
                if priority not in self.priorities:
                    # Not for this worker, acknowledge and skip
                    self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
                    return

            # Process the event (implemented by subclass)
            await self.process_event(event)

            # Acknowledge message
            self.redis_client.xack(self.stream_name, self.consumer_group, message_id)

            # Update stats
            self.stats['processed'] += 1

        except Exception as e:
            logger.error(f"Failed to process message {message_id}: {e}")
            self.stats['failed'] += 1

            # Still acknowledge to prevent infinite retry
            # TODO: Consider DLQ for permanent failures
            self.redis_client.xack(self.stream_name, self.consumer_group, message_id)

    def _decode_message(self, message_data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """
        Decode Redis stream message data.

        Args:
            message_data: Raw message data from Redis

        Returns:
            Decoded event dictionary
        """
        return {
            key.decode('utf-8'): value.decode('utf-8')
            for key, value in message_data.items()
        }

    @abstractmethod
    async def process_event(self, event: Dict[str, Any]) -> None:
        """
        Process a single CDC event.

        Must be implemented by subclasses.

        Args:
            event: CDC event dictionary with keys:
                - sequence: Sequence number in SQLite
                - event_id: Event ID
                - session_id: Session ID
                - event_type: Type of event
                - platform: Platform name
                - timestamp: Event timestamp
                - priority: Priority level
        """
        raise NotImplementedError

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            'worker': self.consumer_name,
            'running': self.running,
            **self.stats
        }
