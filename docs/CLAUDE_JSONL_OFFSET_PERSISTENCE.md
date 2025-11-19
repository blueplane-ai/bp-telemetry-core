# Claude JSONL Offset Persistence (Spec)

## Goals
- Persist JSONL tail offsets in SQLite instead of `~/.blueplane/claude_jsonl_offsets.json`.
- Associate each tracked file with the originating Claude session/agent for easier cleanup and observability.
- Make offsets durable across restarts and visible via SQL tooling.
- Remove all code paths that read or write the legacy JSON file (no backward compatibility required).

## Non-goals
- Backfilling existing offsets from the JSON file.
- Changing how JSONL files are discovered or parsed.
- Implementing incremental compaction/TTL beyond tying records to session lifecycle hooks.

## Database Schema
Add a new table managed alongside other Claude tables:

```
claude_jsonl_offsets (
    file_path TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT,
    line_offset INTEGER NOT NULL,
    last_size INTEGER NOT NULL,
    last_mtime REAL NOT NULL,
    last_read_time REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES conversations(session_id)
)
```

Notes:
- `file_path` is unique because a given JSONL file belongs to a single session/agent.
- `agent_id` is nullable (only set for agent-side JSONL files).
- `updated_at` uses SQLite trigger `DEFAULT CURRENT_TIMESTAMP` for quick staleness checks.

## Persistence API
Introduce `JSONLOffsetStore` (e.g., `src/processing/claude_code/jsonl_offset_store.py`) with:
- `get_state(file_path: Path) -> FileState | None`
- `upsert_state(file_path, session_id, agent_id, state)`
- `delete_for_session(session_id: str)`
- (optional) `delete(file_path)` for manual cleanup.

The store uses the shared `SQLiteClient` and performs `INSERT ... ON CONFLICT(file_path) DO UPDATE`.

## Monitor Changes
- `ClaudeCodeJSONLMonitor` now depends on `SQLiteClient` (passed in via `TelemetryServer`) and uses `JSONLOffsetStore` to hydrate/persist `FileState`.
- `FileState` retains in-memory helpers (`reset`, `has_changed`) but no longer serializes to JSON.
- Each read updates the DB row; truncations reset offsets before persisting.
- When session metadata is available, pass `session_id` and `agent_id` to the store so rows can be enumerated/cleaned later.

## Cleanup Lifecycle
- On `session_end` (from hooks or timeout manager) call `offset_store.delete_for_session(session_id)` to drop lingering rows.
- Optional future work: add periodic vacuum for files missing on disk, but not required for this change.

## Server Wiring
- Update `TelemetryServer._initialize_claude_code_monitor` to pass `sqlite_client` into `ClaudeCodeJSONLMonitor`.
- Remove references to the legacy JSON file and delete the old persistence helper.

## Testing
- Unit-ish coverage via existing e2e test after it exercises restart scenarios.
- Manual verification: start server, ingest events, restart server; observe that offsets continue from prior rows by querying `claude_jsonl_offsets`.


