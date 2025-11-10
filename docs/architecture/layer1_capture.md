<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Layer 1: Open Source Capture

> Part of the Blueplane MVP Architecture
> [Back to Main Architecture](./BLUEPLANE_MVP_ARCHITECTURE.md)

---

## Overview

The capture layer is a lightweight telemetry collection system that runs within the IDE environment. It consists of hooks and extensions that emit events to a message queue for processing by Layer 2 (Local Telemetry Server).

**Key Principles**:
- **No project-level storage** - Layer 1 only emits events to message queue
- **Message queue pattern** - Asynchronous, reliable event delivery
- **External session IDs** - Preserves platform-native session identifiers
- **Stateless hooks** - All state managed by extensions via environment variables
- **Platform-specific capture** - Different hooks and trace mechanisms per IDE

## Architecture

```mermaid
graph TB
    subgraph "Claude Code Implementation"
        CC[Claude Code] -->|Direct Hooks| CCH[Claude Hooks]
        CCH -->|Session Events| MQW1[Message Queue Writer]
    end

    subgraph "Cursor Implementation"
        CI[Cursor IDE] -->|Extension API| CE[Cursor Extension]
        CE -->|Environment Vars| CH[Cursor Hooks]
        CE -->|DB Monitor| CD[Database Watcher]
        CH -->|Hook Events| MQW2[Message Queue Writer]
        CD -->|Trace Events| MQW2
    end

    subgraph "Shared Components"
        MQW1 -->|Write| MQ[Message Queue]
        MQW2 -->|Write| MQ

        subgraph "Message Queue System (Redis Streams)"
            MQ --> Events[telemetry:events<br/>Stream]
            Events --> Processors[Consumer Group:<br/>processors]
            Processors --> CDC[CDC Stream]
            Events --> DLQ[telemetry:dlq<br/>Dead Letter Queue]
        end
    end

    subgraph "Layer 2"
        Consumer[Queue Consumer] -->|Process| Layer2[Local Telemetry Server]
    end

    MQ --> Consumer
```

## Shared Components

### 1.1 Message Queue System (Redis Streams)

**Technology**: Redis Streams

**Stream Structure**:
```
Main Queue: telemetry:events
  - Consumer Group: processors
  - Max Length: ~10,000 (approximate trim)
  - Consumers: fast-path-1, fast-path-2, ...

Dead Letter Queue: telemetry:dlq
  - No consumer groups (manual inspection)
  - Retention: 7 days for debugging
```

**Message Format** (Redis Stream Entry):
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "enqueued_at": "2025-11-06T15:30:45.123Z",
  "retry_count": "0",
  "platform": "claude_code",
  "external_session_id": "6f967aab-03c6-4b94-ba66-9666e81c033b",
  "hook_type": "SessionStart",
  "timestamp": "2025-11-06T15:30:45.100Z",
  "sequence_num": "1",
  "data": "{\"cwd\":\"/Users/user/project\",\"source\":\"startup\"}"
}
```

**Dead Letter Queue Entry** (telemetry:dlq stream):
```json
{
  "original_event_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_data": "{...}",
  "error_type": "processing_error",
  "error_message": "Failed to determine project_id",
  "error_stack": "...",
  "attempted_at": "2025-11-06T15:30:46.123Z",
  "retry_count": "3",
  "dlq_queued_at": "2025-11-06T15:30:47.000Z",
  "can_retry": "true",
  "suggested_action": "check_workspace_path"
}
```

### 1.2 Message Queue Writer

**Shared component used by both Claude Code and Cursor hooks to write events to the message queue.**

**Location**: `capture-sdk/shared/queue_writer.py`

**Implementation** (pseudocode):
```python
# capture-sdk/shared/queue_writer.py (pseudocode)

