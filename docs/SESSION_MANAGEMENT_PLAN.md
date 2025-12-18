# Claude Code Session Management Implementation Plan

## Executive Summary

This document outlines a comprehensive plan for implementing robust session management for Claude Code telemetry, addressing critical gaps in persistence, recovery, and lifecycle management.

### Current State
- Sessions are tracked **only in-memory** (`active_sessions` dictionary)
- Session data is **lost on server restart**
- Session end hooks fire correctly but **don't persist** any data
- The `conversations` table exists but is **never populated**
- No mechanism for **timeout handling** or **session recovery**

### Proposed Solution
Implement database-persisted session management using SQLite, providing:
- Session persistence to survive server restarts
- Automatic recovery of incomplete sessions
- Timeout handling for abandoned sessions
- Complete session lifecycle tracking
- Metrics calculation and conversation reconstruction

---

## 1. Current Implementation Analysis

### 1.1 Session End Hook Status

**Location**: `src/capture/claude_code/hooks/session_end.py`

The session end hook **IS working correctly** from a technical perspective:
- Fires when Claude Code closes
- Receives `transcript_path` and session metadata
- Creates `SESSION_END` event and enqueues to Redis

**However**, it's **NOT resolving sessions properly** because:
- Only removes session from in-memory dictionary
- Doesn't update any database records
- Doesn't calculate final metrics
- Session data is effectively lost after removal

### 1.2 Session Tracking Architecture

**Current Flow**:
```
SessionStart Hook → Redis Stream → SessionMonitor (in-memory) → Active Sessions Dict
                                                                        ↓
JSONL Monitor ← ← ← ← ← ← ← ← ← ← Polls active sessions ← ← ← ← ← ← ←
     ↓
Redis Stream → Fast Path → SQLite (raw_traces only)

SessionEnd Hook → Redis Stream → SessionMonitor → Remove from memory (data lost!)
```

### 1.3 Database Schema Analysis

The `conversations` table already exists with perfect schema:
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    workspace_hash TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,              -- EXISTS but never populated!
    context TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    interaction_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    -- ... other metrics fields
);
```

**Critical Finding**: This table is defined but **completely unused**.

### 1.4 Key Problems Identified

1. **No Persistence**: Server restart = all session data lost
2. **No Recovery**: Can't resume tracking interrupted sessions
3. **No Finalization**: Sessions just disappear without proper closure
4. **No Timeouts**: Abandoned sessions stay in memory forever
5. **No Metrics**: Session statistics are never calculated
6. **Missing Slow Path**: ConversationWorker doesn't exist

---

## 2. Detailed Implementation Plan

### Phase 1: Core Session Persistence

#### 2.1.1 Create Session Persistence Module

**New File**: `src/processing/claude_code/session_persistence.py`

```python
class SessionPersistence:
    """
    Manages persistent session state in SQLite database.
    Provides durability and recovery capabilities.
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    async def save_session_start(
        self,
        session_id: str,
        workspace_hash: str,
        workspace_path: str,
        metadata: dict
    ) -> None:
        """
        Persist new session to conversations table.
        Called when session_start event is received.
        """

    async def save_session_end(
        self,
        session_id: str,
        end_reason: str = 'normal'  # 'normal', 'timeout', 'crash'
    ) -> None:
        """
        Mark session as ended with timestamp and reason.
        Called when session_end event is received or timeout occurs.
        """

    async def recover_active_sessions(self) -> Dict[str, dict]:
        """
        Query database for sessions without ended_at.
        Called on server startup to restore state.
        Returns dict of session_id -> session_info
        """

    async def mark_session_timeout(
        self,
        session_id: str,
        last_activity: datetime
    ) -> None:
        """
        Mark abandoned session as timed out.
        Called by cleanup task for stale sessions.
        """
```

#### 2.1.2 Integrate with SessionMonitor

**Modify**: `src/processing/claude_code/session_monitor.py`

```python
class ClaudeCodeSessionMonitor:
    def __init__(self, redis_client, sqlite_client):
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.persistence = SessionPersistence(sqlite_client)  # NEW
        self.active_sessions = {}  # Keep for fast lookups

    async def _process_session_start(self, event):
        # Add to in-memory dict (fast path)
        self.active_sessions[session_id] = session_info

        # Persist to database (durable)
        await self.persistence.save_session_start(
            session_id, workspace_hash, workspace_path, metadata
        )

    async def _process_session_end(self, event):
        # Update database first (ensure durability)
        await self.persistence.save_session_end(session_id)

        # Then remove from memory
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
```

### Phase 2: Recovery & Resilience

#### 2.2.1 Startup Recovery Mechanism

```python
async def start(self):
    """Enhanced startup with session recovery."""
    self.running = True

    # Step 1: Recover incomplete sessions from last run
    recovered = await self.persistence.recover_active_sessions()

    for session_id, session_info in recovered.items():
        # Restore to active sessions
        self.active_sessions[session_id] = session_info

        # Check if JSONL file still exists
        jsonl_path = self._get_jsonl_path(session_info)
        if jsonl_path.exists():
            logger.info(f"Recovered active session: {session_id}")
        else:
            # JSONL gone = session likely crashed
            logger.warning(f"Recovered orphaned session: {session_id}")
            await self.persistence.save_session_end(session_id, 'crash')

    # Step 2: Catch up on events that occurred while down
    await self._catch_up_historical_events()

    # Step 3: Start normal monitoring
    await self._listen_redis_events()
```

#### 2.2.2 Session Timeout Handling

```python
class SessionTimeoutManager:
    """
    Handles cleanup of abandoned sessions.
    Runs periodically to prevent memory leaks.
    """

    DEFAULT_TIMEOUT_HOURS = 24
    CLEANUP_INTERVAL_SECONDS = 3600  # Run hourly

    async def cleanup_stale_sessions(self):
        """Mark inactive sessions as timed out."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=self.DEFAULT_TIMEOUT_HOURS
        )

        # Query database for old active sessions
        stale = await self.sqlite_client.query("""
            SELECT session_id, started_at
            FROM conversations
            WHERE platform = 'claude_code'
              AND ended_at IS NULL
              AND started_at < ?
        """, (cutoff_time,))

        for session in stale:
            logger.warning(f"Timing out stale session: {session['session_id']}")
            await self.persistence.mark_session_timeout(
                session['session_id'],
                last_activity=session['started_at']
            )

            # Remove from memory if present
            self.active_sessions.pop(session['session_id'], None)
