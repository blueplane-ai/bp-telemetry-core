# Database Monitor Implementation Tasks

**Date**: November 11, 2025  
**Status**: Implementation Plan  
**Based on**: `DATABASE_MONITOR_REFACTOR.md` (Option 2 - Production-Ready)

---

## Overview

This document outlines the implementation tasks for moving database monitoring from TypeScript extension to Python processing server. The implementation follows the production-ready design with comprehensive error handling, schema detection, deduplication, and robust workspace mapping.

**Note**: Session monitoring relies exclusively on Redis events from the extension. The extension must be installed and running for database monitoring to work.

---

## Phase 1: Foundation & Infrastructure

### 1.1 Create Directory Structure
- [ ] Create `src/processing/cursor/` directory
- [ ] Create `src/processing/cursor/__init__.py`
- [ ] Create placeholder files for all modules:
  - `session_monitor.py`
  - `workspace_mapper.py`
  - `schema_detector.py`
  - `database_monitor.py`

### 1.2 Dependencies & Configuration
- [ ] Add `aiosqlite` to `requirements.txt`
- [ ] Add `python-dateutil` for date parsing (if not already present)
- [ ] Create `config/cursor.yaml` configuration file with:
  - `enabled: true/false`
  - `poll_interval_seconds: 30`
  - `sync_window_hours: 24`
  - `query_timeout_seconds: 1.5`
  - `max_retries: 3`
  - `retry_backoff_seconds: 2`
  - `dedup_window_hours: 24`
  - `max_concurrent_workspaces: 10`
- [ ] Update `src/capture/shared/config.py` to load cursor config
- [ ] Add cursor config validation

### 1.3 Platform Detection Utilities
- [ ] Create `src/processing/cursor/platform.py`:
  - Detect OS (macOS, Linux, Windows)
  - Get Cursor database base paths per platform:
    - macOS: `~/Library/Application Support/Cursor/User/workspaceStorage`
    - Linux: `~/.config/Cursor/User/workspaceStorage`
    - Windows: `~/AppData/Roaming/Cursor/User/workspaceStorage`
  - Handle path normalization

---

## Phase 2: Session Monitor

### 2.1 Core Session Monitor Implementation
- [ ] Implement `SessionMonitor` class in `session_monitor.py`:
  - [ ] `__init__()`: Initialize Redis client, active_sessions dict
  - [ ] `start()`: Start Redis event listener
  - [ ] `stop()`: Clean shutdown
  - [ ] `get_active_workspaces()`: Return active sessions dict
  - [ ] `get_workspace_path()`: Get workspace path for hash

### 2.2 Redis Event Listener
- [ ] Implement `_listen_redis_events()`:
  - [ ] Use `redis_client.xread()` with blocking
  - [ ] Track `last_redis_id` for resuming
  - [ ] Handle connection errors with retry logic
  - [ ] Process messages in batches
- [ ] Implement `_process_redis_message()`:
  - [ ] Decode Redis message fields
  - [ ] Filter for `session_start` and `session_end` events
  - [ ] Parse payload and metadata JSON
  - [ ] Extract `workspace_hash`, `session_id`, `workspace_path`
  - [ ] Update `active_sessions` dict
  - [ ] Log session lifecycle events
- [ ] Implement `_decode_field()` helper for Redis field decoding

### 2.3 Error Handling & Resilience
- [ ] Add try/except blocks around all Redis operations
- [ ] Implement exponential backoff for Redis connection failures
- [ ] Log warnings for incomplete session events
- [ ] Handle JSON parsing errors gracefully
- [ ] Add health check method

### 2.4 Testing
- [ ] Unit tests for `SessionMonitor`:
  - [ ] Test Redis event processing
  - [ ] Test session lifecycle (start/end)
  - [ ] Test error handling
  - [ ] Test Redis connection failures and retries
- [ ] Mock Redis client for testing
- [ ] Create test fixtures with sample Redis messages

---

