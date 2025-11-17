# Claude Code Raw Traces Implementation Plan

**Status**: ✅ **Core Implementation Complete** | 🔧 **Critical Issues to Address**  
**Date**: January 2025  
**Branch**: `feature/claude-code-trace-capture-sql-rewrite`

---

## Executive Summary

This document tracks the implementation status and critical issues for the Claude Code telemetry capture and processing pipeline. The core implementation is complete and functional, but several critical issues must be addressed before production deployment.

---

## ✅ What's Already Implemented

### Layer 1: Capture

- ✅ **Session Start Hook** (`src/capture/claude_code/hooks/session_start.py`)

  - Captures session initialization events
  - Sends events to Redis Streams
  - Includes workspace path and session metadata

- ✅ **Hook Filtering** (`src/processing/fast_path/consumer.py:274-286`)
  - Prevents hook-generated events from being written to database
  - Filters by `source` metadata and `hook_type`
  - Only JSONL/transcript monitor events are stored

### Layer 2: Processing

- ✅ **JSONL Monitor** (`src/processing/claude_code/jsonl_monitor.py`)

  - Real-time monitoring of Claude Code JSONL files
  - Incremental file reading with position tracking
  - Dynamic agent file detection via `toolUseResult.agentId`
  - 30-second polling interval
  - Session-based file tracking

- ✅ **Session Monitor** (`src/processing/claude_code/session_monitor.py`)

  - Listens to Redis session_start/end events
  - Tracks active sessions with metadata
  - Historical event catch-up on startup

- ✅ **Database Schema** (`src/processing/database/schema.py`)

  - `claude_raw_traces` table with comprehensive indexed fields
  - Support for main session and agent files
  - zlib compression (7-10x reduction)
  - Generated columns for partitioning

- ✅ **Database Writer** (`src/processing/database/writer.py`)

  - `write_claude_batch_sync()` method
  - Field extraction from JSONL events
  - Batch inserts with compression
  - Sub-10ms batch ingestion

- ✅ **Consumer Integration** (`src/processing/fast_path/consumer.py`)

  - Platform-based event routing
  - Claude Code events → `claude_raw_traces` table
  - Hook event filtering

- ✅ **Server Integration** (`src/processing/server.py`)
  - Claude Code monitor initialization
  - Background thread management
  - Graceful shutdown handling

### Testing

- ✅ **End-to-End Test** (`tests/test_claude_e2e.py`)
  - Complete pipeline validation
  - Session start → JSONL monitoring → Database storage
  - Agent file detection testing
  - Database verification

### Documentation

- ✅ **JSONL Schema Documentation** (`docs/CLAUDE_JSONL_SCHEMA.md`)
  - Comprehensive event type documentation
  - Field descriptions and examples

---

## 🔴 Critical Issues to Address

### Issue 1: File Truncation/Recreation Not Handled

**Severity**: 🔴 **CRITICAL**  
**Location**: `src/processing/claude_code/jsonl_monitor.py:223-258`  
**Impact**: Data loss or duplicate events if JSONL files are deleted/recreated

**Problem**:

- `line_offset` tracking assumes files only grow
- If a file is deleted and recreated, `line_offset` becomes invalid
- No detection of file size decrease (truncation)

**Solution Plan**:

```python
# In _read_new_lines() method:
async def _read_new_lines(self, file_path: Path, file_state: FileState) -> list:
    """Read only new lines from JSONL file since last read."""
    new_events = []

    try:
        stat = file_path.stat()

        # CRITICAL FIX: Detect file truncation/recreation
        if stat.st_size < file_state.last_size:
            logger.warning(f"File {file_path.name} was truncated or recreated, resetting offset")
            file_state.line_offset = 0

        # Also check mtime - if file was recreated, mtime will be newer
        # but size might be smaller initially
        if stat.st_mtime < file_state.last_mtime:
            logger.warning(f"File {file_path.name} mtime decreased, possible recreation")
            file_state.line_offset = 0

        with open(file_path, 'r', encoding='utf-8') as f:
            # ... rest of implementation
```

**Implementation Steps**:

1. Add truncation detection in `_read_new_lines()` method
2. Reset `line_offset = 0` when truncation detected
3. Add logging for truncation events
4. Test with file deletion/recreation scenario

**Test Case**:

- Create session file with 10 events
- Monitor reads all 10 events
- Delete and recreate file with 5 new events
- Verify all 5 new events are captured (not skipped)

---

### Issue 2: JSON Decode Error Handling Bug

**Severity**: 🔴 **CRITICAL**  
**Location**: `src/processing/claude_code/jsonl_monitor.py:223-258`  
**Impact**: Infinite loop on corrupted JSONL lines