```

### Phase 3: Event Processing Enhancement

#### 2.3.1 Enable Session Lifecycle Events in Database

**Modify**: `src/processing/fast_path/consumer.py`

```python
# CURRENT CODE (problematic):
if platform == 'claude_code':
    source = event.get('metadata', {}).get('source', '')
    if source in ('jsonl_monitor', 'transcript_monitor'):
        claude_events.append(event)
    else:
        logger.debug(f"Skipping Claude Code hook event")  # BAD!

# NEW CODE (fixed):
if platform == 'claude_code':
    source = event.get('metadata', {}).get('source', '')
    event_type = event.get('event_type', '')

    # Include JSONL events AND session lifecycle events
    if (source in ('jsonl_monitor', 'transcript_monitor') or
        event_type in ('session_start', 'session_end')):
        claude_events.append(event)
    else:
        # Only skip non-essential hook events
        logger.debug(f"Skipping non-essential hook event")
```

#### 2.3.2 Implement Conversation Worker (Slow Path)

**New File**: `src/processing/slow_path/conversation_worker.py`

```python
class ConversationWorker:
    """
    Async worker that processes completed sessions.
    Reads from CDC stream and builds conversation structure.
    """

    def __init__(self, redis_client, sqlite_client):
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.consumer_group = "conversation-workers"

    async def start(self):
        """Main worker loop."""
        while True:
            # Read CDC events
            messages = await self._read_cdc_stream()

            for msg in messages:
                if msg['event_type'] == 'session_end':
                    await self._process_completed_session(msg['session_id'])

    async def _process_completed_session(self, session_id: str):
        """Build conversation from raw events."""

        # 1. Query all events for this session
        events = await self.sqlite_client.query("""
            SELECT * FROM claude_raw_traces
            WHERE session_id = ?
            ORDER BY timestamp
        """, (session_id,))

        # 2. Build conversation structure
        conversation = self._reconstruct_conversation(events)

        # 3. Calculate metrics
        metrics = {
            'interaction_count': len(conversation['interactions']),
            'total_tokens': sum(e.get('tokens', 0) for e in events),
            'acceptance_rate': self._calculate_acceptance_rate(events),
            'total_changes': self._count_file_changes(events),
        }

        # 4. Update conversations table
        await self.sqlite_client.execute("""
            UPDATE conversations
            SET
                interaction_count = ?,
                total_tokens = ?,
                acceptance_rate = ?,
                total_changes = ?,
                metadata = ?,
                tool_sequence = ?
            WHERE session_id = ?
        """, (
            metrics['interaction_count'],
            metrics['total_tokens'],
            metrics['acceptance_rate'],
            metrics['total_changes'],
            json.dumps(conversation['metadata']),
            json.dumps(conversation['tool_sequence']),
            session_id
        ))
