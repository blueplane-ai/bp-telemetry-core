# Claude Code Telemetry Capture

This directory contains the **Claude Code telemetry capture implementation** for Blueplane Telemetry Core.

## Overview

Claude Code hooks receive JSON input via stdin at key points during AI-assisted development sessions. These hooks capture telemetry and send events to Redis Streams for processing.

**Important**: Claude Code has **no separate session concept**. Sessions and conversations are 1:1—when a Claude Code session starts, a conversation is created immediately. Only conversations are tracked in the database (no `cursor_sessions`-equivalent table). See [Session & Conversation Schema](../../../docs/SESSION_CONVERSATION_SCHEMA.md) for details.

## Architecture

```
Claude Code IDE
    ↓
Hook Triggers (SessionStart, UserPromptSubmit, PreToolUse, etc.)
    ↓
Hook Scripts (Python, read JSON from stdin)
    ↓
MessageQueueWriter (Redis Streams)
    ↓
Layer 2 Processing → SQLite raw_traces
```

## Hook Scripts

### Location

Hooks are installed globally at: `~/.claude/hooks/telemetry/`

### Available Hooks

1. **`session_start.py`** - SessionStart hook
   - Fires at the start of a new Claude Code session/conversation
   - Creates a conversation record in `conversations` table (no separate session table)
   - The `session_id` from Claude Code becomes the `external_id` in conversations table
   - `conversations.session_id` is set to NULL (Claude Code has no session concept)
   - Input: `{"session_id": "...", "source": "startup"}`

2. **`session_end.py`** - SessionEnd hook
   - Fires at the end of a session/conversation (when Claude Code closes)
   - Updates the conversation record with `ended_at` timestamp
   - Captures final transcript path for processing
   - Input: `{"session_id": "...", "transcript_path": "..."}`

3. **`user_prompt_submit.py`** - UserPromptSubmit hook
   - Fires when user submits a prompt
   - Captures prompt text and length
   - Input: `{"session_id": "...", "prompt": "..."}`

4. **`pre_tool_use.py`** - PreToolUse hook
   - Fires before tool execution
   - Captures tool name and input parameters
   - Input: `{"session_id": "...", "tool_name": "Read", "tool_input": {...}}`

5. **`post_tool_use.py`** - PostToolUse hook
   - Fires after tool execution completes
   - Captures tool results, success/failure, and errors
   - Input: `{"session_id": "...", "tool_name": "Read", "tool_result": "...", "error": null}`

6. **`pre_compact.py`** - PreCompact hook
   - Fires before context window compaction
   - Captures compaction trigger and transcript path
   - Input: `{"session_id": "...", "trigger": "context_limit", "transcript_path": "..."}`

7. **`stop.py`** - Stop hook
   - Fires when assistant stops generating (end of turn/interaction)
   - Captures completion of assistant response and incremental transcript
   - Input: `{"session_id": "...", "transcript_path": "...", "stop_hook_active": true}`

## Installation

### Quick Install

```bash
# Install session hooks and update settings.json
python scripts/install_claude_hooks.py

# Dry run to see what would be done
python scripts/install_claude_hooks.py --dry-run
```

**Note:** Currently only session lifecycle hooks (session_start.py and session_end.py) are installed. Other hooks are available but disabled by default.

### Manual Installation

