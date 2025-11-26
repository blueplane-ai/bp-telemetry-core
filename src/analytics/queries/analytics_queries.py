# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Analytics query functions for DuckDB.

Provides query functions for analyzing workspace activity and AI interactions.
"""

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


def query_workspace_activity(
    database_path: Path,
    workspace_hash: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Query workspace activity over time.
    
    Returns aggregated activity metrics per trace, including:
    - Trace timestamp
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
        List of activity records with trace_sequence, timestamp, and metrics
    """
    if not DUCKDB_AVAILABLE:
        raise RuntimeError("DuckDB is not available. Install with: pip install duckdb>=0.9.0")
    
    conn = duckdb.connect(str(database_path))
    
    try:
        query = """
            SELECT 
                t.trace_sequence,
                t.timestamp,
                COUNT(DISTINCT g.generation_id) as generation_count,
                COUNT(DISTINCT c.composer_id) as composer_session_count,
                COUNT(DISTINCT f.id) as file_count,
                COALESCE(SUM(c.lines_added), 0) as total_lines_added,
                COALESCE(SUM(c.lines_removed), 0) as total_lines_removed
            FROM raw_traces t
            LEFT JOIN ai_generations g ON t.trace_sequence = g.trace_sequence
            LEFT JOIN composer_sessions c ON t.trace_sequence = c.trace_sequence
            LEFT JOIN file_history f ON t.trace_sequence = f.trace_sequence
            WHERE t.workspace_hash = ?
        """
        
        params = [workspace_hash]
        
        if start_time:
            query += " AND t.timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND t.timestamp <= ?"
            params.append(end_time)
        
        query += " GROUP BY t.trace_sequence, t.timestamp ORDER BY t.timestamp DESC"
        
        result = conn.execute(query, params).fetchall()
        
        # Convert to list of dicts
        columns = ['trace_sequence', 'timestamp', 'generation_count', 
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
        generation_type, description, and trace_sequence
    """
    if not DUCKDB_AVAILABLE:
        raise RuntimeError("DuckDB is not available. Install with: pip install duckdb>=0.9.0")
    
    conn = duckdb.connect(str(database_path))
    
    try:
        query = """
            SELECT 
                generation_id,
                workspace_hash,
                trace_sequence,
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
        columns = ['generation_id', 'workspace_hash', 'trace_sequence', 
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
                trace_sequence,
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
        columns = ['composer_id', 'workspace_hash', 'trace_sequence', 'created_at',
                  'unified_mode', 'force_mode', 'lines_added', 'lines_removed', 'is_archived']
        return [dict(zip(columns, row)) for row in result]
    
    finally:
        conn.close()

