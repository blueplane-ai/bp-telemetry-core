# Cursor Telemetry Capture

Layer 1 telemetry capture system for Cursor IDE using VSCode extension and database monitoring.

**Important:** Cursor does not use hooks. All telemetry is captured through the VSCode extension and database monitoring.

## Architecture

### Extension-Based Approach (No Hooks)

Cursor telemetry is captured through two mechanisms:

- **Extension Events**: VSCode extension manages sessions and sends session lifecycle events (start/end)
- **Database Monitoring**: Python processing server monitors Cursor's SQLite database for AI generations and traces
- **Workspace-Specific Sessions**: Each workspace gets its own session with unique session ID

### How It Works

```
┌─────────────────────┐
│  Cursor Workspace   │
│   (any project)     │
└──────────┬──────────┘
           │
           ├─ Extension activated
           │  └─> Sends session_start event (workspace_hash, PID)
           │
           ├─ User interacts with AI
           │  └─> Python database monitor detects changes in state.vscdb
           │      └─> Sends AI generation events (prompts, responses, tool usage)
           │
           └─ Extension deactivated
              └─> Sends session_end event
```

## Installation

### Prerequisites

- Cursor IDE installed
- Python 3.11+
- Redis server running (localhost:6379)

### 1. Install Extension

```bash
cd src/capture/cursor/extension
npm install
npm run compile
# Then install via Cursor: Extensions → Install from VSIX
# Or: code --install-extension <path-to-vsix>
```

### 2. Start Redis

```bash
redis-server
```

### 3. Start Processing Server

The processing server includes the database monitor that polls Cursor's SQLite database:

```bash
python scripts/start_server.py
```

### 4. Configure (Optional)

Create `~/.blueplane/config.yaml`:

```yaml
redis:
  host: localhost
  port: 6379

privacy:
  opt_out:
    - code_content
    - file_paths

stream:
  name: telemetry:message_queue
  max_length: 10000
```

## Session Tracking

### Sessions vs Conversations

**Important**: Cursor has a distinct concept of **sessions** and **conversations**:

- **Session**: Represents an IDE window/workspace instance. Created when you open a Cursor workspace. Stored in `cursor_sessions` table.
- **Conversation**: Represents a single chat thread within a session. Multiple conversations can occur within one session. Stored in `conversations` table with `session_id` referencing the session.

This is different from Claude Code, where sessions and conversations are 1:1 (no separate session concept).

See [Session & Conversation Schema](../../../docs/SESSION_CONVERSATION_SCHEMA.md) for complete details.

### Session Files

Each workspace gets a unique session file:

```
~/.blueplane/cursor-session/
  ├─ a1b2c3d4e5f6g7h8.json  (workspace 1)
  ├─ 9i8h7g6f5e4d3c2b.json  (workspace 2)
  └─ ...
```

Filename is SHA256 hash of workspace path (truncated to 16 chars).

### Session File Format

```json
{
  "CURSOR_SESSION_ID": "curs_1731283200000_abc123",
  "CURSOR_WORKSPACE_HASH": "a1b2c3d4e5f6g7h8",
  "workspace_path": "/home/user/my-project",
  "updated_at": "2025-11-11T10:30:00.000Z"
}
```

**Note**: The `CURSOR_SESSION_ID` in the session file is the **external session ID**. The processing server creates an internal UUID (`cursor_sessions.id`) and stores the mapping. Conversations reference the internal session ID via `conversations.session_id`.

### Session Events

The extension sends session lifecycle events to Redis:

**session_start:**

```json
{
  "hook_type": "session",
  "event_type": "session_start",
  "timestamp": "2025-11-11T10:30:00.000Z",
  "payload": {
    "workspace_path": "/home/user/my-project",
    "session_id": "curs_1731283200000_abc123",
    "workspace_hash": "a1b2c3d4e5f6g7h8"
  },
  "metadata": {
    "pid": 12345,
    "workspace_hash": "a1b2c3d4e5f6g7h8",
    "platform": "cursor"
  }
}
```

**session_end:**
Same format, but `event_type: "session_end"`.

## Event Capture

### Extension Events

The extension captures:

1. **Session lifecycle** - Session start/end with workspace context

