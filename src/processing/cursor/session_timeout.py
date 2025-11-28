# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Timeout Manager for Cursor.

Handles cleanup of abandoned sessions by marking them as timed out.
Runs periodically to prevent memory leaks and ensure proper session closure.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .session_persistence import CursorSessionPersistence
from .session_monitor import SessionMonitor
from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class CursorSessionTimeoutManager:
    """
    Handles cleanup of abandoned Cursor sessions.
    
    Runs periodically to prevent memory leaks and ensure proper session closure.
    Similar to Claude Code's SessionTimeoutManager but works with cursor_sessions table.
    """

    DEFAULT_TIMEOUT_HOURS = 24
    CLEANUP_INTERVAL_SECONDS = 3600  # Run hourly

    def __init__(
        self,
        session_monitor: SessionMonitor,
        sqlite_client: SQLiteClient,
        timeout_hours: int = DEFAULT_TIMEOUT_HOURS,
        cleanup_interval: float = CLEANUP_INTERVAL_SECONDS
    ):
        """
        Initialize Cursor session timeout manager.

        Args:
            session_monitor: Session monitor instance (to remove from memory)
            sqlite_client: SQLite client for database operations
            timeout_hours: Hours of inactivity before timeout (default: 24)
            cleanup_interval: Seconds between cleanup runs (default: 3600)
        """
        self.session_monitor = session_monitor
        self.persistence = CursorSessionPersistence(sqlite_client)
        self.timeout_hours = timeout_hours
        self.cleanup_interval = cleanup_interval
        self.running = False

    async def start(self):
        """Start timeout manager background task."""
        self.running = True
        logger.info(
            f"Cursor session timeout manager started "
            f"(timeout: {self.timeout_hours}h, interval: {self.cleanup_interval}s)"
        )
        
        while self.running:
            try:
                await self.cleanup_stale_sessions()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in Cursor timeout manager cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)  # Back off on error

    async def stop(self):
        """Stop timeout manager."""
        self.running = False
        logger.info("Cursor session timeout manager stopped")

    async def cleanup_stale_sessions(self):
        """
        Mark inactive Cursor sessions as timed out.
        
        Processes sessions in batches to avoid memory issues with large datasets.
        Queries cursor_sessions table for sessions without ended_at that are older than timeout threshold.
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.timeout_hours)
            batch_size = 100  # Process 100 sessions at a time
            offset = 0
            total_processed = 0
            
            while True:
                # Query database for old active Cursor sessions (paginated)
                # Note: We query cursor_sessions table, not conversations table
                with self.persistence.sqlite_client.get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT external_session_id, started_at
                        FROM cursor_sessions
                        WHERE ended_at IS NULL
                          AND started_at < ?
                        ORDER BY started_at ASC
                        LIMIT ? OFFSET ?
                    """, (cutoff_time.isoformat(), batch_size, offset))
                    
                    stale_sessions = cursor.fetchall()
                
                if not stale_sessions:
                    # No more sessions to process
                    break
                
                logger.info(
                    f"Processing batch of {len(stale_sessions)} stale Cursor sessions "
                    f"(offset: {offset})"
                )
                
                for external_session_id, started_at_str in stale_sessions:
                    try:
                        # Parse started_at timestamp
                        started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                        
                        logger.warning(
                            f"Timing out stale Cursor session: {external_session_id} "
                            f"(started: {started_at}, age: {datetime.now(timezone.utc) - started_at})"
                        )
                        
                        # Mark as timed out in database
                        await self.persistence.mark_session_timeout(
                            external_session_id,
                            last_activity=started_at
                        )
                        
                        # Remove from memory if present
                        if self.session_monitor.remove_session_by_external_id(external_session_id):
                            logger.debug(f"Removed timed-out session {external_session_id} from memory")
                        
                        total_processed += 1
                        
                    except Exception as e:
                        logger.error(
                            f"Failed to timeout Cursor session {external_session_id}: {e}",
                            exc_info=True
                        )
                
                offset += batch_size
                
                # Small delay between batches to avoid overwhelming the database
                await asyncio.sleep(0.1)
            
            if total_processed > 0:
                logger.info(f"Completed timeout cleanup: {total_processed} sessions processed")
                    
        except Exception as e:
            logger.error(f"Error during stale Cursor session cleanup: {e}", exc_info=True)

