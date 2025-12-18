# Blueplane Telemetry Core - Outputs and Models Reference

**Generated**: November 11, 2025

---

## Overview

This document describes the outputs, data models, and tracked metrics in the Blueplane Telemetry Core system.

---

## 1. AI Models Tracked

The system captures and tracks usage of various AI models used in Cursor and Claude Code:

### Cursor Models
- **Claude 3.5 Sonnet** (`claude-sonnet-4-5-20250929`, `claude-3-5-sonnet-20241022`)
- **Claude 3 Opus** (`claude-3-opus-20240229`)
- **Claude 3 Sonnet** (`claude-3-sonnet-20240229`)
- **Claude 3 Haiku** (`claude-3-haiku-20240307`)
- **GPT-4** (various versions when used)
- **Custom models** (extensible)

### Model Metadata Captured
- Model name/identifier
- Token usage (prompt tokens, completion tokens, total)
- Response duration
- Generation ID
- Workspace context

---

## 2. Event Types and Outputs

### 2.1 Core Event Schema

All events follow this standard structure:

```json
{
  "event_id": "uuid-v4",
  "timestamp": "2025-11-11T10:30:45.123Z",
  "platform": "cursor|claude_code",
  "session_id": "internal-uuid",
  "external_session_id": "curs_1731320400_abc123",
  "event_type": "user_prompt|assistant_response|file_edit|...",
  "hook_type": "beforeSubmitPrompt|afterAgentResponse|...",
  "metadata": {
    "workspace_hash": "a1b2c3d4",
    "project_hash": "e5f6g7h8",
    "model": "claude-sonnet-4-5-20250929",
    "git_branch_hash": "i9j0k1l2",
    "sequence_num": 42,
    "pid": 12345
  },
  "payload": {
    "event_specific_data": "..."
  }
}
```

### 2.2 Event Type Details

#### Session Events
**SESSION_START**
```json
{
  "event_type": "session_start",
  "hook_type": "session",
  "payload": {
    "workspace_hash": "a1b2c3d4",
    "pid": 12345
  }
}
```

**SESSION_END**
```json
{
  "event_type": "session_end",
  "hook_type": "stop",
  "payload": {
    "session_duration_ms": 3600000,
    "total_interactions": 47
  }
}
```

#### User Interaction Events
**USER_PROMPT**
```json
{
  "event_type": "user_prompt",
  "hook_type": "beforeSubmitPrompt",
  "payload": {
    "generation_id": "gen-uuid",
    "prompt_length": 250,
    "workspace_root": "/path/to/project",
    "context_files": 5
  }
}
```

**ASSISTANT_RESPONSE**
```json
{
  "event_type": "assistant_response",
  "hook_type": "afterAgentResponse",
  "metadata": {
    "model": "claude-sonnet-4-5-20250929"
  },
  "payload": {
    "generation_id": "gen-uuid",
    "response_length": 1500,
    "tokens_used": 1250,
    "duration_ms": 3400
  }
}
```

#### Code Change Events
**FILE_EDIT**
```json
{
  "event_type": "file_edit",
  "hook_type": "afterFileEdit",
  "payload": {
    "file_extension": "py",
    "lines_added": 12,
    "lines_removed": 5,
    "operation": "edit"
  }
}
```

**FILE_READ**
```json
{
  "event_type": "file_read",
  "hook_type": "beforeReadFile",
  "payload": {
    "file_extension": "ts",
    "file_size": 2048
  }
}
```

#### Tool Execution Events
**MCP_EXECUTION**
```json
{
  "event_type": "mcp_execution",
  "hook_type": "beforeMCPExecution|afterMCPExecution",
  "payload": {
    "tool_name": "read_file",
    "input_size": 128,
    "duration_ms": 45,
    "success": true,
    "error_message": null
  }
}
```

**SHELL_EXECUTION**
```json
{
  "event_type": "shell_execution",
  "hook_type": "beforeShellExecution|afterShellExecution",
  "payload": {
    "command_length": 25,
    "exit_code": 0,
    "duration_ms": 1200,
    "output_lines": 15
  }
}
```

