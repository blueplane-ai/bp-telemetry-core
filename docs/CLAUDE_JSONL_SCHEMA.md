<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Claude Code JSONL File Schema

This document provides a comprehensive analysis of the Claude Code project session JSONL files, including all fields, data types, and patterns discovered through analysis of actual session files.

## Overview

Claude Code stores session data in JSONL (JSON Lines) format at:
```
~/.claude/projects/{project-path-encoded}/
```

Each line in the JSONL file represents a single event in the session. There are multiple event types, each with its own structure.

## Directory Structure

The directory contains two types of files:
1. **Session files**: Named with UUID format (e.g., `91ac0085-3035-4bb4-953b-4bcfa3eb9336.jsonl`)
2. **Agent files**: Named with `agent-` prefix (e.g., `agent-26026dd1.jsonl`)

## Event Types

### 1. USER Event
Represents a message from the user.

```json
{
  "type": "user",
  "uuid": "27198e6d-9553-40a9-9f37-3e099b4e15dc",
  "parentUuid": null,
  "sessionId": "18d57daa-b29d-4f65-a348-1c6895c49825",
  "timestamp": "2025-11-11T23:52:57.032Z",
  "isSidechain": false,
  "userType": "external",
  "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
  "version": "2.0.37",
  "gitBranch": "main",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "hello world"
      }
    ]
  }
}
```

**Fields:**
- `type`: "user"
- `uuid`: Unique identifier for this event
- `parentUuid`: UUID of parent event (null for root messages)
- `sessionId`: Session identifier
- `timestamp`: ISO 8601 timestamp
- `isSidechain`: Boolean indicating if this is a sidechain conversation
- `userType`: "external" or other user type
- `cwd`: Current working directory
- `version`: Claude Code version
- `gitBranch`: Current git branch
- `message`: User message object
  - `role`: "user"
  - `content`: Array of content items (see Content Types below)

### 2. ASSISTANT Event
Represents a response from Claude.

```json
{
  "type": "assistant",
  "uuid": "6e45211b-8768-4871-8c57-3ea75ff3ad77",
  "parentUuid": "27198e6d-9553-40a9-9f37-3e099b4e15dc",
  "sessionId": "18d57daa-b29d-4f65-a348-1c6895c49825",
  "timestamp": "2025-11-11T23:53:02.470Z",
  "requestId": "req_011CV315CohSwsJtiJnPwiVt",
  "isSidechain": false,
  "userType": "external",
  "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
  "version": "2.0.37",
  "gitBranch": "main",
  "message": {
    "model": "claude-sonnet-4-5-20250929",
    "id": "msg_01Tu4zZHguWARUg8LiMJavep",
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "thinking",
        "thinking": "The user has just said \"hello world\"...",
        "signature": "Ev8FCkYICRgCKkBr..."
      },
      {
        "type": "text",
        "text": "Hello! I'm Claude Code..."
      }
    ],
    "stop_reason": "end_turn",
    "stop_sequence": null,
    "usage": {
      "input_tokens": 9,
      "cache_creation_input_tokens": 5354,
      "cache_read_input_tokens": 12878,
      "output_tokens": 193,
      "service_tier": "standard",
      "cache_creation": {
        "ephemeral_5m_input_tokens": 5354,
        "ephemeral_1h_input_tokens": 0
      }
    }
  }
}
```

