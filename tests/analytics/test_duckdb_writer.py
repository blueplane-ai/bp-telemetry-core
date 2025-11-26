# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Unit tests for DuckDBWriter."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from datetime import datetime, timezone

from src.analytics.workers.duckdb_writer import DuckDBWriter, DUCKDB_AVAILABLE
from tests.fixtures.duckdb_fixtures import temp_duckdb, verify_duckdb_schema
from tests.fixtures.sqlite_fixtures import sqlite_db_with_cursor_traces


@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not available")
class TestDuckDBWriter:
    """Test DuckDBWriter class."""
    
    def test_init_creates_database(self, temp_duckdb):
        """Test that initialization creates database file."""
        db_path, conn = temp_duckdb
        
        writer = DuckDBWriter(Path(db_path))
        assert Path(db_path).exists()
    
    def test_connect_creates_schema(self, temp_duckdb):
        """Test that connect() creates schema."""
        db_path, conn = temp_duckdb
        
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        
        # Verify schema exists
        assert verify_duckdb_schema(writer._connection)
    
    def test_write_traces_empty_list(self, temp_duckdb):
        """Test writing empty trace list."""
        db_path, _ = temp_duckdb
        
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        
        # Should not raise error
        writer.write_traces([])
    
    def test_write_traces_cursor_generations(self, temp_duckdb, sqlite_db_with_cursor_traces):
        """Test writing Cursor traces with AI generations."""
        db_path, _ = temp_duckdb
        sqlite_path, _ = sqlite_db_with_cursor_traces
        
        # Read traces from SQLite
        from src.analytics.workers.sqlite_reader import SQLiteReader
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("cursor", since_sequence=0)
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify generations were inserted
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM ai_generations
        """).fetchone()
        assert result[0] == 1
        
        # Verify generation data
        gen = writer._connection.execute("""
            SELECT generation_id, workspace_hash, generation_type, description
            FROM ai_generations
        """).fetchone()
        assert gen[0] == 'gen_001'
        assert gen[2] == 'cmdk'
    
    def test_write_traces_cursor_composer_sessions(self, temp_duckdb, sqlite_db_with_cursor_traces):
        """Test writing Cursor traces with composer sessions."""
        db_path, _ = temp_duckdb
        sqlite_path, _ = sqlite_db_with_cursor_traces
        
        # Read traces from SQLite
        from src.analytics.workers.sqlite_reader import SQLiteReader
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("cursor", since_sequence=0)
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify composer sessions were inserted
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM composer_sessions
        """).fetchone()
        assert result[0] == 1
        
        # Verify composer session data
        session = writer._connection.execute("""
            SELECT composer_id, workspace_hash, lines_added, lines_removed
            FROM composer_sessions
        """).fetchone()
        assert session[0] == 'composer_001'
        assert session[2] == 50
        assert session[3] == 10
    
    def test_write_traces_cursor_file_history(self, temp_duckdb, sqlite_db_with_cursor_traces):
        """Test writing Cursor traces with file history."""
        db_path, _ = temp_duckdb
        sqlite_path, _ = sqlite_db_with_cursor_traces
        
        # Read traces from SQLite
        from src.analytics.workers.sqlite_reader import SQLiteReader
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("cursor", since_sequence=0)
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify file history was inserted
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM file_history
        """).fetchone()
        assert result[0] == 2  # Two file entries
    
    def test_write_traces_updates_workspaces(self, temp_duckdb, sqlite_db_with_cursor_traces):
        """Test that writing traces updates workspace metadata."""
        db_path, _ = temp_duckdb
        sqlite_path, _ = sqlite_db_with_cursor_traces
        
        # Read traces from SQLite
        from src.analytics.workers.sqlite_reader import SQLiteReader
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("cursor", since_sequence=0)
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify workspace was created
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM workspaces
        """).fetchone()
        assert result[0] == 1
        
        # Verify workspace data
        workspace = writer._connection.execute("""
            SELECT workspace_hash, total_traces FROM workspaces
        """).fetchone()
        assert workspace[0] == 'test_workspace_hash'
        assert workspace[1] == 3
    
    def test_write_traces_claude_code(self, temp_duckdb, sqlite_db_with_claude_traces):
        """Test writing Claude Code traces."""
        db_path, _ = temp_duckdb
        sqlite_path, _ = sqlite_db_with_claude_traces
        
        # Read traces from SQLite
        from src.analytics.workers.sqlite_reader import SQLiteReader
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("claude_code", since_sequence=0)
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify raw traces were inserted
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'claude_code'
        """).fetchone()
        assert result[0] == 2
    
    def test_sync_workspace_metadata(self, temp_duckdb):
        """Test syncing workspace metadata."""
        db_path, _ = temp_duckdb
        
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        
        # Sync workspace metadata
        writer.sync_workspace_metadata("test_hash", "/test/path")
        
        # Verify workspace was created
        result = writer._connection.execute("""
            SELECT workspace_hash, workspace_path FROM workspaces
        """).fetchone()
        assert result[0] == 'test_hash'
        assert result[1] == '/test/path'
        
        # Update existing workspace
        writer.sync_workspace_metadata("test_hash", "/test/path/updated")
        
        result = writer._connection.execute("""
            SELECT workspace_path FROM workspaces WHERE workspace_hash = 'test_hash'
        """).fetchone()
        assert result[0] == '/test/path/updated'
    
    def test_write_traces_handles_malformed_data(self, temp_duckdb):
        """Test that malformed trace data is handled gracefully."""
        db_path, _ = temp_duckdb
        
        writer = DuckDBWriter(Path(db_path))
        writer.connect()
        
        # Create trace with malformed event_data
        malformed_trace = {
            'sequence': 1,
            'event_id': 'test_001',
            'event_type': 'test',
            'timestamp': datetime.now(timezone.utc),
            'workspace_hash': 'test_hash',
            'platform': 'cursor',
            'event_data': {'invalid': 'data'}  # Missing expected fields
        }
        
        # Should not raise error
        writer.write_traces([malformed_trace])
        
        # Verify raw trace was still inserted
        result = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces
        """).fetchone()
        assert result[0] == 1

