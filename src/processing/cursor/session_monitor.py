# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Monitor for Cursor workspaces.

Listens to Redis session_start/end events from the extension.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
import redis

logger = logging.getLogger(__name__)


class SessionMonitor:
    """
    Monitor Cursor sessions via Redis events.

    Design:
    - Redis stream events are the only source (extension required)
    - Tracks active workspaces with metadata
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

        # Active sessions: workspace_hash -> session_info
        self.active_sessions: Dict[str, dict] = {}

        # Track last processed Redis message ID (for resuming)
        self.last_redis_id = "0-0"

        self.running = False

    async def start(self):
        """Start monitoring sessions."""
        self.running = True

        # Process historical events first (catch up on existing sessions)
        await self._catch_up_historical_events()

        # Start Redis event listener
        asyncio.create_task(self._listen_redis_events())

        logger.info("Session monitor started (Redis events only)")

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

                logger.info(f"Processed {len(msgs)} historical events")
        except Exception as e:
            logger.warning(f"Error catching up historical events: {e}")

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        logger.info("Session monitor stopped")

    async def _listen_redis_events(self):
        """
        Listen to session_start/end events from Redis stream.

        Reads from telemetry:events stream, filters for session events.
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

                except redis.ConnectionError:
                    logger.warning("Redis connection lost, retrying...")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Error reading Redis events: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Redis event listener failed: {e}")

    async def _process_redis_message(self, msg_id, fields: dict):
        """Process a Redis message and update session state."""
        try:
            # Decode fields
            event_type = self._decode_field(fields, 'event_type')
            hook_type = self._decode_field(fields, 'hook_type')

            # Only process session events
            if event_type not in ('session_start', 'session_end'):
                return

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

            workspace_hash = metadata.get('workspace_hash') or payload.get('workspace_hash')
            session_id = payload.get('session_id') or metadata.get('session_id')
            workspace_path = payload.get('workspace_path', '')

            if not workspace_hash or not session_id:
                logger.debug(f"Incomplete session event: {msg_id}")
                return

            if event_type == 'session_start':
                self.active_sessions[workspace_hash] = {
                    "session_id": session_id,
                    "workspace_hash": workspace_hash,
                    "workspace_path": workspace_path,
                    "started_at": asyncio.get_event_loop().time(),
                    "source": "redis",
                }
                logger.info(f"Session started: {workspace_hash} -> {session_id}")

            elif event_type == 'session_end':
                if workspace_hash in self.active_sessions:
                    del self.active_sessions[workspace_hash]
                    logger.info(f"Session ended: {workspace_hash}")

        except Exception as e:
            logger.error(f"Error processing Redis message {msg_id}: {e}")

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
        return self.active_sessions.copy()

    def get_workspace_path(self, workspace_hash: str) -> Optional[str]:
        """Get workspace path for hash."""
        session = self.active_sessions.get(workspace_hash)
        return session.get("workspace_path") if session else None



