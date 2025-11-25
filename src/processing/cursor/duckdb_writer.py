# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
DuckDB Sink for Cursor Workspace History.

STUB IMPLEMENTATION - Scaffolded for M4, not yet fully functional.

This module provides a DuckDB sink for storing workspace history data
in a queryable analytics database. Currently behind a feature flag.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Flag to check if DuckDB is available
try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    logger.warning("DuckDB not available - install with: pip install duckdb>=0.9.0")


class CursorDuckDBWriter:
    """
    DuckDB writer for Cursor workspace history.
    
    STUB IMPLEMENTATION - Feature is scaffolded but not fully implemented.
    
    This class will write workspace history data to DuckDB for analytics.
    When fully implemented, it will:
    - Store workspace metadata
    - Store AI generations with full context
    - Store composer sessions
    - Store file history
    - Enable SQL analytics on workspace activity
    """

    def __init__(self, database_path: Optional[Path] = None):
        """
        Initialize DuckDB writer.

        Args:
            database_path: Path to DuckDB database file
                          (default: ~/.blueplane/cursor_history.duckdb)
        """
        if not DUCKDB_AVAILABLE:
            raise RuntimeError(
                "DuckDB is not available. Install with: pip install duckdb>=0.9.0"
            )
        
        if database_path is None:
            database_path = Path.home() / ".blueplane" / "cursor_history.duckdb"
        
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._connection: Optional[duckdb.DuckDBPyConnection] = None
        
        logger.info(f"DuckDB writer initialized (database: {self.database_path})")

    def connect(self) -> None:
        """Connect to DuckDB database and initialize schema."""
        if self._connection is not None:
            return
        
        logger.info(f"Connecting to DuckDB: {self.database_path}")
        self._connection = duckdb.connect(str(self.database_path))
        
        # Initialize schema
        self._create_schema()
        
        logger.info("DuckDB connection established and schema initialized")

    def _create_schema(self) -> None:
        """
        Create DuckDB schema for workspace history.
        
        STUB IMPLEMENTATION - Schema is scaffolded but may need refinement.
        """
        if self._connection is None:
            raise RuntimeError("Not connected to DuckDB")
        
        # Workspace metadata table
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_hash VARCHAR PRIMARY KEY,
                workspace_path VARCHAR NOT NULL,
                first_seen TIMESTAMP NOT NULL,
                last_seen TIMESTAMP NOT NULL,
                total_snapshots INTEGER DEFAULT 0
            )
        """)
        
        # Workspace snapshots table (one per markdown write)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS workspace_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,
                data_hash VARCHAR NOT NULL,
                markdown_path VARCHAR,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash)
            )
        """)
        
        # AI generations table (extracted from snapshots)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS ai_generations (
                generation_id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                snapshot_id VARCHAR NOT NULL,
                generation_time TIMESTAMP,
                generation_type VARCHAR,
                description TEXT,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash),
                FOREIGN KEY (snapshot_id) REFERENCES workspace_snapshots(snapshot_id)
            )
        """)
        
        # Composer sessions table
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS composer_sessions (
                composer_id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                snapshot_id VARCHAR NOT NULL,
                created_at TIMESTAMP,
                unified_mode VARCHAR,
                force_mode VARCHAR,
                lines_added INTEGER,
                lines_removed INTEGER,
                is_archived BOOLEAN,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash),
                FOREIGN KEY (snapshot_id) REFERENCES workspace_snapshots(snapshot_id)
            )
        """)
        
        # File history table
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS file_history (
                id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                snapshot_id VARCHAR NOT NULL,
                file_path VARCHAR NOT NULL,
                accessed_at TIMESTAMP,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash),
                FOREIGN KEY (snapshot_id) REFERENCES workspace_snapshots(snapshot_id)
            )
        """)
        
        logger.info("DuckDB schema created/verified")

    def write_workspace_history(
        self,
        workspace_hash: str,
        workspace_path: str,
        data: Dict[str, Any],
        data_hash: str,
        timestamp: datetime,
        markdown_path: Optional[Path] = None
    ) -> str:
        """
        Write workspace history to DuckDB.
        
        STUB IMPLEMENTATION - Basic structure only.
        
        Args:
            workspace_hash: Hash of workspace path
            workspace_path: Path to workspace
            data: Dictionary of ItemTable data
            data_hash: Hash of data
            timestamp: Snapshot timestamp
            markdown_path: Path to markdown file (if written)

        Returns:
            Snapshot ID
        """
        if self._connection is None:
            self.connect()
        
        snapshot_id = f"{workspace_hash}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # Update workspace metadata
        self._connection.execute("""
            INSERT INTO workspaces (workspace_hash, workspace_path, first_seen, last_seen, total_snapshots)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT (workspace_hash) DO UPDATE SET
                last_seen = EXCLUDED.last_seen,
                total_snapshots = workspaces.total_snapshots + 1
        """, [workspace_hash, workspace_path, timestamp, timestamp])
        
        # Insert snapshot
        self._connection.execute("""
            INSERT INTO workspace_snapshots (snapshot_id, workspace_hash, snapshot_time, data_hash, markdown_path)
            VALUES (?, ?, ?, ?, ?)
        """, [
            snapshot_id,
            workspace_hash,
            timestamp,
            data_hash,
            str(markdown_path) if markdown_path else None
        ])
        
        # Extract and insert generations, composer sessions, file history
        try:
            self._extract_and_insert_generations(
                workspace_hash, snapshot_id, data, timestamp
            )
            self._extract_and_insert_composer_sessions(
                workspace_hash, snapshot_id, data, timestamp
            )
            self._extract_and_insert_file_history(
                workspace_hash, snapshot_id, data, timestamp
            )
        except Exception as e:
            logger.error(f"Error extracting analytics data for snapshot {snapshot_id}: {e}", exc_info=True)
            # Continue - snapshot is already written, analytics extraction failure shouldn't fail the whole operation
        
        logger.info(f"Wrote workspace snapshot {snapshot_id} to DuckDB")
        
        return snapshot_id
    
    def _extract_and_insert_generations(
        self,
        workspace_hash: str,
        snapshot_id: str,
        data: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Extract and insert AI generations from data dictionary."""
        if 'aiService.generations' not in data:
            return
        
        generations_data = data['aiService.generations']
        if not generations_data:
            return
        
        # Parse JSON if needed
        if isinstance(generations_data, bytes):
            generations = json.loads(generations_data.decode('utf-8'))
        elif isinstance(generations_data, str):
            generations = json.loads(generations_data)
        else:
            generations = generations_data
        
        if not isinstance(generations, list):
            logger.warning(f"Expected list for aiService.generations, got {type(generations)}")
            return
        
        generations_to_insert = []
        for gen in generations:
            if not isinstance(gen, dict):
                continue
            
            generation_id = gen.get('generationUUID')
            if not generation_id:
                continue
            
            # Parse timestamp (unixMs is milliseconds since epoch)
            unix_ms = gen.get('unixMs', 0)
            generation_time = None
            if unix_ms:
                try:
                    generation_time = datetime.fromtimestamp(unix_ms / 1000.0)
                except (ValueError, OSError):
                    generation_time = timestamp  # Fallback to snapshot time
            
            generation_type = gen.get('type', 'unknown')
            description = gen.get('textDescription', '')
            
            generations_to_insert.append((
                generation_id,
                workspace_hash,
                snapshot_id,
                generation_time or timestamp,
                generation_type,
                description[:10000] if description else None  # Limit description length
            ))
        
        if generations_to_insert:
            self._connection.executemany("""
                INSERT OR IGNORE INTO ai_generations 
                (generation_id, workspace_hash, snapshot_id, generation_time, generation_type, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, generations_to_insert)
            logger.debug(f"Inserted {len(generations_to_insert)} AI generations for snapshot {snapshot_id}")
    
    def _extract_and_insert_composer_sessions(
        self,
        workspace_hash: str,
        snapshot_id: str,
        data: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Extract and insert composer sessions from data dictionary."""
        if 'composer.composerData' not in data:
            return
        
        composer_data = data['composer.composerData']
        if not composer_data:
            return
        
        # Parse JSON if needed
        if isinstance(composer_data, bytes):
            composer_obj = json.loads(composer_data.decode('utf-8'))
        elif isinstance(composer_data, str):
            composer_obj = json.loads(composer_data)
        else:
            composer_obj = composer_data
        
        if not isinstance(composer_obj, dict):
            logger.warning(f"Expected dict for composer.composerData, got {type(composer_obj)}")
            return
        
        # Extract allComposers array
        all_composers = composer_obj.get('allComposers', [])
        if not isinstance(all_composers, list):
            return
        
        sessions_to_insert = []
        for composer in all_composers:
            if not isinstance(composer, dict):
                continue
            
            composer_id = composer.get('composerId')
            if not composer_id:
                continue
            
            # Parse created_at timestamp
            created_at_ms = composer.get('createdAt', 0)
            created_at = None
            if created_at_ms:
                try:
                    created_at = datetime.fromtimestamp(created_at_ms / 1000.0)
                except (ValueError, OSError):
                    created_at = timestamp  # Fallback to snapshot time
            
            unified_mode = composer.get('unifiedMode')
            force_mode = composer.get('forceMode')
            lines_added = composer.get('totalLinesAdded') or composer.get('linesAdded') or 0
            lines_removed = composer.get('totalLinesRemoved') or composer.get('linesRemoved') or 0
            is_archived = composer.get('isArchived', False)
            
            sessions_to_insert.append((
                composer_id,
                workspace_hash,
                snapshot_id,
                created_at or timestamp,
                unified_mode,
                force_mode,
                lines_added,
                lines_removed,
                bool(is_archived)
            ))
        
        if sessions_to_insert:
            self._connection.executemany("""
                INSERT OR IGNORE INTO composer_sessions 
                (composer_id, workspace_hash, snapshot_id, created_at, unified_mode, force_mode, 
                 lines_added, lines_removed, is_archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sessions_to_insert)
            logger.debug(f"Inserted {len(sessions_to_insert)} composer sessions for snapshot {snapshot_id}")
    
    def _extract_and_insert_file_history(
        self,
        workspace_hash: str,
        snapshot_id: str,
        data: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Extract and insert file history from data dictionary."""
        if 'history.entries' not in data:
            return
        
        history_data = data['history.entries']
        if not history_data:
            return
        
        # Parse JSON if needed
        if isinstance(history_data, bytes):
            entries = json.loads(history_data.decode('utf-8'))
        elif isinstance(history_data, str):
            entries = json.loads(history_data)
        else:
            entries = history_data
        
        if not isinstance(entries, list):
            logger.warning(f"Expected list for history.entries, got {type(entries)}")
            return
        
        files_to_insert = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            # Extract file path - could be in different fields
            file_path = (
                entry.get('uri') or 
                entry.get('path') or 
                entry.get('resource') or
                entry.get('filePath')
            )
            
            if not file_path:
                # Try to extract from URI object if it's nested
                uri_obj = entry.get('uri')
                if isinstance(uri_obj, dict):
                    file_path = uri_obj.get('path') or uri_obj.get('fsPath') or uri_obj.get('scheme')
            
            if not file_path:
                continue
            
            # Generate ID from file path and snapshot
            entry_id = f"{snapshot_id}_{hash(file_path) % 1000000}"
            
            # Parse accessed_at timestamp if available
            accessed_at = None
            if 'timestamp' in entry:
                try:
                    ts = entry['timestamp']
                    if isinstance(ts, (int, float)):
                        # Could be milliseconds or seconds
                        accessed_at = datetime.fromtimestamp(ts / 1000.0 if ts > 1e10 else ts)
                    elif isinstance(ts, str):
                        accessed_at = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except (ValueError, OSError, TypeError):
                    accessed_at = timestamp  # Fallback to snapshot time
            
            files_to_insert.append((
                entry_id,
                workspace_hash,
                snapshot_id,
                str(file_path)[:1000],  # Limit path length
                accessed_at or timestamp
            ))
        
        if files_to_insert:
            self._connection.executemany("""
                INSERT OR IGNORE INTO file_history 
                (id, workspace_hash, snapshot_id, file_path, accessed_at)
                VALUES (?, ?, ?, ?, ?)
            """, files_to_insert)
            logger.debug(f"Inserted {len(files_to_insert)} file history entries for snapshot {snapshot_id}")

    def close(self) -> None:
        """Close DuckDB connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("DuckDB connection closed")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# Analytics query functions

def query_workspace_activity(
    database_path: Path,
    workspace_hash: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Query workspace activity over time.
    
    Returns aggregated activity metrics per snapshot, including:
    - Snapshot timestamp
    - Number of AI generations
    - Number of composer sessions
    - Number of files accessed
    - Total lines added/removed
    
    Args:
        database_path: Path to DuckDB database
        workspace_hash: Workspace to query
        start_time: Start of time range (optional)
        end_time: End of time range (optional)

    Returns:
        List of activity records with snapshot_id, snapshot_time, and metrics
    """
    if not DUCKDB_AVAILABLE:
        raise RuntimeError("DuckDB is not available. Install with: pip install duckdb>=0.9.0")
    
    conn = duckdb.connect(str(database_path))
    
    try:
        query = """
            SELECT 
                s.snapshot_id,
                s.snapshot_time,
                COUNT(DISTINCT g.generation_id) as generation_count,
                COUNT(DISTINCT c.composer_id) as composer_session_count,
                COUNT(DISTINCT f.id) as file_count,
                COALESCE(SUM(c.lines_added), 0) as total_lines_added,
                COALESCE(SUM(c.lines_removed), 0) as total_lines_removed
            FROM workspace_snapshots s
            LEFT JOIN ai_generations g ON s.snapshot_id = g.snapshot_id
            LEFT JOIN composer_sessions c ON s.snapshot_id = c.snapshot_id
            LEFT JOIN file_history f ON s.snapshot_id = f.snapshot_id
            WHERE s.workspace_hash = ?
        """
        
        params = [workspace_hash]
        
        if start_time:
            query += " AND s.snapshot_time >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND s.snapshot_time <= ?"
            params.append(end_time)
        
        query += " GROUP BY s.snapshot_id, s.snapshot_time ORDER BY s.snapshot_time DESC"
        
        result = conn.execute(query, params).fetchall()
        
        # Convert to list of dicts
        columns = ['snapshot_id', 'snapshot_time', 'generation_count', 
                  'composer_session_count', 'file_count', 'total_lines_added', 'total_lines_removed']
        return [dict(zip(columns, row)) for row in result]
    
    finally:
        conn.close()


def query_ai_generations(
    database_path: Path,
    workspace_hash: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Query AI generations.
    
    Returns AI generation records with metadata.
    
    Args:
        database_path: Path to DuckDB database
        workspace_hash: Optional workspace filter
        limit: Maximum number of results

    Returns:
        List of generation records with generation_id, workspace_hash, generation_time, 
        generation_type, description, and snapshot_id
    """
    if not DUCKDB_AVAILABLE:
        raise RuntimeError("DuckDB is not available. Install with: pip install duckdb>=0.9.0")
    
    conn = duckdb.connect(str(database_path))
    
    try:
        query = """
            SELECT 
                generation_id,
                workspace_hash,
                snapshot_id,
                generation_time,
                generation_type,
                description
            FROM ai_generations
        """
        
        params = []
        if workspace_hash:
            query += " WHERE workspace_hash = ?"
            params.append(workspace_hash)
        
        query += " ORDER BY generation_time DESC LIMIT ?"
        params.append(limit)
        
        result = conn.execute(query, params).fetchall()
        
        # Convert to list of dicts
        columns = ['generation_id', 'workspace_hash', 'snapshot_id', 
                  'generation_time', 'generation_type', 'description']
        return [dict(zip(columns, row)) for row in result]
    
    finally:
        conn.close()


def query_composer_sessions(
    database_path: Path,
    workspace_hash: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Query composer sessions.
    
    Returns composer session records with activity metrics.
    
    Args:
        database_path: Path to DuckDB database
        workspace_hash: Optional workspace filter
        limit: Maximum number of results

    Returns:
        List of composer session records
    """
    if not DUCKDB_AVAILABLE:
        raise RuntimeError("DuckDB is not available. Install with: pip install duckdb>=0.9.0")
    
    conn = duckdb.connect(str(database_path))
    
    try:
        query = """
            SELECT 
                composer_id,
                workspace_hash,
                snapshot_id,
                created_at,
                unified_mode,
                force_mode,
                lines_added,
                lines_removed,
                is_archived
            FROM composer_sessions
        """
        
        params = []
        if workspace_hash:
            query += " WHERE workspace_hash = ?"
            params.append(workspace_hash)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        result = conn.execute(query, params).fetchall()
        
        # Convert to list of dicts
        columns = ['composer_id', 'workspace_hash', 'snapshot_id', 'created_at',
                  'unified_mode', 'force_mode', 'lines_added', 'lines_removed', 'is_archived']
        return [dict(zip(columns, row)) for row in result]
    
    finally:
        conn.close()
