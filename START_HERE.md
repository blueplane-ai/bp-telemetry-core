# Blueplane Telemetry - Quick Start Guide

**Platform Support:** macOS only (for now)

This guide will help you set up Blueplane Telemetry from scratch to track your AI coding sessions in Claude Code and Cursor.

## Prerequisites

- macOS (Intel or Apple Silicon)
- Python 3.8 or higher
- Node.js 16+ (for Cursor extension)
- Redis server (can be installed via Homebrew)
- Claude Code and/or Cursor installed

## Step 1: Install Dependencies

### 1.1 Install Redis (if not already installed)

```bash
# Install Redis using Homebrew
brew install redis

# Start Redis service
brew services start redis

# Verify Redis is running
redis-cli ping
# Should respond with: PONG
```

### 1.2 Install Python Dependencies

```bash
# Clone the repository (if you haven't already)
git clone https://github.com/your-org/bp-telemetry-core.git
cd bp-telemetry-core

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install required Python packages
pip install -r requirements.txt
```

## Step 2: Claude Code Setup

Claude Code uses session hooks to track the lifecycle of your coding sessions. Install them with:

```bash
# Run the Claude hooks installation script
python scripts/install_claude_hooks.py

# This will:
# - Copy session hooks (session_start.py, session_end.py) to ~/.claude/hooks/telemetry/
# - Update ~/.claude/settings.json with hook configurations
# - Create ~/.blueplane/ directory for data storage
```

**Note:** Claude Code currently only uses session lifecycle hooks (session_start and session_end) to track when sessions begin and end. Additional telemetry is captured through transcript monitoring.

### Verify Claude Code Installation

```bash
# Check that session hooks are installed
ls ~/.claude/hooks/telemetry/
# Should show: session_start.py, session_end.py

# Check settings.json was updated
cat ~/.claude/settings.json | grep -A 5 "hooks"
```

## Step 3: Cursor Setup

Cursor uses a VSCode extension for all telemetry capture. No hooks are required.

### 3.1 Build the Extension

```bash
# Navigate to the extension directory
cd src/capture/cursor/extension

# Install dependencies
npm install

# Compile the TypeScript code
npm run compile

# Package the extension
npx vsce package
# This creates blueplane-cursor-telemetry-0.1.0.vsix
```

### 3.2 Install the Extension in Cursor

```bash
# Install the extension using Cursor's command line
cursor --install-extension ./blueplane-cursor-telemetry-0.1.0.vsix

# Or install manually:
# 1. Open Cursor
# 2. Go to Extensions (Cmd+Shift+X)
# 3. Click the "..." menu → "Install from VSIX..."
# 4. Select the blueplane-cursor-telemetry-0.1.0.vsix file
```

### 3.3 Verify Extension Installation

