# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Persistence Module for Claude Code.

Manages persistent session state in SQLite database, providing durability
and recovery capabilities for Claude Code session management.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List
import uuid

from ..database.sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


def _extract_workspace_name(workspace_path: str) -> str:
    """
    Extract human-readable workspace name from full path.
    
    Examples:
        /Users/user/projects/my-app -> my-app
        /home/user/dev/workspace -> workspace
        C:\\Users\\user\\projects\\my-app -> my-app
    
    Args:
        workspace_path: Full workspace path
        
    Returns:
        Workspace name (directory name) or empty string if path is invalid
    """
    if not workspace_path:
        return ""
    
    try:
        # Use Path to handle cross-platform paths
        path = Path(workspace_path)
        # Get the last component (directory name)
        name = path.name
        # If it's empty (e.g., root path), try parent
        if not name and path.parent != path:
            name = path.parent.name
        return name or ""
    except Exception:
        # Fallback: try to extract manually
        parts = workspace_path.replace('\\', '/').rstrip('/').split('/')
        return parts[-1] if parts else ""


class SessionPersistence:
    """
    Manages persistent session state in SQLite database for Claude Code.
    
    Provides durability and recovery capabilities for session lifecycle management.
    """

    def __init__(self, sqlite_client: SQLiteClient):
        """
        Initialize session persistence.

        Args:
            sqlite_client: SQLiteClient instance for database operations
        """
        self.sqlite_client = sqlite_client

    async def save_session_start(
        self,
        session_id: str,
        workspace_hash: str,
        workspace_path: str,
        metadata: dict
    ) -> None:
        """
        Persist new session to conversations table.
        
        Called when session_start event is received.

        Args:
            session_id: Unique session identifier
            workspace_hash: Hash of workspace path
            workspace_path: Full workspace path
            metadata: Additional session metadata
        """
        try:
            # Generate conversation ID (use session_id as external_session_id)
            conversation_id = str(uuid.uuid4())
            external_session_id = session_id
            
            # Extract human-readable workspace name
            workspace_name = _extract_workspace_name(workspace_path)
            
            # Prepare context and metadata JSON
            context = {
                'workspace_path': workspace_path,
                'workspace_hash': workspace_hash,
                'workspace_name': workspace_name,
            }
            
            session_metadata = {
                'source': metadata.get('source', 'hooks'),
                'started_via': 'session_start_hook',
                'workspace_name': workspace_name,
                'workspace_path': workspace_path,
                'workspace_hash': workspace_hash,
                **metadata
            }
            
            # Insert into conversations table
            with self.sqlite_client.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT OR REPLACE INTO conversations (
                        id, session_id, external_session_id, platform,
                        workspace_hash, workspace_name, started_at,
                        context, metadata,
                        interaction_count, total_tokens, total_changes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    conversation_id,
                    session_id,
                    external_session_id,
                    'claude_code',
                    workspace_hash,
                    workspace_name,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(context),
                    json.dumps(session_metadata),
                    0,  # interaction_count
                    0,  # total_tokens
                    0,  # total_changes
                ))
                conn.commit()
                
            logger.info(f"Persisted Claude Code session start: {session_id}")

        except Exception as e:
            logger.error(f"Failed to persist session start for {session_id}: {e}", exc_info=True)
            # Don't raise - allow in-memory tracking to continue

    async def save_session_end(
        self,
        session_id: str,
        end_reason: str = 'normal'  # 'normal', 'timeout', 'crash'
    ) -> None:
        """
        Mark session as ended with timestamp and reason.
        
        Called when session_end event is received or timeout occurs.

        Args:
            session_id: Session identifier
            end_reason: Reason for session end ('normal', 'timeout', 'crash')
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                # Update ended_at timestamp
                cursor = conn.execute("""
                    UPDATE conversations
                    SET ended_at = ?
                    WHERE session_id = ? AND platform = 'claude_code'
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    session_id
                ))
                
                if cursor.rowcount == 0:
                    logger.warning(f"Session {session_id} not found in conversations table for end update")
                else:
                    # Update metadata with end reason
                    cursor = conn.execute("""
                        SELECT metadata FROM conversations
                        WHERE session_id = ? AND platform = 'claude_code'
                    """, (session_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        try:
                            metadata = json.loads(row[0]) if row[0] else {}
                            metadata['end_reason'] = end_reason
                            metadata['ended_at'] = datetime.now(timezone.utc).isoformat()
                            
                            cursor = conn.execute("""
                                UPDATE conversations
                                SET metadata = ?
                                WHERE session_id = ? AND platform = 'claude_code'
                            """, (
                                json.dumps(metadata),
                                session_id
                            ))
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse metadata for session {session_id}")
                    
                    conn.commit()
                    logger.info(f"Persisted Claude Code session end: {session_id} (reason: {end_reason})")

        except Exception as e:
            logger.error(f"Failed to persist session end for {session_id}: {e}", exc_info=True)
            # Don't raise - allow cleanup to continue

    async def recover_active_sessions(self) -> Dict[str, dict]:
        """
        Query database for sessions without ended_at.
        
        Called on server startup to restore state.

        Returns:
            Dictionary of session_id -> session_info
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT
                        session_id, workspace_hash, workspace_name, context, metadata, started_at
                    FROM conversations
                    WHERE platform = 'claude_code' AND ended_at IS NULL
                    ORDER BY started_at DESC
                """)
                
                rows = cursor.fetchall()
                recovered = {}
                
                for row in rows:
                    session_id = row[0]
                    workspace_hash = row[1]
                    workspace_name = row[2] or ''
                    context_str = row[3] or '{}'
                    metadata_str = row[4] or '{}'
                    started_at = row[5]
                    
                    try:
                        context = json.loads(context_str) if context_str else {}
                        metadata = json.loads(metadata_str) if metadata_str else {}
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON for recovered session {session_id}")
                        context = {}
                        metadata = {}
                    
                    # Use workspace_name from database or fallback to context/metadata
                    if not workspace_name:
                        workspace_name = context.get('workspace_name') or metadata.get('workspace_name') or ''
                    
                    recovered[session_id] = {
                        "session_id": session_id,
                        "workspace_hash": workspace_hash,
                        "workspace_name": workspace_name,
                        "workspace_path": context.get('workspace_path', ''),
                        "platform": "claude_code",
                        "started_at": started_at,
                        "source": metadata.get('source', 'recovered'),
                        "recovered": True,
                    }
                
                logger.info(f"Recovered {len(recovered)} active Claude Code sessions from database")
                return recovered

        except Exception as e:
            logger.error(f"Failed to recover active sessions: {e}", exc_info=True)
            return {}

    async def mark_session_timeout(
        self,
        session_id: str,
        last_activity: datetime
    ) -> None:
        """
        Mark abandoned session as timed out.
        
        Called by cleanup task for stale sessions.

        Args:
            session_id: Session identifier
            last_activity: Last known activity timestamp
        """
        try:
            await self.save_session_end(session_id, end_reason='timeout')
            logger.info(f"Marked session {session_id} as timed out (last activity: {last_activity})")
        except Exception as e:
            logger.error(f"Failed to mark session timeout for {session_id}: {e}", exc_info=True)

    async def update_workspace_path(self, session_id: str, workspace_path: str) -> None:
        """
        Update the workspace path for an existing session.

        Called when workspace path is discovered from JSONL content.

        Args:
            session_id: Session identifier
            workspace_path: Discovered workspace path
        """
        try:
            import hashlib
            workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()[:16]
            workspace_name = _extract_workspace_name(workspace_path)

            with self.sqlite_client.get_connection() as conn:
                # Update workspace information
                cursor = conn.execute("""
                    UPDATE conversations
                    SET workspace_hash = ?,
                        workspace_name = ?,
                        context = json_set(context, '$.workspace_path', ?),
                        metadata = json_set(metadata, '$.workspace_path', ?)
                    WHERE session_id = ? AND platform = 'claude_code'
                """, (
                    workspace_hash,
                    workspace_name,
                    workspace_path,
                    workspace_path,
                    session_id
                ))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Updated workspace path in database for session {session_id}")
                else:
                    logger.warning(f"Session {session_id} not found in database for workspace update")

        except Exception as e:
            logger.error(f"Failed to update workspace path for session {session_id}: {e}", exc_info=True)

    async def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        Get session information from database.

        Args:
            session_id: Session identifier

        Returns:
            Session info dict or None if not found
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT
                        session_id, workspace_hash, workspace_name, context, metadata,
                        started_at, ended_at,
                        interaction_count, total_tokens, total_changes
                    FROM conversations
                    WHERE session_id = ? AND platform = 'claude_code'
                """, (session_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                try:
                    context = json.loads(row[3]) if row[3] else {}
                    metadata = json.loads(row[4]) if row[4] else {}
                except json.JSONDecodeError:
                    context = {}
                    metadata = {}
                
                # Use workspace_name from database or fallback to context/metadata
                workspace_name = row[2] or context.get('workspace_name') or metadata.get('workspace_name') or ''
                
                return {
                    'session_id': row[0],
                    'workspace_hash': row[1],
                    'workspace_name': workspace_name,
                    'workspace_path': context.get('workspace_path', ''),
                    'started_at': row[5],
                    'ended_at': row[6],
                    'interaction_count': row[7],
                    'total_tokens': row[8],
                    'total_changes': row[9],
                    'metadata': metadata,
                }
        except Exception as e:
            logger.error(f"Failed to get session info for {session_id}: {e}", exc_info=True)
            return None

