# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""SQLite test fixtures for analytics service tests."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
import tempfile
import zlib
from datetime import datetime, timezone
from typing import Dict, Any, List

import pytest

from src.processing.database.sqlite_client import SQLiteClient
from src.processing.database.schema import create_schema


@pytest.fixture
def temp_sqlite_db():
    """Create temporary SQLite database for testing."""
    db_dir = tempfile.mkdtemp()
    db_path = Path(db_dir) / "test_telemetry.db"
    
    # Initialize database
    client = SQLiteClient(str(db_path))
    client.initialize_database()
    create_schema(client)
    
    yield str(db_path), client
    
    # Cleanup
    import shutil
    shutil.rmtree(db_dir)


def create_cursor_trace_event(
    sequence: int,
    event_type: str,
    workspace_hash: str = "test_workspace_hash",
    external_session_id: str = "test_session_123",
    event_data: Dict[str, Any] = None
) -> tuple:
    """Create a Cursor trace event tuple for insertion."""
    if event_data is None:
        event_data = {}
    
    # Compress event_data
    event_data_json = json.dumps(event_data).encode('utf-8')
    event_data_compressed = zlib.compress(event_data_json, level=6)
    
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = f"cursor_event_{sequence}"
    
    # Return tuple matching cursor_raw_traces schema (excluding sequence which is AUTOINCREMENT)
    return (
        event_id,
        external_session_id,
        event_type,
        timestamp,
        "workspace",  # storage_level
        workspace_hash,
        "ItemTable",  # database_table
        "test_key",  # item_key
        None,  # generation_uuid
        None,  # generation_type
        None,  # command_type
        None,  # composer_id
        None,  # bubble_id
        None,  # server_bubble_id
        None,  # message_type
        None,  # is_agentic
        None,  # text_description
        None,  # raw_text
        None,  # rich_text
        None,  # unix_ms
        None,  # created_at
        None,  # last_updated_at
        None,  # completed_at
        None,  # client_start_time
        None,  # client_end_time
        None,  # lines_added
        None,  # lines_removed
        None,  # token_count_up_until_here
        None,  # capabilities_ran
        None,  # capability_statuses
        None,  # project_name
        None,  # relevant_files
        None,  # selections
        None,  # is_archived
        None,  # has_unread_messages
        event_data_compressed,  # event_data
    )


def create_claude_trace_event(
    sequence: int,
    event_type: str,
    external_id: str = "test_session_456",
    workspace_hash: str = "test_workspace_hash",
    event_data: Dict[str, Any] = None
) -> tuple:
    """Create a Claude Code trace event tuple for insertion."""
    if event_data is None:
        event_data = {}
    
    # Compress event_data
    event_data_json = json.dumps(event_data).encode('utf-8')
    event_data_compressed = zlib.compress(event_data_json, level=6)
    
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = f"claude_event_{sequence}"
    
    # Return tuple matching claude_raw_traces schema (excluding sequence which is AUTOINCREMENT, platform is in INSERT)
    # Columns: event_id, external_id, event_type, timestamp, workspace_hash, uuid, parent_uuid, request_id, agent_id,
    #          project_name, is_sidechain, user_type, cwd, version, git_branch,
    #          message_role, message_model, message_id, message_type, stop_reason, stop_sequence,
    #          input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
    #          output_tokens, service_tier, cache_5m_tokens, cache_1h_tokens,
    #          operation, subtype, level, is_meta,
    #          summary, leaf_uuid,
    #          duration_ms, tokens_used, tool_calls_count,
    #          event_data
    return (
        event_id,
        external_id,
        event_type,
        timestamp,
        workspace_hash,
        None,  # uuid
        None,  # parent_uuid
        None,  # request_id
        None,  # agent_id
        None,  # project_name
        None,  # is_sidechain
        None,  # user_type
        None,  # cwd
        None,  # version
        None,  # git_branch
        None,  # message_role
        None,  # message_model
        None,  # message_id
        None,  # message_type
        None,  # stop_reason
        None,  # stop_sequence
        None,  # input_tokens
        None,  # cache_creation_input_tokens
        None,  # cache_read_input_tokens
        None,  # output_tokens
        None,  # service_tier
        None,  # cache_5m_tokens
        None,  # cache_1h_tokens
        None,  # operation
        None,  # subtype
        None,  # level
        None,  # is_meta
        None,  # summary
        None,  # leaf_uuid
        None,  # duration_ms
        None,  # tokens_used
        None,  # tool_calls_count
        event_data_compressed,  # event_data
    )


