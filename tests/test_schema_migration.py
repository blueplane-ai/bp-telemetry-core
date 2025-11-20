#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Tests for schema migration v1 -> v2."""

import hashlib
import pytest
import tempfile
import shutil
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.processing.database.sqlite_client import SQLiteClient
from src.processing.database.schema import (
    migrate_schema, get_schema_version, SCHEMA_VERSION,
    create_schema
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    db_dir = tempfile.mkdtemp()
    db_path = Path(db_dir) / "test.db"
    yield str(db_path)
    shutil.rmtree(db_dir)


@pytest.fixture
def v1_schema_db(temp_db):
    """Create database with v1 schema (old conversations table)."""
    client = SQLiteClient(temp_db)
    
    # Create old schema
    client.execute("""
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            external_session_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            workspace_hash TEXT,
            workspace_name TEXT,
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            context TEXT DEFAULT '{}',
            metadata TEXT DEFAULT '{}',
            tool_sequence TEXT DEFAULT '[]',
            acceptance_decisions TEXT DEFAULT '[]',
            interaction_count INTEGER DEFAULT 0,
            acceptance_rate REAL,
            total_tokens INTEGER DEFAULT 0,
            total_changes INTEGER DEFAULT 0
        )
    """)
    
    # Insert test data
    client.execute("""
        INSERT INTO conversations (
            id, session_id, external_session_id, platform,
            workspace_hash, workspace_name, started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        'conv1', 'sess1', 'ext_sess1', 'cursor',
        'hash1', 'workspace1', '2025-01-01T00:00:00Z'
    ))
    
    client.execute("""
        INSERT INTO conversations (
            id, session_id, external_session_id, platform,
            workspace_hash, workspace_name, started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        'conv2', 'sess1', 'ext_sess1', 'cursor',
        'hash1', 'workspace1', '2025-01-02T00:00:00Z'
    ))
    
    # Claude Code conversation (should have NULL session_id after migration)
    client.execute("""
        INSERT INTO conversations (
            id, session_id, external_session_id, platform,
            workspace_hash, workspace_name, started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        'conv3', 'claude_sess', 'claude_ext1', 'claude_code',
        'hash2', 'workspace2', '2025-01-01T00:00:00Z'
    ))
    
    return client


class TestMigrationV1ToV2:
    """Test migration from schema v1 to v2."""
    
    def test_migrates_empty_database(self, temp_db):
        """Test migration on empty database."""
        client = SQLiteClient(temp_db)
        migrate_schema(client, 1, SCHEMA_VERSION)
        
        assert get_schema_version(client) == SCHEMA_VERSION
        
        # Verify cursor_sessions table exists
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='cursor_sessions'
            """)
            assert cursor.fetchone() is not None
    
    def test_migrates_cursor_sessions(self, v1_schema_db):
        """Test that Cursor sessions are migrated to cursor_sessions table."""
        migrate_schema(v1_schema_db, 1, SCHEMA_VERSION)
        
        # Check cursor_sessions table
        with v1_schema_db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cursor_sessions")
            count = cursor.fetchone()[0]
            assert count == 1  # Should have one unique session (ext_sess1)
            
            cursor = conn.execute("""
                SELECT external_session_id, workspace_hash 
                FROM cursor_sessions
            """)
            row = cursor.fetchone()
            assert row[0] == 'ext_sess1'
            assert row[1] == 'hash1'
    
    def test_conversations_table_updated(self, v1_schema_db):
        """Test that conversations table has new schema."""
        migrate_schema(v1_schema_db, 1, SCHEMA_VERSION)
        
        with v1_schema_db.get_connection() as conn:
            # Check columns
            cursor = conn.execute("PRAGMA table_info(conversations)")
            columns = {row[1] for row in cursor.fetchall()}
            
            assert 'external_id' in columns
            assert 'external_session_id' not in columns
            assert 'session_id' in columns  # Should still exist but nullable
    
    def test_conversation_references_updated(self, v1_schema_db):
        """Test that conversations reference cursor_sessions correctly."""
        migrate_schema(v1_schema_db, 1, SCHEMA_VERSION)
        
        with v1_schema_db.get_connection() as conn:
            # Cursor conversation should have session_id pointing to cursor_sessions
            cursor = conn.execute("""
                SELECT c.session_id, cs.id, c.external_id
                FROM conversations c
                LEFT JOIN cursor_sessions cs ON c.session_id = cs.id
                WHERE c.platform = 'cursor'
                LIMIT 1
            """)
            row = cursor.fetchone()
            assert row[0] is not None  # session_id should be set
            assert row[1] is not None  # Should join successfully
            assert row[2] == 'ext_sess1'  # external_id should be set
            
            # Claude Code conversation should have NULL session_id
            cursor = conn.execute("""
                SELECT session_id, external_id
                FROM conversations
                WHERE platform = 'claude_code'
            """)
            row = cursor.fetchone()
            assert row[0] is None  # session_id should be NULL
            assert row[1] == 'claude_ext1'
    
    def test_handles_duplicate_external_session_ids(self, temp_db):
        """Test migration handles duplicate external_session_ids gracefully."""
        client = SQLiteClient(temp_db)
        
        # Create v1 schema with duplicates
        client.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                workspace_hash TEXT,
                started_at TIMESTAMP NOT NULL
            )
        """)
        
        # Insert same external_session_id with different workspace_hash
        client.execute("""
            INSERT INTO conversations VALUES 
            ('c1', 's1', 'ext1', 'cursor', 'hash1', '2025-01-01T00:00:00Z'),
            ('c2', 's1', 'ext1', 'cursor', 'hash2', '2025-01-02T00:00:00Z')
        """)
        
        # Migration should handle this
        migrate_schema(client, 1, SCHEMA_VERSION)
        
        # Should only have one cursor_session (picks earliest)
        with client.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cursor_sessions")
            assert cursor.fetchone()[0] == 1
            
            # Should pick the earliest one (hash1)
            cursor = conn.execute("""
                SELECT workspace_hash FROM cursor_sessions
                WHERE external_session_id = 'ext1'
            """)
            row = cursor.fetchone()
            assert row[0] == 'hash1'
    
    def test_migration_idempotent(self, v1_schema_db):
        """Test that running migration twice doesn't break anything."""
        migrate_schema(v1_schema_db, 1, SCHEMA_VERSION)
        version_after_first = get_schema_version(v1_schema_db)
        
        # Run again
        migrate_schema(v1_schema_db, version_after_first, SCHEMA_VERSION)
        version_after_second = get_schema_version(v1_schema_db)
        
        assert version_after_first == version_after_second == SCHEMA_VERSION
        
        # Data should still be intact
        with v1_schema_db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM conversations")
            assert cursor.fetchone()[0] == 3  # Original 3 conversations
    
    def test_no_duplicates_after_migration(self, temp_db):
        """Test that migration doesn't create duplicate external_session_ids."""
        client = SQLiteClient(temp_db)
        
        # Create v1 schema
        client.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                workspace_hash TEXT,
                started_at TIMESTAMP NOT NULL
            )
        """)
        
        # Insert multiple conversations with same external_session_id
        client.execute("""
            INSERT INTO conversations VALUES 
            ('c1', 's1', 'ext1', 'cursor', 'hash1', '2025-01-01T00:00:00Z'),
            ('c2', 's1', 'ext1', 'cursor', 'hash1', '2025-01-02T00:00:00Z'),
            ('c3', 's1', 'ext1', 'cursor', 'hash1', '2025-01-03T00:00:00Z')
        """)
        
        # Migration should succeed without duplicates
        migrate_schema(client, 1, SCHEMA_VERSION)
        
        # Verify no duplicates in cursor_sessions
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT external_session_id, COUNT(*) as cnt
                FROM cursor_sessions
                GROUP BY external_session_id
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            assert len(duplicates) == 0, f"Found duplicates: {duplicates}"

    def test_migration_derives_workspace_hash_from_context(self, temp_db):
        """Sessions without workspace_hash but with workspace_path are retained."""
        client = SQLiteClient(temp_db)
        client.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                workspace_hash TEXT,
                workspace_name TEXT,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                context TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                tool_sequence TEXT DEFAULT '[]',
                acceptance_decisions TEXT DEFAULT '[]',
                interaction_count INTEGER DEFAULT 0,
                acceptance_rate REAL,
                total_tokens INTEGER DEFAULT 0,
                total_changes INTEGER DEFAULT 0
            )
        """)
        client.execute("""
            INSERT INTO conversations (
                id, session_id, external_session_id, platform,
                workspace_hash, workspace_name, started_at, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'ctx_conv',
            'sess_ctx',
            'ext_ctx',
            'cursor',
            None,
            'ctx_workspace',
            '2025-01-01T00:00:00Z',
            '{"workspace_path": "/tmp/ctx"}'
        ))

        migrate_schema(client, 1, SCHEMA_VERSION)

        expected_hash = hashlib.sha256("/tmp/ctx".encode()).hexdigest()[:16]
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT workspace_hash FROM cursor_sessions
                WHERE external_session_id = 'ext_ctx'
            """)
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == expected_hash

            cursor = conn.execute("""
                SELECT workspace_hash FROM conversations
                WHERE external_id = 'ext_ctx'
            """)
            conv_row = cursor.fetchone()
            assert conv_row is not None
            assert conv_row[0] == expected_hash

    def test_migration_generates_workspace_hash_when_missing(self, temp_db):
        """Sessions without any workspace context still migrate with deterministic hash."""
        client = SQLiteClient(temp_db)
        client.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                workspace_hash TEXT,
                workspace_name TEXT,
                started_at TIMESTAMP NOT NULL
            )
        """)
        client.execute("""
            INSERT INTO conversations VALUES
            ('legacy_conv', 'legacy_sess', 'ext_legacy', 'cursor', NULL, 'legacy_workspace', '2025-02-01T00:00:00Z')
        """)

        migrate_schema(client, 1, SCHEMA_VERSION)

        expected_hash = hashlib.sha256("ext_legacy".encode()).hexdigest()[:16]
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT workspace_hash FROM cursor_sessions
                WHERE external_session_id = 'ext_legacy'
            """)
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == expected_hash

            # Conversation should still exist and reference the generated hash
            cursor = conn.execute("""
                SELECT workspace_hash FROM conversations
                WHERE external_id = 'ext_legacy'
            """)
            conv_row = cursor.fetchone()
            assert conv_row is not None
            assert conv_row[0] == expected_hash