```

---

## 3. Technical Architecture

### 3.1 Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Layer 1: Capture                         │
├───────────────────────────────┬─────────────────────────────────┤
│     Session Start Hook        │        Session End Hook         │
└───────────┬───────────────────┴──────────────┬──────────────────┘
            │                                   │
            ▼                                   ▼
┌───────────────────────────────────────────────────────────────────┐
│                Redis Stream (telemetry:message_queue)             │
└───────────┬──────────────────────────────────┬────────────────────┘
            │                                   │
            ▼                                   ▼
┌───────────────────────────────────────────────────────────────────┐
│                      Layer 2: Processing                          │
├───────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────┐    ┌────────────────────────────┐  │
│  │    Session Monitor        │    │     Fast Path Consumer     │  │
│  │  - In-memory tracking     │    │  - Write to raw_traces     │  │
│  │  - SQLite persistence ←───┼────┼─ Include lifecycle events  │  │
│  │  - Recovery on startup    │    │  - Publish CDC             │  │
│  │  - Timeout handling       │    └────────────┬───────────────┘  │
│  └──────────────┬────────────┘                 │                  │
│                 │                               ▼                  │
│                 ▼                    ┌──────────────────────────┐ │
│  ┌──────────────────────────┐       │  Conversation Worker     │ │
│  │   SQLite Database        │       │  - Read CDC stream       │ │
│  │  - conversations table ◄─┼───────┼─ Process ended sessions  │ │
│  │  - raw_traces table      │       │  - Calculate metrics     │ │
│  └──────────────────────────┘       └──────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2 Session State Transitions

```
                    ┌─────────────┐
                    │   CREATED    │
                    └──────┬───────┘
                           │ session_start event
                           ▼
                    ┌─────────────┐
                ┌───│   ACTIVE     │───┐
                │   └──────┬───────┘   │
                │          │           │ timeout (24h)
    crash/      │          │           │
    restart     │          │           ▼
                │          │    ┌─────────────┐
                │          │    │  TIMED_OUT  │
                │          │    └─────────────┘
                │          │ session_end event
                │          ▼
                │   ┌─────────────┐
                └──►│  COMPLETED   │
                    └─────────────┘