### Database Monitoring Events

The Python processing server monitors Cursor's `state.vscdb` database and captures:

1. **AI prompts** - User prompt submissions to AI
2. **AI responses** - Assistant responses and generations
3. **Tool usage** - MCP tool executions, file operations
4. **Conversation traces** - Full conversation history

## Event Flow

```
Extension Start → session_start event → Redis
    ↓
Python Database Monitor detects AI activity → Sends traces → Redis
    ↓
Extension Stop → session_end event → Redis
```

## Privacy

All telemetry capture respects privacy settings from `~/.blueplane/config.yaml`:

- **Code content**: Never captured by default
- **File paths**: Hashed if `file_paths` opt-out enabled
- **Error messages**: Redacted to error type only
- **Environment vars**: Never logged

See `config/privacy.yaml` for full privacy settings.

## Debugging

### Check Extension Status

View extension logs in Cursor:

- `View` → `Output` → Select "Blueplane Telemetry"

### Check Session File

```bash
cat ~/.blueplane/cursor-session/*.json
```

Should show session info for each workspace.

### Monitor Redis Events

```bash
redis-cli XREAD COUNT 10 STREAMS telemetry:message_queue 0
```

### Check Database Monitor

```bash
# Check if processing server is running with database monitor
ps aux | grep start_server.py

# View processing server logs
python scripts/start_server.py  # Should show database monitor activity
```

## Multiple Workspaces

The extension-based approach supports multiple Cursor workspaces simultaneously:

1. Each workspace gets unique session file (workspace hash)
2. Each workspace has unique session ID (external session ID from extension)
3. Processing server creates internal session record in `cursor_sessions` table
4. Extension sends session events with workspace hash for each workspace
5. Database monitor tracks all Cursor instances via PID
6. All events tagged with workspace_hash and PID
7. Multiple conversations can occur within each session (stored in `conversations` table with `session_id` reference)

## Uninstallation

```bash
# Uninstall extension from Cursor
# Extensions → Blueplane Telemetry → Uninstall

# Remove session files
rm -rf ~/.blueplane/cursor-session
```

## Troubleshooting

**Extension not capturing events:**

- Check extension is installed and activated in Cursor
- View extension logs: Cursor > View > Output > Blueplane Telemetry
- Verify Redis is running: `redis-cli ping`
- Check Redis connection in extension settings

**Database monitor not working:**

- Verify processing server is running: `ps aux | grep start_server.py`
- Check server logs for database monitor errors
- Verify Cursor's `state.vscdb` database exists in workspace
- Ensure database monitor is enabled in configuration

**Wrong session ID:**

- Check session file for current workspace in `~/.blueplane/cursor-session/`
- Verify workspace hash matches current directory hash
- Restart extension to create new session

**Events not appearing in Redis:**

- Check Redis connection in extension logs
- Verify config.yaml has correct Redis host/port
- Ensure processing server has access to Redis

## Development

### Testing Extension

1. Open extension directory in VSCode:

   ```bash
   cd src/capture/cursor/extension
   code .
   ```

2. Run in debug mode:

   - Press F5 to launch Extension Development Host
   - Open a Cursor workspace in the new window
   - View extension logs in Output panel

3. Check Redis for events:
   ```bash
   redis-cli XLEN telemetry:message_queue
   redis-cli XREAD COUNT 1 STREAMS telemetry:message_queue 0-0
   ```

### Extending the Extension

1. Modify TypeScript files in `extension/src/`
2. Add new event capture logic
3. Compile: `npm run compile`
4. Test in Extension Development Host
5. Package: `npx vsce package`

## Architecture

See main documentation:

- [Layer 1 Capture](../../../docs/architecture/layer1_capture.md)
- [Database Architecture](../../../docs/architecture/layer2_db_architecture.md)
- [Overall Architecture](../../../docs/ARCHITECTURE.md)

## Next Steps

After installation, Layer 2 (Processing) will:

1. Read events from Redis Streams
2. Process and enrich events
3. Store in DuckDB (raw traces) and SQLite (conversations)
4. Derive metrics and update Redis TimeSeries

See `docs/architecture/layer2_async_pipeline.md` for details.