#### Database Trace Events (Cursor-specific)
**DATABASE_TRACE**
```json
{
  "event_type": "database_trace",
  "hook_type": "DatabaseTrace",
  "metadata": {
    "model": "claude-3-opus-20240229",
    "source": "database_monitor"
  },
  "payload": {
    "trace_type": "generation",
    "generation_id": "gen-uuid",
    "data_version": 12345,
    "tokens_used": 1500,
    "completion_tokens": 800,
    "prompt_tokens": 700
  }
}
```

---

## 3. Database Schema (SQLite)

### 3.1 Raw Traces Table

**Table**: `raw_traces`

Stores compressed raw event data with fast query indexes.

```sql
CREATE TABLE raw_traces (
    -- Core identification
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Event metadata (indexed)
    event_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    platform TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    -- Context fields
    workspace_hash TEXT,
    model TEXT,
    tool_name TEXT,
    
    -- Metrics (for fast filtering)
    duration_ms INTEGER,
    tokens_used INTEGER,
    lines_added INTEGER,
    lines_removed INTEGER,
    
    -- Compressed payload (zlib, 7-10x compression)
    event_data BLOB NOT NULL,
    
    -- Generated partitioning columns
    event_date DATE GENERATED ALWAYS AS (DATE(timestamp)),
    event_hour INTEGER GENERATED ALWAYS AS (CAST(strftime('%H', timestamp) AS INTEGER))
);
```

**Indexes:**
- `idx_session_time` - Fast session-based queries
- `idx_event_type_time` - Filter by event type
- `idx_date_hour` - Time-based partitioning
- `idx_timestamp` - Chronological queries

**Example Queries:**

```sql
-- Get all events for a session
SELECT sequence, event_type, timestamp, model, tokens_used
FROM raw_traces
WHERE session_id = 'session-uuid'
ORDER BY timestamp;

-- Daily token usage by model
SELECT 
    event_date,
    model,
    SUM(tokens_used) as total_tokens,
    COUNT(*) as event_count
FROM raw_traces
WHERE model IS NOT NULL
GROUP BY event_date, model
ORDER BY event_date DESC;

-- File edit statistics
SELECT 
    event_date,
    SUM(lines_added) as total_added,
    SUM(lines_removed) as total_removed,
    COUNT(*) as edit_count
FROM raw_traces
WHERE event_type = 'file_edit'
GROUP BY event_date;

-- Most active hours
SELECT 
    event_hour,
    COUNT(*) as event_count
FROM raw_traces
GROUP BY event_hour
ORDER BY event_count DESC;
```

### 3.2 Conversations Table

**Table**: `conversations`

Reconstructed conversation threads with metrics.

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    external_session_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    workspace_hash TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    
    -- JSON fields
    context TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    tool_sequence TEXT DEFAULT '[]',
    acceptance_decisions TEXT DEFAULT '[]',
    
    -- Metrics
    interaction_count INTEGER DEFAULT 0,
    acceptance_rate REAL,
    total_tokens INTEGER DEFAULT 0,
    total_changes INTEGER DEFAULT 0,
    
    UNIQUE(external_session_id, platform)
);
```

**Example Queries:**

```sql
-- Recent conversations
SELECT 
    external_session_id,
    platform,
    started_at,
    ended_at,
    interaction_count,
    acceptance_rate,
    total_tokens
FROM conversations
ORDER BY started_at DESC
LIMIT 10;

-- Average acceptance rate by workspace
SELECT 
    workspace_hash,
    AVG(acceptance_rate) as avg_acceptance,
    COUNT(*) as conversation_count,
    SUM(total_tokens) as total_tokens
