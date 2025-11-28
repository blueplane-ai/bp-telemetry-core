#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
General Integration Tests for Blueplane Telemetry Core

Tests the core functionality of the telemetry system:
- Database operations
- Event processing
- Queue handling
- Monitor components

Run: pytest tests/test_integration.py -v
"""

import asyncio
import json
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Database Tests
# ============================================================================

class TestSQLiteClient:
    """Test SQLite database operations."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        db_path.unlink(missing_ok=True)
    
    def test_database_creation(self, temp_db):
        """Test database file is created by initialize_database."""
        from src.processing.database.sqlite_client import SQLiteClient

        # Remove the temp file so we can test actual creation
        temp_db.unlink(missing_ok=True)
        assert not temp_db.exists(), "File should not exist before initialization"

        client = SQLiteClient(str(temp_db))
        client.initialize_database()
        assert temp_db.exists(), "Database file should be created after initialize_database"
    
    def test_execute_query(self, temp_db):
        """Test basic query execution."""
        from src.processing.database.sqlite_client import SQLiteClient
        
        client = SQLiteClient(str(temp_db))
        with client.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO test (value) VALUES (?)", ("hello",))
            conn.commit()
            
            cursor = conn.execute("SELECT value FROM test")
            result = cursor.fetchone()
            assert result[0] == "hello"
    
    def test_transaction_rollback(self, temp_db):
        """Test transaction rollback on error."""
        from src.processing.database.sqlite_client import SQLiteClient
        
        client = SQLiteClient(str(temp_db))
        
        # Create table
        with client.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
            conn.commit()
        
        # Try to insert duplicate - should rollback
        try:
            with client.get_connection() as conn:
                conn.execute("INSERT INTO test (value) VALUES (?)", ("unique",))
                conn.execute("INSERT INTO test (value) VALUES (?)", ("unique",))  # Duplicate
                conn.commit()
        except Exception:
            pass  # Expected
        
        # Verify rollback worked - no data should be inserted
        # Python's sqlite3 uses deferred transactions by default, so both INSERTs
        # are part of the same implicit transaction. When the second fails before
        # commit(), the context manager's rollback() reverts both.
        with client.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 0, f"Expected 0 rows after rollback, got {count}"


class TestSchema:
    """Test database schema operations."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        db_path.unlink(missing_ok=True)
    
    def test_schema_creation(self, temp_db):
        """Test schema creates all required tables."""
        from src.processing.database.sqlite_client import SQLiteClient
        from src.processing.database.schema import create_schema
        
        client = SQLiteClient(str(temp_db))
        create_schema(client)
        
        # Check tables exist
        with client.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
        
        expected_tables = {"cursor_raw_traces", "conversations", "claude_raw_traces"}
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"


# ============================================================================
# Event Processing Tests
# ============================================================================

class TestEventStructure:
    """Test event structure and validation."""
    
    def test_event_has_required_fields(self):
        """Test events have all required fields."""
        event = {
            "version": "0.1.0",
            "hook_type": "test",
            "event_type": "test_event",
            "platform": "cursor",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
            "payload": {}
        }
        
        required_fields = ["version", "hook_type", "event_type", "timestamp"]
        for field in required_fields:
            assert field in event, f"Missing required field: {field}"
    
    def test_timestamp_format(self):
        """Test timestamp is valid ISO format."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Should parse without error
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None
    
    def test_platform_values(self):
        """Test valid platform values."""
        valid_platforms = ["cursor", "claude_code"]
        
        for platform in valid_platforms:
            event = {"platform": platform}
            assert event["platform"] in valid_platforms


class TestEventRouting:
    """Test event routing logic."""
    
    def test_cursor_event_detection(self):
        """Test Cursor event detection."""
        cursor_event = {
            "platform": "cursor",
            "metadata": {"source": "database_trace"}
        }
        
        platform = cursor_event.get("platform", "")
        source = cursor_event.get("metadata", {}).get("source", "")
        
        is_cursor = platform == "cursor" or source in ["database_trace", "workspace_listener"]
        assert is_cursor is True
    
    def test_claude_event_detection(self):
        """Test Claude Code event detection."""
        claude_event = {
            "platform": "claude_code",
            "metadata": {"source": "jsonl_monitor"}
        }
        
        platform = claude_event.get("platform", "")
        source = claude_event.get("metadata", {}).get("source", "")
        
        is_claude = platform == "claude_code" or source in ["jsonl_monitor", "transcript_monitor"]
        assert is_claude is True


# ============================================================================
# Monitor Component Tests
# ============================================================================