**Fields:**
- `type`: "assistant"
- `uuid`: Unique identifier for this event
- `parentUuid`: UUID of the user message this is responding to
- `sessionId`: Session identifier
- `timestamp`: ISO 8601 timestamp
- `requestId`: API request identifier
- `isSidechain`: Boolean
- `userType`: "external" or other
- `cwd`: Current working directory
- `version`: Claude Code version
- `gitBranch`: Current git branch
- `message`: Assistant message object
  - `model`: Model identifier (e.g., "claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805")
  - `id`: Message ID from API
  - `type`: "message"
  - `role`: "assistant"
  - `content`: Array of content items (see Content Types below)
  - `stop_reason`: "end_turn", "tool_use", or null
  - `stop_sequence`: null (or sequence that stopped generation)
  - `context_management`: null (context management info if present)
  - `usage`: Token usage statistics
    - `input_tokens`: Number of input tokens
    - `cache_creation_input_tokens`: Tokens used to create cache
    - `cache_read_input_tokens`: Tokens read from cache
    - `output_tokens`: Number of output tokens
    - `service_tier`: "standard" or other tier
    - `cache_creation`: Cache creation details
      - `ephemeral_5m_input_tokens`: Tokens cached for 5 minutes
      - `ephemeral_1h_input_tokens`: Tokens cached for 1 hour

### 3. QUEUE-OPERATION Event
Represents queue operations (enqueue/dequeue).

```json
{
  "type": "queue-operation",
  "operation": "enqueue",
  "timestamp": "2025-11-11T23:52:57.025Z",
  "sessionId": "18d57daa-b29d-4f65-a348-1c6895c49825",
  "content": [
    {
      "type": "text",
      "text": "<ide_opened_file>The user opened the file...</ide_opened_file>"
    }
  ]
}
```

**Fields:**
- `type`: "queue-operation"
- `operation`: "enqueue" or "dequeue"
- `timestamp`: ISO 8601 timestamp
- `sessionId`: Session identifier
- `content`: Array of content items (for enqueue operations)

### 4. SYSTEM Event
Represents system-level events.

```json
{
  "type": "system",
  "subtype": "local_command",
  "uuid": "59dd10d0-08ba-45ca-94fe-d1490c147763",
  "parentUuid": null,
  "sessionId": "553f9ad5-4a17-405e-9081-aa697b89b188",
  "timestamp": "2025-11-11T21:28:31.512Z",
  "isSidechain": false,
  "isMeta": false,
  "userType": "external",
  "cwd": "/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core",
  "version": "2.0.31",
  "gitBranch": "main",
  "level": "info",
  "content": "<command-name>/hooks</command-name>..."
}
```

**Fields:**
- `type`: "system"
- `subtype`: "local_command" or other subtypes
- `uuid`: Unique identifier
- `parentUuid`: Parent event UUID
- `sessionId`: Session identifier
- `timestamp`: ISO 8601 timestamp
- `isSidechain`: Boolean
- `isMeta`: Boolean indicating if this is metadata
- `userType`: "external" or other
- `cwd`: Current working directory
- `version`: Claude Code version
- `gitBranch`: Current git branch
- `level`: "info", "error", "warning", etc.
- `content`: String or structured content

### 5. SUMMARY Event
Represents a session summary.

```json
{
  "type": "summary",
  "summary": "Session summary text",
  "leafUuid": "26cf709c-c035-49bc-a65a-e6d38be637fa"
}
```

**Fields:**
- `type`: "summary"
- `summary`: Summary text
- `leafUuid`: UUID of the final leaf event in the conversation tree

### 6. USER Event with Tool Result
When a tool execution completes, the result is sent back as a user event.

```json
{
  "type": "user",
  "uuid": "69e965fa-5f23-4bac-89a3-8a8bc7fe9439",
  "parentUuid": "e3161e7e-59ef-4e9d-97a1-faef287b4589",
  "sessionId": "18d57daa-b29d-4f65-a348-1c6895c49825",
  "timestamp": "2025-11-12T00:01:27.045Z",
  "message": {
    "role": "user",
    "content": [
      {
        "tool_use_id": "toolu_01U2FXRMcS8YDFRqKz1hY7ab",
        "type": "tool_result",
        "content": "command output here...",
        "is_error": false
      }
    ]
  },
  "toolUseResult": {
    "stdout": "command output...",
    "stderr": "",
    "interrupted": false,
    "isImage": false
  }
}
```