## Phase 3: Workspace Mapper

### 3.1 Core Workspace Mapper Implementation
- [ ] Implement `WorkspaceMapper` class in `workspace_mapper.py`:
  - [ ] `__init__()`: Initialize session_monitor reference, mapping_cache dict
  - [ ] `_load_cache()`: Load persistent cache from `~/.blueplane/workspace_db_cache.json`
  - [ ] `_save_cache()`: Save cache to disk
  - [ ] `find_database()`: Main entry point with strategy fallback

### 3.2 Strategy 1: Workspace Path Hash Matching
- [ ] Implement `_strategy_path_hash()`:
  - [ ] Hash workspace path using SHA256 (first 16 chars)
  - [ ] Call `_discover_all_databases()` to get all DB files
  - [ ] Check if parent directory name contains hash
  - [ ] Fallback: Call `_db_contains_path()` to search DB contents
  - [ ] Return matching `Path` or `None`

### 3.3 Strategy 2: Session ID Matching
- [ ] Implement `_strategy_session_id()`:
  - [ ] Get session_id from session_monitor
  - [ ] Iterate through all discovered databases
  - [ ] Open each DB with `aiosqlite` (timeout 2s)
  - [ ] Check if `composer.composerData` table exists
  - [ ] Query for session_id in table values
  - [ ] Return matching DB path or `None`
  - [ ] Handle errors gracefully (skip on failure)

### 3.4 Strategy 3: Database Content Search
- [ ] Implement `_db_contains_path()`:
  - [ ] Open database with timeout
  - [ ] List all tables
  - [ ] Search for workspace_path in table values/text columns
  - [ ] Return `True` if found, `False` otherwise
  - [ ] Handle errors gracefully

### 3.5 Database Discovery
- [ ] Implement `_discover_all_databases()`:
  - [ ] Use platform detection to get base paths
  - [ ] Iterate through `workspaceStorage/*/state.vscdb`
  - [ ] Return list of `Path` objects
  - [ ] Handle missing directories gracefully
  - [ ] Filter out non-existent files

### 3.6 Cache Management
- [ ] Implement cache validation:
  - [ ] Check if cached paths still exist
  - [ ] Remove invalid cache entries
  - [ ] Update cache on successful mappings
- [ ] Add cache TTL (optional: expire after N days)

### 3.7 Testing
- [ ] Unit tests for `WorkspaceMapper`:
  - [ ] Test path hash matching
  - [ ] Test session ID matching
  - [ ] Test database discovery
  - [ ] Test cache loading/saving
  - [ ] Test fallback strategies
- [ ] Create mock databases for testing
- [ ] Test with multiple workspace scenarios

---

## Phase 4: Schema Detector

### 4.1 Core Schema Detector Implementation
- [ ] Implement `SchemaDetector` class in `schema_detector.py`:
  - [ ] `__init__()`: Initialize schema_cache dict
  - [ ] `detect_schema()`: Main entry point with caching
  - [ ] `_detect_schema_impl()`: Actual detection logic

### 4.2 Schema Detection Logic
- [ ] Implement `_detect_schema_impl()`:
  - [ ] Open database with `aiosqlite` (timeout 2s)
  - [ ] Query `sqlite_master` for all tables
  - [ ] Detect generations table:
    - [ ] Check for `aiService.generations`
    - [ ] Check for `ai.generations`
    - [ ] Check for `generations` (fallback)
  - [ ] Detect prompts table:
    - [ ] Check for `aiService.prompts`
    - [ ] Check for `ai.prompts`
    - [ ] Check for `prompts` (fallback)
  - [ ] Determine schema version (`v1` vs `v2` vs `unknown`)
  - [ ] Return schema info dict

### 4.3 Query Generation
- [ ] Implement `get_generations_query()`:
  - [ ] Accept schema_info, from_version, to_version
  - [ ] Generate query based on schema:
    - [ ] If prompts table exists: JOIN query
    - [ ] Otherwise: Simple SELECT query
  - [ ] Handle table name quoting (e.g., `"aiService.generations"`)
  - [ ] Return query string or `None` if invalid schema

