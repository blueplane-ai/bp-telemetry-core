# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
EventConsumer - Reliable message consumption with XREADGROUP/XACK.

Implements at-least-once delivery guarantee with:
- Consumer groups and Pending Entries List (PEL)
- Automatic retry with exponential backoff
- Dead Letter Queue (DLQ) for failed events
- Claim mechanism for stale events
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Callable
import redis

logger = logging.getLogger(__name__)


class EventConsumer:
    """
    Consumes events from Redis stream with proper ACK handling.
    Implements at-least-once delivery guarantee.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream_name: str = "telemetry:events",
        consumer_group: str = "processors",
        consumer_name: Optional[str] = None
    ):
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer-{os.getpid()}"
        self.max_retries = 3
        self.claim_min_idle_time = 60000  # 60 seconds in milliseconds
        self.running = False

        # Ensure consumer group exists
        self._ensure_consumer_group()

    def _ensure_consumer_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0',  # Start from beginning
                mkstream=True  # Create stream if doesn't exist
            )
            logger.info(f"Created consumer group '{self.consumer_group}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists, that's fine
                logger.debug(f"Consumer group '{self.consumer_group}' already exists")
            else:
                raise

    async def consume_events(
        self,
        block_ms: int = 1000,
        count: int = 100
    ) -> List[Tuple[str, dict]]:
        """
        Consume events from stream using consumer group.
        Returns list of (entry_id, event_data) tuples.

        IMPORTANT: Caller MUST acknowledge processed events using ack_events().
        """
        try:
            # Read new messages from the stream
            messages = self.redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream_name: '>'},  # '>' means only new messages
                block=block_ms,
                count=count
            )

            events = []
            if messages:
                for stream_name, stream_messages in messages:
                    for entry_id, data in stream_messages:
                        # Deserialize the data
                        event = self._deserialize_event(data)
                        events.append((entry_id, event))

            return events

        except Exception as e:
            logger.error(f"Error consuming events: {e}")
            return []

    async def ack_events(self, entry_ids: List[str]):
        """
        Acknowledge successful processing of events.
        This removes them from the Pending Entries List (PEL).
        """
        if not entry_ids:
            return

        try:
            # XACK returns the number of messages successfully acknowledged
            ack_count = self.redis_client.xack(
                self.stream_name,
                self.consumer_group,
                *entry_ids
            )

            logger.debug(f"Acknowledged {ack_count}/{len(entry_ids)} events")

            if ack_count < len(entry_ids):
                logger.warning(
                    f"Only {ack_count} of {len(entry_ids)} events were acknowledged. "
                    "Some may have been already ACKed or don't exist."
                )

        except Exception as e:
            logger.error(f"Error acknowledging events: {e}")

    async def process_pending_events(self) -> List[Tuple[str, dict]]:
        """
        Process events that are in the Pending Entries List (PEL).
        These are events that were delivered but not acknowledged.
        """
        try:
            # Get pending events info
            pending_info = self.redis_client.xpending_range(
                self.stream_name,
                self.consumer_group,
                min='-',
                max='+',
                count=100
            )

            stale_events = []
            for entry in pending_info:
                entry_id = entry['message_id']
                idle_time = entry['time_since_delivered']
                delivery_count = entry['times_delivered']

                # Check if event exceeded max retries
                if delivery_count > self.max_retries:
                    await self._move_to_dlq(entry_id)
                    # ACK to remove from PEL
                    await self.ack_events([entry_id])
                    continue

                # Check if event is stale (idle for too long)
                if idle_time > self.claim_min_idle_time:
                    stale_events.append(entry_id)

            # Claim and process stale events
            if stale_events:
                claimed = await self._claim_events(stale_events)
                return claimed

            return []

        except Exception as e:
            logger.error(f"Error processing pending events: {e}")
            return []

    async def _claim_events(self, entry_ids: List[str]) -> List[Tuple[str, dict]]:
        """
        Claim ownership of pending events from other consumers.
        Used for recovering stale/abandoned events.
        """
        try:
            # XCLAIM changes ownership of pending messages
            claimed_messages = self.redis_client.xclaim(
                self.stream_name,
                self.consumer_group,
                self.consumer_name,
                min_idle_time=self.claim_min_idle_time,
                message_ids=entry_ids
            )

            events = []
            for entry_id, data in claimed_messages:
                event = self._deserialize_event(data)
                events.append((entry_id, event))

            logger.info(f"Claimed {len(events)} stale events")
            return events

        except Exception as e:
            logger.error(f"Error claiming events: {e}")
            return []

    async def _move_to_dlq(self, entry_id: str):
        """
        Move failed event to Dead Letter Queue (DLQ).
        """
        try:
            # Read the event data
            events = self.redis_client.xrange(
                self.stream_name,
                min=entry_id,
                max=entry_id,
                count=1
            )

            if events:
                _, event_data = events[0]

                # Add to DLQ stream with failure metadata
                dlq_entry = {
                    **event_data,
                    'original_entry_id': entry_id,
                    'moved_to_dlq_at': datetime.now(timezone.utc).isoformat(),
                    'stream': self.stream_name,
                    'consumer_group': self.consumer_group
                }

                self.redis_client.xadd(
                    f"{self.stream_name}:dlq",
                    dlq_entry,
                    maxlen=10000,
                    approximate=True
                )

                logger.warning(f"Moved event {entry_id} to DLQ after max retries")

        except Exception as e:
            logger.error(f"Error moving event to DLQ: {e}")

    def _deserialize_event(self, data: dict) -> dict:
        """Deserialize event from Redis."""
        deserialized = {}

        for key, value in data.items():
            key = key.decode() if isinstance(key, bytes) else key
            value = value.decode() if isinstance(value, bytes) else value

            # Try to parse JSON fields
            if key in ['metadata', 'payload', 'extracted_fields', 'full_data']:
                try:
                    deserialized[key] = json.loads(value)
                except json.JSONDecodeError:
                    deserialized[key] = value
            else:
                deserialized[key] = value

        return deserialized

    async def get_consumer_stats(self) -> dict:
        """Get statistics about consumer group and pending messages."""
        try:
            # Get consumer group info
            groups = self.redis_client.xinfo_groups(self.stream_name)
            group_info = next(
                (g for g in groups if g['name'] == self.consumer_group.encode()),
                None
            )

            if not group_info:
                return {}

            # Get pending messages summary
            pending_summary = self.redis_client.xpending(
                self.stream_name,
                self.consumer_group
            )

            # Get consumer info
            consumers = self.redis_client.xinfo_consumers(
                self.stream_name,
                self.consumer_group
            )

            return {
                'group': {
                    'name': group_info['name'].decode() if isinstance(group_info['name'], bytes) else group_info['name'],
                    'consumers': group_info['consumers'],
                    'pending': group_info['pending'],
                },
                'pending': {
                    'total': pending_summary['pending'],
                },
                'consumers': [
                    {
                        'name': c['name'].decode() if isinstance(c['name'], bytes) else c['name'],
                        'pending': c['pending'],
                        'idle': c['idle']
                    }
                    for c in consumers
                ]
            }

        except Exception as e:
            logger.error(f"Error getting consumer stats: {e}")
            return {}


class CursorEventProcessor:
    """
    Main processor that ties together consumption and processing with ACK.
    Processes events from Redis and writes to cursor_raw_traces.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        db_writer: 'CursorRawTracesWriter',
        pending_check_interval: int = 30
    ):
        self.redis_client = redis_client
        self.db_writer = db_writer
        self.consumer = EventConsumer(redis_client)
        self.running = False
        self.pending_check_interval = pending_check_interval

    async def start(self):
        """Start the processing loop."""
        self.running = True
        logger.info("Starting Cursor event processor")

        # Start main processing loop
        asyncio.create_task(self._process_loop())

        # Start pending events checker
        asyncio.create_task(self._pending_check_loop())

    async def stop(self):
        """Stop the processing loop."""
        self.running = False
        logger.info("Stopping Cursor event processor")

    def _should_process_event(self, event: dict) -> bool:
        """
        Check if this event should be processed by Cursor writer.

        Filter criteria:
        1. Platform must be "cursor" OR
        2. Source must be from Cursor monitors OR
        3. Has workspace_hash from Cursor hooks
        """
        platform = event.get("platform", "")
        metadata = event.get("metadata", {})
        source = metadata.get("source", "")

        # Cursor-specific sources from UnifiedCursorMonitor
        cursor_sources = [
            "workspace_monitor",
            "composer_extractor",
            "generation_extractor",
            "bubble_extractor",
            "agent_mode_extractor",
            "background_composer_extractor",
            "prompt_extractor",
            "capability_extractor",
            "unified_monitor",
            "user_level_listener"
        ]

        # Check if it's a Cursor event
        is_cursor = (
            platform == "cursor" or
            source in cursor_sources or
            (metadata.get("workspace_hash") and not event.get("sessionId"))  # Cursor hooks have workspace_hash but not sessionId
        )

        # Explicitly exclude Claude Code events
        # Note: Rely on platform field and source, not hardcoded session ID prefixes
        is_claude = (
            platform == "claude_code" or
            source in ["jsonl_monitor", "transcript_monitor", "claude_session_monitor"]
        )

        return is_cursor and not is_claude

    async def _process_loop(self):
        """
        Main processing loop with proper ACK handling.
        """
        while self.running:
            try:
                # Consume new events
                events = await self.consumer.consume_events(
                    block_ms=1000,
                    count=100
                )

                if events:
                    await self._process_and_ack(events)

            except Exception as e:
                logger.error(f"Processing loop error: {e}")
                await asyncio.sleep(1)

    async def _pending_check_loop(self):
        """
        Periodically check for and process stale pending events.
        """
        while self.running:
            try:
                await asyncio.sleep(self.pending_check_interval)

                # Check for stale pending events
                stale_events = await self.consumer.process_pending_events()
                if stale_events:
                    await self._process_and_ack(stale_events)

            except Exception as e:
                logger.error(f"Pending check loop error: {e}")

    async def _process_and_ack(self, events: List[Tuple[str, dict]]):
        """
        Process events and acknowledge them.
        """
        successful_ids = []
        failed_ids = []

        # Filter events by platform - only process Cursor events
        cursor_events = []
        skipped_ids = []

        for entry_id, event in events:
            if self._should_process_event(event):
                cursor_events.append((entry_id, event))
            else:
                # Skip non-Cursor events but still ACK them
                skipped_ids.append(entry_id)
                logger.debug(f"Skipping non-Cursor event: {event.get('event_type', 'unknown')}")

        if cursor_events:
            # Extract event data for batch processing
            event_data_list = [event for _, event in cursor_events]

            try:
                # Process the batch (write to database)
                written = await self.db_writer.write_events(event_data_list)

                if written > 0:
                    # All events processed successfully
                    successful_ids = [entry_id for entry_id, _ in cursor_events]

            except Exception as e:
                logger.error(f"Failed to process event batch: {e}")
                # All events failed, they remain in PEL for retry
                failed_ids = [entry_id for entry_id, _ in cursor_events]

        # ACK skipped events (they were successfully processed by not writing them)
        successful_ids.extend(skipped_ids)

        # ACK successful events
        if successful_ids:
            await self.consumer.ack_events(successful_ids)
            logger.info(f"Processed and ACKed {len(successful_ids)} events")

        # Failed events remain in PEL for retry
        if failed_ids:
            logger.warning(
                f"{len(failed_ids)} events failed processing. "
                "They remain in PEL for retry."
            )
