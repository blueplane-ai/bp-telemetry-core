# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Conversation Worker for Claude Code (Slow Path).

Processes completed sessions to build conversation structure and calculate metrics.
Reads from CDC stream and updates conversations table with derived data.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any
import redis

from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class ConversationWorker:
    """
    Async worker that processes completed Claude Code sessions.
    
    Reads from CDC stream and builds conversation structure with metrics.
    This is the "slow path" for non-real-time processing.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: SQLiteClient,
        cdc_stream_name: str = "telemetry:cdc",
        consumer_group: str = "conversation-workers",
        consumer_name: str = "conversation-worker-1",
    ):
        """
        Initialize conversation worker.

        Args:
            redis_client: Redis client for CDC stream
            sqlite_client: SQLite client for database operations
            cdc_stream_name: CDC stream name
            consumer_group: Consumer group name
            consumer_name: Consumer name (unique per instance)
        """
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.cdc_stream_name = cdc_stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.running = False

    def _ensure_consumer_group(self) -> None:
        """Ensure consumer group exists, create if not."""
        try:
            self.redis_client.xgroup_create(
                self.cdc_stream_name,
                self.consumer_group,
                id="0",
                mkstream=True
            )
            logger.info(f"Created consumer group {self.consumer_group}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group {self.consumer_group} already exists")
            else:
                raise

    async def start(self):
        """Main worker loop."""
        self.running = True
        self._ensure_consumer_group()
        
        logger.info(f"Conversation worker started: {self.consumer_name}")
        
        while self.running:
            try:
                # Read CDC events
                messages = await self._read_cdc_stream()
                
                for msg in messages:
                    message_id = msg.get('id')
                    event = msg.get('event', {})
                    event_type = event.get('event_type', '')
                    
                    if event_type == 'session_end':
                        session_id = event.get('session_id') or event.get('payload', {}).get('session_id')
                        if session_id:
                            await self._process_completed_session(session_id)
                    
                    if message_id:
                        self._ack_message(message_id)
                
                await asyncio.sleep(0.1)  # Small delay between reads
                
            except Exception as e:
                logger.error(f"Error in conversation worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back off on error

    async def _read_cdc_stream(self) -> List[Dict[str, Any]]:
        """
        Read messages from CDC stream.

        Returns:
            List of message dictionaries
        """
        try:
            messages = self.redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.cdc_stream_name: ">"},
                count=10,
                block=1000  # 1 second block
            )
            
            if not messages:
                return []
            
            result = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    # Decode fields
                    event = {}
                    for key, value in fields.items():
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                        if isinstance(value, bytes):
                            val_str = value.decode('utf-8')
                        else:
                            val_str = str(value)
                        
                        if key_str in ('event', 'payload'):
                            try:
                                event[key_str] = json.loads(val_str)
                            except json.JSONDecodeError:
                                event[key_str] = {}
                        else:
                            event[key_str] = val_str
                    
                    result.append({
                        'id': message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id),
                        'event': event
                    })
            
            return result
            
        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading CDC stream: {e}")
            return []

    def _ack_message(self, message_id: str) -> None:
        """Acknowledge a CDC message to prevent reprocessing."""
        try:
            self.redis_client.xack(
                self.cdc_stream_name,
                self.consumer_group,
                message_id
            )
        except redis.RedisError as e:
            logger.error(f"Failed to ack CDC message {message_id}: {e}")

    async def _process_completed_session(self, session_id: str):
        """
        Build conversation from raw events and calculate metrics.
        
        This is a placeholder implementation. Full implementation would:
        1. Query all events for this session from claude_raw_traces
        2. Build conversation structure
        3. Calculate metrics (interaction_count, total_tokens, acceptance_rate, etc.)
        4. Update conversations table

        Args:
            session_id: Session identifier
        """
        try:
            logger.debug(f"Processing completed Claude Code session: {session_id}")
            
            # TODO: Implement full conversation reconstruction
            # For now, just log that we received the session_end event
            # Future implementation will:
            # - Query claude_raw_traces for all events in this session
            # - Reconstruct conversation turns
            # - Calculate metrics
            # - Update conversations table with metrics
            
            # Placeholder: Query basic metrics
            with self.sqlite_client.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as event_count,
                        SUM(tokens_used) as total_tokens
                    FROM claude_raw_traces
                    WHERE session_id = ?
                """, (session_id,))
                
                row = cursor.fetchone()
                if row:
                    event_count = row[0] or 0
                    total_tokens = row[1] or 0
                    
                    # Update conversations table with basic metrics
                    cursor = conn.execute("""
                        UPDATE conversations
                        SET 
                            interaction_count = ?,
                            total_tokens = ?
                        WHERE session_id = ? AND platform = 'claude_code'
                    """, (
                        event_count,
                        total_tokens,
                        session_id
                    ))
                    conn.commit()
                    
                    logger.info(
                        f"Updated metrics for session {session_id}: "
                        f"{event_count} events, {total_tokens} tokens"
                    )
                    
        except Exception as e:
            logger.error(f"Failed to process completed session {session_id}: {e}", exc_info=True)

    async def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("Conversation worker stopped")