1. **Copy hooks to ~/.claude/hooks/telemetry/**
   ```bash
   mkdir -p ~/.claude/hooks/telemetry
   cp src/capture/claude_code/hooks/*.py ~/.claude/hooks/telemetry/
   cp src/capture/claude_code/hook_base.py ~/.claude/hooks/
   cp -r src/capture/shared ~/.claude/hooks/
   chmod +x ~/.claude/hooks/telemetry/*.py
   ```

2. **Update ~/.claude/settings.json**
   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/session_start.py"
             }
           ]
         }
       ],
       "SessionEnd": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/session_end.py"
             }
           ]
         }
       ],
       "UserPromptSubmit": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/user_prompt_submit.py"
             }
           ]
         }
       ],
       "PreToolUse": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/pre_tool_use.py"
             }
           ]
         }
       ],
       "PostToolUse": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/post_tool_use.py"
             }
           ]
         }
       ],
       "PreCompact": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/pre_compact.py"
             }
           ]
         }
       ],
       "Stop": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/telemetry/stop.py"
             }
           ]
         }
       ]
     }
   }
   ```

3. **Install Python dependencies**
   ```bash
   pip install redis pyyaml aiosqlite
   ```

4. **Start Redis server**
   ```bash
   redis-server
   ```

5. **Initialize Redis streams**
   ```bash
   python scripts/init_redis.py
   ```

6. **Start processing server**
   ```bash
   python scripts/start_server.py
   ```

## Configuration

### Global Configuration

Configuration files are stored in `~/.blueplane/`:

- **`redis.yaml`** - Redis connection settings
- **`privacy.yaml`** - Privacy controls

### Hook Behavior

- **Silent failure**: Hooks never block Claude Code operations
- **1-second timeout**: Network operations timeout after 1 second
- **No code capture**: Only metadata is captured (lengths, counts, hashes)
- **Privacy-first**: File paths are hashed, content is not captured by default

## Event Flow

```
1. Claude Code triggers hook (e.g., UserPromptSubmit)
2. Hook script receives JSON via stdin
3. Hook extracts session_id and event data
4. Hook builds event dictionary
5. MessageQueueWriter sends to Redis Streams
6. Fast path consumer processes event
7. Event written to SQLite raw_traces table
8. (Stop/SessionEnd hooks) Transcript monitor processes .jsonl file if provided
```

## Transcript Processing

Both the **Stop** and **SessionEnd** hooks have special transcript processing behavior:

1. When Stop or SessionEnd hook fires with `transcript_path` in payload
2. ClaudeCodeTranscriptMonitor detects the event
3. Monitor reads the .jsonl transcript file
4. Each transcript entry becomes a trace event with `event_type: transcript_trace`
5. Trace events are sent back to Redis for processing
6. All traces written to raw_traces table

This provides conversation history for analytics:
- **Stop hook**: Processes transcript after each turn (incremental capture)
- **SessionEnd hook**: Processes final transcript when session ends (complete capture)

**Note**: The hooks serve different purposes:
- **Stop**: Fires at the end of each assistant response (end of turn) - processes incremental transcript
- **SessionEnd**: Fires when Claude Code closes (end of session) - processes final transcript

Deduplication ensures the same transcript is not processed twice.

## Troubleshooting

### Hooks not firing

1. Check hooks are installed:
   ```bash
   ls -la ~/.claude/hooks/telemetry/
   ```

2. Verify settings.json:
   ```bash
   cat ~/.claude/settings.json
   ```

3. Check hooks are executable:
   ```bash
   chmod +x ~/.claude/hooks/telemetry/*.py
   ```

### Events not reaching Redis

1. Verify Redis is running:
   ```bash
   redis-cli PING
   ```

2. Check stream exists:
   ```bash
   redis-cli XLEN telemetry:events
   ```

3. Test queue writer:
   ```bash
   python -c "from src.capture.shared.queue_writer import MessageQueueWriter; w = MessageQueueWriter(); print(w.health_check())"
   ```

### Processing server not starting

1. Check dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Verify database exists:
   ```bash
   ls -la ~/.blueplane/telemetry.db
   ```

3. Check logs:
   ```bash
   python scripts/start_server.py
   ```

## Development

### Testing Hooks

Test individual hooks with JSON input:

```bash
echo '{"session_id":"test-123","prompt":"Hello"}' | python ~/.claude/hooks/telemetry/user_prompt_submit.py
```

### Running Tests

```bash
python test_claude_code_hook.py
```

### Adding New Hooks

1. Create new hook script in `src/capture/claude_code/hooks/`
2. Extend `ClaudeCodeHookBase` class
3. Implement `execute()` method
4. Add to installation script
5. Update settings.json registration

Example:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType

class MyNewHook(ClaudeCodeHookBase):
    def __init__(self):
        super().__init__(HookType.MY_NEW_HOOK)

    def execute(self) -> int:
        # Extract data from self.input_data
        payload = {"my_field": self.input_data.get('my_field')}

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.MY_EVENT,
            payload=payload
        )
        self.enqueue_event(event)
        return 0

if __name__ == '__main__':
    hook = MyNewHook()
    sys.exit(hook.run())
```

## Related Documentation

- [Architecture Overview](../../../docs/ARCHITECTURE.md)
- [Layer 1 Capture Specification](../../../docs/architecture/layer1_capture.md)
- [Claude Code Hook Input Reference](../../../docs/architecture/layer1_claude_hook_output.md)

---

**Status**: ✅ Implementation Complete
- Hook base class implemented
- 6 hook scripts implemented
- Transcript monitor implemented
- Installation script ready
- Documentation complete
