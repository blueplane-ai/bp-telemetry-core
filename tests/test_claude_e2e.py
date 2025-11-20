#!/usr/bin/env python3
"""
Complete end-to-end test for Claude Code telemetry.

Tests the full pipeline:
1. SessionStart hook triggers session monitoring
2. JSONL files are created with events
3. JSONL Monitor polls and reads files (main + agent)
4. Events are sent to Redis streams
5. Database writer processes and stores in claude_raw_traces
6. Verify all fields are correctly populated
"""

import json
import sys
import time
import uuid
import redis
import sqlite3
import zlib
from pathlib import Path
from io import StringIO
from datetime import datetime, timezone
from typing import Tuple, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def trigger_session_start(session_id: str, workspace_path: str) -> bool:
    """
    Trigger SessionStart hook programmatically.

    Args:
        session_id: UUID for the session
        workspace_path: Workspace directory path

    Returns:
        True if hook executed successfully
    """
    # Create hook input
    hook_input = {
        "session_id": session_id,
        "workspace_path": workspace_path,
        "source": "test"
    }

    # Mock stdin for the hook
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(hook_input))

    try:
        from src.capture.claude_code.hooks.session_start import SessionStartHook
        hook = SessionStartHook()
        result = hook.execute()
        return result == 0
    except Exception as e:
        print(f"Error triggering session start hook: {e}")
        return False
    finally:
        sys.stdin = old_stdin


def create_test_jsonl_files(project_dir: Path, session_id: str) -> Tuple[Path, Path]:
    """
    Create test JSONL files with sample events.

    Args:
        project_dir: Claude project directory path
        session_id: Session UUID

    Returns:
        Tuple of (session_file_path, agent_file_path)
    """
    # Create project directory if it doesn't exist
    project_dir.mkdir(parents=True, exist_ok=True)

    # Main session file
    session_file = project_dir / f"{session_id}.jsonl"

    # Create events for main session file
    events = []

    # 1. Queue operation - enqueue
    events.append({
        "type": "queue-operation",
        "operation": "enqueue",
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "sessionId": session_id,
        "content": [
            {"type": "text", "text": "Test input for end-to-end test"}
        ]
    })

    # 2. Queue operation - dequeue
    events.append({
        "type": "queue-operation",
        "operation": "dequeue",
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "sessionId": session_id
    })

    # 3. User message
    user_uuid = str(uuid.uuid4())
    events.append({
        "type": "user",
        "uuid": user_uuid,
        "parentUuid": None,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "role": "user",
            "content": [
                {"type": "text", "text": "Write a test function"}
            ]
        }
    })

    # 4. Assistant response with thinking
    assistant_uuid_1 = str(uuid.uuid4())
    events.append({
        "type": "assistant",
        "uuid": assistant_uuid_1,
        "parentUuid": user_uuid,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "requestId": f"req_{uuid.uuid4().hex[:12]}",
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "model": "claude-sonnet-4-5-20250929",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "I need to create a test function for this end-to-end test...",
                    "signature": "base64encodedstring=="
                }
            ],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 500,
                "output_tokens": 50,
                "service_tier": "standard",
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 1000,
                    "ephemeral_1h_input_tokens": 0
                }
            }
        }
    })

    # 5. Assistant response with tool_use (triggers agent monitoring)
    assistant_uuid_2 = str(uuid.uuid4())
    tool_use_id = f"toolu_{uuid.uuid4().hex[:12]}"
    agent_id = "test123abc"

    events.append({
        "type": "assistant",
        "uuid": assistant_uuid_2,
        "parentUuid": user_uuid,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "requestId": f"req_{uuid.uuid4().hex[:12]}",
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "model": "claude-sonnet-4-5-20250929",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Task",
                    "input": {
                        "description": "Run a sub-task",
                        "prompt": "Complete this task for testing...",
                        "subagent_type": "general-purpose"
                    }
                }
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 150,
                "output_tokens": 75,
                "service_tier": "standard"
            }
        }
    })

    # 6. User event with tool_result (includes agentId for detection)
    tool_result_uuid = str(uuid.uuid4())
    events.append({
        "type": "user",
        "uuid": tool_result_uuid,
        "parentUuid": assistant_uuid_2,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "role": "user",
            "content": [
                {
                    "tool_use_id": tool_use_id,
                    "type": "tool_result",
                    "content": "Task completed successfully",
                    "is_error": False
                }
            ]
        },
        "toolUseResult": {
            "status": "completed",
            "agentId": agent_id,  # This triggers agent file monitoring
            "content": [{"type": "text", "text": "Agent task result"}],
            "totalDurationMs": 5432
        }
    })

    # Write main session file
    with open(session_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event, separators=(',', ':')) + '\n')

    # Create agent file
    agent_file = project_dir / f"agent-{agent_id}.jsonl"

    # Agent events
    agent_events = []

    # Agent assistant response
    agent_uuid = str(uuid.uuid4())
    agent_events.append({
        "type": "assistant",
        "uuid": agent_uuid,
        "parentUuid": None,
        "sessionId": session_id,
        "agentId": agent_id,
        "isSidechain": True,  # Important: marks this as agent event
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "requestId": f"req_{uuid.uuid4().hex[:12]}",
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "model": "claude-sonnet-4-5-20250929",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Agent is processing the task..."}
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 50,
                "output_tokens": 25,
                "service_tier": "standard"
            }
        }
    })

    # Write agent file
    with open(agent_file, 'w') as f:
        for event in agent_events:
            f.write(json.dumps(event, separators=(',', ':')) + '\n')

    return session_file, agent_file


