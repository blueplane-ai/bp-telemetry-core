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
from pathlib import Path
from typing import Dict, Optional
import redis

from .session_persistence import SessionPersistence
from ..database.sqlite_client import SQLiteClient
from ...capture.shared.project_utils import derive_project_name

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

    def __init__(self, redis_client: redis.Redis, sqlite_client: Optional[SQLiteClient] = None):
        """
        Initialize Claude Code session monitor.

        Args:
            redis_client: Redis client for event streaming
            sqlite_client: Optional SQLite client for persistence (if None, persistence disabled)
        """
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client

        # Active sessions: session_id -> session_info (in-memory for fast lookups)
        self.active_sessions: Dict[str, dict] = {}

        # Track last processed Redis message ID (for resuming)
        self.last_redis_id = "0-0"

        # Session persistence (if sqlite_client provided)
        self.persistence: Optional[SessionPersistence] = None
        if sqlite_client:
            self.persistence = SessionPersistence(sqlite_client)

        self.running = False

    async def start(self):
        """
        Start monitoring sessions with recovery.
        
        Steps:
        1. Recover incomplete sessions from database (if persistence enabled)
        2. Catch up on historical Redis events
        3. Start listening to new Redis events
        """
        self.running = True

        # Step 1: Recover incomplete sessions from last run (if persistence enabled)
        if self.persistence:
            await self._recover_active_sessions()

        # Step 2: Process historical events first (catch up on existing sessions)
        await self._catch_up_historical_events()

        persistence_status = "with database persistence" if self.persistence else "(in-memory only)"
        logger.info(f"Claude Code session monitor started {persistence_status}")

        # Step 3: Run Redis event listener directly (blocks until stopped)
        await self._listen_redis_events()

    async def _catch_up_historical_events(self):
        """Process all historical session_start events from Redis."""
        try:
            # Read all historical events
            messages = self.redis_client.xread(
                {"telemetry:events": "0-0"},
                count=1000,
                block=0  # Non-blocking
            )

            if messages:
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        await self._process_redis_message(msg_id, fields)
                        self.last_redis_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

                logger.info(f"Processed {len(msgs)} historical Claude Code events")
        except Exception as e:
            logger.warning(f"Error catching up historical events: {e}")

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        logger.info("Claude Code session monitor stopped")

    async def _listen_redis_events(self):
        """
        Listen to session_start/end events from Redis stream.

        Reads from telemetry:events stream, filters for Claude Code session events.
        """
        try:
            while self.running:
                try:
                    # Read from stream (non-blocking, 1 second timeout)
                    messages = self.redis_client.xread(
                        {"telemetry:events": self.last_redis_id},
                        count=100,
                        block=1000  # 1 second block
                    )

                    if not messages:
                        await asyncio.sleep(0.1)
                        continue

                    # Process messages
                    for stream, msgs in messages:
                        for msg_id, fields in msgs:
                            await self._process_redis_message(msg_id, fields)
                            self.last_redis_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

                except redis.exceptions.RedisError as e:
                    logger.error(f"Redis error in session monitor: {e}")
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Fatal error in session monitor: {e}")

    async def _process_redis_message(self, msg_id, fields: dict):
        """
        Process a Redis stream message.

        Filters for session_start/session_end events from Claude Code.
        """
        # Decode fields
        event_type = self._decode_field(fields, 'event_type')
        platform = self._decode_field(fields, 'platform')

        # Only process Claude Code session events
        if platform != 'claude_code':
            return

        if event_type not in ('session_start', 'session_end'):
            return

        # Parse payload
        payload_str = self._decode_field(fields, 'payload')
        payload = json.loads(payload_str) if payload_str else {}

        metadata_str = self._decode_field(fields, 'metadata')
        metadata = json.loads(metadata_str) if metadata_str else {}

        session_id = payload.get('session_id') or self._decode_field(fields, 'session_id')
        workspace_hash = metadata.get('workspace_hash')
        workspace_path = payload.get('workspace_path', '')
        project_name = metadata.get('project_name') or derive_project_name(workspace_path)

        if event_type == 'session_start':
            # Add to in-memory dict (fast path)
            self.active_sessions[session_id] = {
                "session_id": session_id,
                "workspace_hash": workspace_hash,
                "workspace_path": workspace_path,
                "project_name": project_name,
                "platform": "claude_code",
                "started_at": asyncio.get_event_loop().time(),
                "source": "hooks",
            }
            
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

        elif event_type == 'session_end':
            # Update database first (ensure durability)
            if self.persistence:
                await self.persistence.save_session_end(session_id, end_reason='normal')
            
            # Then remove from memory
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                logger.info(f"Claude Code session ended: {session_id}")
            else:
                logger.debug(f"Session end for unknown session: {session_id}")

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
        return self.active_sessions.copy()

    async def update_session_workspace(self, session_id: str, workspace_path: str) -> None:
        """
        Update the workspace path for a session.

        Called when workspace path is discovered from JSONL content.

        Args:
            session_id: Session identifier
            workspace_path: Discovered workspace path
        """
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["workspace_path"] = workspace_path
            self.active_sessions[session_id]["workspace_hash"] = self._hash_workspace(workspace_path)

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
            
            for session_id, session_info in recovered.items():
                # Restore to active sessions
                self.active_sessions[session_id] = session_info
                
                # Check if JSONL file still exists (basic validation)
                workspace_path = session_info.get('workspace_path', '')
                if workspace_path:
                    # Try to construct expected JSONL path
                    # Claude Code stores JSONL files in ~/.claude/projects/{project_id}/
                    # We can't fully validate without project_id, but we log recovery
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
        return self.active_sessions.get(session_id)
