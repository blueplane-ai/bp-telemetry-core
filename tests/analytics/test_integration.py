# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Integration tests for analytics service."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import asyncio

from src.analytics.workers.sqlite_reader import SQLiteReader
from src.analytics.workers.duckdb_writer import DuckDBWriter, DUCKDB_AVAILABLE
from tests.fixtures.sqlite_fixtures import (
    temp_sqlite_db,
    sqlite_db_with_cursor_traces,
    sqlite_db_with_claude_traces
)
from tests.fixtures.duckdb_fixtures import temp_duckdb


@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not available")
class TestAnalyticsIntegration:
    """Integration tests for SQLite → DuckDB pipeline."""
    
    def test_full_pipeline_cursor(self, sqlite_db_with_cursor_traces, temp_duckdb):
        """Test full pipeline: SQLite Cursor traces → DuckDB."""
        sqlite_path, _ = sqlite_db_with_cursor_traces
        duckdb_path, _ = temp_duckdb
        
        # Read from SQLite
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("cursor", since_sequence=0)
        assert len(traces) == 3
        
        # Write to DuckDB
        writer = DuckDBWriter(Path(duckdb_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify data in DuckDB
        # Check raw traces
        raw_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'cursor'
        """).fetchone()[0]
        assert raw_count == 3
        
        # Check generations
        gen_count = writer._connection.execute("""
            SELECT COUNT(*) FROM ai_generations
        """).fetchone()[0]
        assert gen_count == 1
        
        # Check composer sessions
        composer_count = writer._connection.execute("""
            SELECT COUNT(*) FROM composer_sessions
        """).fetchone()[0]
        assert composer_count == 1
        
        # Check file history
        file_count = writer._connection.execute("""
            SELECT COUNT(*) FROM file_history
        """).fetchone()[0]
        assert file_count == 2
    
    def test_incremental_processing(self, sqlite_db_with_cursor_traces, temp_duckdb):
        """Test incremental processing (only new traces)."""
        sqlite_path, _ = sqlite_db_with_cursor_traces
        duckdb_path, _ = temp_duckdb
        
        reader = SQLiteReader(Path(sqlite_path))
        writer = DuckDBWriter(Path(duckdb_path))
        writer.connect()
        
        # Process first batch
        traces = reader.get_new_traces("cursor", since_sequence=0, limit=2)
        writer.write_traces(traces)
        reader.update_last_processed("cursor", traces[-1]['sequence'])
        
        # Verify first batch
        raw_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'cursor'
        """).fetchone()[0]
        assert raw_count == 2
        
        # Process remaining traces
        last_seq = reader.get_last_processed_sequence("cursor")
        traces = reader.get_new_traces("cursor", since_sequence=last_seq)
        writer.write_traces(traces)
        
        # Verify all traces processed
        raw_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'cursor'
        """).fetchone()[0]
        assert raw_count == 3
    
    def test_state_persistence(self, sqlite_db_with_cursor_traces, temp_duckdb):
        """Test that processing state persists across reader instances."""
        sqlite_path, _ = sqlite_db_with_cursor_traces
        duckdb_path, _ = temp_duckdb
        
        # First reader instance
        reader1 = SQLiteReader(Path(sqlite_path))
        traces = reader1.get_new_traces("cursor", since_sequence=0, limit=2)
        reader1.update_last_processed("cursor", traces[-1]['sequence'])
        
        # Second reader instance (simulates restart)
        reader2 = SQLiteReader(Path(sqlite_path))
        last_seq = reader2.get_last_processed_sequence("cursor")
        assert last_seq == traces[-1]['sequence']
        
        # Should only get remaining traces
        remaining = reader2.get_new_traces("cursor", since_sequence=last_seq)
        assert len(remaining) == 1
    
    def test_mixed_platforms(self, temp_sqlite_db, temp_duckdb):
        """Test processing traces from both platforms."""
        sqlite_path, client = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        # Insert both Cursor and Claude Code traces
        from tests.fixtures.sqlite_fixtures import (
            create_cursor_trace_event,
            create_claude_trace_event
        )
        
        cursor_trace = create_cursor_trace_event(
            sequence=1,
            event_type="generation",
            event_data={"generationUUID": "gen_001"}
        )
        client.execute("""
            INSERT INTO cursor_raw_traces (
                event_id, external_session_id, event_type, timestamp,
                storage_level, workspace_hash, database_table, item_key,
                event_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cursor_trace[0], cursor_trace[1], cursor_trace[2], cursor_trace[3],
            cursor_trace[4], cursor_trace[5], cursor_trace[6], cursor_trace[7],
            cursor_trace[-1]
        ))
        
        claude_trace = create_claude_trace_event(
            sequence=1,
            event_type="user_message",
            event_data={"role": "user"}
        )
        # Insert using full tuple (matching schema)
        client.execute("""
            INSERT INTO claude_raw_traces (
                event_id, external_id, event_type, timestamp, workspace_hash,
                uuid, parent_uuid, request_id, agent_id,
                project_name, is_sidechain, user_type, cwd, version, git_branch,
                message_role, message_model, message_id, message_type,
                stop_reason, stop_sequence,
                input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
                output_tokens, service_tier, cache_5m_tokens, cache_1h_tokens,
                operation, subtype, level, is_meta,
                summary, leaf_uuid,
                duration_ms, tokens_used, tool_calls_count,
                event_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, claude_trace)
        
        # Process both platforms
        reader = SQLiteReader(Path(sqlite_path))
        writer = DuckDBWriter(Path(duckdb_path))
        writer.connect()
        
        cursor_traces = reader.get_new_traces("cursor", since_sequence=0)
        claude_traces = reader.get_new_traces("claude_code", since_sequence=0)
        
        # Verify traces were read
        assert len(cursor_traces) == 1, f"Expected 1 Cursor trace, got {len(cursor_traces)}"
        assert len(claude_traces) == 1, f"Expected 1 Claude trace, got {len(claude_traces)}"
        assert claude_traces[0].get('platform') == 'claude_code', f"Platform mismatch: {claude_traces[0].get('platform')}"
        
        # Write traces
        all_traces = cursor_traces + claude_traces
        writer.write_traces(all_traces)
        
        # Verify both platforms processed
        cursor_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'cursor'
        """).fetchone()[0]
        claude_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'claude_code'
        """).fetchone()[0]
        
        assert cursor_count == 1, f"Expected 1 Cursor trace in DuckDB, got {cursor_count}"
        assert claude_count == 1, f"Expected 1 Claude trace in DuckDB, got {claude_count}. All traces: {[t.get('platform') for t in all_traces]}"