**Additional Fields for Tool Results:**
- `toolUseResult`: Object containing tool execution details
  - `stdout`: Standard output (for Bash tool)
  - `stderr`: Standard error (for Bash tool)
  - `interrupted`: Boolean indicating if execution was interrupted
  - `isImage`: Boolean indicating if result is an image
  - `returnCodeInterpretation`: Optional interpretation of return code
  - `type`: Type of tool result (e.g., "create" for Write tool)
  - `filePath`: Path to created/modified file (for file tools)
  - `content`: File content (for file tools)
  - `structuredPatch`: Structured diff for file changes

## Message Content Types

Messages can contain multiple content items. Each item has a `type` field indicating its purpose.

### TEXT Content
Plain text content.

```json
{
  "type": "text",
  "text": "The actual text content"
}
```

### THINKING Content
Claude's internal reasoning (visible in extended thinking mode).

```json
{
  "type": "thinking",
  "thinking": "The user wants to...",
  "signature": "cryptographic signature"
}
```

### TOOL_USE Content
A request to execute a tool.

```json
{
  "type": "tool_use",
  "id": "toolu_01U2FXRMcS8YDFRqKz1hY7ab",
  "name": "Bash",
  "input": {
    "command": "ls -la",
    "description": "List files in current directory"
  }
}
```

**Common Tools:**
- **Bash**: Execute shell commands
  - `command`: Shell command to execute
  - `description`: Human-readable description
- **Read**: Read file contents
  - `file_path`: Path to file
- **Write**: Write file contents
  - `file_path`: Path to file
  - `content`: File content
- **Edit**: Edit file contents
  - `file_path`: Path to file
  - `old_string`: String to replace
  - `new_string`: Replacement string
- **Glob**: Find files matching pattern
  - `pattern`: Glob pattern
- **Grep**: Search for text in files
  - `pattern`: Search pattern
- **Task**: Execute a sub-task
  - `description`: Task description
  - `prompt`: Detailed prompt
  - `subagent_type`: "Plan" or "general-purpose"