```

### 3.3 Data Flow

1. **Session Start**:
   - Hook → Redis → Monitor → Memory + SQLite (conversations)

2. **During Session**:
   - JSONL Monitor → Redis → Fast Path → SQLite (raw_traces)

3. **Session End**:
   - Hook → Redis → Monitor → SQLite (update ended_at)
   - CDC → Conversation Worker → SQLite (update metrics)

4. **Server Restart**:
   - SQLite (query incomplete) → Monitor → Memory (restored)

---

## 4. Implementation Roadmap

### Week 1: Foundation
- [ ] Create `session_persistence.py` module
- [ ] Add database write methods
- [ ] Integrate with SessionMonitor
- [ ] Test basic persistence

### Week 2: Recovery
- [ ] Implement startup recovery
- [ ] Add timeout manager
- [ ] Test restart scenarios
- [ ] Verify recovery works

### Week 3: Processing
- [ ] Enable lifecycle events in fast path
- [ ] Create conversation worker
- [ ] Implement CDC processing
- [ ] Test end-to-end flow

### Week 4: Polish
- [ ] Add comprehensive logging
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] Integration tests

---

## 5. Testing Strategy

### 5.1 Test Scenarios

#### Scenario 1: Normal Flow
```
1. Start Claude Code session
2. Generate events (tool calls, completions)
3. End session normally
4. Verify: conversations table has complete record
```

#### Scenario 2: Server Restart
```
1. Start Claude Code session
2. Generate some events
3. Kill telemetry server (simulate crash)
4. Restart telemetry server
5. Verify: session recovered and tracking continues
6. End session normally
7. Verify: complete session in database
```

#### Scenario 3: Timeout Handling
```
1. Start Claude Code session
2. Generate events
3. Kill Claude Code (simulate crash, no end hook)
4. Wait for timeout period
5. Verify: session marked as timed out in database
```

#### Scenario 4: Multiple Sessions
```
1. Start multiple Claude Code sessions
2. Restart server during active sessions
3. Verify: all sessions recovered correctly
4. End sessions in different orders
5. Verify: no data mixing between sessions
```

### 5.2 Edge Cases

- JSONL file deleted during session
- Database write failures
- Redis connection loss
- Concurrent session starts
- Rapid start/stop cycles
- Clock skew issues

### 5.3 Performance Tests

- Measure overhead of database writes
- Test with 100+ concurrent sessions
- Verify <10ms write latency
- Check memory usage with many sessions

### 5.4 End-to-End Test Implementation

The existing end-to-end test (`tests/test_claude_e2e.py`) must be enhanced to fully verify session lifecycle management and database persistence.

#### 5.4.1 Current Test Coverage

The existing test validates:
- SessionStart hook triggers monitoring
- JSONL files are read and processed
- Events are stored in `claude_raw_traces` table
- Agent files are detected and monitored
- Token counts and metadata are preserved

**Missing Coverage**:
- Session end hook execution
- Session persistence in `conversations` table
- Session recovery after restart
- Session timeout scenarios

#### 5.4.2 Enhanced End-to-End Test Requirements

**New File**: `tests/test_claude_session_lifecycle_e2e.py`

```python
def test_complete_session_lifecycle():
    """
    Test the full session lifecycle including persistence and recovery.
    """

    # Phase 1: Session Start
    session_id = trigger_session_start(workspace_path)

    # Verify session is tracked in memory
    assert session_id in monitor.active_sessions

    # Verify session is persisted to database
    session = query_conversations_table(session_id)
    assert session is not None
    assert session['started_at'] is not None
    assert session['ended_at'] is None  # Still active
    assert session['platform'] == 'claude_code'

    # Phase 2: Generate Events
    create_jsonl_events(session_id)
    wait_for_processing()

    # Verify events in raw_traces
    events = query_raw_traces(session_id)
    assert len(events) > 0

    # Phase 3: Session End
    trigger_session_end(session_id)
    wait_for_processing()

    # Verify session is removed from memory
    assert session_id not in monitor.active_sessions

    # Verify session is closed in database
    session = query_conversations_table(session_id)
    assert session['ended_at'] is not None
    assert session['interaction_count'] > 0
    assert session['total_tokens'] > 0
```

#### 5.4.3 Database Verification Functions

```python
def verify_session_in_conversations(session_id: str) -> Dict[str, Any]:
    """
    Verify session exists in conversations table with correct fields.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id, session_id, platform,
            workspace_hash, started_at, ended_at,
            interaction_count, total_tokens,
            metadata
        FROM conversations
        WHERE session_id = ?
    """, (session_id,))

    row = cursor.fetchone()
    if not row:
        raise AssertionError(f"Session {session_id} not found in conversations table")

    session = {
        'id': row[0],
        'session_id': row[1],
        'platform': row[2],
        'workspace_hash': row[3],
        'started_at': row[4],
        'ended_at': row[5],
        'interaction_count': row[6],
        'total_tokens': row[7],
        'metadata': json.loads(row[8]) if row[8] else {}
    }

    # Assertions
    assert session['platform'] == 'claude_code'
    assert session['session_id'] == session_id

    if session['ended_at']:
        # Completed session should have metrics
        assert session['interaction_count'] >= 0
        assert session['total_tokens'] >= 0

    return session

def verify_active_sessions_in_db() -> List[str]:
    """
    Query for all active sessions (ended_at IS NULL).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT session_id
        FROM conversations
        WHERE platform = 'claude_code' AND ended_at IS NULL
    """)

    return [row[0] for row in cursor.fetchall()]