class MessageQueueWriter:
    """Write events to Redis Streams message queue - shared by all platforms"""

    def __init__(self):
        """
        Initialize Redis connection.

        - Connect to localhost:6379
        - Use connection pooling
        - Set socket timeouts (1 second max)
        - Fail gracefully if Redis unavailable
        """

    def enqueue(event: dict, platform: str, session_id: str) -> bool:
        """
        Write event to Redis Streams telemetry:events.

        - Generate event_id (UUID)
        - Add enqueued_at timestamp
        - Flatten event dict to Redis hash format
        - XADD to 'telemetry:events' stream with MAXLEN ~10000
        - Return true on success, false on failure
        - Fail silently on error (hooks must not block IDE)
        - Timeout after 1 second
        """
```

**Pseudocode Details**:
```python
def enqueue(event: dict, platform: str, session_id: str) -> bool:
    try:
        # Generate message ID
        event_id = generate_uuid()

        # Build Redis stream entry (flat key-value pairs)
        stream_entry = {
            'event_id': event_id,
            'enqueued_at': current_timestamp(),
            'retry_count': '0',
            'platform': platform,
            'external_session_id': session_id,
            'hook_type': event['hook_type'],
            'timestamp': event['timestamp'],
            'data': json.dumps(event['payload'])  # Serialize complex data
        }

        # Write to Redis Streams with auto-trim
        redis.xadd(
            name='telemetry:events',
            fields=stream_entry,
            maxlen=10000,
            approximate=True  # Efficient approximate trimming
        )

        return True

    except (ConnectionError, TimeoutError) as e:
        # Log error but don't raise (silent failure)
        # Hooks must never block IDE operations
        return False
```

**Features**:
- Atomic Redis XADD operations (guaranteed message delivery)
- Platform-agnostic interface
- Silent failure to prevent blocking IDE operations
- Connection pooling for performance
- Auto-trim to prevent unbounded growth (MAXLEN ~10000)
- 1-second timeout for network operations
- Standardized message format for both platforms

## Claude Code Implementation

### 2.1 Hook System

**Location**: `.claude/hooks/telemetry/`

**Hook Names and Events**:
- `SessionStart` - Session initialization with transcript path
- `PreToolUse` - Before tool execution
- `PostToolUse` - After tool execution with results
- `UserPromptSubmit` - User prompt submission
- `Stop` - Session termination
- `PreCompact` - Context window compaction

**Hook Script Structure**:
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# Hook Script (pseudocode)

def main():
    """
    Claude Code hook pattern.

    - Read JSON from stdin
    - Extract session_id (provided by Claude Code)
    - Build event dict with hook_type, timestamp, sequence_num, metadata
    - Write to message queue via MessageQueueWriter
    - Always exit 0 (never block Claude Code)
    - Fail silently on all errors
    """
```

### 2.2 Session Management

**Claude Code provides**:
- Direct session ID in each hook event
- Transcript file path for full conversation history
- Session metadata (CWD, git branch, model info)

**No extension required** - Claude Code handles session management internally

### 2.3 Trace Capture

**Transcript Files**:
- Located at path provided in `SessionStart` hook
- JSONL format with complete conversation history
- Includes model usage, token counts, tool calls

## Cursor Implementation

### 3.1 Hook System

**Location**: `.cursor/hooks/telemetry/`

**Hook Names and Events** (Different from Claude Code):
- `beforeSubmitPrompt` - Before user prompt submission
- `afterAgentResponse` - After AI response
- `beforeMCPExecution` - Before MCP tool execution
- `afterMCPExecution` - After MCP tool execution
- `afterFileEdit` - After file modification
- `beforeShellExecution` - Before shell command
- `afterShellExecution` - After shell command
- `beforeReadFile` - Before file read
- `stop` - Session termination

**Hook Script Structure**:
```python
#!/usr/bin/env python3
# Cursor Telemetry - Before Submit Prompt Hook (pseudocode)
# Zero dependencies - stdlib only

def main():
    """
    Cursor hook pattern (different from Claude Code).

    - Parse command-line args (--workspace-root, --generation-id, --prompt-length)
    - Get session_id from environment variable CURSOR_SESSION_ID (set by extension)
    - Exit silently if no session_id (extension not active)
    - Build event dict with hook_type, timestamp, generation_id, etc.
    - Write to message queue via MessageQueueWriter
    - Always exit 0 (never block Cursor)
    - Fail silently on all errors
    """
```