**Problem**:

- When JSON decode fails, line is skipped but `line_offset` is not incremented
- Next read will attempt same corrupted line again
- Causes infinite loop and blocks monitoring

**Solution Plan**:

```python
# In _read_new_lines() method:
line_count = 0
for line in f:
    line = line.strip()
    if not line:
        line_count += 1  # Count empty lines too
        continue

    try:
        entry = json.loads(line)
        new_events.append(entry)
        line_count += 1
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in {file_path} at line {file_state.line_offset + line_count + 1}: {e}")
        line_count += 1  # CRITICAL FIX: Increment even on error
        continue

# Update line offset (includes all lines, even corrupted ones)
file_state.line_offset += line_count
```

**Implementation Steps**:

1. Always increment `line_count` even for invalid JSON
2. Update `line_offset` with total lines read (including corrupted)
3. Add line number to error messages for debugging
4. Test with corrupted JSONL file

**Test Case**:

- Create JSONL file with one corrupted line
- Verify monitoring continues past corrupted line
- Verify subsequent valid events are captured

---

### Issue 3: Agent File Detection Race Condition

**Severity**: 🟠 **IMPORTANT**  
**Location**: `src/processing/claude_code/jsonl_monitor.py:310-336`  
**Impact**: Early agent events may be missed

**Problem**:

- Agent files may be created before `toolUseResult.agentId` is detected in main session file
- Events written to agent file before detection are missed

**Solution Plan**:

```python
# In _monitor_session() method:
async def _monitor_session(self, session_id: str, session_info: dict):
    """Monitor JSONL files for a specific session."""
    # ... existing code ...

    # NEW: Scan for existing agent files on first monitoring
    if session_id not in self.monitored_sessions:
        self.monitored_sessions.add(session_id)
        self.session_agents[session_id] = set()

        # Scan project directory for existing agent-*.jsonl files
        agent_files = list(project_dir.glob("agent-*.jsonl"))
        for agent_file in agent_files:
            # Extract agent_id from filename: agent-{agent_id}.jsonl
            agent_id = agent_file.stem.replace("agent-", "")
            if agent_id:
                self.session_agents[session_id].add(agent_id)
                logger.info(f"Found existing agent file: {agent_id}")

    # ... rest of existing code ...
```

**Implementation Steps**:

1. Add agent file scanning on session start
2. Extract agent IDs from existing filenames
3. Add to `session_agents` set before monitoring
4. Test with pre-existing agent files

**Test Case**:

- Create agent file before main session file has toolUseResult
- Verify agent file is monitored immediately
- Verify all agent events are captured

---

### Issue 5: File State Cleanup Missing

**Severity**: 🟠 **IMPORTANT**  
**Location**: `src/processing/claude_code/jsonl_monitor.py:358-373`  
**Impact**: Memory leak over time

**Problem**:

- File states persist after session cleanup
- `file_states` dict grows unbounded
- No cleanup of file states for inactive sessions

**Solution Plan**:

```python
# In _cleanup_inactive_sessions() method:
async def _cleanup_inactive_sessions(self, active_session_ids: Set[str]):
    """Clean up resources for inactive sessions."""
    inactive = self.monitored_sessions - active_session_ids

    for session_id in inactive:
        # Remove from monitored sessions
        self.monitored_sessions.discard(session_id)

        # Remove agent tracking
        if session_id in self.session_agents:
            del self.session_agents[session_id]

        # NEW: Clean up file states for this session's files
        # Find all file states that belong to this session
        session_files_to_remove = []
        for file_path, file_state in self.file_states.items():
            # Check if this file belongs to the inactive session
            # (file paths contain session_id or are in session's project dir)
            if session_id in str(file_path):
                session_files_to_remove.append(file_path)

        for file_path in session_files_to_remove:
            del self.file_states[file_path]
            logger.debug(f"Cleaned up file state for {file_path.name}")

        logger.info(f"Cleaned up inactive session: {session_id}")
```

**Implementation Steps**:

1. Track which files belong to which session
2. Clean up file states when session becomes inactive
3. Add logging for cleanup operations
4. Test with multiple sessions starting/stopping

**Alternative Approach**:

- Use LRU cache with max size for `file_states`
- Or periodically clean up file states older than X hours

---

### Issue 6: Session Monitor Catch-Up Efficiency

**Severity**: 🟠 **IMPORTANT**  
**Location**: `src/processing/claude_code/session_monitor.py:53-71`  
**Impact**: May miss session starts on restart if >1000 events

**Problem**:

- `count=1000` limit may miss events if more than 1000 historical events exist
- No loop to read all historical events

**Solution Plan**:

```python
async def _catch_up_historical_events(self):
    """Process all historical session_start events from Redis."""
    try:
        last_id = "0-0"
        total_processed = 0

        while True:
            # Read batch of historical events
            messages = self.redis_client.xread(
                {"telemetry:events": last_id},
                count=1000,
                block=0  # Non-blocking
            )

            if not messages:
                break  # No more events

            for stream, msgs in messages:
                for msg_id, fields in msgs:
                    await self._process_redis_message(msg_id, fields)
                    last_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    total_processed += 1

            # If we got fewer than count, we're done
            if len(msgs) < 1000:
                break

        if total_processed > 0:
            logger.info(f"Processed {total_processed} historical Claude Code events")

    except Exception as e:
        logger.warning(f"Error catching up historical events: {e}")
```

**Implementation Steps**:

1. Loop until no more events returned
2. Track total processed count
3. Break early if fewer than count returned
4. Test with >1000 historical events

---

### Issue 7: Missing Field Validation

**Severity**: 🟡 **MINOR**  
**Location**: `src/processing/claude_code/jsonl_monitor.py:260-308`  
**Impact**: Invalid events may be written to database

**Problem**:

- No validation of required fields before processing
- Missing `sessionId`, `type`, or `timestamp` could cause issues

**Solution Plan**:

```python
async def _process_event(self, entry_data: dict, session_id: str, session_info: dict):
    """Process a single JSONL event."""
    try:
        # Validate required fields
        if not entry_data.get("type"):
            logger.warning(f"Skipping event without type field: {entry_data.get('uuid', 'unknown')}")
            return

        if not entry_data.get("sessionId") and not session_id:
            logger.warning(f"Skipping event without sessionId: {entry_data.get('uuid', 'unknown')}")
            return

        # Extract timestamp with fallback
        timestamp = entry_data.get("timestamp", "")
        if not timestamp:
            timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
            logger.debug(f"Event missing timestamp, using current time: {entry_data.get('uuid', 'unknown')}")

        # ... rest of processing
```

**Implementation Steps**:

1. Add validation for `type` field
2. Add validation for `sessionId` (with fallback to parameter)
3. Add logging for validation failures
4. Test with invalid events

---

## 📋 Implementation Priority

### Must Fix Before Merge (Critical)

1. ✅ Issue 1: File truncation/recreation handling
2. ✅ Issue 2: JSON decode error handling
3. ✅ Issue 5: File state cleanup

### Should Fix Soon (Important)

4. ✅ Issue 4: Agent file detection race condition
5. ✅ Issue 6: Session monitor catch-up efficiency

### Nice to Have (Minor)

6. ✅ Issue 3: Poll interval documentation
7. ✅ Issue 7: Field validation

---

## 🧪 Testing Plan

### Unit Tests Needed

- [ ] File truncation detection
- [ ] Corrupted JSONL handling
- [ ] Agent file scanning on session start
- [ ] File state cleanup
- [ ] Session monitor catch-up with >1000 events

### Integration Tests Needed

- [ ] File deletion/recreation scenario
- [ ] Agent file created before detection
- [ ] Multiple sessions cleanup
- [ ] Corrupted JSONL file recovery

### End-to-End Tests Needed

- [ ] Full pipeline with file truncation
- [ ] Agent file race condition
- [ ] Memory leak verification (long-running test)

---

## 📝 Code Review Checklist

Before merging, verify:

- [ ] File truncation detection implemented
- [ ] JSON decode errors don't cause infinite loops
- [ ] File states are cleaned up on session end
- [ ] Agent files are scanned on session start
- [ ] Session monitor catches up on all historical events
- [ ] Field validation prevents invalid events
- [ ] All tests pass
- [ ] Documentation updated

---

## 🔄 Follow-up Work (Post-Merge)

### Performance Optimizations

- [ ] LRU cache for file states (prevent unbounded growth)
- [ ] Configurable poll interval
- [ ] Batch file reads for multiple sessions

### Reliability Improvements

- [ ] Retry logic for file read failures
- [ ] Exponential backoff for errors
- [ ] Health check endpoints

### Features

- [ ] Metrics derivation for Claude Code events
- [ ] Conversation reconstruction from raw traces
- [ ] Layer 3 CLI commands for Claude Code analytics
- [ ] Performance optimization for very large JSONL files (>1GB)

---

## Related Documentation

- `docs/CLAUDE_JSONL_SCHEMA.md` - JSONL file format documentation
- `docs/architecture/layer2_db_architecture.md` - Database schema details
- `src/processing/claude_code/jsonl_monitor.py` - Implementation code
- `tests/test_claude_e2e.py` - End-to-end test suite

---

**Last Updated**: January 2025  
**Status**: Core implementation complete, critical fixes in progress