class TestFileWatcher:
    """Test file watching functionality."""
    
    @pytest.mark.asyncio
    async def test_filewatcher_initialization(self):
        """Test FileWatcher initializes correctly."""
        from src.processing.cursor.unified_cursor_monitor import FileWatcher
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            test_path = Path(f.name)
        
        try:
            callback_called = False
            async def callback():
                nonlocal callback_called
                callback_called = True
            
            watcher = FileWatcher(test_path, callback)
            assert watcher.db_path == test_path
            assert watcher.active is True
            assert watcher._loop is None  # Not set until start_watching
        finally:
            test_path.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_filewatcher_detects_changes(self):
        """Test FileWatcher detects file changes."""
        from src.processing.cursor.unified_cursor_monitor import FileWatcher
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            test_path = Path(f.name)
            f.write(b"initial content")
        
        try:
            change_detected = asyncio.Event()
            
            async def callback():
                change_detected.set()
            
            watcher = FileWatcher(test_path, callback)
            await watcher.start_watching()
            
            # Modify file
            test_path.write_text("modified content")
            
            # Check for changes (polling fallback)
            changed = await watcher.check_for_changes()
            
            await watcher.stop()
            assert changed is True
        finally:
            test_path.unlink(missing_ok=True)


class TestIncrementalSync:
    """Test incremental sync state tracking."""
    
    def test_initial_state_empty(self):
        """Test initial state is empty."""
        from src.processing.cursor.unified_cursor_monitor import IncrementalSync
        
        sync = IncrementalSync()
        assert len(sync.state) == 0
    
    def test_should_process_new_data(self):
        """Test new data is marked for processing."""
        from src.processing.cursor.unified_cursor_monitor import IncrementalSync
        
        sync = IncrementalSync()
        
        # First time seeing this data - should process
        result = sync.should_process("workspace", "hash123", "key1", {"value": "test"})
        assert result is True
    
    def test_should_not_process_same_data(self):
        """Test same data is not reprocessed."""
        from src.processing.cursor.unified_cursor_monitor import IncrementalSync
        
        sync = IncrementalSync()
        data = {"value": "test"}
        
        # First time - process
        sync.should_process("workspace", "hash123", "key1", data)
        
        # Same data - don't process
        result = sync.should_process("workspace", "hash123", "key1", data)
        assert result is False
    
    def test_should_process_changed_data(self):
        """Test changed data is processed."""
        from src.processing.cursor.unified_cursor_monitor import IncrementalSync
        
        sync = IncrementalSync()
        
        # First data
        sync.should_process("workspace", "hash123", "key1", {"value": "old"})
        
        # Changed data - should process
        result = sync.should_process("workspace", "hash123", "key1", {"value": "new"})
        assert result is True


# ============================================================================
# Queue Tests
# ============================================================================

class TestQueueWriter:
    """Test message queue operations."""
    
    def test_event_serialization(self):
        """Test events can be serialized to JSON."""
        event = {
            "version": "0.1.0",
            "hook_type": "test",
            "event_type": "test_event",
            "platform": "cursor",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"key": "value"},
            "payload": {"data": [1, 2, 3]}
        }
        
        # Should serialize without error
        serialized = json.dumps(event)
        assert isinstance(serialized, str)
        
        # Should deserialize back
        deserialized = json.loads(serialized)
        assert deserialized == event


# ============================================================================
# Config Tests
# ============================================================================

class TestConfig:
    """Test configuration handling."""
    
    def test_config_loads(self):
        """Test config can be loaded."""
        from src.capture.shared.config import Config
        
        config = Config()
        assert config is not None
    
    def test_config_has_redis_settings(self):
        """Test config has Redis property returning RedisConfig."""
        from src.capture.shared.config import Config

        config = Config()
        # Config should have redis property
        assert hasattr(config, 'redis'), "Config missing 'redis' property"
        redis_config = config.redis
        assert redis_config is not None, "redis property returned None"
        assert hasattr(redis_config, 'host'), "RedisConfig missing 'host' attribute"


# ============================================================================
# End-to-End Simulation
# ============================================================================

class TestEndToEndSimulation:
    """Simulate end-to-end event flow (without real Redis)."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database with schema."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        
        from src.processing.database.sqlite_client import SQLiteClient
        from src.processing.database.schema import create_schema
        
        client = SQLiteClient(str(db_path))
        create_schema(client)
        
        yield db_path, client
        db_path.unlink(missing_ok=True)
    
    def test_event_to_database_flow(self, temp_db):
        """Test event can be written to database."""
        import zlib
        db_path, client = temp_db

        # Simulate event with required fields matching actual schema
        event_id = str(uuid.uuid4())
        event_type = "test_event"
        timestamp = datetime.now(timezone.utc).isoformat()

        # event_data is compressed JSON blob
        event_json = json.dumps({"test": True, "event_type": event_type})
        event_data = zlib.compress(event_json.encode(), level=6)

        # Write to database (using actual required schema columns)
        with client.get_connection() as conn:
            conn.execute("""
                INSERT INTO cursor_raw_traces
                (event_id, event_type, timestamp, storage_level, workspace_hash,
                 database_table, item_key, event_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                event_type,
                timestamp,
                "workspace",
                "test_hash_123",
                "ItemTable",
                "test_key",
                event_data
            ))
            conn.commit()

        # Verify
        with client.get_connection() as conn:
            cursor = conn.execute(
                "SELECT event_type FROM cursor_raw_traces WHERE event_id = ?",
                (event_id,)
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "test_event"


# Run with: pytest tests/test_integration.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