1. Open Cursor
2. Go to Extensions (Cmd+Shift+X)
3. Search for "Blueplane"
4. Ensure "Blueplane Telemetry for Cursor" is installed and enabled
5. Open Command Palette (Cmd+Shift+P) and verify these commands exist (No action needed with them, just confirms it's running):
   - `Blueplane: Show Session Status`
   - `Blueplane: Start New Session`
   - `Blueplane: Stop Current Session`
6. Alternatively, look for "Blueplane" on the bottom right corner in your extension status bar

### 3.4 Configure Cursor Log Level

To ensure detailed traces are being captured, set your log level to Trace:

1. Open Command Palette (Cmd+Shift+P on macOS, Ctrl+Shift+P on Windows/Linux)
2. Type and select: `Developer: Set Log Level`
3. Select: `Trace`

This enables detailed logging that can help diagnose issues with the extension or telemetry capture.

## Step 4: Configuration (Optional)

Blueplane Telemetry Core uses a unified YAML configuration system. The default configuration (`config/config.yaml`) works out of the box, but you can customize settings by creating a user config file.

### 4.1 Review Default Configuration

```bash
# View the default configuration
cat config/config.yaml

# View the configuration schema documentation
cat config/config.schema.yaml
```

### 4.2 Create User Configuration (Optional)

```bash
# Create user config directory
mkdir -p ~/.blueplane

# Copy default config as starting point
cp config/config.yaml ~/.blueplane/config.yaml

# Edit to customize (optional)
# Common customizations:
# - Redis connection settings (if not using default localhost:6379)
# - Poll intervals for monitors
# - Logging levels
# - Platform-specific paths (Windows/Linux)
```

**Note**: You only need to override settings you want to change. The system merges your user config with defaults.

### 4.3 Configuration Sections

The configuration includes these main sections:

- **paths**: Database and IDE file paths
- **redis**: Redis connection and pool settings
- **streams**: Message queue, DLQ, and CDC stream settings
- **timeouts**: Various timeout values
- **monitoring**: Poll intervals and thresholds
- **batching**: Batch processing settings
- **logging**: Log levels and feature flags
- **features**: Feature toggles

See `config/config.schema.yaml` for complete documentation.

## Step 5: Initialize and Start the Server

### 5.1 Initialize the Database

```bash
# Return to project root
cd /path/to/bp-telemetry-core

# Initialize SQLite database
python scripts/init_database.py
# Creates ~/.blueplane/telemetry.db with required tables

# Initialize Redis streams
python scripts/init_redis.py
# Creates Redis streams and consumer groups
```

### 5.2 Start the Processing Server

```bash
# Start the telemetry processing server
python scripts/server_ctl.py start --daemon

# The server will:
# - Load configuration from ~/.blueplane/config.yaml (if exists) or config/config.yaml
# - Monitor Claude Code transcript files
# - Process Cursor database events
# - Write to SQLite database
# - Update Redis metrics

# Keep this running in a terminal window or use a process manager
```

### 5.3 Verify Server is Running

```bash
# Check server status
python scripts/check_status.py

# Or manually check:
python scripts/server_ctl.py status --verbose
redis-cli XLEN telemetry:events
```

## Step 6: Observation and Data Access

Once everything is running, your telemetry data is being collected in the following locations:

### Data Locations

| Component                   | Location                                                     | Description                              |
| --------------------------- | ------------------------------------------------------------ | ---------------------------------------- |
| **Main Database**           | `~/.blueplane/telemetry.db`                                  | SQLite database with all telemetry data  |
| **Redis Metrics**           | `localhost:6379`                                             | Real-time metrics and message queue      |
| **Claude Code Sessions**    | `~/.claude/projects/<project>/<session-hash>.jsonl`          | Raw Claude Code transcripts              |
| **Cursor Workspace Traces** | `~/Library/Application Support/Cursor/User/<workspace-hash>` | Raw Cursor Conversation Info             |
| **Processing Logs**         | `~/.blueplane/server.log`                                    | Server activity and errors (daemon mode) |

### Accessing Your Data

#### Quick Database Check

```bash
# View recent conversations
sqlite3 ~/.blueplane/telemetry.db "
  SELECT platform, session_id, started_at, ended_at
  FROM conversations
  ORDER BY started_at DESC
  LIMIT 10;
"

# Check raw event count
sqlite3 ~/.blueplane/telemetry.db "
  SELECT COUNT(*) as total_events FROM raw_traces;
"
```

#### View Redis Metrics

```bash
# Check message queue length
redis-cli XLEN telemetry:events

# View consumer group info
redis-cli XINFO GROUPS telemetry:events
```

#### Monitor Claude Code Sessions

```bash
# List active Claude Code sessions
ls -la ~/.claude/sessions/

# View current transcript (if session is active)
tail -f ~/.claude/sessions/*/transcript.jsonl | jq '.'
```

#### Monitor Cursor Sessions

```bash
# Check Cursor history files
ls -la ~/.cursor/User/History/

# View recent Cursor activity (last modified files)
ls -lt ~/.cursor/User/History/*.json | head -10
```

## Step 7: Test Your Setup

### Test Claude Code Capture

1. Open Claude Code
2. Start a new conversation
3. Ask a simple question like "What is 2+2?"
4. Check that events appear in the database:

```bash
sqlite3 ~/.blueplane/telemetry.db "
  SELECT * FROM raw_traces
  WHERE platform='claude_code'
  ORDER BY timestamp DESC
  LIMIT 5;
"
```

### Test Cursor Capture

1. Open Cursor with a project
2. Use the AI chat to ask a question
3. Verify session tracking:

```bash
# Check extension status in Cursor
# Command Palette → "Blueplane: Show Session Status"

# Check database for Cursor events
sqlite3 ~/.blueplane/telemetry.db "
  SELECT * FROM raw_traces
  WHERE platform='cursor'
  ORDER BY timestamp DESC
  LIMIT 5;
"
```

## Troubleshooting

### Common Issues

#### Redis Connection Failed

```bash
# Check Redis is running
redis-cli ping

# Restart Redis if needed
brew services restart redis
```

#### No Claude Code Events

```bash
# Verify hooks are installed
cat ~/.claude/settings.json | grep telemetry

# Check hook permissions
ls -la ~/.claude/hooks/telemetry/*.py
# All hooks should be executable (755)
```

#### No Cursor Events

```bash
# Check extension is running
# In Cursor: View → Output → Select "Blueplane Telemetry"

# Verify Redis connection from extension
# Check extension settings in Cursor
```

#### Server Not Processing Events

```bash
# Check server logs
# Look for errors in the server logs
tail -f ~/.blueplane/server.log

# Verify database exists
ls -la ~/.blueplane/telemetry.db

# Check Redis stream
redis-cli XLEN telemetry:events
```

## Step 8: Install Claude Code Skill (Recommended)

For the best experience working with Blueplane in Claude Code, install the Blueplane management skill at the user level. This makes the skill available across all your projects.

```bash
# Copy the skill to your user-level Claude skills directory
mkdir -p ~/.claude/skills
cp -r .claude/skills/blueplane ~/.claude/skills/

# The skill will now be available in all Claude Code sessions
```

### What the Skill Provides

The Blueplane skill gives Claude comprehensive knowledge about:

- **Server Management**: Commands to start, stop, restart, and check server status
- **Database Queries**: How to retrieve traces, sessions, conversations, and workspace data
- **Troubleshooting**: Debug telemetry issues and verify data collection
- **Development Workflow**: Integrated server lifecycle management

### Using the Skill

Once installed, you can ask Claude questions like:

- "Show me recent Claude Code traces from the database"
- "What Cursor sessions are currently active?"
- "Restart the Blueplane server and check its status"
- "Query conversation data for this workspace"
- "How many events have been captured today?"

The skill contains detailed documentation about the database schema, query patterns, and server management commands. See [Blueplane Skill Documentation](./.claude/skills/blueplane/SKILL.md) for complete reference.

## Additional Resources

- [Architecture Documentation](docs/ARCHITECTURE.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Database Schema](docs/architecture/layer2_db_architecture.md)
- [Privacy & Security](docs/architecture/layer1_capture.md#privacy-considerations)

## Support

- **Issues:** File a GitHub issue in the repository
- **Questions:** Check the documentation first, then open a GitHub Discussion

---

**Note:** This system is designed to keep all your data local. No telemetry is sent to external servers. All data stays on your machine in `~/.blueplane/` and Redis.
