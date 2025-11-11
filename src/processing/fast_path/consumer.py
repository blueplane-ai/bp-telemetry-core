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
from typing import Dict, List, Any, Optional, Set
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
        self.pending_retry_idle_ms = max(int(batch_timeout * 1000), 100)

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

    def _decode_stream_message(self, message_id: str, fields: Dict[Any, Any]) -> Optional[Dict[str, Any]]:
        """
        Decode Redis Stream fields into an event dictionary.

        Args:
            message_id: Redis Stream message ID
            fields: Raw fields returned by Redis

        Returns:
            Event dictionary or None if decoding failed
        """
        try:
            event: Dict[str, Any] = {}

            for key, value in fields.items():
                key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                if isinstance(value, bytes):
                    val_str = value.decode("utf-8")
                else:
                    val_str = str(value)

                if key_str in ("payload", "metadata"):
                    try:
                        event[key_str] = json.loads(val_str)
                    except json.JSONDecodeError:
                        event[key_str] = {}
                else:
                    event[key_str] = val_str

            if "event_id" not in event:
                event["event_id"] = message_id
            if "session_id" not in event:
                event["session_id"] = event.get("external_session_id", "")

            # Enhanced logging for database_trace events
            event_type = event.get("event_type", "")
            if event_type == "database_trace":
                metadata = event.get("metadata", {})
                workspace_hash = metadata.get("workspace_hash") if isinstance(metadata, dict) else None
                logger.info(
                    f"Decoded database_trace event: msg_id={message_id[:20]}..., "
                    f"event_type={event_type}, workspace_hash={workspace_hash}, "
                    f"session_id={event.get('session_id', '')[:20]}..."
                )

            return event
        except Exception as exc:
            logger.error(f"Failed to parse event from message {message_id}: {exc}")
            return None

    async def _read_messages(self) -> List[Dict[str, Any]]:
        """
        Read messages from Redis Streams using XREADGROUP.

        Returns:
            List of message dictionaries with 'id' and 'event' keys
        """
        try:
            # Read from stream with consumer group
            # Use current_batch_size for adaptive batching
            messages = self.redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream_name: ">"},
                count=self.current_batch_size,
                block=self.block_ms
            )

            if not messages:
                return []

            # Parse messages
            result = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    # Convert message_id to string
                    msg_id = message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id)
                    event = self._decode_stream_message(msg_id, fields)
                    result.append({
                        'id': msg_id,
                        'event': event
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
        db_trace_events = []
        
        for msg in messages:
            if msg['event'] is not None:
                event = msg['event']
                events.append(event)
                valid_message_ids.append(msg['id'])
                
                # Track database_trace events for detailed logging
                if event.get('event_type') == 'database_trace':
                    metadata = event.get('metadata', {})
                    workspace_hash = metadata.get('workspace_hash') if isinstance(metadata, dict) else None
                    db_trace_events.append({
                        'msg_id': msg['id'],
                        'workspace_hash': workspace_hash,
                        'session_id': event.get('session_id', ''),
                    })
            else:
                # Invalid event - send to DLQ immediately
                logger.warning(f"Invalid event (None) for message {msg['id']}, sending to DLQ")
                await self._handle_failed_message(msg['id'], msg.get('event'), retry_count=self.max_retries)

        if not events:
            logger.debug("No valid events to process in batch")
            return []

        # Log database_trace events being processed
        if db_trace_events:
            workspace_hashes = [e['workspace_hash'] for e in db_trace_events[:5]]
            logger.info(
                f"Processing batch with {len(db_trace_events)} database_trace events: "
                f"{', '.join([f'wh={wh}' for wh in workspace_hashes])}"
            )

        try:
            # Write to SQLite (runs in thread pool, non-blocking)
            start_time = time.time()
            sequences = await self.sqlite_writer.write_batch(events)
            write_duration = time.time() - start_time
            
            # Track write latency for backpressure
            self.write_times.append(write_duration)
            
            # Enhanced logging for database_trace events
            if db_trace_events and sequences:
                db_trace_sequences = [
                    seq for seq, event in zip(sequences, events)
                    if event.get('event_type') == 'database_trace'
                ]
                logger.info(
                    f"Successfully wrote {len(db_trace_sequences)} database_trace events: "
                    f"sequences {db_trace_sequences[:5] if db_trace_sequences else 'none'}"
                )
            
            # Publish CDC events (fire-and-forget, synchronous call)
            for sequence, event in zip(sequences, events):
                self.cdc_publisher.publish(sequence, event)

            logger.debug(f"Processed batch: {len(events)} events, sequences {sequences[0]}-{sequences[-1]}, duration: {write_duration:.3f}s")
            
            # ACK messages immediately after successful write
            # This prevents message loss if consumer crashes
            await self._ack_messages(valid_message_ids)
            
            return valid_message_ids

        except Exception as e:
            logger.error(f"Failed to process batch: {e}", exc_info=True)
            if db_trace_events:
                logger.error(
                    f"Failed batch included {len(db_trace_events)} database_trace events: "
                    f"{', '.join([e['msg_id'][:20] for e in db_trace_events[:3]])}"
                )
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
        Updates both current_batch_size and batch_manager.batch_size.
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
            new_size = max(
                self.min_batch_size,
                int(self.current_batch_size * 0.8)
            )
            if new_size != self.current_batch_size:
                self.current_batch_size = new_size
                self.batch_manager.batch_size = new_size
                logger.debug(f"Reduced batch size to {self.current_batch_size} (avg latency: {avg_latency:.3f}s)")
        elif avg_latency < target_latency * 0.5:
            # Writes are fast - increase batch size
            new_size = min(
                self.max_batch_size,
                int(self.current_batch_size * 1.1)
            )
            if new_size != self.current_batch_size:
                self.current_batch_size = new_size
                self.batch_manager.batch_size = new_size
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

            retry_ids: List[str] = []
            dlq_candidates: Dict[str, int] = {}

            for entry in pending:
                message_id = entry.get('message_id')
                if not message_id:
                    continue

                # Redis-py returns message_id as string
                msg_id_str = str(message_id)
                delivery_count = entry.get('delivery_count', 0)
                idle_time_ms = entry.get('idle', 0)

                if delivery_count >= self.max_retries:
                    dlq_candidates[msg_id_str] = delivery_count
                elif idle_time_ms >= self.pending_retry_idle_ms:
                    retry_ids.append(msg_id_str)

            # First, move messages that exceeded retry limit to DLQ
            if dlq_candidates:
                try:
                    claimed_dlq = self.redis_client.xclaim(
                        self.stream_name,
                        self.consumer_group,
                        self.consumer_name,
                        min_idle_time=0,
                        message_ids=list(dlq_candidates.keys())
                    )
                except Exception as claim_error:
                    logger.error(f"Failed to claim DLQ candidates: {claim_error}")
                    claimed_dlq = []

                for msg_id, fields in claimed_dlq:
                    msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                    event = self._decode_stream_message(msg_id_str, fields)
                    retry_count = dlq_candidates.get(msg_id_str, self.max_retries)

                    await self._handle_failed_message(msg_id_str, event, retry_count=retry_count)

                    try:
                        self.redis_client.xack(self.stream_name, self.consumer_group, msg_id_str)
                    except Exception as ack_error:
                        logger.error(f"Failed to ACK DLQ message {msg_id_str}: {ack_error}")

                    # Ensure duplicates aren't processed later
                    self.batch_manager.remove_message_ids([msg_id_str])

            # Reprocess pending messages that have been idle long enough
            if retry_ids:
                try:
                    claimed_retry = self.redis_client.xclaim(
                        self.stream_name,
                        self.consumer_group,
                        self.consumer_name,
                        min_idle_time=self.pending_retry_idle_ms,
                        message_ids=retry_ids
                    )
                except Exception as claim_error:
                    logger.error(f"Failed to claim retry messages: {claim_error}")
                    claimed_retry = []

                if claimed_retry:
                    messages = []
                    for msg_id, fields in claimed_retry:
                        msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                        event = self._decode_stream_message(msg_id_str, fields)

                        if event is None:
                            # Unparseable event - send to DLQ immediately
                            await self._handle_failed_message(msg_id_str, event, retry_count=self.max_retries)
                            try:
                                self.redis_client.xack(self.stream_name, self.consumer_group, msg_id_str)
                            except Exception as ack_error:
                                logger.error(f"Failed to ACK malformed message {msg_id_str}: {ack_error}")
                            self.batch_manager.remove_message_ids([msg_id_str])
                            continue

                        messages.append({'id': msg_id_str, 'event': event})

                    if messages:
                        processed_ids = await self._process_batch(messages)
                        if processed_ids:
                            self.batch_manager.remove_message_ids(processed_ids)
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

                # Read new messages (adaptive batch size already set in _adjust_batch_size)
                messages = await self._read_messages()

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
                    event = self._decode_stream_message(msg_id, fields)
                    result.append({
                        'id': msg_id,
                        'event': event
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