FROM conversations
GROUP BY workspace_hash;
```

### 3.3 Conversation Turns Table

**Table**: `conversation_turns`

Individual turns within conversations.

```sql
CREATE TABLE conversation_turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    turn_number INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    turn_type TEXT CHECK (turn_type IN ('user_prompt', 'assistant_response', 'tool_use')),
    
    content_hash TEXT,
    metadata TEXT DEFAULT '{}',
    tokens_used INTEGER,
    latency_ms INTEGER,
    tools_called TEXT,
    
    UNIQUE(conversation_id, turn_number)
);
```

### 3.4 Code Changes Table

**Table**: `code_changes`

Detailed code modification tracking.

```sql
CREATE TABLE code_changes (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    turn_id TEXT REFERENCES conversation_turns(id),
    timestamp TIMESTAMP NOT NULL,
    
    file_extension TEXT,
    operation TEXT CHECK (operation IN ('create', 'edit', 'delete', 'read')),
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    
    accepted BOOLEAN,
    acceptance_delay_ms INTEGER,
    revision_count INTEGER DEFAULT 0
);
```

**Example Queries:**

```sql
-- Acceptance rate by file type
SELECT 
    file_extension,
    COUNT(*) as total_changes,
    SUM(CASE WHEN accepted THEN 1 ELSE 0 END) as accepted_changes,
    ROUND(AVG(CASE WHEN accepted THEN 1.0 ELSE 0.0 END) * 100, 2) as acceptance_rate
FROM code_changes
WHERE file_extension IS NOT NULL
GROUP BY file_extension
ORDER BY total_changes DESC;

-- Code velocity over time
SELECT 
    DATE(timestamp) as date,
    SUM(lines_added) as added,
    SUM(lines_removed) as removed,
    COUNT(*) as changes
FROM code_changes
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

### 3.5 Trace Stats Table

**Table**: `trace_stats`

Pre-computed daily aggregations.

```sql
CREATE TABLE trace_stats (
    stat_date DATE PRIMARY KEY,
    total_events INTEGER NOT NULL,
    unique_sessions INTEGER NOT NULL,
    event_types TEXT NOT NULL,
    platform_breakdown TEXT NOT NULL,
    error_count INTEGER DEFAULT 0,
    avg_duration_ms REAL,
    total_tokens INTEGER DEFAULT 0,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Redis Streams Output

### 4.1 Message Queue Stream

**Stream**: `telemetry:message_queue`

Primary event stream for real-time processing. All producers (HTTP hooks, JSONL monitor, database monitors) write to this stream.

**Format**:
```
Stream Entry:
  ID: 1731320400123-0
  Fields:
    event_id: "uuid-v4"
    enqueued_at: "2025-11-11T10:30:45.123Z"
    retry_count: "0"
    platform: "cursor"
    external_session_id: "curs_1731320400_abc123"
    hook_type: "afterFileEdit"
    event_type: "file_edit"
    timestamp: "2025-11-11T10:30:45.120Z"
    payload: "{\"file_extension\":\"py\",\"lines_added\":10}"
    metadata: "{\"workspace_hash\":\"a1b2c3d4\"}"
```

**Consumer Groups**:
- `processors` - Fast path consumers for immediate ingestion

**Commands**:
```bash
# Check stream length
redis-cli XLEN telemetry:message_queue

# View recent events
redis-cli XREAD COUNT 5 STREAMS telemetry:message_queue 0-0

# Monitor stream in real-time
redis-cli XREAD BLOCK 1000 COUNT 10 STREAMS telemetry:message_queue $
```

### 4.2 CDC Event Stream

**Stream**: `cdc:events`

Change Data Capture events for slow path workers.

**Format**:
```json
{
  "sequence": 12345,
  "event_type": "file_edit",
  "session_id": "uuid",
  "timestamp": "2025-11-11T10:30:45.123Z",
  "metadata": {
    "workspace_hash": "a1b2c3d4",
    "model": "claude-sonnet-4-5"
  }
}
```

### 4.3 Dead Letter Queue

**Stream**: `telemetry:dlq`

Failed events for manual inspection and retry.

---

## 5. Derived Metrics and Analytics

### 5.1 Productivity Metrics

**Outputs:**
- Daily active sessions
- Events per session
- Code changes per session
- Lines of code added/removed
- Average session duration
- Tool usage frequency

**Example Query:**
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(DISTINCT session_id) as active_sessions,
    COUNT(*) as total_events,
    SUM(lines_added) as total_lines_added,
    SUM(lines_removed) as total_lines_removed
FROM raw_traces
WHERE timestamp >= DATE('now', '-7 days')
GROUP BY DATE(timestamp);
```

