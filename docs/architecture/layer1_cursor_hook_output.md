# Cursor Hook Input Data Reference

## Overview

Cursor hooks receive JSON input via stdin at key points during AI-assisted development sessions. This document describes the input data structure for each hook type.

## Hook Types

### 1. BeforeSubmitPrompt

**Trigger**: User submits a prompt

**Input Data**:

```json
{
  "prompt": "User's actual prompt text here...",
  "context": {
    "files": [
      {
        "path": "/path/to/file1.py",
        "content": "file contents..."
      },
      {
        "path": "/path/to/file2.js",
        "content": "file contents..."
      }
    ],
    "workspaceFolder": "/Users/user/project"
  }
}
```

**Fields**:

- `prompt` (string): Full user prompt text
- `context` (object, optional): Context information
  - `files` (array): Files included in context
    - `path` (string): Full file path
    - `content` (string): File contents
  - `workspaceFolder` (string): Workspace root directory

---

### 2. BeforeMCPExecution

**Trigger**: Before MCP tool execution

**Input Data**:

```json
{
  "tool": "read_file",
  "params": {
    "path": "/Users/user/project/src/main.py",
    "encoding": "utf-8"
  }
}
```

**Fields**:

- `tool` (string): MCP tool name
- `params` (object): Tool-specific parameters (varies by tool)

**Common MCP Tool Names**:

- `"read_file"` - Read file contents
- `"edit_file"` - Edit file
- `"write_file"` - Write new file
- `"list_files"` - List files in directory
- `"run_command"` - Execute shell command
- `"apply_diff"` - Apply diff patch

**Common params structures**:

read_file:

```json
{
  "path": "/path/to/file.py",
  "encoding": "utf-8"
}
```

edit_file:

```json
{
  "path": "/path/to/file.py",
  "edits": [
    {
      "oldText": "original",
      "newText": "replacement"
    }
  ]
}
```

write_file:

```json
{
  "path": "/path/to/file.py",
  "content": "file contents"
}
```

run_command:

```json
{
  "command": "npm test",
  "cwd": "/path/to/project"
}
```

---

### 3. AfterMCPExecution

**Trigger**: After MCP tool execution completes

**Input Data**:

```json
{
  "tool": "read_file",
  "result": {
    "success": true,
    "content": "File contents...",
    "lines_changed": 0
  },
  "duration_ms": 45
}
```

**Fields**:

- `tool` (string): MCP tool name
- `result` (object/string/null): Result returned by tool
  - `success` (boolean, optional): Whether operation succeeded
  - Tool-specific result fields
- `duration_ms` (number, optional): Execution time in milliseconds

**Error Scenario**:

```json
{
  "tool": "read_file",
  "result": {
    "success": false,
    "error": "File not found"
  },
  "duration_ms": 12
}
```

---

### 4. AfterFileEdit

**Trigger**: After AI edits a file

**Input Data**:

```json
{
  "file": "/Users/user/project/src/components/Button.tsx",
  "changes": {
    "added": 12,
    "removed": 5,
    "modified": 3
  }
}
```

**Fields**:

- `file` (string): Full path to edited file
- `changes` (object): Line change statistics
  - `added` (number): Lines added
  - `removed` (number): Lines removed
  - `modified` (number): Lines modified

---

### 5. AfterAgentResponse

**Trigger**: After AI generates a response

**Input Data**:

```json
{
  "response": "AI response text here...",
  "model": "claude-sonnet-4-5-20250929",
  "tokens": 1250,
  "duration_ms": 3400
}
```

**Fields**:

- `response` (string): Full AI response text
- `model` (string, optional): Model identifier
- `tokens` (number, optional): Token count
- `duration_ms` (number, optional): Response generation time in milliseconds

---

### 6. Stop

**Trigger**: End of session

**Input Data**:

```json
{
  "reason": "user_exit",
  "total_turns": 47
}
```

**Fields**:

- `reason` (string, optional): Reason for session end
  - `"user_exit"` - User closed session
  - `"timeout"` - Session timeout
  - `"error"` - Error termination
  - `"complete"` - Task completion
- `total_turns` (number, optional): Total conversation turns

---

## Common Patterns

### MCP Tool Names

All MCP tools use snake_case naming (e.g., `read_file`, `edit_file`, `run_command`).

### File Paths

File paths are always absolute, not relative.

### Optional Fields

Fields marked as optional may be omitted or set to `null`. Both should be handled equivalently.

### Duration Metrics

Duration fields (`duration_ms`) are in milliseconds and may be omitted if timing data is unavailable.
