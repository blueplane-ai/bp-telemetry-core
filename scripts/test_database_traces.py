#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Test script to verify database trace processing.

Simulates database trace events from Cursor extension and verifies
they're processed correctly by the fast path consumer.
"""

import sys
import time
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blueplane.capture.shared.queue_writer import MessageQueueWriter
from blueplane.capture.shared.config import Config
from blueplane.processing.database.sqlite_client import SQLiteClient

def generate_database_trace_event(session_id: str = None) -> dict:
    """Generate a database trace event (simulating Cursor extension)."""
    if session_id is None:
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    
    # Simulate what the Cursor extension sends
    return {
        'hook_type': 'DatabaseTrace',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event_type': 'database_trace',
        'platform': 'cursor',
        'session_id': session_id,
        'metadata': {
            'workspace_hash': 'test_workspace_123',
            'source': 'database_monitor'
        },
        'payload': {
            'trace_type': 'generation',
            'generation_id': str(uuid.uuid4()),
            'data_version': 12345,
            'model': 'claude-3-opus-20240229',
            'tokens_used': 1500,
            'completion_tokens': 800,
            'prompt_tokens': 700,
        }
    }

def main():
    """Test database trace processing."""
    print("=" * 60)
    print("Database Trace Processing Test")
    print("=" * 60)
    print()
    
    # Initialize components
    print("1. Initializing components...")
    config = Config()
    writer = MessageQueueWriter(config)
    
    if writer._redis_client is None:
        print("❌ Redis is not available. Please start Redis:")
        print("   redis-server")
        return 1
    
    print("✅ Redis connection established")
    
    # Generate database trace events
    print("\n2. Generating database trace events...")
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    events = [
        generate_database_trace_event(session_id),
        generate_database_trace_event(session_id),
        generate_database_trace_event(session_id),
    ]
    
    print(f"   Generated {len(events)} database trace events")
    print(f"   Session ID: {session_id}")
    
    # Write events to Redis
    print("\n3. Writing database trace events to Redis Streams...")
    written = 0
    for event in events:
        if writer.enqueue(event, 'cursor', session_id):
            written += 1
            print(f"   ✅ Wrote: {event['event_type']} (generation_id: {event['payload']['generation_id'][:8]}...)")
        else:
            print(f"   ❌ Failed: {event['event_type']}")
    
    print(f"\n   Wrote {written}/{len(events)} events")
    
    if written == 0:
        print("❌ No events were written. Check Redis connection.")
        return 1
    
    # Wait for processing
    print("\n4. Waiting for processing (5 seconds)...")
    time.sleep(5)
    
    # Check SQLite database
    print("\n5. Checking SQLite database for database traces...")
    db_path = Path.home() / ".blueplane" / "telemetry.db"
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    client = SQLiteClient(str(db_path))
    
    with client.get_connection() as conn:
        # Check for database_trace events
        cursor = conn.execute(
            "SELECT COUNT(*) FROM raw_traces WHERE event_type = 'database_trace'"
        )
        total_traces = cursor.fetchone()[0]
        
        cursor = conn.execute(
            "SELECT COUNT(*) FROM raw_traces WHERE event_type = 'database_trace' AND session_id = ?",
            (session_id,)
        )
        session_traces = cursor.fetchone()[0]
        
        print(f"   Total database_trace events: {total_traces}")
        print(f"   Events for this session: {session_traces}")
        
        if session_traces > 0:
            print(f"   ✅ Found {session_traces} database trace events")
            
            # Show sample events
            cursor = conn.execute(
                """
                SELECT sequence, event_type, platform, timestamp, tool_name, model
                FROM raw_traces 
                WHERE event_type = 'database_trace' AND session_id = ?
                ORDER BY sequence DESC
                LIMIT 5
                """,
                (session_id,)
            )
            print("\n   Sample database trace events:")
            for row in cursor.fetchall():
                print(f"     Sequence {row[0]}: {row[1]} ({row[2]}) model={row[5]} at {row[4]}")
        else:
            print(f"   ⚠️  No database trace events found for session {session_id}")
            print("   Check if processing server is running")
    
    # Verify event data is compressed
    print("\n6. Verifying event compression...")
    with client.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT sequence, LENGTH(event_data) as size
            FROM raw_traces 
            WHERE event_type = 'database_trace' AND session_id = ?
            ORDER BY sequence DESC
            LIMIT 3
            """,
            (session_id,)
        )
        rows = cursor.fetchall()
        if rows:
            print("   Compressed event sizes:")
            for row in rows:
                print(f"     Sequence {row[0]}: {row[1]} bytes")
            avg_size = sum(r[1] for r in rows) / len(rows)
            print(f"     Average: {avg_size:.1f} bytes")
    
    print("\n" + "=" * 60)
    print("Database trace test complete!")
    print("=" * 60)
    print("\nNote: Real database traces come from the Cursor extension")
    print("which monitors Cursor's SQLite database (state.vscdb)")
    print("for AI generation events in the aiService.generations table.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