### 5.2 AI Interaction Metrics

**Outputs:**
- Prompts per session
- Average response time
- Token usage per session
- Model usage distribution
- Tool call frequency

**Example Query:**
```sql
SELECT 
    model,
    COUNT(*) as response_count,
    AVG(duration_ms) as avg_latency,
    SUM(tokens_used) as total_tokens,
    AVG(tokens_used) as avg_tokens
FROM raw_traces
WHERE event_type = 'assistant_response'
  AND model IS NOT NULL
GROUP BY model;
```

### 5.3 Acceptance Metrics

**Outputs:**
- Code change acceptance rate
- Time to acceptance
- Revision frequency
- Acceptance by file type
- Acceptance by time of day

### 5.4 Workflow Patterns

**Outputs:**
- Common tool sequences
- Session duration distribution
- Peak activity hours
- Context switching frequency

---

## 6. Export Formats

### 6.1 JSON Export

Events can be exported as JSON for analysis:

```json
{
  "session_id": "uuid",
  "session_start": "2025-11-11T09:00:00Z",
  "session_end": "2025-11-11T11:30:00Z",
  "events": [
    {
      "timestamp": "2025-11-11T09:01:23Z",
      "event_type": "user_prompt",
      "model": "claude-sonnet-4-5",
      "metadata": {...},
      "payload": {...}
    }
  ],
  "summary": {
    "total_events": 47,
    "total_tokens": 12500,
    "code_changes": 8,
    "lines_added": 120,
    "lines_removed": 45
  }
}
```

### 6.2 CSV Export

Flat format for spreadsheet analysis:

```csv
timestamp,event_type,model,tokens_used,duration_ms,lines_added,lines_removed
2025-11-11T10:30:45Z,assistant_response,claude-sonnet-4-5,1250,3400,,
2025-11-11T10:31:12Z,file_edit,,,10,5
```

---

## 7. Query Examples

### Most Used Models
```sql
SELECT 
    model,
    COUNT(*) as usage_count,
    SUM(tokens_used) as total_tokens
FROM raw_traces
WHERE model IS NOT NULL
GROUP BY model
ORDER BY usage_count DESC;
```

### Hourly Activity Pattern
```sql
SELECT 
    event_hour,
    COUNT(*) as events,
    COUNT(DISTINCT session_id) as sessions
FROM raw_traces
GROUP BY event_hour
ORDER BY event_hour;
```

### Session Timeline
```sql
SELECT 
    sequence,
    timestamp,
    event_type,
    hook_type,
    model,
    tokens_used
FROM raw_traces
WHERE session_id = 'your-session-id'
ORDER BY sequence;
```

### Code Productivity
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(CASE WHEN event_type = 'file_edit' THEN 1 END) as edits,
    SUM(lines_added) as added,
    SUM(lines_removed) as removed
FROM raw_traces
WHERE timestamp >= DATE('now', '-30 days')
GROUP BY DATE(timestamp)
ORDER BY date;
```

---

## 8. Privacy & Data Redaction

### What is NOT Captured
- ❌ Actual prompt text
- ❌ AI response content
- ❌ File contents
- ❌ Command text
- ❌ File paths (hashed only)

### What IS Captured
- ✅ Event types and timing
- ✅ Metrics (tokens, lines, duration)
- ✅ Model identifiers
- ✅ File extensions (not paths)
- ✅ Tool names (not parameters)
- ✅ Hashes (workspace, files, prompts)

---

## 9. Future Outputs

**Planned for Layer 3:**
- 📊 Interactive web dashboard
- 📈 Real-time metrics visualization
- 🤖 MCP server for AI-powered insights
- 📋 CLI with rich terminal output
- 🎯 Personalized productivity recommendations
- 🔍 Pattern recognition and anomaly detection

---

**Document Version**: 1.0  
**Last Updated**: November 11, 2025  
**Status**: Production-ready (Layer 1 & 2 Complete)