### 4.4 Error Handling
- [ ] Handle missing tables gracefully
- [ ] Handle database connection errors
- [ ] Return "unknown" schema on errors
- [ ] Log schema detection failures

### 4.5 Testing
- [ ] Unit tests for `SchemaDetector`:
  - [ ] Test v1 schema detection (`aiService.*`)
  - [ ] Test v2 schema detection (`ai.*`)
  - [ ] Test missing tables
  - [ ] Test query generation for both schemas
  - [ ] Test caching behavior
- [ ] Create test databases with different schemas
- [ ] Test error scenarios

---

## Phase 5: Database Monitor (Main Component)

### 5.1 Core Database Monitor Implementation
- [ ] Implement `CursorDatabaseMonitor` class in `database_monitor.py`:
  - [ ] `__init__()`: Initialize all dependencies, config, state tracking
  - [ ] `start()`: Start monitoring loop and cleanup tasks
  - [ ] `stop()`: Clean shutdown, close connections
  - [ ] Initialize state:
    - [ ] `last_synced` dict (workspace_hash -> version)
    - [ ] `db_connections` dict (workspace_hash -> Connection)
    - [ ] `schema_info` dict (db_path -> schema_info)
    - [ ] `seen_generations` set (deduplication)
    - [ ] `generation_ttl` dict (TTL tracking)
    - [ ] `health_stats` dict (monitoring)

### 5.2 Main Monitoring Loop
- [ ] Implement `_monitor_loop()`:
  - [ ] Run continuously while `running == True`
  - [ ] Get active workspaces from session_monitor
  - [ ] Call `_monitor_workspace()` for each active workspace
  - [ ] Call `_cleanup_inactive_workspaces()` periodically
  - [ ] Sleep for `poll_interval`
  - [ ] Handle exceptions gracefully

### 5.3 Workspace Monitoring
- [ ] Implement `_monitor_workspace()`:
  - [ ] Get workspace_path from session_info
  - [ ] Call `workspace_mapper.find_database()`
  - [ ] Check if database exists
  - [ ] Lazy-load connection if needed (`_open_database()`)
  - [ ] On first open: call `_sync_session_start()`
  - [ ] Call `_check_for_changes()` for incremental updates
  - [ ] Update health stats

### 5.4 Database Connection Management
- [ ] Implement `_open_database()`:
  - [ ] Detect schema using `schema_detector`
  - [ ] Verify generations table exists
  - [ ] Open connection with `aiosqlite` (timeout from config)
  - [ ] Set PRAGMAs:
    - [ ] `PRAGMA journal_mode=WAL`
    - [ ] `PRAGMA read_uncommitted=1`
    - [ ] `PRAGMA query_only=1` (read-only)
  - [ ] Store connection in `db_connections`
  - [ ] Cache schema_info
  - [ ] Handle timeouts and errors

### 5.5 Session Start Sync
- [ ] Implement `_sync_session_start()`:
  - [ ] Get last_synced version (or 0)
  - [ ] If 0: calculate cutoff timestamp (sync_window_hours ago)
  - [ ] Call `_get_min_version_after()` to find starting version
  - [ ] Get current max version (`_get_current_data_version()`)
  - [ ] If versions differ: call `_capture_changes()`
  - [ ] Update `last_synced`
  - [ ] Log sync progress

### 5.6 Incremental Change Detection
- [ ] Implement `_check_for_changes()`:
  - [ ] Get last_synced version
  - [ ] Retry loop (max_retries):
    - [ ] Call `_get_current_data_version()` with timeout
    - [ ] If version increased: call `_capture_changes()`
    - [ ] Update `last_synced`
    - [ ] Handle TimeoutError with exponential backoff
    - [ ] Handle "locked" errors with retry
    - [ ] Handle other errors with logging
  - [ ] Update health stats

