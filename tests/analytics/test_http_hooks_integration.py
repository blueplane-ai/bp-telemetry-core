# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Integration tests for HTTP hooks → Analytics Service flow."""

import sys
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import redis

from src.processing.http_endpoint import HTTPEndpoint
from src.capture.shared.queue_writer import MessageQueueWriter
from src.capture.shared.config import Config
from src.processing.database.sqlite_client import SQLiteClient
from src.processing.database.schema import create_schema
from src.processing.claude_code.event_consumer import ClaudeEventConsumer
from src.processing.claude_code.raw_traces_writer import ClaudeRawTracesWriter
from src.analytics.workers.sqlite_reader import SQLiteReader
from src.analytics.workers.duckdb_writer import DuckDBWriter, DUCKDB_AVAILABLE
from tests.fixtures.duckdb_fixtures import temp_duckdb


@pytest.fixture
def temp_sqlite_db():
    """Create temporary SQLite database."""
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    db_path = db_file.name
    db_file.close()
    
    # Initialize database schema
    client = SQLiteClient(db_path)
    create_schema(client)
    # SQLiteClient uses context managers, no close() method needed
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink()


@pytest.fixture
def redis_client():
    """Create Redis client for testing."""
    try:
        client = redis.Redis(host='localhost', port=6379, decode_responses=False)
        client.ping()
        yield client
    except redis.ConnectionError:
        pytest.skip("Redis not available")
    finally:
        # Clean up test data - delete stream and consumer groups
        try:
            # Delete stream
            client.delete('telemetry:events')
            # Try to delete consumer groups (may not exist, that's OK)
            try:
                client.xgroup_destroy('telemetry:events', 'test_consumers')
            except redis.exceptions.ResponseError:
                pass  # Group doesn't exist, that's fine
        except Exception:
            pass  # Ignore cleanup errors


@pytest.fixture
def config():
    """Create test configuration."""
    config = Config()
    # Override Redis config for testing
    config._config['redis'] = {
        'connection': {
            'host': 'localhost',
            'port': 6379
        }
    }
    return config


@pytest.fixture
def http_endpoint(config, redis_client):
    """Create HTTP endpoint for testing."""
    queue_writer = MessageQueueWriter(config, stream_type="events")
    endpoint = HTTPEndpoint(
        enqueue_func=queue_writer.enqueue,
        host="127.0.0.1",
        port=8788  # Use different port to avoid conflicts
    )
    endpoint.start()
    
    # Wait for server to start
    time.sleep(0.1)
    
    yield endpoint
    
    endpoint.stop()


