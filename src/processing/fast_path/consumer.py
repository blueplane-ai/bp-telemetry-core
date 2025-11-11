# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Fast path consumer for Redis Streams.

Reads events from Redis Streams, batches them, writes to SQLite,
and publishes CDC events for slow path workers.
"""

import json
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from collections import deque
import redis

from .batch_manager import BatchManager
from .cdc_publisher import CDCPublisher
from ..database.writer import SQLiteBatchWriter

logger = logging.getLogger(__name__)


class FastPathConsumer:
    """
    High-throughput consumer that writes raw events with zero blocking.
    
    Target: <10ms per batch at P95.
    
    Features:
    - Redis Streams XREADGROUP for consumer groups
    - Batch accumulation (100 events or 100ms timeout)
    - SQLite batch writes with compression
    - CDC event publishing
    - Dead Letter Queue (DLQ) for failed messages
    - Pending Entries List (PEL) retry handling
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_writer: SQLiteBatchWriter,
        cdc_publisher: CDCPublisher,
        stream_name: str = "telemetry:events",
        consumer_group: str = "processors",
        consumer_name: str = "fast-path-1",
        batch_size: int = 100,
        batch_timeout: float = 0.1,
        block_ms: int = 1000,
        max_retries: int = 3,
    ):
        """
        Initialize fast path consumer.

        Args:
            redis_client: Redis client instance
            sqlite_writer: SQLite batch writer
            cdc_publisher: CDC publisher
            stream_name: Redis Stream name
            consumer_group: Consumer group name
            consumer_name: Consumer name (unique per instance)
            batch_size: Maximum batch size
            batch_timeout: Batch timeout in seconds
            block_ms: Blocking timeout for XREADGROUP (ms)
            max_retries: Maximum retries before DLQ
        """
        self.redis_client = redis_client
        self.sqlite_writer = sqlite_writer
        self.cdc_publisher = cdc_publisher
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.batch_manager = BatchManager(batch_size, batch_timeout)
        self.block_ms = block_ms
        self.max_retries = max_retries
        self.running = False
        self.dlq_stream = "telemetry:dlq"
        
        # Backpressure handling
        self.current_batch_size = batch_size  # Adaptive batch size
        self.min_batch_size = 10  # Minimum batch size
        self.max_batch_size = batch_size  # Maximum batch size
        self.write_times = deque(maxlen=100)  # Track write latencies for backpressure

    async def _ensure_consumer_group(self) -> None:
        """Ensure consumer group exists, create if not."""
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0",
                mkstream=True
            )
            logger.info(f"Created consumer group {self.consumer_group}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists, that's fine
                logger.debug(f"Consumer group {self.consumer_group} already exists")
            else:
                raise

    async def _read_messages(self) -> List[Dict[str, Any]]:
        """
        Read messages from Redis Streams using XREADGROUP.

        Returns:
            List of message dictionaries with 'id' and 'event' keys
        """
        try:
            # Read from stream with consumer group
            # Note: redis-py xreadgroup returns list of tuples: [(stream_name, [(id, {field: value}), ...])]
            messages = self.redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream_name: ">"},
                count=self.batch_manager.batch_size,
                block=self.block_ms
            )

            if not messages:
                return []

            # Parse messages
            # queue_writer stores events as flat key-value pairs:
            # event_id, enqueued_at, platform, hook_type, timestamp, payload (JSON), metadata (JSON), etc.
            result = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    # Convert message_id to string
                    msg_id = message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id)
                    
                    try:
                        # Reconstruct event from flat fields
                        event = {}
                        
                        # Helper to decode field value
                        def decode_field(key, value):
                            if isinstance(value, bytes):
                                return value.decode('utf-8')
                            return str(value)
                        
                        # Copy top-level fields
                        for key, value in fields.items():
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                            val_str = decode_field(key_str, value)
                            
                            # Parse JSON fields (payload, metadata)
                            if key_str in ('payload', 'metadata'):
                                try:
                                    event[key_str] = json.loads(val_str)
                                except json.JSONDecodeError:
                                    event[key_str] = {}
                            else:
                                # Store other fields as-is
                                event[key_str] = val_str
                        
                        # Ensure required fields exist
                        if 'event_id' not in event:
                            event['event_id'] = msg_id
                        if 'session_id' not in event:
                            # Use external_session_id if available
                            event['session_id'] = event.get('external_session_id', '')
                        
                        result.append({
                            'id': msg_id,
                            'event': event
                        })
                        
                    except Exception as e:
                        logger.error(f"Failed to parse event from message {msg_id}: {e}")
                        result.append({
                            'id': msg_id,
                            'event': None,
                            'error': str(e)
                        })

            return result

        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading messages: {e}")
            return []

    async def _process_batch(self, messages: List[Dict[str, Any]]) -> List[str]:
        """
        Process batch of messages: write to SQLite and publish CDC events.
        
        ACKs messages immediately after successful write to prevent message loss.

        Args:
            messages: List of message dictionaries

        Returns:
            List of message IDs that were successfully processed
        """
        if not messages:
            return []

        # Extract events (skip None events from parse errors)
        events = []
        valid_message_ids = []
        for msg in messages:
            if msg['event'] is not None:
                events.append(msg['event'])
                valid_message_ids.append(msg['id'])
            else:
                # Invalid event - send to DLQ immediately
                await self._handle_failed_message(msg['id'], msg.get('event'), retry_count=self.max_retries)

        if not events:
            return []

        try:
            # Write to SQLite (runs in thread pool, non-blocking)
            start_time = time.time()
            sequences = await self.sqlite_writer.write_batch(events)
            write_duration = time.time() - start_time
            
            # Track write latency for backpressure
            self.write_times.append(write_duration)
            
            # Publish CDC events (fire-and-forget, synchronous call)
            for sequence, event in zip(sequences, events):
                self.cdc_publisher.publish(sequence, event)

            logger.debug(f"Processed batch: {len(events)} events, sequences {sequences[0]}-{sequences[-1]}, duration: {write_duration:.3f}s")
            
            # ACK messages immediately after successful write
            # This prevents message loss if consumer crashes
            await self._ack_messages(valid_message_ids)
            
            return valid_message_ids

        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
            # Don't ACK messages - they'll retry via PEL
            return []

    async def _ack_messages(self, message_ids: List[str]) -> None:
        """
        Acknowledge processed messages.

        Args:
            message_ids: List of message IDs to acknowledge
        """
        if not message_ids:
            return

        try:
            self.redis_client.xack(
                self.stream_name,
                self.consumer_group,
                *message_ids
            )
        except Exception as e:
            logger.error(f"Failed to ACK messages: {e}")

    async def _handle_failed_message(self, message_id: str, event: Optional[Dict], retry_count: int) -> None:
        """
        Handle failed message: send to DLQ if max retries exceeded.

        Args:
            message_id: Message ID
            event: Event data (may be None)
            retry_count: Current retry count
        """
        if retry_count >= self.max_retries:
            # Send to Dead Letter Queue
            try:
                dlq_data = {
                    'message_id': message_id,
                    'retry_count': retry_count,
                    'event': json.dumps(event) if event else 'null',
                }
                self.redis_client.xadd(
                    self.dlq_stream,
                    dlq_data,
                    maxlen=1000,
                    approximate=True
                )
                logger.warning(f"Sent message {message_id} to DLQ after {retry_count} retries")
            except Exception as e:
                logger.error(f"Failed to send message to DLQ: {e}")

    def _adjust_batch_size(self) -> None:
        """
        Adjust batch size based on write latency (adaptive backpressure).
        
        If writes are slow, reduce batch size to prevent memory buildup.
        If writes are fast, increase batch size for better throughput.
        """
        if len(self.write_times) < 10:
            # Not enough data yet
            return
        
        # Calculate average write latency
        avg_latency = sum(self.write_times) / len(self.write_times)
        
        # Target latency: 10ms per batch
        target_latency = 0.010
        
        if avg_latency > target_latency * 2:
            # Writes are slow - reduce batch size
            self.current_batch_size = max(
                self.min_batch_size,
                int(self.current_batch_size * 0.8)
            )
            logger.debug(f"Reduced batch size to {self.current_batch_size} (avg latency: {avg_latency:.3f}s)")
        elif avg_latency < target_latency * 0.5:
            # Writes are fast - increase batch size
            self.current_batch_size = min(
                self.max_batch_size,
                int(self.current_batch_size * 1.1)
            )
            logger.debug(f"Increased batch size to {self.current_batch_size} (avg latency: {avg_latency:.3f}s)")

    def _should_throttle_reads(self) -> bool:
        """
        Check if we should throttle reads due to backpressure.
        
        Returns:
            True if reads should be throttled
        """
        # Throttle if batch manager is nearly full
        if self.batch_manager.size() >= self.max_batch_size * 0.9:
            return True
        
        # Throttle if recent writes are very slow
        if len(self.write_times) >= 5:
            recent_latencies = list(self.write_times)[-5:]
            avg_recent = sum(recent_latencies) / len(recent_latencies)
            if avg_recent > 0.050:  # 50ms average
                return True
        
        return False

    async def _process_pending_messages(self) -> None:
        """Process pending messages from PEL (retry failed messages)."""
        try:
            # Get pending messages for this consumer
            pending = self.redis_client.xpending_range(
                self.stream_name,
                self.consumer_group,
                min="-",
                max="+",
                count=100,
                consumername=self.consumer_name
            )

            if not pending:
                return

            # Claim messages that are older than retry timeout
            # For immediate retry, use 0 min_idle_time (messages already delivered to this consumer)
            message_ids = [msg['message_id'] for msg in pending]
            if message_ids:
                claimed = self.redis_client.xclaim(
                    self.stream_name,
                    self.consumer_group,
                    self.consumer_name,
                    min_idle_time=0,  # Claim immediately for this consumer
                    message_ids=message_ids
                )

                # Process claimed messages
                # Parse them the same way as new messages (they have the same field structure)
                if claimed:
                    messages = []
                    for msg_id, fields in claimed:
                        msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                        
                        try:
                            event = {}
                            
                            def decode_field(key, value):
                                if isinstance(value, bytes):
                                    return value.decode('utf-8')
                                return str(value)
                            
                            for key, value in fields.items():
                                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                                val_str = decode_field(key_str, value)
                                
                                if key_str in ('payload', 'metadata'):
                                    try:
                                        event[key_str] = json.loads(val_str)
                                    except json.JSONDecodeError:
                                        event[key_str] = {}
                                else:
                                    event[key_str] = val_str
                            
                            # Ensure required fields exist
                            if 'event_id' not in event:
                                event['event_id'] = msg_id_str
                            if 'session_id' not in event:
                                event['session_id'] = event.get('external_session_id', '')
                            
                            messages.append({
                                'id': msg_id_str,
                                'event': event
                            })
                        except Exception as e:
                            logger.error(f"Failed to parse claimed message {msg_id_str}: {e}")

                    if messages:
                        processed_ids = await self._process_batch(messages)
                        # ACK is already done in _process_batch, but verify it succeeded
                        if processed_ids:
                            logger.debug(f"Processed {len(processed_ids)} pending messages")

        except Exception as e:
            logger.error(f"Error processing pending messages: {e}")

    async def run(self) -> None:
        """
        Main consumer loop.

        Continuously reads from Redis Streams, batches events,
        writes to SQLite, and publishes CDC events.
        
        Features:
        - Non-blocking SQLite writes (via thread pool)
        - Immediate ACK after successful write (prevents message loss)
        - Backpressure handling (adaptive batch sizing, read throttling)
        """
        self.running = True
        await self._ensure_consumer_group()

        logger.info(f"Fast path consumer started: {self.consumer_name}")

        while self.running:
            try:
                # Process pending messages first (retries)
                await self._process_pending_messages()

                # Adjust batch size based on write latency (backpressure)
                self._adjust_batch_size()

                # Throttle reads if we have too many pending batches
                if self._should_throttle_reads():
                    logger.debug(f"Throttling reads due to backpressure")
                    await asyncio.sleep(0.1)  # Wait for writes to catch up
                    continue

                # Read new messages (with adaptive count based on backpressure)
                read_count = min(
                    self.current_batch_size,
                    self.max_batch_size - self.batch_manager.size()
                )
                
                # Temporarily override batch manager count for this read
                original_count = self.batch_manager.batch_size
                messages = await self._read_messages_with_count(read_count)

                if messages:
                    # Add events to batch with their message IDs
                    for msg in messages:
                        if msg['event']:
                            ready = self.batch_manager.add_event(msg['event'], msg['id'])
                            if ready:
                                # Batch is full, get events and IDs
                                batch_events, batch_ids = self.batch_manager.get_batch()
                                
                                # Reconstruct messages with IDs
                                batch_messages = [
                                    {'id': msg_id, 'event': event}
                                    for event, msg_id in zip(batch_events, batch_ids)
                                ]
                                
                                # Process batch (includes immediate ACK)
                                await self._process_batch(batch_messages)

                # Check if timeout-based flush is needed
                if self.batch_manager.should_flush() and not self.batch_manager.is_empty():
                    # Get events and message IDs for timeout flush
                    batch_events, batch_ids = self.batch_manager.get_batch()
                    if batch_events:
                        # Reconstruct messages with IDs for proper ACK
                        batch_messages = [
                            {'id': msg_id, 'event': event}
                            for event, msg_id in zip(batch_events, batch_ids)
                        ]
                        
                        # Process batch (includes immediate ACK)
                        await self._process_batch(batch_messages)

                # Small sleep to prevent tight loop
                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(1)  # Back off on error

        logger.info("Fast path consumer stopped")

    async def _read_messages_with_count(self, count: int) -> List[Dict[str, Any]]:
        """
        Read messages with specified count (for backpressure handling).
        
        Args:
            count: Maximum number of messages to read
            
        Returns:
            List of message dictionaries
        """
        try:
            messages = self.redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream_name: ">"},
                count=count,
                block=self.block_ms
            )

            if not messages:
                return []

            # Parse messages (same logic as _read_messages)
            result = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    msg_id = message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id)
                    
                    try:
                        event = {}
                        
                        def decode_field(key, value):
                            if isinstance(value, bytes):
                                return value.decode('utf-8')
                            return str(value)
                        
                        for key, value in fields.items():
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                            val_str = decode_field(key_str, value)
                            
                            if key_str in ('payload', 'metadata'):
                                try:
                                    event[key_str] = json.loads(val_str)
                                except json.JSONDecodeError:
                                    event[key_str] = {}
                            else:
                                event[key_str] = val_str
                        
                        if 'event_id' not in event:
                            event['event_id'] = msg_id
                        if 'session_id' not in event:
                            event['session_id'] = event.get('external_session_id', '')
                        
                        result.append({
                            'id': msg_id,
                            'event': event
                        })
                        
                    except Exception as e:
                        logger.error(f"Failed to parse event from message {msg_id}: {e}")
                        result.append({
                            'id': msg_id,
                            'event': None,
                            'error': str(e)
                        })

            return result

        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading messages: {e}")
            return []

    def stop(self) -> None:
        """Stop the consumer."""
        self.running = False

