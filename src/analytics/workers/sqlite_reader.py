# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
SQLite Reader for Analytics Service.

Reads raw traces from SQLite database for processing into DuckDB analytics.

See also:
- Architecture: docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md
- Platform column handling: docs/ANALYTICS_PLATFORM_COLUMN_FIX.md
- Testing: docs/ANALYTICS_TESTING_SUMMARY.md
"""

import json
import logging
import zlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.processing.database.sqlite_client import SQLiteClient
from .duckdb_writer import DuckDBWriter

logger = logging.getLogger(__name__)


class SQLiteReader:
    """
    Reads raw traces from SQLite for analytics processing.
    
    Supports incremental processing with state tracking via DuckDB analytics_processing_state table.
    
    Platform-specific handling:
    - Cursor: Uses external_session_id column
    - Claude Code: Uses external_id column
    
    See also:
    - Platform column fix: docs/ANALYTICS_PLATFORM_COLUMN_FIX.md
    - State tracking: Uses analytics_processing_state table in DuckDB (not SQLite)
    """

    def __init__(self, db_path: Path, duckdb_writer: Optional[DuckDBWriter] = None):
        """
        Initialize SQLite reader.

        Args:
            db_path: Path to SQLite telemetry database
            duckdb_writer: DuckDBWriter instance for state tracking (required for state operations)
        """
        self.db_path = Path(db_path).expanduser()
        self.client = SQLiteClient(str(self.db_path))
        self.duckdb_writer = duckdb_writer

    def get_last_processed_sequence(self, platform: str) -> int:
        """
        Get last processed sequence number for a platform from DuckDB.

        Args:
            platform: Platform name ('cursor' or 'claude_code')

        Returns:
            Last processed sequence number (0 if none or DuckDB writer not available)
        """
        if not self.duckdb_writer:
            logger.warning("DuckDB writer not available for state tracking, returning 0")
            return 0
        return self.duckdb_writer.get_last_processed_sequence(platform)

    def update_last_processed(self, platform: str, sequence: int, timestamp: Optional[datetime] = None) -> None:
        """
        Update last processed sequence for a platform in DuckDB.

        Args:
            platform: Platform name ('cursor' or 'claude_code')
            sequence: Last processed sequence number
            timestamp: Optional timestamp of last processed record
        """
        if not self.duckdb_writer:
            logger.warning("DuckDB writer not available for state tracking, cannot update state")
            return
        self.duckdb_writer.update_last_processed(platform, sequence, timestamp)

    def get_new_traces(self, platform: str, since_sequence: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get new traces from SQLite since last processed sequence.

        Args:
            platform: Platform name ('cursor' or 'claude_code')
            since_sequence: Sequence number to start from (exclusive)
            limit: Maximum number of traces to return

        Returns:
            List of trace dictionaries with decompressed event_data
        """
        # Map platform names to table names
        table_name_map = {
            'cursor': 'cursor_raw_traces',
            'claude_code': 'claude_raw_traces'
        }
        table_name = table_name_map.get(platform)
        if not table_name:
            raise ValueError(f"Unknown platform: {platform}")
        
        with self.client.get_connection() as conn:
            # Different columns for different platforms
            if platform == 'cursor':
                cursor = conn.execute(f"""
                    SELECT 
                        sequence,
                        event_id,
                        external_session_id,
                        event_type,
                        timestamp,
                        workspace_hash,
                        event_data
                    FROM {table_name}
                    WHERE sequence > ?
                    ORDER BY sequence ASC
                    LIMIT ?
                """, (since_sequence, limit))
            else:  # claude_code
                cursor = conn.execute(f"""
                    SELECT 
                        sequence,
                        event_id,
                        external_id,
                        event_type,
                        timestamp,
                        workspace_hash,
                        event_data
                    FROM {table_name}
                    WHERE sequence > ?
                    ORDER BY sequence ASC
                    LIMIT ?
                """, (since_sequence, limit))
            
            traces = []
            for row in cursor.fetchall():
                try:
                    # Decompress event_data (always last column)
                    compressed_data = row[-1]  # event_data BLOB
                    if compressed_data:
                        decompressed = zlib.decompress(compressed_data)
                        event_data = json.loads(decompressed.decode('utf-8'))
                    else:
                        event_data = {}
                    
                    if platform == 'cursor':
                        trace = {
                            'sequence': row[0],
                            'event_id': row[1],
                            'external_id': None,
                            'external_session_id': row[2],
                            'event_type': row[3],
                            'timestamp': row[4],
                            'workspace_hash': row[5],
                            'event_data': event_data,
                            'platform': platform
                        }
                    else:  # claude_code
                        trace = {
                            'sequence': row[0],
                            'event_id': row[1],
                            'external_id': row[2],
                            'external_session_id': None,
                            'event_type': row[3],
                            'timestamp': row[4],
                            'workspace_hash': row[5],
                            'event_data': event_data,
                            'platform': platform
                        }
                    traces.append(trace)
                except Exception as e:
                    logger.error(f"Error decompressing trace sequence {row[0]}: {e}")
                    continue
            
            return traces

    def get_conversations(self, since_timestamp: Optional[datetime] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get conversations from SQLite.

        Args:
            since_timestamp: Optional timestamp to filter conversations
            limit: Maximum number of conversations to return

        Returns:
            List of conversation dictionaries
        """
        with self.client.get_connection() as conn:
            query = """
                SELECT 
                    id,
                    session_id,
                    external_id,
                    platform,
                    workspace_hash,
                    workspace_name,
                    started_at,
                    ended_at,
                    context,
                    metadata,
                    interaction_count,
                    total_tokens,
                    total_changes
                FROM conversations
            """
            params = []
            
            if since_timestamp:
                query += " WHERE started_at >= ?"
                # Convert datetime to ISO format string to avoid Python 3.12 deprecation warning
                params.append(since_timestamp.isoformat() if isinstance(since_timestamp, datetime) else since_timestamp)
            
            query += " ORDER BY started_at ASC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            conversations = []
            for row in cursor.fetchall():
                try:
                    conv = {
                        'id': row[0],
                        'session_id': row[1],
                        'external_id': row[2],
                        'platform': row[3],
                        'workspace_hash': row[4],
                        'workspace_name': row[5],
                        'started_at': row[6],
                        'ended_at': row[7],
                        'context': json.loads(row[8]) if row[8] else {},
                        'metadata': json.loads(row[9]) if row[9] else {},
                        'interaction_count': row[10] or 0,
                        'total_tokens': row[11] or 0,
                        'total_changes': row[12] or 0,
                    }
                    conversations.append(conv)
                except Exception as e:
                    logger.error(f"Error parsing conversation {row[0]}: {e}")
                    continue
            
            return conversations

    def get_sessions(self, since_timestamp: Optional[datetime] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get Cursor sessions from SQLite.

        Args:
            since_timestamp: Optional timestamp to filter sessions
            limit: Maximum number of sessions to return

        Returns:
            List of session dictionaries (Cursor only)
        """
        with self.client.get_connection() as conn:
            query = """
                SELECT 
                    id,
                    external_session_id,
                    workspace_hash,
                    workspace_name,
                    workspace_path,
                    started_at,
                    ended_at,
                    metadata
                FROM cursor_sessions
            """
            params = []
            
            if since_timestamp:
                query += " WHERE started_at >= ?"
                # Convert datetime to ISO format string to avoid Python 3.12 deprecation warning
                params.append(since_timestamp.isoformat() if isinstance(since_timestamp, datetime) else since_timestamp)
            
            query += " ORDER BY started_at ASC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            sessions = []
            for row in cursor.fetchall():
                try:
                    session = {
                        'id': row[0],
                        'external_session_id': row[1],
                        'workspace_hash': row[2],
                        'workspace_name': row[3],
                        'workspace_path': row[4],
                        'started_at': row[5],
                        'ended_at': row[6],
                        'metadata': json.loads(row[7]) if row[7] else {},
                    }
                    sessions.append(session)
                except Exception as e:
                    logger.error(f"Error parsing session {row[0]}: {e}")
                    continue
            
            return sessions