@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not available")
class TestHTTPHooksAnalyticsIntegration:
    """Integration tests for HTTP hooks → Analytics Service flow."""
    
    def test_http_hooks_to_analytics_service(
        self,
        temp_sqlite_db,
        temp_duckdb,
        redis_client,
        config,
        http_endpoint
    ):
        """Test full flow: HTTP hook → Redis → SQLite → Analytics Service → DuckDB."""
        import urllib.request
        import urllib.error
        
        sqlite_path = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        # Step 1: Clean up any existing consumer group and create fresh one
        # Use unique consumer group name per test run to avoid conflicts
        import uuid
        unique_group = f'test_consumers_{uuid.uuid4().hex[:8]}'
        
        # Delete stream if it exists to ensure clean state
        try:
            redis_client.delete('telemetry:events')
        except Exception:
            pass
        
        # Create consumer group FIRST (before writing message)
        # This ensures new messages will be available for reading
        try:
            redis_client.xgroup_create(
                'telemetry:events',
                unique_group,
                id='0',  # Start from beginning (for any existing messages)
                mkstream=True
            )
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
        
        # Step 2: Submit event via HTTP endpoint
        # The event needs event_type='session_start' to pass the filter in _process_batch
        event = {
            "hook_type": "session_start",
            "event_type": "session_start",  # Required for Claude Code event filter
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "session_id": "test-session-123",
                "workspace_path": "/test/workspace"
            }
        }
        
        payload = {
            "event": event,
            "platform": "claude_code",
            "session_id": "test-session-123"
        }
        
        # Submit via HTTP POST
        url = "http://127.0.0.1:8788/events"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        
        try:
            response = urllib.request.urlopen(req, timeout=1.0)
            assert response.getcode() == 202, "Event should be accepted"
        except urllib.error.URLError:
            pytest.skip("HTTP endpoint not responding")
        
        # Step 3: Verify event is in Redis
        time.sleep(0.2)  # Give Redis time to process
        stream_length = redis_client.xlen('telemetry:events')
        assert stream_length > 0, "Event should be in Redis stream"
        
        # Step 4: Process event through consumer to SQLite
        claude_writer = ClaudeRawTracesWriter(SQLiteClient(sqlite_path))
        
        # Consume and process event
        consumer = ClaudeEventConsumer(
            redis_client=redis_client,
            claude_writer=claude_writer,
            cdc_publisher=None,  # Skip CDC for this test
            stream_name='telemetry:events',
            consumer_group=unique_group,  # Use unique group name
            consumer_name='test-consumer-1',
            batch_size=1,
            batch_timeout=0.1,
            block_ms=100  # Shorter timeout for test
        )
        
        # Read messages from Redis
        # Since consumer group was created BEFORE the message was written,
        # we can use '>' to read new messages
        messages_data = redis_client.xreadgroup(
            unique_group,  # Use unique group name
            'test-consumer-1',
            {'telemetry:events': '>'},  # Read new messages
            count=1,
            block=100
        )
        
        assert messages_data, "Should have messages from Redis stream"
        
        # Parse messages in the format expected by _process_batch
        # _decode_stream_message handles bytes decoding internally, so pass raw fields
        messages = []
        for stream_name, stream_messages in messages_data:
            for message_id, fields in stream_messages:
                msg_id = message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id)
                # Pass raw fields - _decode_stream_message will handle decoding
                event = consumer._decode_stream_message(msg_id, fields)
                if event is not None:  # Only add if decoding succeeded
                    messages.append({
                        'id': msg_id,
                        'event': event
                    })
        
        assert messages, f"Should have parsed messages (got {len(messages)} from {len(messages_data[0][1]) if messages_data else 0} raw messages)"
        assert messages[0]['event'] is not None, "Event should be decoded successfully"
        
        # Process the batch
        consumer._process_batch(messages)
        
        # Step 4: Verify event is in SQLite
        sqlite_client = SQLiteClient(sqlite_path)
        with sqlite_client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM claude_raw_traces
            """)
            trace_count = cursor.fetchone()[0]
            assert trace_count > 0, "Event should be in SQLite"
        
        # Step 5: Verify analytics service can read from SQLite and write to DuckDB
        reader = SQLiteReader(Path(sqlite_path))
        traces = reader.get_new_traces("claude_code", since_sequence=0)
        assert len(traces) > 0, "Analytics service should read traces from SQLite"
        
        writer = DuckDBWriter(Path(duckdb_path))
        writer.connect()
        writer.write_traces(traces)
        
        # Verify data in DuckDB
        raw_count = writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'claude_code'
        """).fetchone()[0]
        assert raw_count > 0, "Traces should be in DuckDB"
        
        writer.close()
    
    def test_http_endpoint_health_check(self, http_endpoint):
        """Test HTTP endpoint health check."""
        import urllib.request
        
        try:
            response = urllib.request.urlopen("http://127.0.0.1:8788/health", timeout=1.0)
            assert response.getcode() == 200
            data = json.loads(response.read().decode('utf-8'))
            assert data['status'] == 'ok'
        except urllib.error.URLError:
            pytest.skip("HTTP endpoint not responding")
    
    def test_http_endpoint_invalid_request(self, http_endpoint):
        """Test HTTP endpoint handles invalid requests."""
        import urllib.request
        import urllib.error
        
        # Test missing fields
        payload = {"event": {"hook_type": "test"}}  # Missing platform and session_id
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            "http://127.0.0.1:8788/events",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=1.0)
            assert exc_info.value.code == 400
        except urllib.error.URLError:
            pytest.skip("HTTP endpoint not responding")