### 3.2 Cursor Extension

**Location**: `.cursor/extensions/telemetry-session-manager/`

**Purpose**: Manages session IDs and monitors Cursor's SQLite database for traces

**Extension Components** (TypeScript pseudocode):

```typescript
// src/extension.ts (pseudocode)

export async function activate(context: vscode.ExtensionContext) {
    /**
     * Extension activation.
     *
     * - Create SessionManager and DatabaseMonitor
     * - Start new session (sets CURSOR_SESSION_ID environment variable)
     * - Start database monitoring
     * - Register VSCode commands (showStatus, newSession)
     */
}
```

**Session Manager**:
```typescript
// src/sessionManager.ts (pseudocode)

export class SessionManager {
    /**
     * Manages session lifecycle and environment variables.
     *
     * - startNewSession(): Generate session ID (curs_{timestamp}_{random}),
     *   set CURSOR_SESSION_ID and CURSOR_WORKSPACE_HASH env vars
     * - getSessionId(): Return current session_id
     * - computeWorkspaceHash(): SHA256 hash of workspace path (first 16 chars)
     * - showStatus(): Display session info to user
     */
}
```

### 3.3 Database Monitoring

**Cursor Traces Database**:
- Location: `~/Library/Application Support/Cursor/User/workspaceStorage/{id}/state.vscdb`
- Contains: prompts, generations, composer sessions
- Monitored tables: `aiService.prompts`, `aiService.generations`, `composer.composerData`

**Database Monitor**:
```typescript
// src/databaseMonitor.ts (pseudocode)

export class DatabaseMonitor {
    /**
     * Monitors Cursor's SQLite database for trace events.
     *
     * - startMonitoring(): Open DB readonly, start file watcher + polling
     * - checkForChanges(): Compare data_version, capture if changed
     * - captureChanges():
     *   - Query "aiService.generations" WHERE data_version > last
     *   - For each generation: get related prompt and composer data
     *   - Transform to trace event
     *   - Write to message queue
     *
     * Dual monitoring strategy:
     * 1. File watcher (chokidar) - primary, real-time
     * 2. Polling (every 30s) - backup, catch missed changes
     */
}

            // Create trace event
            const event = {
                hook_type: 'DatabaseTrace',
                timestamp: new Date().toISOString(),
                trace_type: 'generation',
                generation_id: gen.value.uuid,
                prompt_data: promptData,
                composer_data: composerData,
                metadata: {
                    data_version: gen.data_version,
                    model: gen.value.model
                }
            };

            // Send to message queue
            this.writer.enqueue(event, 'cursor', process.env.CURSOR_SESSION_ID);
        }
    }
}
```

## Installation

### 4.1 Claude Code Installation

**Requirements**:
- Claude Code CLI installed
- Python 3.11+ (handled by uv)
- Write access to home directory

**Installation Steps**:

```bash
# 1. Obtain the Blueplane capture SDK
# (Source code should be available in the project)

# 2. Run Claude Code installer
python install_claude.py

# This will:
# - Copy hooks to .claude/hooks/telemetry/
# - Configure hooks in Claude settings
# - Create message queue directories
# - Set up privacy configuration
```

**Manual Installation**:
```bash
# Copy hook files
cp -r capture-sdk/hooks/claude/* ~/.claude/hooks/telemetry/

# Update Claude settings.json
# Add hook configurations for SessionStart, PreToolUse, etc.
```

**Verification**:
```bash
# Test hook installation
python verify_claude_hooks.py

# Expected output:
# ✅ SessionStart hook installed
# ✅ PreToolUse hook installed
# ✅ PostToolUse hook installed
# ✅ UserPromptSubmit hook installed
# ✅ Stop hook installed
# ✅ PreCompact hook installed
```

### 4.2 Cursor Installation

