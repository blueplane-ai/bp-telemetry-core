# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
DuckDB Writer for Analytics Service.

Writes analytics data from SQLite traces to DuckDB for queryable analytics.

See also:
- Schema design: docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md
- Materialized views: docs/ANALYTICS_MATERIALIZED_VIEWS.md
- Query functions: src/analytics/queries/analytics_queries.py
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


class DuckDBWriter:
    """
    DuckDB writer for analytics data from SQLite traces.
    
    Processes raw traces from SQLite and writes structured analytics data to DuckDB.
    
    Schema:
    - workspaces: Workspace metadata and statistics
    - ai_generations: AI generation events
    - composer_sessions: Composer session data
    - file_history: File access history
    - raw_traces: Raw trace data with composite key (trace_sequence, platform)
    
    See also:
    - Schema documentation: docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md
    - Materialized views design: docs/ANALYTICS_MATERIALIZED_VIEWS.md
    """

    def __init__(self, database_path: Optional[Path] = None):
        """
        Initialize DuckDB writer.

        Args:
            database_path: Path to DuckDB database file
                          (default: ~/.blueplane/analytics.duckdb)
        """
        if not DUCKDB_AVAILABLE:
            raise RuntimeError(
                "DuckDB is not available. Install with: pip install duckdb>=0.9.0"
            )
        
        if database_path is None:
            database_path = Path.home() / ".blueplane" / "analytics.duckdb"
        
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
        """Create DuckDB schema for analytics data."""
        if self._connection is None:
            raise RuntimeError("Not connected to DuckDB")
        
        # Workspace metadata table
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_hash VARCHAR PRIMARY KEY,
                workspace_path VARCHAR NOT NULL,
                first_seen TIMESTAMP NOT NULL,
                last_seen TIMESTAMP NOT NULL,
                total_traces INTEGER DEFAULT 0
            )
        """)
        
        # AI generations table (extracted from Cursor traces)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS ai_generations (
                generation_id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                trace_sequence INTEGER NOT NULL,
                generation_time TIMESTAMP,
                generation_type VARCHAR,
                description TEXT,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash)
            )
        """)
        
        # Composer sessions table (extracted from Cursor traces)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS composer_sessions (
                composer_id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                trace_sequence INTEGER NOT NULL,
                created_at TIMESTAMP,
                unified_mode VARCHAR,
                force_mode VARCHAR,
                lines_added INTEGER,
                lines_removed INTEGER,
                is_archived BOOLEAN,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash)
            )
        """)
        
        # File history table (extracted from Cursor traces)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS file_history (
                id VARCHAR PRIMARY KEY,
                workspace_hash VARCHAR NOT NULL,
                trace_sequence INTEGER NOT NULL,
                file_path VARCHAR NOT NULL,
                accessed_at TIMESTAMP,
                FOREIGN KEY (workspace_hash) REFERENCES workspaces(workspace_hash)
            )
        """)
        
        # Analytics processing state table (tracks last processed sequence per platform)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS analytics_processing_state (
                platform VARCHAR PRIMARY KEY,
                last_processed_sequence INTEGER NOT NULL DEFAULT 0,
                last_processed_timestamp TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Raw traces table (for reference and debugging)
        # Use composite primary key (trace_sequence, platform) to allow same sequence across platforms
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS raw_traces (
                trace_sequence INTEGER NOT NULL,
                platform VARCHAR NOT NULL,
                event_id VARCHAR NOT NULL,
                workspace_hash VARCHAR NOT NULL,
                event_type VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                ingested_at TIMESTAMP,
                PRIMARY KEY (trace_sequence, platform)
            )
        """)
        
        logger.info("DuckDB schema created/verified")

    def write_traces(self, traces: List[Dict[str, Any]]) -> None:
        """
        Write traces from SQLite to DuckDB.

        Args:
            traces: List of trace dictionaries from SQLiteReader
        """
        if self._connection is None:
            self.connect()
        
        if not traces:
            return
        
        # Group traces by platform
        cursor_traces = [t for t in traces if t.get('platform') == 'cursor']
        claude_traces = [t for t in traces if t.get('platform') == 'claude_code']
        
        # Process Cursor traces
        if cursor_traces:
            self._process_cursor_traces(cursor_traces)
        
        # Process Claude Code traces (future: may add Claude-specific analytics)
        if claude_traces:
            self._process_claude_traces(claude_traces)
        
        logger.info(f"Processed {len(traces)} traces ({len(cursor_traces)} Cursor, {len(claude_traces)} Claude)")

    def _process_cursor_traces(self, traces: List[Dict[str, Any]]) -> None:
        """Process Cursor traces and extract analytics data."""
        workspaces_to_update = set()
        generations_to_insert = []
        composer_sessions_to_insert = []
        file_history_to_insert = []
        raw_traces_to_insert = []
        
        for trace in traces:
            workspace_hash = trace.get('workspace_hash')
            if not workspace_hash:
                continue
            
            workspaces_to_update.add(workspace_hash)
            event_data = trace.get('event_data', {})
            event_type = trace.get('event_type', '')
            sequence = trace.get('sequence')
            timestamp = trace.get('timestamp')
            
            # Parse timestamp if it's a string
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = datetime.now()
            
            # Extract workspace path from event_data if available
            workspace_path = event_data.get('workspace_path') or event_data.get('workspace_name') or ''
            
            # Update raw_traces table
            raw_traces_to_insert.append((
                sequence,
                'cursor',
                trace.get('event_id', ''),
                workspace_hash,
                event_type,
                timestamp,
                datetime.now()
            ))
            
            # Extract AI generations
            if event_type == 'generation' and 'generationUUID' in event_data:
                generation_id = event_data.get('generationUUID')
                generation_time = None
                if 'unixMs' in event_data:
                    try:
                        unix_ms = event_data['unixMs']
                        if isinstance(unix_ms, (int, float)):
                            generation_time = datetime.fromtimestamp(unix_ms / 1000.0)
                    except (ValueError, OSError, TypeError):
                        generation_time = timestamp
            
                generations_to_insert.append((
                    generation_id,
                    workspace_hash,
                    sequence,
                    generation_time or timestamp,
                    event_data.get('type', 'unknown'),
                    (event_data.get('textDescription', '') or '')[:10000] if event_data.get('textDescription') else None
                ))
            
            # Extract composer sessions
            # Handle both single composer and allComposers array
            if event_type == 'composer':
                # Check for allComposers array (from composer.composerData)
                all_composers = event_data.get('allComposers', [])
                if isinstance(all_composers, list) and all_composers:
                    # Process each composer in the array
                    for composer in all_composers:
                        if not isinstance(composer, dict):
                            continue
                        composer_id = composer.get('composerId')
                        if not composer_id:
                            continue
                        
                        created_at = None
                        if 'createdAt' in composer:
                            try:
                                created_at_ms = composer['createdAt']
                                if isinstance(created_at_ms, (int, float)):
                                    created_at = datetime.fromtimestamp(created_at_ms / 1000.0)
                            except (ValueError, OSError, TypeError):
                                created_at = timestamp
                        
                        composer_sessions_to_insert.append((
                            composer_id,
                            workspace_hash,
                            sequence,
                            created_at or timestamp,
                            composer.get('unifiedMode'),
                            composer.get('forceMode'),
                            composer.get('totalLinesAdded') or composer.get('linesAdded') or 0,
                            composer.get('totalLinesRemoved') or composer.get('linesRemoved') or 0,
                            bool(composer.get('isArchived', False))
                        ))
                elif 'composerId' in event_data:
                    # Single composer event
                    composer_id = event_data.get('composerId')
                    created_at = None
                    if 'createdAt' in event_data:
                        try:
                            created_at_ms = event_data['createdAt']
                            if isinstance(created_at_ms, (int, float)):
                                created_at = datetime.fromtimestamp(created_at_ms / 1000.0)
                        except (ValueError, OSError, TypeError):
                            created_at = timestamp
                    
                    composer_sessions_to_insert.append((
                        composer_id,
                        workspace_hash,
                        sequence,
                        created_at or timestamp,
                        event_data.get('unifiedMode'),
                        event_data.get('forceMode'),
                        event_data.get('totalLinesAdded') or event_data.get('linesAdded') or 0,
                        event_data.get('totalLinesRemoved') or event_data.get('linesRemoved') or 0,
                        bool(event_data.get('isArchived', False))
                    ))
            
            # Extract file history
            # Handle both direct entries and items wrapper
            if event_type == 'history':
                entries = event_data.get('entries') or event_data.get('items', [])
                if isinstance(entries, list):
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        
                        file_path = (
                            entry.get('uri') or 
                            entry.get('path') or 
                            entry.get('resource') or
                            entry.get('filePath')
                        )
                        if not file_path and isinstance(entry.get('uri'), dict):
                            uri_obj = entry.get('uri')
                            file_path = uri_obj.get('path') or uri_obj.get('fsPath')
                        
                        if file_path:
                            entry_id = f"{sequence}_{hash(str(file_path)) % 1000000}"
                            accessed_at = timestamp
                            if 'timestamp' in entry:
                                try:
                                    ts = entry['timestamp']
                                    if isinstance(ts, (int, float)):
                                        accessed_at = datetime.fromtimestamp(ts / 1000.0 if ts > 1e10 else ts)
                                    elif isinstance(ts, str):
                                        accessed_at = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                except (ValueError, OSError, TypeError):
                                    pass
                            
                            file_history_to_insert.append((
                                entry_id,
                                workspace_hash,
                                sequence,
                                str(file_path)[:1000],
                                accessed_at
                            ))
        
        # Batch insert all data
        try:
            # Update workspaces (count traces per workspace)
            workspace_trace_counts = {}
            for trace in traces:
                workspace_hash = trace.get('workspace_hash')
                if workspace_hash:
                    workspace_trace_counts[workspace_hash] = workspace_trace_counts.get(workspace_hash, 0) + 1
            
            for workspace_hash in workspaces_to_update:
                # Try to get workspace_path from traces
                workspace_path = ''
                for trace in traces:
                    if trace.get('workspace_hash') == workspace_hash:
                        event_data = trace.get('event_data', {})
                        workspace_path = event_data.get('workspace_path') or event_data.get('workspace_name') or ''
                        break
                
                if not workspace_path:
                    workspace_path = workspace_hash  # Fallback
                
                trace_count = workspace_trace_counts.get(workspace_hash, 1)
                now = datetime.now()
                self._connection.execute("""
                    INSERT INTO workspaces (workspace_hash, workspace_path, first_seen, last_seen, total_traces)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (workspace_hash) DO UPDATE SET
                        last_seen = ?,
                        total_traces = workspaces.total_traces + ?
                """, (workspace_hash, workspace_path, now, now, trace_count, now, trace_count))
            
            # Insert raw traces
            if raw_traces_to_insert:
                self._connection.executemany("""
                    INSERT OR IGNORE INTO raw_traces 
                    (trace_sequence, platform, event_id, workspace_hash, event_type, timestamp, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, raw_traces_to_insert)
            
            # Insert generations
            if generations_to_insert:
                self._connection.executemany("""
                    INSERT OR IGNORE INTO ai_generations 
                    (generation_id, workspace_hash, trace_sequence, generation_time, generation_type, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, generations_to_insert)
                logger.debug(f"Inserted {len(generations_to_insert)} AI generations")
            
            # Insert composer sessions
            if composer_sessions_to_insert:
                self._connection.executemany("""
                    INSERT OR IGNORE INTO composer_sessions 
                    (composer_id, workspace_hash, trace_sequence, created_at, unified_mode, force_mode, 
                     lines_added, lines_removed, is_archived)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, composer_sessions_to_insert)
                logger.debug(f"Inserted {len(composer_sessions_to_insert)} composer sessions")
            
            # Insert file history
            if file_history_to_insert:
                self._connection.executemany("""
                    INSERT OR IGNORE INTO file_history 
                    (id, workspace_hash, trace_sequence, file_path, accessed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, file_history_to_insert)
                logger.debug(f"Inserted {len(file_history_to_insert)} file history entries")
        
        except Exception as e:
            logger.error(f"Error writing traces to DuckDB: {e}", exc_info=True)
            raise

    def _process_claude_traces(self, traces: List[Dict[str, Any]]) -> None:
        """Process Claude Code traces (placeholder for future Claude-specific analytics)."""
        # For now, just track raw traces
        raw_traces_to_insert = []
        
        for trace in traces:
            workspace_hash = trace.get('workspace_hash') or ''
            sequence = trace.get('sequence')
            timestamp = trace.get('timestamp')
            
            raw_traces_to_insert.append((
                sequence,
                'claude_code',
                trace.get('event_id', ''),
                workspace_hash,
                trace.get('event_type', ''),
                timestamp,
                datetime.now()
            ))
        
        if raw_traces_to_insert:
            try:
                self._connection.executemany("""
                    INSERT OR IGNORE INTO raw_traces 
                    (trace_sequence, platform, event_id, workspace_hash, event_type, timestamp, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, raw_traces_to_insert)
                logger.debug(f"Inserted {len(raw_traces_to_insert)} Claude Code traces")
            except Exception as e:
                logger.error(f"Error writing Claude traces: {e}", exc_info=True)
                raise  # Re-raise to see errors in tests

    def write_conversations(self, conversations: List[Dict[str, Any]]) -> None:
        """
        Write conversations to DuckDB (future: may add conversation analytics).

        Args:
            conversations: List of conversation dictionaries from SQLiteReader
        """
        # Placeholder for future conversation analytics
        logger.debug(f"Received {len(conversations)} conversations (not yet processed)")

    def write_sessions(self, sessions: List[Dict[str, Any]]) -> None:
        """
        Write Cursor sessions to DuckDB (future: may add session analytics).

        Args:
            sessions: List of session dictionaries from SQLiteReader
        """
        # Placeholder for future session analytics
        logger.debug(f"Received {len(sessions)} sessions (not yet processed)")

    def sync_workspace_metadata(self, workspace_hash: str, workspace_path: str) -> None:
        """
        Sync workspace metadata to DuckDB.

        Args:
            workspace_hash: Hash of workspace path
            workspace_path: Path to workspace
        """
        if self._connection is None:
            self.connect()
        
        now = datetime.now()
        self._connection.execute("""
            INSERT INTO workspaces (workspace_hash, workspace_path, first_seen, last_seen, total_traces)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT (workspace_hash) DO UPDATE SET
                workspace_path = EXCLUDED.workspace_path,
                last_seen = ?
        """, (workspace_hash, workspace_path, now, now, now))

    def get_last_processed_sequence(self, platform: str) -> int:
        """
        Get last processed sequence number for a platform from DuckDB.
        
        Args:
            platform: Platform name ('cursor' or 'claude_code')
            
        Returns:
            Last processed sequence number (0 if none)
        """
        if self._connection is None:
            self.connect()
        
        result = self._connection.execute(
            "SELECT last_processed_sequence FROM analytics_processing_state WHERE platform = ?",
            (platform,)
        ).fetchone()
        
        if result:
            return result[0]
        return 0
    
    def update_last_processed(self, platform: str, sequence: int, timestamp: Optional[datetime] = None) -> None:
        """
        Update last processed sequence for a platform in DuckDB.
        
        Args:
            platform: Platform name ('cursor' or 'claude_code')
            sequence: Last processed sequence number
            timestamp: Optional timestamp of last processed record
        """
        if self._connection is None:
            self.connect()
        
        timestamp_str = timestamp.isoformat() if timestamp else None
        self._connection.execute("""
            INSERT INTO analytics_processing_state (platform, last_processed_sequence, last_processed_timestamp)
            VALUES (?, ?, ?)
            ON CONFLICT (platform) DO UPDATE SET
                last_processed_sequence = EXCLUDED.last_processed_sequence,
                last_processed_timestamp = EXCLUDED.last_processed_timestamp,
                updated_at = CURRENT_TIMESTAMP
        """, (platform, sequence, timestamp_str))
        
        logger.debug(f"Updated processing state for {platform}: sequence={sequence}")

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

