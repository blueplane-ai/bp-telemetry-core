# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Monitor for Cursor workspaces.

Listens to Redis session_start/end events from the extension.
Provides persistent session management with database-backed recovery.
"""

import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional
import redis

from .session_persistence import (
    CursorSessionPersistence,
    SessionNotFoundError,
    DatabaseError
)
from ..database.sqlite_client import SQLiteClient
from ...capture.shared.redis_streams import TELEMETRY_MESSAGE_QUEUE_STREAM

logger = logging.getLogger(__name__)


def _extract_workspace_name(workspace_path: str) -> str:
    """
    Extract human-readable workspace name from full path.

    Examples:
        /Users/user/projects/my-app -> my-app
        /home/user/dev/workspace -> workspace
        C:\\Projects\\my-app -> my-app

    Args:
        workspace_path: Full path to workspace

    Returns:
        Last directory name in path, or empty string if extraction fails
    """
    if not workspace_path:
        return ""

    try:
        # First normalize path separators for cross-platform handling
        # This ensures Windows paths work on Unix and vice versa
        normalized = workspace_path.replace('\\', '/')

        # Check if this looks like a Windows path on a Unix system
        # If the path doesn't start with '/' and contains ':', it's likely Windows
        if not normalized.startswith('/') and ':' in normalized:
            # Windows path - use string manipulation
            parts = normalized.rstrip('/').split('/')
            # Return last non-empty part
            for part in reversed(parts):
                if part and part != ':':  # Ignore drive letter only
                    return part
            return ""
        else:
            # Unix path or already normalized - use pathlib
            path = Path(workspace_path)
            name = path.name  # Get last component

            # Handle edge case where path ends with separator
            if not name and path.parent != path:
                name = path.parent.name

            return name or ""
    except Exception as e:
        # Fallback to simple string manipulation if pathlib fails
        logger.debug(f"Path extraction failed, using fallback: {e}")
        try:
            # Normalize separators and remove trailing ones
            normalized = workspace_path.replace('\\', '/').rstrip('/')
            parts = normalized.split('/')
            # Return last non-empty part
            for part in reversed(parts):
                if part:
                    return part
            return ""
        except Exception:
            logger.warning(f"Failed to extract workspace name from path: {workspace_path}")
            return ""


class SessionMonitor:
    """
    Monitor Cursor sessions via Redis events with database persistence.

    Design:
    - Redis stream events from extension (session_start/end)
    - Tracks active sessions with metadata (session_id, workspace_path)
    - Persists sessions to SQLite database for durability
    - Recovers incomplete sessions on startup
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: Optional[SQLiteClient] = None,
        stream_name: str = TELEMETRY_MESSAGE_QUEUE_STREAM,
        consumer_group: str = "cursor_session_monitors",
        consumer_name: str = "cursor_session_monitor",
    ):
        """
        Initialize Cursor session monitor.

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

        # Active sessions: workspace_hash -> session_info (in-memory for fast lookups)
        self.active_sessions: Dict[str, dict] = {}
        self._lock = threading.Lock()
        
        # Thread pool for running synchronous Redis calls
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cursor-session-redis")

        # Session persistence (if sqlite_client provided)
        self.persistence: Optional[CursorSessionPersistence] = None
        if sqlite_client:
            self.persistence = CursorSessionPersistence(sqlite_client)

        self.running = False

        # Callbacks for session lifecycle events
        self.on_session_start = None  # Called when a session starts
        self.on_session_end = None    # Called when a session ends

    async def start(self):
        """
        Start monitoring sessions with recovery.
        
        Steps:
        1. Ensure consumer group exists
        2. Recover incomplete sessions from database (if persistence enabled)
        3. Process pending messages (from previous runs)
        4. Start listening to new Redis events
        """
        logger.info(
            f"Starting Cursor session monitor: "
            f"stream={self.stream_name}, "
            f"consumer_group={self.consumer_group}, "
            f"consumer_name={self.consumer_name}"
        )
        self.running = True

        # Step 1: Ensure consumer group exists
        self._ensure_consumer_group()

        # Step 2: Recover incomplete sessions from last run (if persistence enabled)
        if self.persistence:
            await self._recover_active_sessions()

        # Step 3: Process pending messages first (catch up on unprocessed messages)
        try:
            await self._process_pending_messages()
        except Exception as e:
            logger.error(f"Error in _process_pending_messages, continuing anyway: {e}", exc_info=True)

        persistence_status = "with database persistence" if self.persistence else "(in-memory only)"
        logger.info(f"Cursor session monitor started {persistence_status}, listening for new events...")

        # Step 4: Run Redis event listener directly (blocks until stopped)
        await self._listen_redis_events()

    async def _recover_active_sessions(self):
        """Recover active sessions from database."""
        if not self.persistence:
            return

        try:
            recovered = await self.persistence.recover_active_sessions()
            with self._lock:
                for external_session_id, session_info in recovered.items():
                    workspace_hash = session_info.get('workspace_hash')
                    if workspace_hash:
                        self.active_sessions[workspace_hash] = session_info
            logger.info(f"Recovered {len(recovered)} active Cursor sessions from database")

            # Call on_session_start callbacks for recovered sessions
            if self.on_session_start:
                for workspace_hash, session_info in self.active_sessions.items():
                    try:
                        await self.on_session_start(workspace_hash, session_info)
                    except Exception as e:
                        logger.error(f"Error calling on_session_start for recovered session {workspace_hash}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to recover active sessions: {e}", exc_info=True)

    def _ensure_consumer_group(self) -> None:
        """
        Ensure consumer group exists, create if not.

        Uses id='0' to process from beginning, ensuring no messages are lost
        after restart. Safe because processed messages are trimmed via ACK.
        """
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0',  # Start from beginning - process unprocessed messages
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

    def _read_pending_messages_sync(self):
        """Synchronous helper for reading pending messages in executor."""
        return self.redis_client.xreadgroup(
            groupname=self.consumer_group,
            consumername=self.consumer_name,
            streams={self.stream_name: "0"},  # "0" means read from PEL
            count=100,
            block=0  # Non-blocking
        )
    
    def _ack_message_sync(self, message_id: str):
        """Synchronous helper for ACKing messages in executor."""
        return self.redis_client.xack(
            self.stream_name,
            self.consumer_group,
            message_id
        )
    
    def _read_new_messages_sync(self):
        """Synchronous helper for reading new messages in executor."""
        return self.redis_client.xreadgroup(
            groupname=self.consumer_group,
            consumername=self.consumer_name,
            streams={self.stream_name: ">"},  # ">" means new messages
            count=100,
            block=1000  # 1 second block
        )

    async def _process_pending_messages(self):
        """Process pending messages from previous runs (messages in PEL)."""
        logger.info(f"Checking for pending messages in consumer group '{self.consumer_group}'...")
        try:
            total_cursor_events = 0
            total_acked = 0
            total_messages_read = 0
            empty_reads = 0
            max_empty_reads = 3  # Stop after 3 consecutive empty reads
            max_iterations = 1000  # Safety limit to prevent infinite loops

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                try:
                    # Read pending messages assigned to this consumer (using "0")
                    # Run Redis call in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    messages = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            self._read_pending_messages_sync
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

                batch_cursor_events = 0
                batch_acked = 0
                batch_messages = 0
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        batch_messages += 1
                        total_messages_read += 1
                        
                        # Decode message_id
                        msg_id_str = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else str(msg_id)
                        
                        # Check if this is a Cursor event before processing
                        event_type = self._decode_field(fields, 'event_type')
                        platform = self._decode_field(fields, 'platform')
                        is_cursor_event = (
                            platform == 'cursor' and 
                            event_type in ('session_start', 'session_end')
                        )
                        
                        try:
                            # Process message (will ACK filtered messages too)
                            success = await self._process_redis_message(msg_id_str, fields)
                            
                            if is_cursor_event:
                                batch_cursor_events += 1
                                total_cursor_events += 1
                            
                            # ACK if successfully processed (including filtered messages)
                            # Errors will remain in PEL for retry
                            if success:
                                try:
                                    # Run ACK in executor to avoid blocking
                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(
                                        self._executor,
                                        self._ack_message_sync,
                                        msg_id_str
                                    )
                                    batch_acked += 1
                                    total_acked += 1
                                except Exception as e:
                                    logger.error(f"Failed to ACK message {msg_id_str}: {e}")
                            # If success is False, it's an error - don't ACK, let it retry
                        except Exception as e:
                            logger.error(
                                f"Exception processing pending message {msg_id_str}: {e}",
                                exc_info=True
                            )
                            # Don't ACK on exception - let it retry

                # Only log if we processed Cursor events
                if batch_cursor_events > 0:
                    logger.info(
                        f"Processed {batch_cursor_events} pending Cursor events "
                        f"(ACKed {batch_acked}, total processed: {total_cursor_events})"
                    )
                await asyncio.sleep(0)  # Yield control during long catch-up

            # Always log completion
            if total_cursor_events == 0:
                if total_messages_read > 0:
                    logger.info(
                        f"No pending Cursor events to process "
                        f"(read {total_messages_read} messages from other platforms)"
                    )
                else:
                    logger.info("No pending Cursor events to process")
            else:
                logger.info(
                    f"Finished processing pending messages: {total_cursor_events} Cursor events "
                    f"processed, {total_acked} ACKed"
                )
        except Exception as e:
            logger.error(f"Error processing pending messages: {e}", exc_info=True)
            # Don't re-raise - continue to start listening for new events

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
        logger.info("Session monitor stopped")

    async def _listen_redis_events(self):
        """
        Listen to session_start/end events from Redis stream using consumer groups.

        Reads from telemetry:events stream, filters for Cursor session events.
        ACKs messages after successful processing.
        """
        logger.info("Cursor session monitor: Starting to listen for new Redis events...")
        try:
            while self.running:
                try:
                    # Read from stream using consumer group (">" means new messages)
                    # Run Redis call in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    messages = await loop.run_in_executor(
                        self._executor,
                        self._read_new_messages_sync
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
                                        loop_ack = asyncio.get_event_loop()
                                        await loop_ack.run_in_executor(
                                            self._executor,
                                            self._ack_message_sync,
                                            msg_id_str
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
        Process a Redis message and update session state.
        
        Args:
            msg_id: Redis message ID (string)
            fields: Redis stream fields dictionary
            
        Returns:
            True if message was processed (or should be ACKed), False if error occurred
        """
        try:
            # Decode fields
            event_type = self._decode_field(fields, 'event_type')
            platform = self._decode_field(fields, 'platform')


            # Only process Cursor session events
            if platform != 'cursor':
                return True  # Filtered out - ACK to prevent reprocessing

            # Only process session events
            if event_type not in ('session_start', 'session_end'):
                logger.debug(
                    f"Filtering out Cursor event (not session_start/end): "
                    f"event_type={event_type}, msg_id={msg_id}"
                )
                return True  # Filtered out - ACK to prevent reprocessing

            # Parse payload
            payload_str = self._decode_field(fields, 'payload')
            if payload_str:
                payload = json.loads(payload_str)
            else:
                payload = {}

            # Parse metadata
            metadata_str = self._decode_field(fields, 'metadata')
            if metadata_str:
                metadata = json.loads(metadata_str)
            else:
                metadata = {}

            # Extract session_id from multiple possible locations:
            # 1. Top-level external_session_id field (from extension)
            # 2. payload.session_id (from extension)
            # 3. metadata.session_id (fallback)
            external_session_id_field = self._decode_field(fields, 'external_session_id')
            session_id = (
                external_session_id_field or
                payload.get('session_id') or
                metadata.get('session_id')
            )
            
            # Extract workspace_hash from multiple possible locations:
            # 1. metadata.workspace_hash (from extension)
            # 2. payload.workspace_hash (from extension)
            workspace_hash = metadata.get('workspace_hash') or payload.get('workspace_hash')
            workspace_path = payload.get('workspace_path', '')

            if not workspace_hash or not session_id:
                logger.warning(
                    f"Incomplete session event: msg_id={msg_id}, "
                    f"workspace_hash={workspace_hash}, session_id={session_id}, "
                    f"payload_keys={list(payload.keys())}, metadata_keys={list(metadata.keys())}"
                )
                return True  # ACK to prevent reprocessing

            if event_type == 'session_start':
                # Extract workspace_name - try from event first, then extract from path
                workspace_name_from_event = metadata.get('workspace_name') or payload.get('workspace_name')
                if workspace_name_from_event:
                    workspace_name = workspace_name_from_event
                    logger.debug(f"Using workspace_name from event: {workspace_name}")
                else:
                    workspace_name = _extract_workspace_name(workspace_path)
                    if workspace_name:
                        logger.debug(f"Extracted workspace_name from path: {workspace_name} (path: {workspace_path})")
                    else:
                        logger.warning(f"Could not extract workspace_name from path: {workspace_path}")
                
                # Persist to database (durable)
                internal_session_id = None
                if self.persistence:
                    try:
                        internal_session_id = await self.persistence.save_session_start(
                            external_session_id=session_id,
                            workspace_hash=workspace_hash,
                            workspace_path=workspace_path,
                            workspace_name=workspace_name,
                            metadata=metadata
                        )
                    except SessionNotFoundError:
                        # This shouldn't happen for session_start, but log it
                        logger.error(f"Session not found during start (unexpected): {session_id}")
                        # Continue with in-memory tracking
                    except DatabaseError as e:
                        logger.error(f"Database error persisting session start: {e}")
                        # Continue with in-memory tracking - system degrades gracefully
                    except Exception as e:
                        logger.error(f"Unexpected error persisting session start: {e}", exc_info=True)
                        # Continue with in-memory tracking
                
                # Add to in-memory dict (fast path)
                session_info = {
                    "session_id": session_id,  # External session ID (backwards compatibility)
                    "internal_session_id": internal_session_id,
                    "external_session_id": session_id,
                    "workspace_hash": workspace_hash,
                    "workspace_path": workspace_path,
                    "workspace_name": workspace_name,
                    "started_at": time.time(),
                    "source": "redis",
                }

                with self._lock:
                    self.active_sessions[workspace_hash] = session_info

                logger.info(f"Cursor session started: {workspace_hash} -> {session_id}")

                # Call the on_session_start callback if registered
                if self.on_session_start:
                    try:
                        await self.on_session_start(workspace_hash, session_info)
                    except Exception as e:
                        logger.error(f"Error in on_session_start callback: {e}", exc_info=True)

                return True  # Successfully processed

            elif event_type == 'session_end':
                # Update database first (ensure durability)
                if self.persistence:
                    try:
                        await self.persistence.save_session_end(session_id, end_reason='normal')
                    except SessionNotFoundError as e:
                        logger.warning(f"Session not found during end: {e}")
                        # Continue with cleanup
                    except DatabaseError as e:
                        logger.error(f"Database error persisting session end: {e}")
                        # Continue with cleanup - system degrades gracefully
                    except Exception as e:
                        logger.error(f"Unexpected error persisting session end: {e}", exc_info=True)
                        # Continue with cleanup
                
                # Then remove from memory
                with self._lock:
                    removed = self.active_sessions.pop(workspace_hash, None)
                    if removed:
                        logger.info(f"Cursor session ended: {workspace_hash}")
                    else:
                        logger.debug(f"Session end for unknown workspace: {workspace_hash}")

                # Call the on_session_end callback if registered (outside the lock)
                if removed and self.on_session_end:
                    try:
                        await self.on_session_end(workspace_hash)
                    except Exception as e:
                        logger.error(f"Error in on_session_end callback: {e}", exc_info=True)
                return True  # Successfully processed

            return False  # Unknown event type
        except Exception as e:
            logger.error(f"Error processing Redis message {msg_id}: {e}", exc_info=True)
            # Return False to prevent ACK, allowing retry via PEL
            return False

    def _decode_field(self, fields: dict, key: str) -> str:
        """Decode a field from Redis message."""
        # Handle both dict and list formats
        if isinstance(fields, dict):
            value = fields.get(key.encode() if isinstance(key, str) else key)
        else:
            # List format: [key1, val1, key2, val2, ...]
            try:
                idx = list(fields).index(key.encode() if isinstance(key, str) else key)
                value = fields[idx + 1] if idx + 1 < len(fields) else None
            except (ValueError, IndexError):
                value = None

        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return str(value)

    def get_active_workspaces(self) -> Dict[str, dict]:
        """Get currently active workspaces."""
        with self._lock:
            return {
                workspace_hash: session.copy()
                for workspace_hash, session in self.active_sessions.items()
            }

    def get_workspace_path(self, workspace_hash: str) -> Optional[str]:
        """Get workspace path for hash."""
        with self._lock:
            session = self.active_sessions.get(workspace_hash)
            return session.get("workspace_path") if session else None

    def remove_session_by_workspace_hash(self, workspace_hash: str) -> bool:
        """
        Remove session from memory by workspace hash.
        
        Args:
            workspace_hash: Workspace hash identifier
            
        Returns:
            True if session was removed, False if not found
        """
        with self._lock:
            removed = self.active_sessions.pop(workspace_hash, None)
            return removed is not None

    def remove_session_by_external_id(self, external_session_id: str) -> bool:
        """
        Remove session from memory by external session ID.
        
        Args:
            external_session_id: External session ID from Cursor extension
            
        Returns:
            True if session was removed, False if not found
        """
        with self._lock:
            for workspace_hash, session_info in list(self.active_sessions.items()):
                if session_info.get('external_session_id') == external_session_id:
                    del self.active_sessions[workspace_hash]
                    return True
            return False