### TOOL_RESULT Content
The result of a tool execution.

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01U2FXRMcS8YDFRqKz1hY7ab",
  "content": "result content",
  "is_error": false
}
```

## Complete Field List

### Top-Level Fields (All Events)

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `type` | string | Event type: "user", "assistant", "queue-operation", "system", "summary" | Yes |
| `uuid` | string | Unique event identifier (UUID v4) | Most events |
| `parentUuid` | string\|null | Parent event UUID for conversation threading | Most events |
| `sessionId` | string | Session identifier (UUID v4) | Yes |
| `timestamp` | string | ISO 8601 timestamp | Yes |
| `isSidechain` | boolean | Whether this is a sidechain conversation | User/Assistant |
| `userType` | string | User type ("external", etc.) | User/Assistant |
| `cwd` | string | Current working directory path | User/Assistant |
| `version` | string | Claude Code version (e.g., "2.0.37") | User/Assistant |
| `gitBranch` | string | Current git branch name | User/Assistant |
| `requestId` | string | API request identifier | Assistant only |
| `message` | object | Message content and metadata | User/Assistant |
| `operation` | string | Queue operation type: "enqueue", "dequeue" | Queue-operation |
| `content` | array\|string | Event content | Queue-operation, System |
| `subtype` | string | System event subtype | System only |
| `level` | string | Log level: "info", "error", "warning" | System only |
| `isMeta` | boolean | Whether this is metadata | System only |
| `summary` | string | Session summary text | Summary only |
| `leafUuid` | string | Final leaf event UUID | Summary only |
| `toolUseResult` | object | Tool execution result details | User (tool results) |

### Message Object Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `role` | string | Message role: "user", "assistant" | Yes |
| `content` | array | Array of content items | Yes |
| `model` | string | Model identifier (e.g., "claude-sonnet-4-5-20250929") | Assistant only |
| `id` | string | API message ID | Assistant only |
| `type` | string | Always "message" | Assistant only |
| `stop_reason` | string\|null | Why generation stopped: "end_turn", "tool_use", null | Assistant only |
| `stop_sequence` | string\|null | Stop sequence that triggered end | Assistant only |
| `context_management` | object\|null | Context management information | Assistant only |
| `usage` | object | Token usage statistics | Assistant only |

### Usage Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | integer | Number of input tokens |
| `cache_creation_input_tokens` | integer | Tokens used for cache creation |
| `cache_read_input_tokens` | integer | Tokens read from cache |
| `output_tokens` | integer | Number of output tokens |
| `service_tier` | string | Service tier: "standard", etc. |
| `cache_creation` | object | Cache creation details |
| `cache_creation.ephemeral_5m_input_tokens` | integer | Tokens cached for 5 minutes |
| `cache_creation.ephemeral_1h_input_tokens` | integer | Tokens cached for 1 hour |

### Content Item Fields (varies by type)

**Common fields:**
- `type`: "text", "thinking", "tool_use", "tool_result"

**Text content:**
- `text`: String content

**Thinking content:**
- `thinking`: Reasoning text
- `signature`: Cryptographic signature

**Tool use content:**
- `id`: Tool use identifier
- `name`: Tool name
- `input`: Tool input parameters (varies by tool)

**Tool result content:**
- `tool_use_id`: Corresponding tool_use ID
- `content`: Result content
- `is_error`: Boolean indicating if execution failed

### ToolUseResult Object Fields

| Field | Type | Description | Tools |
|-------|------|-------------|-------|
| `stdout` | string | Standard output | Bash |
| `stderr` | string | Standard error | Bash |
| `interrupted` | boolean | Whether execution was interrupted | Bash |
| `isImage` | boolean | Whether result is an image | Bash, Read |
| `returnCodeInterpretation` | string | Interpretation of return code | Bash |
| `type` | string | Result type: "create", "edit", etc. | Write, Edit |
| `filePath` | string | Path to affected file | Write, Edit |
| `content` | string | File content | Write, Edit |
| `structuredPatch` | array | Structured diff of changes | Edit |

## Data Patterns

### Conversation Threading
Events are threaded using `parentUuid`:
- User messages typically have `parentUuid: null` (root of thread)
- Assistant responses reference the user message UUID
- Tool results reference the assistant message that requested them

### Session Identification
Each session has:
- A unique `sessionId` (UUID)
- A corresponding JSONL file named with that UUID
- All events in that file share the same `sessionId`

### Timestamps
All timestamps are in ISO 8601 format with millisecond precision:
```
2025-11-11T23:52:57.025Z
```

### Models
Common model identifiers:
- `claude-sonnet-4-5-20250929` - Claude Sonnet 4.5
- `claude-opus-4-1-20250805` - Claude Opus 4.1

### Stop Reasons
- `end_turn` - Natural conversation end
- `tool_use` - Generation stopped to execute a tool
- `null` - Intermediate message or thinking

### Cache Tiers
Cache tokens are tracked in two tiers:
- `ephemeral_5m_input_tokens` - Cached for 5 minutes
- `ephemeral_1h_input_tokens` - Cached for 1 hour

## Event Sequence Patterns

### Typical Conversation Flow

1. **User Input**
   ```
   queue-operation (enqueue) → user event
   ```

2. **Processing**
   ```
   queue-operation (dequeue)
   ```

3. **Assistant Response**
   ```
   assistant event (with thinking) → assistant event (with text)
   ```

4. **Tool Usage** (if needed)
   ```
   assistant event (with tool_use) → user event (with tool_result) → assistant event (with response)
   ```

### Multi-Turn Pattern
```
user → assistant → user → assistant → ...
```

Each turn maintains threading via `parentUuid`.

## Database Schema Considerations

### Primary Table: claude_raw_traces

Recommended fields for one-to-one JSONL mapping:

```sql
CREATE TABLE claude_raw_traces (
    -- Event identification
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    uuid VARCHAR(36),
    parent_uuid VARCHAR(36),
    session_id VARCHAR(36) NOT NULL,
    request_id VARCHAR(50),

    -- Event metadata
    type VARCHAR(20) NOT NULL,
    subtype VARCHAR(50),
    timestamp TIMESTAMP(3) NOT NULL,

    -- Context
    user_type VARCHAR(20),
    is_sidechain BOOLEAN DEFAULT FALSE,
    is_meta BOOLEAN DEFAULT FALSE,
    cwd TEXT,
    version VARCHAR(20),
    git_branch VARCHAR(255),

    -- Message data (for user/assistant events)
    message_role VARCHAR(10),
    message_model VARCHAR(100),
    message_id VARCHAR(50),
    message_type VARCHAR(20),
    message_stop_reason VARCHAR(20),
    message_stop_sequence TEXT,

    -- Usage statistics (for assistant events)
    input_tokens INT,
    cache_creation_input_tokens INT,
    cache_read_input_tokens INT,
    output_tokens INT,
    service_tier VARCHAR(20),
    cache_5m_tokens INT,
    cache_1h_tokens INT,

    -- Queue operation data
    operation VARCHAR(10),

    -- System event data
    level VARCHAR(10),

    -- Summary data
    summary TEXT,
    leaf_uuid VARCHAR(36),

    -- Content (stored as JSON for flexibility)
    content JSON,
    message_content JSON,
    tool_use_result JSON,

    -- Full raw event (compressed)
    raw_event MEDIUMBLOB COMPRESSED,

    -- Indexes
    INDEX idx_session_timestamp (session_id, timestamp),
    INDEX idx_uuid (uuid),
    INDEX idx_parent_uuid (parent_uuid),
    INDEX idx_type (type),
    INDEX idx_message_model (message_model)
);
```

### Considerations

1. **Storage**: Use COMPRESSED columns for `raw_event` to save space (7-10x compression)
2. **Indexing**: Index by `session_id` and `timestamp` for chronological queries
3. **JSON Columns**: Store flexible/nested data as JSON for easier querying
4. **Nullable Fields**: Many fields are only present for specific event types
5. **Thread Reconstruction**: Use `uuid` and `parent_uuid` to rebuild conversation trees

## Example Queries

### Get all messages in a session
```sql
SELECT * FROM claude_raw_traces
WHERE session_id = '18d57daa-b29d-4f65-a348-1c6895c49825'
ORDER BY timestamp ASC;
```

### Get conversation thread
```sql
WITH RECURSIVE thread AS (
    SELECT * FROM claude_raw_traces WHERE uuid = 'root-uuid'
    UNION ALL
    SELECT t.* FROM claude_raw_traces t
    INNER JOIN thread ON t.parent_uuid = thread.uuid
)
SELECT * FROM thread ORDER BY timestamp ASC;
```

### Get tool usage statistics
```sql
SELECT
    session_id,
    JSON_EXTRACT(message_content, '$[*].name') as tools_used,
    COUNT(*) as tool_calls
FROM claude_raw_traces
WHERE type = 'assistant'
  AND message_stop_reason = 'tool_use'
GROUP BY session_id;
```

### Get token usage by model
```sql
SELECT
    message_model,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(cache_read_input_tokens) as cache_hits
FROM claude_raw_traces
WHERE type = 'assistant'
GROUP BY message_model;
```

## Notes

- **File Watching**: JSONL files are append-only; new events are added as new lines
- **Session Files vs Agent Files**: Agent files may have different structure; focus on session files for primary traces
- **Empty Files**: Some JSONL files may be empty (0 bytes) - these represent sessions that never had events
- **Duplicate Events**: Some events may appear multiple times in the file (especially assistant responses with thinking + text)
- **Version Changes**: Field availability may vary by Claude Code version