**Requirements**:
- Cursor IDE installed
- Node.js 16+ (for extension)
- Python 3.11+ (for hooks)
- Project workspace initialized

**Installation Steps**:

```bash
# 1. Obtain the Blueplane capture SDK
# (Source code should be available in the project)

# 2. Install Cursor extension (if using extension-based capture)
cd extensions/cursor-telemetry
npm install
npm run compile
# Then install via Cursor: Extensions → Install from VSIX

# 3. Install project-level hooks
python install_cursor_project.py --workspace /path/to/project

# This will:
# - Copy hooks to .cursor/hooks/telemetry/
# - Create .cursor/hooks.json configuration
# - Initialize session management
# - Set up database monitoring
```

**Manual Installation**:
```bash
# 1. Copy hook files from the SDK
mkdir -p .cursor/hooks/telemetry
cp <sdk-path>/hooks/cursor/* .cursor/hooks/telemetry/

# 2. Create hooks.json
cat > .cursor/hooks.json << 'EOF'
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [
      {"command": "hooks/telemetry/before_submit_prompt.py"}
    ],
    "afterAgentResponse": [
      {"command": "hooks/telemetry/after_agent_response.py"}
    ],
    "afterFileEdit": [
      {"command": "hooks/telemetry/after_file_edit.py"}
    ],
    // ... other hooks
  }
}
EOF

# 3. Install extension manually via Cursor UI
```

**Verification**:
```bash
# Test hook and extension installation
python verify_cursor_installation.py

# Expected output:
# ✅ Extension installed and active
# ✅ Session manager running
# ✅ Database monitor active
# ✅ All hooks configured
# ✅ Message queue accessible
```

### 4.3 Unified Installation System

**Proposed Universal Installer** (pseudocode):

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13.7.0", "click>=8.1.0", "pyyaml>=6.0"]
# ///

"""Blueplane Telemetry Installer - Universal installation for all platforms"""

class UniversalInstaller:
    """
    Unified installer for Claude Code and Cursor telemetry.

    Main workflow:
    1. detect_platforms(): Check for .claude dir, Cursor.app existence
    2. install_redis():
       - Check if Redis is installed (redis-cli --version)
       - If not found, provide installation instructions
       - Start Redis server if not running
       - Create consumer groups: XGROUP CREATE telemetry:events processors
    3. install_claude():
       - Copy hooks/*.py to ~/.claude/hooks/telemetry/
       - Update ~/.claude/settings.json with hook configuration
       - Update hooks to use Redis connection settings
    4. install_cursor():
       - Copy hooks/*.py to .cursor/hooks/telemetry/
       - Create .cursor/hooks.json with hook configuration
       - Optionally install VSCode extension
       - Update hooks to use Redis connection settings
    5. configure_privacy():
       - Write ~/.blueplane/config.yaml with privacy settings
    6. verify():
       - Check Redis is running (redis-cli PING)
       - Verify consumer groups exist
       - Check all hooks exist and are configured
       - Display installation status

    CLI options:
    --platform [auto|claude|cursor|both]
    --workspace [path]
    --privacy [strict|balanced|development]
    --redis-host [localhost]
    --redis-port [6379]
    --dry-run
    """
```

**Installation Commands**:
```bash
# Install for both platforms automatically
curl -sSL https://blueplane.io/install.py | python

# Install for specific platform
python install.py --platform claude

# Install with strict privacy
python install.py --privacy strict