def append_late_event(session_file: Path, session_id: str) -> None:
    """
    Append a new event to simulate ongoing session activity.

    Args:
        session_file: Path to session JSONL file
        session_id: Session UUID
    """
    late_event = {
        "type": "assistant",
        "uuid": str(uuid.uuid4()),
        "parentUuid": None,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "isSidechain": False,
        "userType": "external",
        "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
        "version": "2.0.42",
        "gitBranch": "test-branch",
        "message": {
            "model": "claude-sonnet-4-5-20250929",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "This is a late response added after initial file creation"}
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 75,
                "output_tokens": 35,
                "service_tier": "standard"
            }
        }
    }

    with open(session_file, 'a') as f:
        f.write(json.dumps(late_event, separators=(',', ':')) + '\n')


def verify_database(session_id: str) -> bool:
    """
    Verify events were written to database correctly.

    Args:
        session_id: Session UUID to query

    Returns:
        True if all verifications pass
    """
    db_path = Path.home() / ".blueplane" / "telemetry.db"

    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # 1. Check event count
        cursor.execute(
            "SELECT COUNT(*) FROM claude_raw_traces WHERE external_id = ?",
            (session_id,)
        )
        count = cursor.fetchone()[0]
        print(f"\n✓ Total events in DB: {count}")

        if count < 5:
            print(f"✗ Expected at least 5 events, got {count}")
            return False

        # 2. Check event types
        cursor.execute(
            """
            SELECT event_type, COUNT(*)
            FROM claude_raw_traces
            WHERE session_id = ?
            GROUP BY event_type
            ORDER BY event_type
            """,
            (session_id,)
        )
        types = dict(cursor.fetchall())
        print(f"✓ Event types: {types}")

        # 3. Check assistant events with tokens
        cursor.execute(
            """
            SELECT
                uuid, parent_uuid, message_model,
                input_tokens, output_tokens, tokens_used,
                is_sidechain, agent_id
            FROM claude_raw_traces
            WHERE session_id = ? AND event_type = 'assistant'
            ORDER BY timestamp
            """,
            (session_id,)
        )

        assistant_events = cursor.fetchall()
        print(f"\n✓ Found {len(assistant_events)} assistant events:")

        for row in assistant_events:
            print(f"  UUID: {row[0][:8]}...")
            print(f"  Parent: {row[1][:8] if row[1] else 'None'}...")
            print(f"  Model: {row[2]}")
            print(f"  Tokens: {row[3]} in, {row[4]} out, {row[5]} total")
            print(f"  Sidechain: {bool(row[6])}")
            print(f"  Agent ID: {row[7]}")
            print("  ---")

        # 4. Verify agent file was monitored
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM claude_raw_traces
            WHERE session_id = ? AND agent_id = 'test123abc'
            """,
            (session_id,)
        )
        agent_count = cursor.fetchone()[0]

        if agent_count > 0:
            print(f"✓ Agent file events found: {agent_count}")
        else:
            print("✗ Agent file not monitored")
            return False

        # 5. Check sidechain events
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM claude_raw_traces
            WHERE session_id = ? AND is_sidechain = 1
            """,
            (session_id,)
        )
        sidechain_count = cursor.fetchone()[0]

        if sidechain_count > 0:
            print(f"✓ Sidechain events found: {sidechain_count}")
        else:
            print("✗ No sidechain events found")
            return False

        # 6. Decompress and verify full event
        cursor.execute(
            """
            SELECT event_data
            FROM claude_raw_traces
            WHERE session_id = ? AND event_type = 'assistant'
            LIMIT 1
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            compressed = row[0]
            decompressed = zlib.decompress(compressed).decode('utf-8')
            event = json.loads(decompressed)

            if 'payload' in event and 'entry_data' in event['payload']:
                print(f"✓ Decompressed event structure valid")
                print(f"  Event keys: {list(event.keys())}")
                print(f"  Entry data keys: {list(event['payload']['entry_data'].keys())[:5]}...")
            else:
                print("✗ Invalid decompressed event structure")
                return False

        # 7. Check threading (parentUuid references)
        cursor.execute(
            """
            SELECT uuid, parent_uuid, event_type
            FROM claude_raw_traces
            WHERE session_id = ? AND parent_uuid IS NOT NULL
            ORDER BY timestamp
            """,
            (session_id,)
        )
        threaded = cursor.fetchall()
        if threaded:
            print(f"✓ Found {len(threaded)} threaded events")

        # 8. Check indexed fields are populated
        cursor.execute(
            """
            SELECT
                cwd, version, git_branch, user_type
            FROM claude_raw_traces
            WHERE session_id = ? AND cwd IS NOT NULL
            LIMIT 1
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            print(f"✓ Context fields populated:")
            print(f"  CWD: {row[0]}")
            print(f"  Version: {row[1]}")
            print(f"  Git branch: {row[2]}")
            print(f"  User type: {row[3]}")

        return True

    except Exception as e:
        print(f"✗ Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


def check_prerequisites() -> bool:
    """
    Check that all prerequisites are met before running test.

    Returns:
        True if all checks pass
    """
    print("Checking prerequisites...")

    # Check Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✓ Redis is running")
    except Exception as e:
        print(f"✗ Redis not accessible: {e}")
        return False

    # Check database
    db_path = Path.home() / ".blueplane" / "telemetry.db"
    if db_path.exists():
        print(f"✓ Database exists: {db_path}")
    else:
        print(f"✗ Database not found: {db_path}")
        print("  Run the telemetry server first to create database")
        return False

    # Check if telemetry server is running (check for consumer group)
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        groups = r.xinfo_groups('telemetry:events')
        if any(g[b'name'] == b'processors' for g in groups):
            print("✓ Telemetry server appears to be configured")
        else:
            print("⚠ Consumer group 'processors' not found - server may not be running")
    except Exception as e:
        print(f"⚠ Could not check server status: {e}")

    return True


def run_end_to_end_test() -> bool:
    """
    Run the complete end-to-end test.

    Returns:
        True if test passes
    """
    # 1. Setup test parameters
    session_id = f"test-{uuid.uuid4()}"
    workspace_path = "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core"

    # Calculate project directory path (Claude Code format)
    normalized_path = workspace_path.replace("/", "-")
    if normalized_path.startswith("-"):
        normalized_path = normalized_path[1:]
    project_dir = Path.home() / ".claude" / "projects" / f"-{normalized_path}"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id}")
    print(f"  Workspace: {workspace_path}")
    print(f"  Project dir: {project_dir}")

    # 2. Create JSONL files
    print("\nCreating test JSONL files...")
    session_file, agent_file = create_test_jsonl_files(project_dir, session_id)
    print(f"✓ Created session file: {session_file.name}")
    print(f"✓ Created agent file: {agent_file.name}")

    # Verify files exist
    if not session_file.exists():
        print(f"✗ Session file not created: {session_file}")
        return False
    if not agent_file.exists():
        print(f"✗ Agent file not created: {agent_file}")
        return False

    # Count initial events
    with open(session_file, 'r') as f:
        initial_events = len(f.readlines())
    print(f"  Session file has {initial_events} events")

    with open(agent_file, 'r') as f:
        agent_events = len(f.readlines())
    print(f"  Agent file has {agent_events} events")

    # 3. Trigger session start hook
    print("\nTriggering SessionStart hook...")
    success = trigger_session_start(session_id, workspace_path)
    if success:
        print("✓ SessionStart hook executed successfully")
    else:
        print("✗ SessionStart hook failed")
        return False

    # 4. Wait for initial monitoring cycle
    poll_interval = 35  # 30s poll + 5s buffer
    print(f"\nWaiting {poll_interval} seconds for initial file monitoring cycle...")
    for i in range(poll_interval, 0, -5):
        print(f"  {i} seconds remaining...")
        time.sleep(5)

    # 5. Append new event to simulate ongoing activity
    print("\nAppending late event to session file...")
    append_late_event(session_file, session_id)
    print("✓ Late event appended")

    # 6. Wait for second monitoring cycle
    print(f"\nWaiting {poll_interval} seconds for second monitoring cycle...")
    for i in range(poll_interval, 0, -5):
        print(f"  {i} seconds remaining...")
        time.sleep(5)

    # 7. Verify database
    print("\nVerifying database contents...")
    success = verify_database(session_id)

    # 8. Cleanup (optional - keep files for debugging)
    # session_file.unlink()
    # agent_file.unlink()
    print(f"\nTest files preserved for debugging:")
    print(f"  {session_file}")
    print(f"  {agent_file}")

    return success


def main():
    """Main entry point for the test."""
    print("=" * 70)
    print("Claude Code Telemetry - End-to-End Test")
    print("=" * 70)

    try:
        # Check prerequisites
        if not check_prerequisites():
            print("\n✗ Prerequisites not met. Please ensure:")
            print("  1. Redis server is running")
            print("  2. Telemetry server has been run at least once")
            print("  3. The telemetry server is currently running")
            return 1

        # Run the test
        print("\nStarting end-to-end test...")
        success = run_end_to_end_test()

        if success:
            print("\n" + "=" * 70)
            print("✓ ALL TESTS PASSED")
            print("=" * 70)
            return 0
        else:
            print("\n" + "=" * 70)
            print("✗ TESTS FAILED")
            print("=" * 70)
            return 1

    except KeyboardInterrupt:
        print("\n✗ Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())