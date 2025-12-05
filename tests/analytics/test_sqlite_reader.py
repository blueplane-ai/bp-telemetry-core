# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Unit tests for SQLiteReader."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from datetime import datetime, timezone

from src.analytics.workers.sqlite_reader import SQLiteReader
from tests.fixtures.sqlite_fixtures import (
    temp_sqlite_db,
    sqlite_db_with_cursor_traces,
    sqlite_db_with_claude_traces,
    sqlite_db_with_conversations,
    sqlite_db_with_sessions
)


class TestSQLiteReader:
    """Test SQLiteReader class."""
    
    def test_init_creates_processing_state_table(self, temp_sqlite_db):
        """Test that initialization creates analytics_processing_state table."""
        db_path, client = temp_sqlite_db
        
        reader = SQLiteReader(Path(db_path))
        
        # Verify table exists
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='analytics_processing_state'
            """)
            assert cursor.fetchone() is not None
    
    def test_get_last_processed_sequence_new_platform(self, temp_sqlite_db):
        """Test getting last processed sequence for new platform returns 0."""
        db_path, _ = temp_sqlite_db
        reader = SQLiteReader(Path(db_path))
        
        sequence = reader.get_last_processed_sequence("cursor")
        assert sequence == 0
    
    def test_update_and_get_last_processed_sequence(self, temp_sqlite_db):
        """Test updating and getting last processed sequence."""
        db_path, _ = temp_sqlite_db
        reader = SQLiteReader(Path(db_path))
        
        # Update sequence
        timestamp = datetime.now(timezone.utc)
        reader.update_last_processed("cursor", 100, timestamp)
        
        # Get sequence
        sequence = reader.get_last_processed_sequence("cursor")
        assert sequence == 100
    
    def test_get_new_traces_empty(self, temp_sqlite_db):
        """Test getting new traces when none exist."""
        db_path, _ = temp_sqlite_db
        reader = SQLiteReader(Path(db_path))
        
        traces = reader.get_new_traces("cursor", since_sequence=0)
        assert traces == []
    
    def test_get_new_traces_cursor(self, sqlite_db_with_cursor_traces):
        """Test getting Cursor traces."""
        db_path, _ = sqlite_db_with_cursor_traces
        reader = SQLiteReader(Path(db_path))
        
        # Get all traces
        traces = reader.get_new_traces("cursor", since_sequence=0)
        assert len(traces) == 3
        
        # Verify first trace
        trace = traces[0]
        assert trace['sequence'] == 1
        assert trace['event_type'] == 'generation'
        assert trace['platform'] == 'cursor'
        assert 'event_data' in trace
        assert trace['event_data']['generationUUID'] == 'gen_001'
    
    def test_get_new_traces_incremental(self, sqlite_db_with_cursor_traces):
        """Test incremental reading of traces."""
        db_path, _ = sqlite_db_with_cursor_traces
        reader = SQLiteReader(Path(db_path))
        
        # Get traces after sequence 1
        traces = reader.get_new_traces("cursor", since_sequence=1)
        assert len(traces) == 2
        assert traces[0]['sequence'] == 2
        assert traces[1]['sequence'] == 3
    
    def test_get_new_traces_respects_limit(self, sqlite_db_with_cursor_traces):
        """Test that limit parameter is respected."""
        db_path, _ = sqlite_db_with_cursor_traces
        reader = SQLiteReader(Path(db_path))
        
        traces = reader.get_new_traces("cursor", since_sequence=0, limit=2)
        assert len(traces) == 2
    
    def test_get_new_traces_claude(self, sqlite_db_with_claude_traces):
        """Test getting Claude Code traces."""
        db_path, _ = sqlite_db_with_claude_traces
        reader = SQLiteReader(Path(db_path))
        
        traces = reader.get_new_traces("claude_code", since_sequence=0)
        assert len(traces) == 2
        
        # Verify trace structure
        trace = traces[0]
        assert trace['sequence'] == 1
        assert trace['event_type'] == 'user_message'
        assert trace['platform'] == 'claude_code'
        assert trace['external_id'] == 'claude_session_001'
        assert 'event_data' in trace
    
    def test_get_conversations(self, sqlite_db_with_conversations):
        """Test getting conversations."""
        db_path, _ = sqlite_db_with_conversations
        reader = SQLiteReader(Path(db_path))
        
        conversations = reader.get_conversations()
        assert len(conversations) == 2
        
        # Verify Cursor conversation
        cursor_conv = [c for c in conversations if c['platform'] == 'cursor'][0]
        assert cursor_conv['id'] == 'conv_001'
        assert cursor_conv['session_id'] == 'session_001'
        assert cursor_conv['interaction_count'] == 5
        
        # Verify Claude Code conversation
        claude_conv = [c for c in conversations if c['platform'] == 'claude_code'][0]
        assert claude_conv['id'] == 'conv_002'
        assert claude_conv['session_id'] is None
    
    def test_get_conversations_with_timestamp_filter(self, sqlite_db_with_conversations):
        """Test filtering conversations by timestamp."""
        db_path, _ = sqlite_db_with_conversations
        reader = SQLiteReader(Path(db_path))
        
        # Filter by timestamp
        since = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        conversations = reader.get_conversations(since_timestamp=since)
        assert len(conversations) == 2
    
    def test_get_sessions(self, sqlite_db_with_sessions):
        """Test getting Cursor sessions."""
        db_path, _ = sqlite_db_with_sessions
        reader = SQLiteReader(Path(db_path))
        
        sessions = reader.get_sessions()
        assert len(sessions) == 1
        
        session = sessions[0]
        assert session['id'] == 'session_001'
        assert session['external_session_id'] == 'ext_session_001'
        assert session['workspace_hash'] == 'workspace_hash_001'
    
    def test_get_sessions_with_timestamp_filter(self, sqlite_db_with_sessions):
        """Test filtering sessions by timestamp."""
        db_path, _ = sqlite_db_with_sessions
        reader = SQLiteReader(Path(db_path))
        
        since = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        sessions = reader.get_sessions(since_timestamp=since)
        assert len(sessions) == 1