```

#### 5.4.4 Server Restart Test

```python
def test_session_recovery_after_restart():
    """
    Test that sessions are recovered after server restart.
    """

    # Step 1: Start multiple sessions
    sessions = []
    for i in range(3):
        session_id = trigger_session_start(f"workspace_{i}")
        sessions.append(session_id)
        create_jsonl_events(session_id)

    wait_for_processing()

    # Verify all sessions are active in DB
    active = verify_active_sessions_in_db()
    for sid in sessions:
        assert sid in active

    # Step 2: Simulate server crash (no clean shutdown)
    kill_telemetry_server(signal='SIGKILL')  # Hard kill

    # Sessions should still be in DB with ended_at=NULL
    active = verify_active_sessions_in_db()
    for sid in sessions:
        assert sid in active

    # Step 3: Restart server
    start_telemetry_server()
    wait_for_startup()

    # Verify sessions are recovered
    for sid in sessions:
        assert sid in monitor.active_sessions

    # Step 4: End one session normally
    trigger_session_end(sessions[0])
    wait_for_processing()

    # Verify ended session is closed
    session = query_conversations_table(sessions[0])
    assert session['ended_at'] is not None

    # Other sessions still active
    active = verify_active_sessions_in_db()
    assert sessions[0] not in active
    assert sessions[1] in active
    assert sessions[2] in active
```

#### 5.4.5 Timeout Test

```python
def test_session_timeout():
    """
    Test that abandoned sessions are timed out.
    """

    # Start session
    session_id = trigger_session_start(workspace_path)
    create_jsonl_events(session_id)
    wait_for_processing()

    # Verify session is active
    session = query_conversations_table(session_id)
    assert session['ended_at'] is None

    # Simulate Claude Code crash (no end hook)
    # Just delete JSONL files to simulate crash
    delete_jsonl_files(session_id)

    # Fast-forward time or trigger timeout check
    trigger_timeout_check(hours_ago=25)  # Simulate 25 hours passed

    # Verify session is marked as timed out
    session = query_conversations_table(session_id)
    assert session['ended_at'] is not None
    assert 'timeout' in session['metadata'].get('end_reason', '')
```

#### 5.4.6 Update Existing Test File

**Modify**: `tests/test_claude_e2e.py`

Add these functions to the existing test:

```python
def trigger_session_end(session_id: str, workspace_path: str) -> bool:
    """
    Trigger SessionEnd hook programmatically.
    """
    hook_input = {
        "session_id": session_id,
        "workspace_path": workspace_path,
        "transcript_path": f"/path/to/transcript_{session_id}.md",
        "session_end_hook_active": True
    }

    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(hook_input))

    try:
        from src.capture.claude_code.hooks.session_end import SessionEndHook
        hook = SessionEndHook()
        result = hook.execute()
        return result == 0
    finally:
        sys.stdin = old_stdin

