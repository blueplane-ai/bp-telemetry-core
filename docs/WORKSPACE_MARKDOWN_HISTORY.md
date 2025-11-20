# Workspace Markdown History Pipeline

## Overview

The Workspace Markdown History pipeline monitors Cursor workspace databases and generates human-readable Markdown history files. It captures workspace activity including AI generations, composer sessions, file edits, and more.

## Features

### Implemented (M1-M4)

- **M1: Markdown Generation**: Reads from Cursor's ItemTable and generates formatted Markdown
- **M2: Background Monitoring**: Integrates with TelemetryServer, monitors workspace databases
- **M3: Configuration**: Full configuration support via `config/cursor.yaml`
- **M4: DuckDB Sink**: Scaffolded analytics database (feature-flagged, disabled by default)

## Architecture

### Components

1. **CursorMarkdownWriter** (`src/processing/cursor/markdown_writer.py`)
   - Formats ItemTable data into Markdown
   - Handles 8 different key types with specialized formatting
   - Writes to `<workspace>/.history/{hash}_{timestamp}.md`

2. **CursorMarkdownMonitor** (`src/processing/cursor/markdown_monitor.py`)
   - Polls workspace databases every 2 minutes
   - Detects changes using SHA256 hash
   - Debounces writes (configurable delay)
   - Manages database connections and cleanup

3. **CursorDuckDBWriter** (`src/processing/cursor/duckdb_writer.py`)
   - Optional analytics database sink
   - Scaffolded with schema for future use
   - Behind feature flag (disabled by default)

### Data Flow

```
Cursor Workspace DB (state.vscdb)
  ↓ (polling every 2 minutes)
CursorMarkdownMonitor
  ↓ (change detection via hash)
Debounce (10s default)
  ↓ (write)
CursorMarkdownWriter → Markdown File
  ↓ (optional)
CursorDuckDBWriter → DuckDB
```

## Configuration

Edit `config/cursor.yaml`:

```yaml
cursor:
  markdown_monitor:
    enabled: true
    output_dir: null  # null = workspace/.history/
    poll_interval_seconds: 120  # 2 minutes
    debounce_delay_seconds: 10  # Normal: 10s, Dev: 2s
    query_timeout_seconds: 1.5
    
  duckdb_sink:
    enabled: false  # Feature flag
    database_path: null  # null = ~/.blueplane/cursor_history.duckdb
```

## Monitored Keys

The pipeline reads these keys from Cursor's ItemTable:

1. `aiService.generations` - AI generation metadata
2. `aiService.prompts` - User prompts
3. `composer.composerData` - Composer session data
4. `workbench.backgroundComposer.workspacePersistentData` - Background composer state
5. `workbench.agentMode.exitInfo` - Agent mode visibility state
6. `interactive.sessions` - Interactive session metadata
7. `history.entries` - Recently opened files
8. `cursorAuth/workspaceOpenedDate` - Workspace open timestamp

## Output Format

Generated Markdown files include:

- **Header**: Workspace path, hash, timestamp
- **AI Service Activity**: Generations and prompts
- **Composer Sessions**: Session details, modes, line changes
- **Background Composer**: Setup steps, terminal state
- **Agent Mode**: Exit visibility state
- **File History**: Recently accessed files
- **Interactive Sessions**: Session metadata
- **Workspace Info**: Open timestamp

## Usage

### Server Integration

The monitor is automatically started when TelemetryServer starts:

```python
from src.processing.server import TelemetryServer

server = TelemetryServer()
server.start()  # Markdown monitor starts in background
```

### Manual Testing

```bash
# Test Markdown writer
python test_markdown_writer.py

# Test configuration
python test_config.py

# Test DuckDB (if enabled)
python test_duckdb_writer.py
```

## Performance

- **Polling Interval**: 2 minutes (configurable)
- **Debounce Delay**: 10 seconds (configurable, 2s for dev)
- **Database Timeout**: 1.5 seconds (aggressive to avoid blocking Cursor)
- **Change Detection**: O(1) using SHA256 hash comparison
- **Connection Management**: Lazy loading, automatic cleanup

## Privacy

- **No Code Content**: Only metadata and telemetry
- **Hash-based IDs**: Workspace paths hashed
- **Local Only**: All data stays on local machine
- **Read-Only**: Database opened in read-only mode

## Future Enhancements

- [ ] Complete DuckDB analytics implementation
- [ ] Watchdog file monitoring (replace/augment polling)
- [ ] SQL analytics queries on DuckDB
- [ ] Export to other formats (JSON, CSV)
- [ ] Workspace comparison and diffing
- [ ] Timeline visualization

## Troubleshooting

### Monitor Not Starting

Check logs for initialization errors:
- Ensure Redis is running
- Verify cursor.yaml exists and is valid
- Check session_monitor is initialized

### No Markdown Files Generated

- Verify workspace database exists (`state.vscdb`)
- Check workspace is active (session_start event sent)
- Look for "No data available" debug logs
- Ensure output directory is writable

### DuckDB Errors

- Check DuckDB is installed: `pip install duckdb>=0.9.0`
- Verify `duckdb_sink.enabled` is true in config
- Check database_path is writable

## Development

### Adding New Keys

1. Add key to `TRACE_RELEVANT_KEYS` in `markdown_writer.py`
2. Implement formatting method `_format_<key_name>()`
3. Add section to `_generate_markdown()`
4. Update tests

### Testing

```bash
# Run all tests
python test_markdown_writer.py
python test_config.py
python test_duckdb_writer.py

# Integration test (requires Redis + active workspace)
python -m pytest scripts/test_end_to_end.py -v
```

## Architecture Decisions

### Why Polling Instead of File Watching?

- **Reliability**: File watchers can miss events on some systems
- **Simplicity**: Polling is easier to debug and reason about
- **Safety Net**: 2-minute polling acts as fallback
- **Future**: Can add watchdog as optimization, keep polling as backup

### Why Debounce?

- **Efficiency**: Avoid writing for every tiny change
- **Rate Limiting**: Cursor updates ItemTable frequently
- **Configurable**: 2s for rapid dev iteration, 10s for production

### Why DuckDB?

- **Analytics**: SQL queries on workspace history
- **Performance**: Columnar storage, fast aggregations
- **Embedded**: No server, single file database
- **Future**: Ready for BI tools, dashboards

## License

Copyright © 2025 Sierra Labs LLC  
SPDX-License-Identifier: AGPL-3.0-only
