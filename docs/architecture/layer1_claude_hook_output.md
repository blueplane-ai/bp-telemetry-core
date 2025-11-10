# Claude Code Hook Input Data Reference

## Overview

Claude Code hooks receive JSON input via stdin at key points during AI-assisted development sessions. This document describes the input data structure for each hook type.

## Hook Types

### 1. SessionStart

**Trigger**: Start of new Claude Code session

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "source": "startup"
}
```

**Fields**:

- `session_id` (string, required): Unique session identifier
- `source` (string, optional): Session trigger source (e.g., "startup")

---

### 2. UserPromptSubmit

**Trigger**: User submits a prompt

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "prompt": "User's actual prompt text here..."
}
```

**Fields**:

- `session_id` (string, required): Session identifier
- `prompt` (string): Full user prompt text

---

### 3. PreToolUse

**Trigger**: Before tool execution

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/path/to/file.py"
  }
}
```

**Fields**:

- `session_id` (string, required): Session identifier
- `tool_name` (string): Name of tool being executed (e.g., "Read", "Edit", "Write", "Bash")
- `tool_input` (object): Tool-specific parameters (varies by tool)

**Common tool_input structures**:

Read tool:

```json
{
  "file_path": "/path/to/file.py",
  "offset": 0,
  "limit": 2000
}
```

Edit tool:

```json
{
  "file_path": "/path/to/file.py",
  "old_string": "original text",
  "new_string": "replacement text"
}
```

Write tool:

```json
{
  "file_path": "/path/to/file.py",
  "content": "file contents"
}
```

Bash tool:

```json
{
  "command": "git status",
  "timeout": 120000
}
```

---

### 4. PostToolUse

**Trigger**: After tool execution completes

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/path/to/file.py"
  },
  "tool_result": "File contents here...",
  "tool_response": {
    "success": true
  },
  "error": null,
  "tool_use_error": null
}
```

**Fields**:

- `session_id` (string, required): Session identifier
- `tool_name` (string): Name of executed tool
- `tool_input` (object): Tool parameters (same as PreToolUse)
- `tool_result` (any): Result returned by tool (string, object, null)
- `tool_response` (object, optional): Structured response with success/status
- `error` (string, optional): Top-level error message if tool failed
- `tool_use_error` (string, optional): Tool-specific error message

**Error Scenarios**:

Success:

```json
{
  "tool_name": "Read",
  "tool_result": "file contents...",
  "tool_response": { "success": true },
  "error": null
}
```

Error:

```json
{
  "tool_name": "Read",
  "tool_result": null,
  "error": "FileNotFoundError: No such file or directory",
  "tool_use_error": null
}
```

Tool-specific error:

```json
{
  "tool_name": "Edit",
  "tool_result": { "success": false, "error": "String not found" },
  "tool_use_error": "old_string not found in file"
}
```

---

### 5. PreCompact

**Trigger**: Before context window compaction

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "trigger": "context_limit",
  "transcript_path": "/path/to/transcript.jsonl",
  "custom_instructions": "User's custom instructions..."
}
```

**Fields**:

- `session_id` (string, required): Session identifier
- `trigger` (string, optional): Reason for compaction
  - `"context_limit"` - Token limit reached
  - `"user_request"` - User manually triggered
  - `"periodic"` - Scheduled compaction
- `transcript_path` (string, optional): Path to current transcript
- `custom_instructions` (string, optional): User's custom instructions for the session

---

### 6. Stop

**Trigger**: End of session

**Input Data**:

```json
{
  "session_id": "session_abc123",
  "transcript_path": "/path/to/final/transcript.jsonl",
  "stop_hook_active": true
}
```

**Fields**:

- `session_id` (string, required): Session identifier
- `transcript_path` (string, optional): Path to final transcript
- `stop_hook_active` (boolean, optional): Whether stop hook is configured

---

## Common Patterns

### Session ID

All hooks receive `session_id` as a required field. This is a unique identifier for the session, typically in format: `"session_{uuid}"`.

### Tool Names

Common tool names in PreToolUse and PostToolUse:

- `"Read"` - Read file
- `"Edit"` - Edit file with find/replace
- `"Write"` - Write new file or overwrite
- `"Bash"` - Execute bash command
- `"Glob"` - Find files by pattern
- `"Grep"` - Search file contents
- `"Task"` - Launch sub-agent
- `"WebFetch"` - Fetch web content
- `"WebSearch"` - Search the web

### Null Values

Optional fields may be omitted or set to `null`. Both should be handled equivalently.