# Preview installation
python install.py --dry-run
```

## Platform Comparison

### Implementation Differences

| Aspect | Claude Code | Cursor |
|--------|-------------|---------|
| **Hook Names** | SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop, PreCompact | beforeSubmitPrompt, afterAgentResponse, beforeMCPExecution, afterMCPExecution, afterFileEdit, etc. |
| **Hook Input** | JSON via stdin | Command-line arguments |
| **Session ID** | Provided directly in hook events | Environment variable set by extension |
| **Extension Required** | No | Yes (for session management & DB monitoring) |
| **Database Traces** | Via transcript files | Direct SQLite monitoring |
| **Hook Location** | ~/.claude/hooks/telemetry/ | .cursor/hooks/telemetry/ (project-level) |
| **Configuration** | Claude settings.json | .cursor/hooks.json |
| **Python Runtime** | uv (self-executing) | System Python |
| **Dependencies** | None (stdlib only) | None for hooks, Node.js for extension |

### Data Capture Comparison

| Data Type | Claude Code | Cursor |
|-----------|-------------|---------|
| **Session Management** | Native session IDs from Claude | Extension-generated session IDs |
| **Prompt Text** | Via transcript file | Via beforeSubmitPrompt hook + DB |
| **AI Responses** | Via transcript file | Via afterAgentResponse hook |
| **Tool Execution** | Pre/PostToolUse hooks | before/afterMCPExecution hooks |
| **File Changes** | PostToolUse with Edit tool | afterFileEdit hook with full edits |
| **Model Info** | In transcript metadata | From database traces |
| **Token Usage** | In transcript messages | From database generation data |
| **Context Management** | PreCompact hook | Not available |
| **Shell Commands** | Via PostToolUse | before/afterShellExecution hooks |

## Privacy Controls

```yaml
# capture-sdk/config/privacy.yaml
privacy:
  mode: strict  # strict | balanced | development

  sanitization:
    hash_file_paths: true
    hash_workspace: true
    redact_errors: true
    remove_code_content: true

  opt_out:
    - user_prompts
    - file_contents
    - error_messages

  retention:
    local_days: 30
    before_sync_days: 7
```

## Event Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
    "timestamp": {"type": "string", "format": "date-time"},
    "session_id": {"type": "string"},
    "event_type": {"enum": ["session_start", "tool_use", "completion", "error"]},
    "platform": {"enum": ["claude_code", "cursor"]},
    "metadata": {
      "type": "object",
      "properties": {
        "workspace_hash": {"type": "string"},
        "model": {"type": "string"},
        "sequence_num": {"type": "integer"}
      }
    },
    "payload": {"type": "object"}
  },
  "required": ["version", "timestamp", "session_id", "event_type", "platform"]
}
```

## Summary

### Key Design Decisions

1. **Shared Message Queue**: Both platforms write to the same message queue system, ensuring Layer 2 has a unified interface for event consumption.

2. **Platform-Specific Hooks**: Each platform uses its native hook system with different names and invocation patterns, but all produce standardized events.

3. **Session Management Strategy**:
   - Claude Code: Direct session IDs in hook events (native support)
   - Cursor: Extension-managed sessions via environment variables (no file fallback needed with project-level hooks)

4. **Database Monitoring**: Cursor requires active database monitoring to capture full conversation context, while Claude Code provides transcript files.

5. **Zero Dependencies**: All hooks use only Python stdlib to ensure maximum portability and reliability.

### Benefits of This Architecture

- **Platform Independence**: Layer 2 doesn't need to know which IDE generated the events
- **Reliable Delivery**: Redis Streams provides at-least-once delivery with Pending Entries List (PEL)
- **High Throughput**: 100k+ events/sec capacity with Redis Streams
- **Automatic Retry**: Stuck messages automatically reclaimed via XCLAIM
- **Observability**: Built-in monitoring with XINFO and XPENDING commands
- **Non-Blocking**: Hooks timeout after 1 second to prevent IDE disruption
- **Privacy First**: All sensitive data is sanitized at capture time
- **Extensible**: Easy to add support for new IDEs or editors

### Future Enhancements

1. **Additional IDE Support**: VSCode, IntelliJ, Vim/Neovim plugins
2. **Real-time Streaming**: WebSocket support for live telemetry
3. **Compression**: Event compression for high-volume scenarios
4. **Encryption**: End-to-end encryption for sensitive environments
5. **Cloud Queue**: Option to use cloud message queues (SQS, Pub/Sub)

---

[Back to Main Architecture](./BLUEPLANE_MVP_ARCHITECTURE.md)
