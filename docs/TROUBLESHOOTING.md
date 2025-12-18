# Troubleshooting Guide

## Quick Status Check

Run a comprehensive status check of all components:

```bash
cd /Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core
python scripts/server_ctl.py status --verbose

# Or check manually:
# - Extension status in Cursor
# - Processing server: ps aux | grep start_server.py
# - Redis: redis-cli PING && redis-cli XLEN telemetry:message_queue
```

Or manually check each component:

```bash
# 1. Check Cursor extension
# Open Cursor → Extensions → Search "Blueplane" → Verify it's installed and enabled

# 2. Check Claude Code hooks (if using Claude Code)
ls -la ~/.claude/hooks/telemetry/*.py | wc -l
cat ~/.claude/settings.json | jq '.hooks | length'

# 3. Check Redis queue
redis-cli XLEN telemetry:message_queue
redis-cli XINFO GROUPS telemetry:message_queue

# 4. Check database (cursor events)
sqlite3 ~/.blueplane/telemetry.db "SELECT COUNT(*) FROM cursor_raw_traces;"

# 5. Check processing server
ps aux | grep start_server.py
```

---

## Common Issues and Solutions

### 1. Redis Socket Timeout Error

**Error:**

```
ERROR - Error reading messages: Timeout reading from socket
```

**Cause:**
The Redis `socket_timeout` was too short (1 second) for blocking read operations. When `XREADGROUP` blocks for `block_ms` milliseconds waiting for messages, the socket timeout fires first.

**Solution:**
Already fixed in `config/redis.yaml`:

```yaml
connection_pool:
  socket_timeout: 5.0 # Must be > block_ms (1000ms = 1s)
  socket_connect_timeout: 2.0
  retry_on_timeout: true
```

**How to Apply:**

```bash
# Restart the processing server
# Press Ctrl+C to stop the current server
python scripts/start_server.py
```

---

### 2. Events Stuck in Redis Queue

**Symptom:**

```bash
redis-cli XLEN telemetry:message_queue
# Returns large number (e.g., 403)
```

**Cause:**
Processing server not running or crashed.

**Solution:**

```bash
# Start the processing server
cd /Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core
python scripts/start_server.py
```

**Monitor Progress:**

```bash
# In another terminal, watch the queue drain
watch -n 1 'redis-cli XLEN telemetry:message_queue'
```

---

### 3. No Model Data or Tokens Captured

**Symptom:**
Database has events but `model` and `tokens_used` columns are empty/NULL.

**Cause:**
Database monitor may not be extracting all available data from Cursor's SQLite database, or the data may not be available in Cursor's database schema.

**Solution:**

For **Cursor**:

```bash
# Ensure processing server with database monitor is running
python scripts/start_server.py

# Check database monitor logs for extraction errors
# Restart Cursor to ensure fresh database state
# Command Palette → "Developer: Reload Window"

# Note: Cursor's database may not always contain model/token data
# This is a limitation of Cursor's database schema
```

For **Claude Code**:

```bash
# Reinstall hooks to ensure latest version
python scripts/install_claude_hooks.py

# Restart Claude Code
```

**Verify:**
Submit a new prompt in Cursor and check:

```bash
python3 << 'EOF'
from src.processing.database.sqlite_client import SQLiteClient
from pathlib import Path
client = SQLiteClient(str(Path.home() / '.blueplane' / 'telemetry.db'))
with client.get_connection() as conn:
    cursor = conn.execute('''
        SELECT model, tokens_used, timestamp
        FROM cursor_raw_traces
        WHERE model IS NOT NULL
        ORDER BY sequence DESC
        LIMIT 5
    ''')
    for row in cursor.fetchall():
        print(f"Model: {row[0]}, Tokens: {row[1]}, Time: {row[2]}")
EOF
```

---

### 4. No Database Traces

**Symptom:**
No events with `event_type = 'database_trace'` in database.

**Cause:**
Cursor extension not running or database monitor failed to start.

**Solution:**

1. Check extension status in Cursor:

   ```
   Command Palette → "Blueplane: Show Status"
   ```

2. If extension not active:

   ```bash
   # Recompile extension
   cd src/capture/cursor/extension
   npm install
   npm run compile

   # Install in Cursor via Extensions panel
   # Look for "Blueplane Cursor Telemetry"
   ```

3. Check extension logs:
   ```
   Command Palette → "Developer: Open Extension Logs"
   Filter by: "Blueplane"
   ```

**Common Extension Issues:**

