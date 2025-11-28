# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Timeout Manager for Claude Code.

Handles cleanup of abandoned sessions by marking them as timed out.
Runs periodically to prevent memory leaks and ensure proper session closure.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .session_persistence import SessionPersistence
from .session_monitor import ClaudeCodeSessionMonitor
from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class SessionTimeoutManager:
    """
    Handles cleanup of abandoned Claude Code sessions.
    
    Runs periodically to prevent memory leaks and ensure proper session closure.
    """

    DEFAULT_TIMEOUT_HOURS = 24
    CLEANUP_INTERVAL_SECONDS = 3600  # Run hourly

    def __init__(
        self,
        session_monitor: ClaudeCodeSessionMonitor,
        sqlite_client: SQLiteClient,
        timeout_hours: int = DEFAULT_TIMEOUT_HOURS,
        cleanup_interval: float = CLEANUP_INTERVAL_SECONDS
    ):
        """
        Initialize session timeout manager.

        Args:
            session_monitor: Session monitor instance (to remove from memory)
            sqlite_client: SQLite client for database operations
            timeout_hours: Hours of inactivity before timeout (default: 24)
            cleanup_interval: Seconds between cleanup runs (default: 3600)
        """
        self.session_monitor = session_monitor
        self.persistence = SessionPersistence(sqlite_client)
        self.timeout_hours = timeout_hours
        self.cleanup_interval = cleanup_interval
        self.running = False

    async def start(self):
        """Start timeout manager background task."""
        self.running = True
        logger.info(
            f"Session timeout manager started "
            f"(timeout: {self.timeout_hours}h, interval: {self.cleanup_interval}s)"
        )
        
        while self.running:
            try:
                await self.cleanup_stale_sessions()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in timeout manager cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)  # Back off on error

    async def stop(self):
        """Stop timeout manager."""
        self.running = False
        logger.info("Session timeout manager stopped")

    async def cleanup_stale_sessions(self):
        """
        Mark inactive sessions as timed out.
        
        Queries database for sessions without ended_at that are older than timeout threshold.
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.timeout_hours)
            
            # Query database for old active sessions
            with self.persistence.sqlite_client.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT session_id, started_at
                    FROM conversations
                    WHERE platform = 'claude_code'
                      AND ended_at IS NULL
                      AND started_at < ?
                """, (cutoff_time.isoformat(),))
                
                stale_sessions = cursor.fetchall()
            
            if not stale_sessions:
                return
            
            logger.info(f"Found {len(stale_sessions)} stale Claude Code sessions to timeout")
            
            for session_id, started_at_str in stale_sessions:
                try:
                    # Parse started_at timestamp
                    started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                    
                    logger.warning(
                        f"Timing out stale Claude Code session: {session_id} "
                        f"(started: {started_at}, age: {datetime.now(timezone.utc) - started_at})"
                    )
                    
                    # Mark as timed out in database
                    await self.persistence.mark_session_timeout(
                        session_id,
                        last_activity=started_at
                    )
                    
                    # Remove from memory if present
                    if self.session_monitor.remove_session(session_id):
                        logger.debug(f"Removed timed-out session {session_id} from memory")
                        
                except Exception as e:
                    logger.error(f"Failed to timeout session {session_id}: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Error during stale session cleanup: {e}", exc_info=True)