### 5.7 Version Queries
- [ ] Implement `_get_current_data_version()`:
  - [ ] Get schema_info for database
  - [ ] Execute `SELECT MAX(data_version) FROM {table}`
  - [ ] Return version or 0 if error
- [ ] Implement `_get_min_version_after()`:
  - [ ] Get schema_info for database
  - [ ] Execute `SELECT MIN(data_version) FROM {table} WHERE timestamp >= ?`
  - [ ] Return version or None

### 5.8 Change Capture
- [ ] Implement `_capture_changes()`:
  - [ ] Get schema_info
  - [ ] Get query from `schema_detector.get_generations_query()`
  - [ ] Execute query with from_version/to_version (with timeout)
  - [ ] Fetch all rows
  - [ ] For each row: call `_process_generation()`
  - [ ] Log number of generations found
  - [ ] Handle timeouts and errors

### 5.9 Generation Processing
- [ ] Implement `_process_generation()`:
  - [ ] Extract generation_id (uuid)
  - [ ] Check deduplication (`seen_generations`)
  - [ ] If duplicate: skip and log debug
  - [ ] Add to `seen_generations` and `generation_ttl`
  - [ ] Parse generation value JSON
  - [ ] Build event payload:
    - [ ] trace_type, generation_id, data_version
    - [ ] model, tokens_used, prompt_tokens, completion_tokens
    - [ ] response_text, prompt_text, prompt_id
    - [ ] request_parameters, timestamps
    - [ ] full_generation_data
  - [ ] Build event dict:
    - [ ] version, hook_type, event_type, timestamp
    - [ ] platform, session_id, external_session_id
    - [ ] metadata (workspace_hash, source: "python_monitor")
    - [ ] payload
  - [ ] Send to Redis using `redis_client.xadd()`
  - [ ] Handle errors gracefully

### 5.10 Deduplication Cleanup
- [ ] Implement `_cleanup_dedup_cache()`:
  - [ ] Run in background loop (every hour)
  - [ ] Calculate cutoff time (dedup_window_hours ago)
  - [ ] Remove old entries from `seen_generations` and `generation_ttl`
  - [ ] Log cleanup stats

### 5.11 Resource Cleanup
- [ ] Implement `_cleanup_inactive_workspaces()`:
  - [ ] Compare active_hashes with db_connections keys
  - [ ] For inactive workspaces:
    - [ ] Close database connections
    - [ ] Remove from db_connections
    - [ ] Clear health_stats
    - [ ] Log cleanup

### 5.12 Health Tracking
- [ ] Implement `_update_health()`:
  - [ ] Initialize health_stats entry if needed
  - [ ] Update last_check timestamp
  - [ ] Update status (connected, synced, error, timeout, locked)
  - [ ] Increment error count on errors
  - [ ] Store additional context (version, error message)

### 5.13 Error Handling & Resilience
- [ ] Add try/except around all database operations
- [ ] Implement exponential backoff for retries
- [ ] Handle SQLite locking errors gracefully
- [ ] Handle connection timeouts
- [ ] Handle schema detection failures
- [ ] Log all errors with context
- [ ] Update health stats on errors

### 5.14 Testing
- [ ] Unit tests for `CursorDatabaseMonitor`:
  - [ ] Test database opening/closing
  - [ ] Test session start sync
  - [ ] Test incremental change detection
  - [ ] Test generation processing
  - [ ] Test deduplication
  - [ ] Test error handling and retries
  - [ ] Test resource cleanup
- [ ] Integration tests:
  - [ ] Test full workflow with mock Redis
  - [ ] Test with real test databases
  - [ ] Test multiple workspaces
  - [ ] Test schema detection integration

---

## Phase 6: Deduplication in Consumer