- Database file not found (Cursor's `state.vscdb`)
- Permission denied reading database
- Database schema mismatch

---

### 5. Permission Denied on Extension or Hook Installation

**Error:**

```
Permission denied when installing extension or hooks
```

**Cause:**
Insufficient permissions for installation.

**Solution:**

For **Cursor extension**:

```bash
# Install extension through Cursor UI instead
# Open Cursor → Extensions → Install from VSIX → Select the .vsix file

# Or check file permissions on the extension directory
ls -la src/capture/cursor/extension/
```

For **Claude Code hooks**:

```bash
# Install with appropriate permissions
python scripts/install_claude_hooks.py

# Or manually with sudo if needed:
sudo mkdir -p ~/.claude/hooks/telemetry
sudo cp src/capture/claude_code/hooks/*.py ~/.claude/hooks/telemetry/
sudo chmod +x ~/.claude/hooks/telemetry/*.py
```

---

### 6. Empty event_data BLOB

**Symptom:**
Events in database but `event_data` column is NULL or empty.

**Cause:**
Compression or serialization error during batch write.

**Solution:**
Check processing server logs for errors:

```bash
# Look for write errors
grep "Failed to process batch" ~/.blueplane/logs/processing.log

# Check SQLite writer errors
python3 << 'EOF'
import logging
logging.basicConfig(level=logging.DEBUG)
from src.processing.database.writer import SQLiteBatchWriter
# Test write with sample event
EOF
```

---

### 7. High Memory Usage

**Symptom:**
Processing server using excessive RAM (>500MB).

**Cause:**

- Large backlog in Redis queue
- Batch size too large
- Memory leak in consumer

**Solution:**

1. **Reduce batch size** in `config/redis.yaml`:

   ```yaml
   streams:
     message_queue:
       count: 50 # Reduce from 100
   ```

2. **Enable adaptive backpressure** (already enabled by default)

3. **Monitor memory:**

   ```bash
   # Check Python process memory
   ps aux | grep start_server.py

   # Or use htop/top
   htop -p $(pgrep -f start_server)
   ```

---

### 8. Database Locked Error

**Error:**

```
sqlite3.OperationalError: database is locked
```

**Cause:**
Multiple processes trying to write to SQLite simultaneously.

**Solution:**
SQLite is configured with WAL mode to prevent this, but if it persists:

1. **Check for zombie processes:**

   ```bash
   ps aux | grep start_server
   pkill -f start_server.py
   ```

2. **Verify WAL mode:**

   ```bash
   sqlite3 ~/.blueplane/telemetry.db "PRAGMA journal_mode;"
   # Should return: wal
   ```

3. **Rebuild database** (last resort):
   ```bash
   mv ~/.blueplane/telemetry.db ~/.blueplane/telemetry.db.backup
   python scripts/init_database.py
   ```

---

## Service Status Monitoring

### Real-time Monitoring

**Watch Redis queue:**

```bash
watch -n 1 'redis-cli XLEN telemetry:message_queue'
```

**Monitor processing server logs:**

```bash
tail -f /tmp/bp_server.log
# Or if using log file:
tail -f ~/.blueplane/logs/processing.log
```

**Check database growth:**

```bash
watch -n 5 'sqlite3 ~/.blueplane/telemetry.db "SELECT COUNT(*) FROM cursor_raw_traces;"'
```

### Health Check Dashboard

Run comprehensive status check:

```bash
python scripts/check_status.py
```

Expected output:

```
✅ Hooks: 11 scripts installed
✅ Database Traces: Extension compiled, Cursor DB found
✅ Redis Queue: 454 events, 2 consumers, lag: 0
✅ Database: 740 events, 661 in last hour
✅ Processing Server: Running (PID: 85691)
```

---

## Diagnostic Commands

### Check System Health

```bash
# Redis queue length
redis-cli XLEN telemetry:message_queue

# Database event count (Cursor)
sqlite3 ~/.blueplane/telemetry.db "SELECT COUNT(*) FROM cursor_raw_traces;"

# Recent events
sqlite3 ~/.blueplane/telemetry.db "SELECT event_type, COUNT(*) FROM cursor_raw_traces WHERE timestamp > datetime('now', '-1 hour') GROUP BY event_type;"

# Redis consumer group info
redis-cli XINFO GROUPS telemetry:message_queue

# Processing server status
ps aux | grep start_server.py
```

### Full System Test

```bash
# Run end-to-end test
python scripts/test_end_to_end.py

# Check installation manually:
# - Extension status in Cursor
# - Processing server: ps aux | grep start_server.py
# - Redis: redis-cli PING && redis-cli XLEN telemetry:message_queue
```

---

## Getting Help

If issues persist:

1. **Enable debug logging:**

   ```yaml
   # config/redis.yaml
   logging:
     level: DEBUG
   ```

2. **Collect logs:**

   ```bash
   # Processing server logs
   tail -f logs/processing.log

   # Extension logs (in Cursor)
   Command Palette → "Developer: Open Extension Logs"
   ```

3. **Check GitHub issues:**
   - Search existing issues
   - Create new issue with logs and config

---

**Last Updated:** November 11, 2025