def verify_conversations_table(session_id: str) -> Dict[str, Any]:
    """
    Verify session in conversations table.
    """
    db_path = Path.home() / ".blueplane" / "telemetry.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check conversations table
        cursor.execute("""
            SELECT
                session_id, platform, workspace_hash,
                started_at, ended_at,
                interaction_count, total_tokens
            FROM conversations
            WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if row:
            print(f"✓ Session found in conversations table:")
            print(f"  Platform: {row[1]}")
            print(f"  Started: {row[3]}")
            print(f"  Ended: {row[4] or 'Still active'}")
            print(f"  Interactions: {row[5]}")
            print(f"  Tokens: {row[6]}")

            return {
                'session_id': row[0],
                'platform': row[1],
                'workspace_hash': row[2],
                'started_at': row[3],
                'ended_at': row[4],
                'interaction_count': row[5],
                'total_tokens': row[6]
            }
        else:
            print(f"✗ Session NOT found in conversations table")
            return None

    finally:
        conn.close()

def enhanced_verify_database(session_id: str) -> bool:
    """
    Enhanced verification including conversations table.
    """
    # First do existing raw_traces verification
    if not verify_database(session_id):
        return False

    # Then verify conversations table
    print("\nVerifying conversations table...")
    session = verify_conversations_table(session_id)

    if not session:
        print("✗ Session not persisted to conversations table")
        return False

    if not session['started_at']:
        print("✗ Session missing started_at timestamp")
        return False

    # If test includes session end, verify it's closed
    if SESSION_END_TESTED and not session['ended_at']:
        print("✗ Session not properly closed (ended_at is NULL)")
        return False

    print("✓ Session lifecycle properly tracked in database")
    return True
```

#### 5.4.7 Test Execution Matrix

| Test Scenario | Verifications |
|--------------|---------------|
| **Normal Session Flow** | ✓ started_at set<br>✓ Active in memory<br>✓ Events in raw_traces<br>✓ ended_at set on close<br>✓ Metrics calculated |
| **Server Restart** | ✓ Sessions persist in DB<br>✓ Recovery on startup<br>✓ JSONL monitoring resumes<br>✓ Can end recovered sessions |
| **Session Timeout** | ✓ Stale sessions detected<br>✓ ended_at set with timeout<br>✓ Removed from memory<br>✓ Metadata shows timeout reason |
| **Concurrent Sessions** | ✓ Multiple sessions tracked<br>✓ No data mixing<br>✓ Independent lifecycles<br>✓ Correct parent/child relations |
| **Error Scenarios** | ✓ DB write failures logged<br>✓ Recovery failures handled<br>✓ Partial data preserved<br>✓ Service stays running |

---

## 6. Risk Mitigation

### 6.1 Backward Compatibility
- Existing raw_traces data remains unchanged
- New persistence is additive, not breaking
- Gradual rollout possible with feature flags

### 6.2 Failure Modes

**Database Write Failures**:
- Log errors but don't block session tracking
- Use in-memory fallback for critical operations
- Alert on repeated failures

**Recovery Failures**:
- Continue with new sessions if recovery fails
- Log detailed errors for debugging
- Don't crash the entire service

**Performance Degradation**:
- Monitor write latencies
- Use batching for bulk operations
- Consider connection pooling if needed

### 6.3 Migration Strategy

1. **Phase 1**: Deploy persistence module (no behavior change)
2. **Phase 2**: Enable database writes (dual tracking)
3. **Phase 3**: Enable recovery on startup
4. **Phase 4**: Enable timeout handling
5. **Phase 5**: Deploy conversation worker

Each phase can be rolled back independently.

---

## 7. Success Metrics

### 7.1 Functional Metrics
- 100% of sessions have `started_at` timestamp
- 95%+ of sessions have `ended_at` (allowing for crashes)
- Zero data loss on server restart
- <1% sessions marked as timeout (healthy endings)

### 7.2 Performance Metrics
- <10ms P95 latency for session operations
- <100MB memory usage for 1000 sessions
- <5s conversation reconstruction time
- Zero blocking operations in fast path

### 7.3 Reliability Metrics
- 99.9% uptime for session tracking
- 100% recovery success rate
- Zero data corruption incidents
- <1min MTTR for session issues

---

## 8. Future Enhancements

### 8.1 Short Term (Next Quarter)
- Add session export capabilities
- Implement session replay features
- Add real-time session monitoring dashboard
- Support for session merging (multiple windows)

### 8.2 Long Term (Next Year)
- Distributed session tracking (multiple machines)
- Session analytics and insights
- Machine learning on session patterns
- Cross-platform session correlation

---

## Appendix A: Database Schema Reference

```sql
-- Existing schema (to be utilized)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    external_session_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    workspace_hash TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,              -- Will be populated!

    -- JSON fields for rich data
    context TEXT DEFAULT '{}',       -- Workspace context
    metadata TEXT DEFAULT '{}',      -- Session metadata
    tool_sequence TEXT DEFAULT '[]', -- Tool call sequence
    acceptance_decisions TEXT DEFAULT '[]', -- User decisions

    -- Metrics (to be calculated)
    interaction_count INTEGER DEFAULT 0,
    acceptance_rate REAL,
    total_tokens INTEGER DEFAULT 0,
    total_changes INTEGER DEFAULT 0,

    -- Indexes for performance
    UNIQUE(external_session_id, platform)
);

CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_platform ON conversations(platform);
CREATE INDEX idx_conversations_active ON conversations(ended_at)
    WHERE ended_at IS NULL;  -- Optimize recovery queries
```

## Appendix B: Configuration Options

```python
# Proposed configuration structure
SESSION_CONFIG = {
    'persistence': {
        'enabled': True,
        'database': 'sqlite',  # Future: support other backends
        'table': 'conversations',
    },
    'recovery': {
        'enabled': True,
        'startup_recovery': True,
        'check_jsonl_exists': True,
    },
    'timeouts': {
        'enabled': True,
        'inactive_hours': 24,
        'cleanup_interval_seconds': 3600,
    },
    'metrics': {
        'calculate_on_end': True,
        'include_token_counts': True,
        'track_acceptance_rate': True,
    }
}
```

---

This plan provides a complete, production-ready approach to session management that addresses all identified issues while maintaining high performance and reliability.