### 6.1 Consumer Deduplication
- [ ] Update `EventConsumer` in platform-specific directories (e.g., `cursor/event_consumer.py`):
  - [ ] Add `seen_generation_ids` set to `__init__()`
  - [ ] Add `dedup_ttl` dict to `__init__()`
  - [ ] Add `dedup_window_hours` config parameter

### 6.2 Deduplication Logic
- [ ] Update `_process_batch()`:
  - [ ] Before processing events, filter duplicates:
    - [ ] Check if `event_type == 'database_trace'`
    - [ ] Extract `generation_id` from payload
    - [ ] Extract `session_id` from event
    - [ ] Create dedup_key: `(session_id, generation_id)`
    - [ ] If key in `seen_generation_ids`: skip event
    - [ ] Otherwise: add to set and record TTL
  - [ ] Process only deduplicated events
  - [ ] Log skipped duplicates

### 6.3 Deduplication Cleanup
- [ ] Add cleanup task:
  - [ ] Run periodically (every hour)
  - [ ] Remove old entries based on TTL
  - [ ] Log cleanup stats

### 6.4 Testing
- [ ] Test deduplication:
  - [ ] Send duplicate events
  - [ ] Verify only one processed
  - [ ] Test cleanup logic
  - [ ] Test with different session_ids

---

## Phase 7: Server Integration

### 7.1 Server Integration
- [ ] Update `TelemetryServer` in `server.py`:
  - [ ] Add `cursor_monitor` attribute
  - [ ] Add `session_monitor` attribute
  - [ ] Import cursor modules

### 7.2 Initialization
- [ ] Add `_initialize_cursor_monitor()` method:
  - [ ] Load cursor config
  - [ ] Check if cursor monitoring enabled
  - [ ] Create `SessionMonitor` instance
  - [ ] Create `CursorDatabaseMonitor` instance
  - [ ] Start both monitors (async)

### 7.3 Lifecycle Management
- [ ] Update `start()` method:
  - [ ] Call `_initialize_cursor_monitor()` after Redis init
  - [ ] Start monitors as background tasks
- [ ] Update `stop()` method:
  - [ ] Stop `CursorDatabaseMonitor`
  - [ ] Stop `SessionMonitor`
  - [ ] Wait for graceful shutdown

### 7.4 Error Handling
- [ ] Handle monitor initialization failures gracefully
- [ ] Log warnings if cursor monitoring disabled
- [ ] Don't fail server startup if cursor monitor fails

### 7.5 Testing
- [ ] Test server integration:
  - [ ] Test with cursor monitoring enabled
  - [ ] Test with cursor monitoring disabled
  - [ ] Test graceful shutdown
  - [ ] Test error recovery

---

## Phase 8: Configuration & Documentation

### 8.1 Configuration
- [ ] Document all configuration options
- [ ] Add configuration validation
- [ ] Add configuration examples
- [ ] Add environment variable overrides (if needed)

### 8.2 Logging
- [ ] Add structured logging throughout:
  - [ ] Session lifecycle events
  - [ ] Database connection events
  - [ ] Schema detection events
  - [ ] Generation capture events
  - [ ] Error events with context
- [ ] Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)

### 8.3 Documentation
- [ ] Update `README.md` with cursor monitoring info
- [ ] Create `docs/architecture/layer2_cursor_database_monitor.md`
- [ ] Document configuration options
- [ ] Document troubleshooting steps
- [ ] Document testing approach

---

## Phase 9: Testing & Validation

### 9.1 Unit Tests
- [ ] Achieve >80% code coverage
- [ ] Test all error paths
- [ ] Test edge cases
- [ ] Test platform-specific code

### 9.2 Integration Tests
- [ ] Test with real Cursor databases (test fixtures)
- [ ] Test with Redis integration
- [ ] Test with multiple workspaces
- [ ] Test session lifecycle
- [ ] Test deduplication end-to-end

