# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Monitor for Claude Code sessions.

Listens to Redis session_start/end events from Claude Code hooks.
Provides persistent session management with database-backed recovery.
"""

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional
import redis

from .session_persistence import SessionPersistence
from ..database.sqlite_client import SQLiteClient
from ...capture.shared.project_utils import derive_project_name
from ...capture.shared.redis_streams import TELEMETRY_MESSAGE_QUEUE_STREAM

logger = logging.getLogger(__name__)


class ClaudeCodeSessionMonitor:
    """
    Monitor Claude Code sessions via Redis events with database persistence.

    Design:
    - Redis stream events from OnSessionStart/OnSessionEnd hooks
    - Tracks active sessions with metadata (session_id, workspace_path)
    - Persists sessions to SQLite database for durability
    - Recovers incomplete sessions on startup
    - Used by JSONL monitor to know which sessions to track
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: Optional[SQLiteClient] = None,
        stream_name: str = TELEMETRY_MESSAGE_QUEUE_STREAM,
        consumer_group: str = "session_monitors",
        consumer_name: str = "claude_code_session_monitor",
    ):
        """
        Initialize Claude Code session monitor.

        Args:
            redis_client: Redis client for event streaming
            sqlite_client: Optional SQLite client for persistence (if None, persistence disabled)
            stream_name: Redis stream name to read from
            consumer_group: Consumer group name for Redis streams
            consumer_name: Consumer name (unique per instance)
        """
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name

        # Active sessions: session_id -> session_info (in-memory for fast lookups)
        self.active_sessions: Dict[str, dict] = {}
        self._lock = threading.Lock()

        # Session persistence (if sqlite_client provided)
        self.persistence: Optional[SessionPersistence] = None
        if sqlite_client:
            self.persistence = SessionPersistence(sqlite_client)

        self.running = False
        
        # Thread pool executor for running synchronous Redis calls
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="claude-session-redis")

    async def start(self):
        """
        Start monitoring sessions with recovery.
        
        Steps:
        1. Ensure consumer group exists
        2. Recover incomplete sessions from database (if persistence enabled)
        3. Process pending messages (from previous runs)
        4. Start listening to new Redis events
        """
        self.running = True

        # Step 1: Ensure consumer group exists
        self._ensure_consumer_group()

        # Step 2: Recover incomplete sessions from last run (if persistence enabled)
        if self.persistence:
            await self._recover_active_sessions()

        # Step 3: Process pending messages first (catch up on unprocessed messages)
        await self._process_pending_messages()

        persistence_status = "with database persistence" if self.persistence else "(in-memory only)"
        logger.info(f"Claude Code session monitor started {persistence_status}")

        # Step 4: Run Redis event listener directly (blocks until stopped)
        logger.info("Starting Redis event listener loop...")
        await self._listen_redis_events()

    def _ensure_consumer_group(self) -> None:
        """Ensure consumer group exists, create if not."""
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0',
                mkstream=True
            )
            logger.info(
                f"Created consumer group '{self.consumer_group}' for stream '{self.stream_name}'"
            )
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Failed to create consumer group: {e}")
                raise
            logger.info(
                f"Consumer group '{self.consumer_group}' already exists for stream '{self.stream_name}'"
            )
        except Exception as e:
            logger.error(f"Unexpected error creating consumer group: {e}", exc_info=True)
            raise

    async def _process_pending_messages(self):
        """Process pending messages from previous runs (messages in PEL)."""
        logger.info(f"Checking for pending messages in consumer group '{self.consumer_group}'...")
        try:
            total_claude_events = 0
            total_acked = 0
            total_messages_read = 0
            empty_reads = 0
            max_empty_reads = 3  # Stop after 3 consecutive empty reads
            max_iterations = 1000  # Safety limit to prevent infinite loops
            seen_message_ids = set()  # Track processed message IDs to detect duplicates

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                try:
                    # Read pending messages assigned to this consumer (using "0")
                    # Note: "0" means read from PEL (Pending Entries List) for this consumer
                    # Run in executor to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    messages = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            lambda: self.redis_client.xreadgroup(
                                groupname=self.consumer_group,
                                consumername=self.consumer_name,
                                streams={self.stream_name: "0"},  # "0" means read from PEL
                                count=100,
                                block=0  # Non-blocking (should return immediately)
                            )
                        ),
                        timeout=5.0  # 5 second timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"xreadgroup call timed out after 5 seconds (iteration {iteration})")
                    break
                except redis.exceptions.ResponseError as e:
                    # Handle Redis-specific errors (like NOGROUP)
                    error_str = str(e)
                    if "NOGROUP" in error_str:
                        logger.warning(f"Consumer group '{self.consumer_group}' not found, skipping pending messages")
                    else:
                        logger.error(f"Redis error reading pending messages: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error reading pending messages: {e}", exc_info=True)
                    break

                # Check if we have any messages
                total_msgs_in_batch = 0
                if messages:
                    for stream, msgs in messages:
                        total_msgs_in_batch += len(msgs)

                # If no messages, treat as empty read
                if total_msgs_in_batch == 0:
                    empty_reads += 1
                    if empty_reads >= max_empty_reads:
                        break
                    await asyncio.sleep(0.1)  # Small delay before next read
                    continue

                empty_reads = 0  # Reset counter on successful read

                batch_claude_events = 0
                batch_acked = 0
                batch_messages = 0
                try:
                    for stream, msgs in messages:
                        if not msgs:
                            continue
                        for msg_id, fields in msgs:
                            batch_messages += 1
                            total_messages_read += 1
                            
                            # Decode message_id
                            msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                            
                            # Safety check: if we've seen this message ID before, force-ACK it to prevent infinite loop
                            if msg_id_str in seen_message_ids:
                                try:
                                    loop = asyncio.get_event_loop()
                                    ack_result = await loop.run_in_executor(
                                        self._executor,
                                        lambda: self.redis_client.xack(
                                            self.stream_name,
                                            self.consumer_group,
                                            msg_id_str
                                        )
                                    )
                                    if ack_result == 1:
                                        batch_acked += 1
                                        total_acked += 1
                                except Exception as e:
                                    logger.error(f"Failed to force-ACK duplicate message {msg_id_str}: {e}")
                                continue
                            
                            seen_message_ids.add(msg_id_str)
                            
                            # Check if this is a Claude Code event before processing
                            event_type = self._decode_field(fields, 'event_type')
                            platform = self._decode_field(fields, 'platform')
                            is_claude_event = (
                                platform == 'claude_code' and 
                                event_type in ('session_start', 'session_end')
                            )
                            
                            try:
                                # Process message (will ACK filtered messages too)
                                success = await self._process_redis_message(msg_id_str, fields)
                                
                                if is_claude_event:
                                    batch_claude_events += 1
                                    total_claude_events += 1
                                
                                # ACK if successfully processed (including filtered messages)
                                # Errors will remain in PEL for retry
                                if success:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        ack_result = await loop.run_in_executor(
                                            self._executor,
                                            lambda: self.redis_client.xack(
                                                self.stream_name,
                                                self.consumer_group,
                                                msg_id_str
                                            )
                                        )
                                        if ack_result == 1:
                                            batch_acked += 1
                                            total_acked += 1
                                    except Exception as e:
                                        logger.error(f"Failed to ACK message {msg_id_str}: {e}")
                            except Exception as e:
                                logger.error(f"Exception processing pending message {msg_id_str}: {e}")
                                # Don't ACK on exception - let it retry
                except Exception as e:
                    logger.error(f"Exception iterating over messages batch: {e}", exc_info=True)
                    break

                await asyncio.sleep(0)  # Yield control during long catch-up

            if iteration >= max_iterations:
                logger.warning(
                    f"Hit max_iterations limit ({max_iterations}) while processing pending messages. "
                    f"Processed {total_claude_events} Claude Code events, ACKed {total_acked} messages."
                )

            if total_claude_events > 0:
                logger.info(
                    f"Processed {total_claude_events} pending Claude Code events (ACKed {total_acked})"
                )
        except Exception as e:
            logger.warning(f"Error processing pending messages: {e}", exc_info=True)

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=True)
        logger.info("Claude Code session monitor stopped")

    async def _listen_redis_events(self):
        """
        Listen to session_start/end events from Redis stream using consumer groups.

        Reads from telemetry:message_queue stream, filters for Claude Code session events.
        ACKs messages after successful processing.
        """
        logger.info(
            f"Starting Redis event listener for Claude Code sessions "
            f"(consumer_group={self.consumer_group}, consumer_name={self.consumer_name})"
        )
        try:
            while self.running:
                try:
                    # Read from stream using consumer group (">" means new messages)
                    # Run in executor to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    messages = await loop.run_in_executor(
                        self._executor,
                        lambda: self.redis_client.xreadgroup(
                            groupname=self.consumer_group,
                            consumername=self.consumer_name,
                            streams={self.stream_name: ">"},  # ">" means new messages
                            count=100,
                            block=1000  # 1 second block
                        )
                    )

                    if not messages:
                        await asyncio.sleep(0.1)
                        continue

                    # Process messages
                    for stream, msgs in messages:
                        for msg_id, fields in msgs:
                            # Decode message_id
                            msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                            
                            try:
                                # Process message
                                success = await self._process_redis_message(msg_id_str, fields)
                                
                                if success:
                                    # ACK successful processing (includes filtered messages)
                                    try:
                                        # Run ACK in executor to avoid blocking
                                        await loop.run_in_executor(
                                            self._executor,
                                            lambda: self.redis_client.xack(
                                                self.stream_name,
                                                self.consumer_group,
                                                msg_id_str
                                            )
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to ACK message {msg_id_str}: {e}")
                                # If success is False, it's an error - don't ACK, let it retry via PEL
                            except Exception as e:
                                logger.error(
                                    f"Error processing message {msg_id_str}: {e}",
                                    exc_info=True
                                )
                                # Don't ACK on exception - let it retry via PEL
                                # In production, you might want to implement retry limits and DLQ

                except redis.exceptions.RedisError as e:
                    logger.error(f"Redis error in session monitor: {e}")
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Fatal error in session monitor: {e}")

    async def _process_redis_message(self, msg_id: str, fields: dict) -> bool:
        """
        Process a Redis stream message.

        Filters for session_start/session_end events from Claude Code.
        
        Args:
            msg_id: Redis message ID (string)
            fields: Redis stream fields dictionary
            
        Returns:
            True if message was processed (or should be ACKed), False if filtered out
        """
        try:
            # Decode fields
            event_type = self._decode_field(fields, 'event_type')
            platform = self._decode_field(fields, 'platform')

            # Only process Claude Code session events
            if platform != 'claude_code':
                return True  # Filtered out - ACK to prevent reprocessing

            if event_type not in ('session_start', 'session_end'):
                return True  # Filtered out - ACK to prevent reprocessing

            # Parse payload
            payload_str = self._decode_field(fields, 'payload')
            payload = json.loads(payload_str) if payload_str else {}

            metadata_str = self._decode_field(fields, 'metadata')
            metadata = json.loads(metadata_str) if metadata_str else {}

            # Extract session_id from fields (set by jsonl_monitor)
            # jsonl_monitor sets both session_id and external_session_id
            session_id = self._decode_field(fields, 'session_id') or self._decode_field(fields, 'external_session_id')
            if not session_id:
                logger.warning(f"Message {msg_id} missing session_id, skipping")
                return True  # ACK to prevent reprocessing

            workspace_hash = metadata.get('workspace_hash')
            workspace_path = metadata.get('workspace_path') or payload.get('workspace_path', '')
            project_name = metadata.get('project_name') or derive_project_name(workspace_path)

            if event_type == 'session_start':
                session_info = {
                    "session_id": session_id,
                    "workspace_hash": workspace_hash,
                    "workspace_path": workspace_path,
                    "project_name": project_name,
                    "platform": "claude_code",
                    "started_at": asyncio.get_event_loop().time(),
                    "source": "hooks",
                }

                # Add to in-memory dict (fast path)
                with self._lock:
                    self.active_sessions[session_id] = session_info
                
                # Persist to database (durable)
                if self.persistence:
                    await self.persistence.save_session_start(
                        session_id=session_id,
                        workspace_hash=workspace_hash or '',
                        workspace_path=workspace_path,
                        metadata={
                            'source': metadata.get('source', 'hooks'),
                            'project_name': project_name,
                            **metadata
                        }
                    )
                
                logger.info(f"Claude Code session started: {session_id} (workspace: {workspace_path})")
                return True  # Successfully processed

            elif event_type == 'session_end':
                # Update database first (ensure durability)
                if self.persistence:
                    await self.persistence.save_session_end(session_id, end_reason='normal')
                
                # Then remove from memory
                removed = self.remove_session(session_id)
                if removed:
                    logger.info(f"Claude Code session ended: {session_id}")
                else:
                    logger.debug(f"Session end for unknown session: {session_id}")
                return True  # Successfully processed

            return False  # Unknown event type
        except Exception as e:
            logger.error(f"Error processing Redis message {msg_id}: {e}", exc_info=True)
            # Return False to prevent ACK, allowing retry via PEL
            return False

    def _decode_field(self, fields: dict, key: str) -> Optional[str]:
        """
        Decode a field from Redis stream message.

        Args:
            fields: Redis stream fields dictionary
            key: Field key to decode

        Returns:
            Decoded string value or None
        """
        value = fields.get(key) or fields.get(key.encode())
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return str(value)

    def get_active_sessions(self) -> Dict[str, dict]:
        """
        Get all active Claude Code sessions.

        Returns:
            Dictionary of session_id -> session_info
        """
        with self._lock:
            return self.active_sessions.copy()

    async def update_session_workspace(self, session_id: str, workspace_path: str) -> None:
        """
        Update the workspace path for a session.

        Called when workspace path is discovered from JSONL content.

        Args:
            session_id: Session identifier
            workspace_path: Discovered workspace path
        """
        workspace_hash = self._hash_workspace(workspace_path)

        with self._lock:
            session = self.active_sessions.get(session_id)
            if not session:
                return
            session["workspace_path"] = workspace_path
            session["workspace_hash"] = workspace_hash

        # Update in database if persistence is enabled
        if self.persistence:
            await self.persistence.update_workspace_path(session_id, workspace_path)

        logger.info(f"Updated workspace path for session {session_id}: {workspace_path}")

    def _hash_workspace(self, workspace_path: str) -> str:
        """Generate a hash of the workspace path."""
        import hashlib
        return hashlib.sha256(workspace_path.encode()).hexdigest()[:16]

    async def _recover_active_sessions(self):
        """
        Recover incomplete sessions from database on startup.
        
        Checks for sessions without ended_at and restores them to active_sessions.
        Also validates that JSONL files still exist (if not, marks as crashed).
        """
        if not self.persistence:
            return
        
        try:
            recovered = await self.persistence.recover_active_sessions()
            
            with self._lock:
                for session_id, session_info in recovered.items():
                    self.active_sessions[session_id] = session_info

            # Check if JSONL file still exists (basic validation)
            for session_id, session_info in recovered.items():
                workspace_path = session_info.get('workspace_path', '')
                if workspace_path:
                    logger.info(f"Recovered active Claude Code session: {session_id} (workspace: {workspace_path})")
                else:
                    logger.warning(f"Recovered session {session_id} without workspace_path")
                    
        except Exception as e:
            logger.error(f"Error during session recovery: {e}", exc_info=True)
            # Continue startup even if recovery fails

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        Get info for a specific session.

        Args:
            session_id: Session ID to look up

        Returns:
            Session info dict or None
        """
        with self._lock:
            return self.active_sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """Remove a session from the active map."""
        with self._lock:
            return self.active_sessions.pop(session_id, None) is not None