@pytest.fixture
def sqlite_db_with_cursor_traces(temp_sqlite_db):
    """Create SQLite database with sample Cursor traces."""
    db_path, client = temp_sqlite_db
    
    # Insert sample Cursor traces
    traces = [
        # AI generation event
        create_cursor_trace_event(
            sequence=1,
            event_type="generation",
            event_data={
                "generationUUID": "gen_001",
                "type": "cmdk",
                "unixMs": 1704067200000,  # 2024-01-01 00:00:00 UTC
                "textDescription": "Generate a function to calculate fibonacci"
            }
        ),
        # Composer session event
        create_cursor_trace_event(
            sequence=2,
            event_type="composer",
            event_data={
                "composerId": "composer_001",
                "createdAt": 1704067300000,
                "unifiedMode": "chat",
                "forceMode": None,
                "totalLinesAdded": 50,
                "totalLinesRemoved": 10,
                "isArchived": False,
                "allComposers": [
                    {
                        "composerId": "composer_001",
                        "createdAt": 1704067300000,
                        "unifiedMode": "chat",
                        "forceMode": None,
                        "totalLinesAdded": 50,
                        "totalLinesRemoved": 10,
                        "isArchived": False
                    }
                ]
            }
        ),
        # File history event
        create_cursor_trace_event(
            sequence=3,
            event_type="history",
            event_data={
                "entries": [
                    {"uri": "file:///test/path/file1.py", "timestamp": 1704067400000},
                    {"uri": "file:///test/path/file2.py", "timestamp": 1704067500000}
                ]
            }
        ),
    ]
    
    # Insert traces
    for trace in traces:
        client.execute("""
            INSERT INTO cursor_raw_traces (
                event_id, external_session_id, event_type, timestamp,
                storage_level, workspace_hash, database_table, item_key,
                generation_uuid, generation_type, command_type,
                composer_id, bubble_id, server_bubble_id, message_type, is_agentic,
                text_description, raw_text, rich_text,
                unix_ms, created_at, last_updated_at, completed_at,
                client_start_time, client_end_time,
                lines_added, lines_removed, token_count_up_until_here,
                capabilities_ran, capability_statuses,
                project_name, relevant_files, selections,
                is_archived, has_unread_messages,
                event_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, trace)
    
    return db_path, client


@pytest.fixture
def sqlite_db_with_claude_traces(temp_sqlite_db):
    """Create SQLite database with sample Claude Code traces."""
    db_path, client = temp_sqlite_db
    
    # Insert sample Claude Code traces
    traces = [
        create_claude_trace_event(
            sequence=1,
            event_type="user_message",
            external_id="claude_session_001",
            event_data={
                "role": "user",
                "content": "Hello, how are you?"
            }
        ),
        create_claude_trace_event(
            sequence=2,
            event_type="assistant_message",
            external_id="claude_session_001",
            event_data={
                "role": "assistant",
                "content": "I'm doing well, thank you!"
            }
        ),
    ]
    
    # Insert traces
    # Note: platform has default value 'claude_code' in schema, so we omit it from INSERT
    # Tuple has 38 values: event_id through event_data (excluding sequence and platform)
    for trace in traces:
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
        """, trace)
    
    return db_path, client


@pytest.fixture
def sqlite_db_with_conversations(temp_sqlite_db):
    """Create SQLite database with sample conversations."""
    db_path, client = temp_sqlite_db
    
    # Create cursor_sessions first (required for FK)
    client.execute("""
        INSERT INTO cursor_sessions (
            id, external_session_id, workspace_hash, workspace_name, workspace_path, started_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "session_001",
        "ext_session_001",
        "workspace_hash_001",
        "Test Workspace",
        "/test/workspace",
        "2025-01-01T00:00:00Z"
    ))
    
    # Insert conversations
    client.execute("""
        INSERT INTO conversations (
            id, session_id, external_id, platform, workspace_hash, workspace_name,
            started_at, context, metadata, interaction_count, total_tokens, total_changes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "conv_001",
        "session_001",
        "ext_session_001",
        "cursor",
        "workspace_hash_001",
        "Test Workspace",
        "2025-01-01T00:00:00Z",
        '{}',
        '{}',
        5,
        1000,
        10
    ))
    
    client.execute("""
        INSERT INTO conversations (
            id, session_id, external_id, platform, workspace_hash, workspace_name,
            started_at, context, metadata, interaction_count, total_tokens, total_changes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "conv_002",
        None,
        "claude_session_001",
        "claude_code",
        "workspace_hash_002",
        "Claude Workspace",
        "2025-01-01T00:00:00Z",
        '{}',
        '{}',
        3,
        500,
        5
    ))
    
    return db_path, client


@pytest.fixture
def sqlite_db_with_sessions(temp_sqlite_db):
    """Create SQLite database with sample Cursor sessions."""
    db_path, client = temp_sqlite_db
    
    # Insert sessions
    client.execute("""
        INSERT INTO cursor_sessions (
            id, external_session_id, workspace_hash, workspace_name, workspace_path,
            started_at, ended_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "session_001",
        "ext_session_001",
        "workspace_hash_001",
        "Test Workspace",
        "/test/workspace",
        "2025-01-01T00:00:00Z",
        None,
        '{}'
    ))
    
    return db_path, client