### 9.3 Manual Testing
- [ ] Test on macOS
- [ ] Test on Linux (if available)
- [ ] Test on Windows (if available)
- [ ] Test with extension installed (required for Redis events)
- [ ] Test with multiple Cursor instances
- [ ] Test with schema v1 and v2
- [ ] Test error scenarios (locked DB, missing tables, etc.)
- [ ] Test Redis connection failures

### 9.4 Performance Testing
- [ ] Test with 10+ active workspaces
- [ ] Test query performance
- [ ] Test memory usage
- [ ] Test CPU usage
- [ ] Verify no Cursor performance impact

---

## Phase 10: Migration & Rollout

### 10.1 Feature Flag
- [ ] Add `cursor_database_monitor.enabled` config flag
- [ ] Default to `false` initially
- [ ] Add feature flag check in server initialization

### 10.2 Parallel Running (Optional)
- [ ] If TypeScript monitor still exists:
  - [ ] Run both monitors in parallel
  - [ ] Compare outputs
  - [ ] Verify deduplication works
  - [ ] Fix any issues

### 10.3 Gradual Rollout
- [ ] Enable for test workspace
- [ ] Monitor logs and metrics
- [ ] Enable for 10% of workspaces
- [ ] Gradually increase to 100%
- [ ] Monitor for issues

### 10.4 Monitoring & Observability
- [ ] Add metrics:
  - [ ] Active workspaces monitored
  - [ ] Generations captured per workspace
  - [ ] Database connection errors
  - [ ] Schema detection failures
  - [ ] Deduplication stats
- [ ] Add health check endpoint (if applicable)
- [ ] Add alerting for critical errors

---

## Dependencies Summary

### Python Packages
- `aiosqlite` - Async SQLite driver
- `redis` - Already present
- `python-dateutil` - Date parsing (if not present)

### Configuration Files
- `config/cursor.yaml` - Cursor monitor configuration

### Directory Structure
```
src/processing/cursor/
├── __init__.py
├── session_monitor.py
├── workspace_mapper.py
├── schema_detector.py
├── database_monitor.py
└── platform.py
```

---

## Risk Mitigation Checklist

- [ ] Workspace mapping: Multiple strategies with fallbacks ✅
- [ ] Database locking: Aggressive timeouts, read-only mode ✅
- [ ] Schema changes: Detection and adaptation ✅
- [ ] Data duplication: Built-in deduplication ✅
- [ ] Session dependency: Redis events only (extension required) ✅
- [ ] Resource usage: Lazy loading, connection limits ✅
- [ ] Testing: Comprehensive test suite ✅
- [ ] Migration risk: Feature flag, gradual rollout ✅

---

## Success Criteria

1. ✅ Database monitor captures all AI generations from Cursor databases
2. ✅ Zero impact on Cursor performance (timeouts, read-only)
3. ✅ Handles schema changes gracefully (v1 and v2)
4. ✅ Prevents duplicate events (deduplication works)
5. ✅ Works with multiple workspaces simultaneously
6. ✅ Handles errors gracefully (no crashes)
7. ✅ Comprehensive test coverage (>80%)
8. ✅ Production-ready logging and monitoring

---

## Estimated Timeline

- **Phase 1-2**: Foundation & Session Monitor (3-4 days)
- **Phase 3**: Workspace Mapper (2-3 days)
- **Phase 4**: Schema Detector (1-2 days)
- **Phase 5**: Database Monitor (4-5 days)
- **Phase 6**: Consumer Deduplication (1 day)
- **Phase 7**: Server Integration (1-2 days)
- **Phase 8**: Configuration & Documentation (1-2 days)
- **Phase 9**: Testing & Validation (3-4 days)
- **Phase 10**: Migration & Rollout (1-2 weeks)

**Total**: ~3-4 weeks for full implementation and testing

---

## Notes

- Start with Phase 1-2 to get basic infrastructure working
- Test each phase before moving to the next
- Use feature flags to enable/disable during development
- Keep TypeScript monitor as fallback during migration
- Monitor performance and resource usage closely
- Document all design decisions and trade-offs

