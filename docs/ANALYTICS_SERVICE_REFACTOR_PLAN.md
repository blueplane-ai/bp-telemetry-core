# Analytics Service Refactor - Implementation Plan

## Overview

This document outlines the implementation plan for refactoring the DuckDB analytics pipeline to read from SQLite instead of the monitor queue, creating a dedicated analytics service, and deprecating markdown writing.

**Issue**: https://github.com/blueplane-ai/bp-telemetry-core/issues/28

## Current Architecture (Before Refactor)

```
Cursor Workspace DB (state.vscdb)
  ↓ (polling)
CursorMarkdownMonitor
  ↓ (reads ItemTable directly)
  ├─→ CursorMarkdownWriter → Markdown File (.md)
  └─→ CursorDuckDBWriter → DuckDB (reads from ItemTable data dict)
```

**Problems:**
- DuckDB writes directly from monitor queue (real-time interference)
- Tight coupling between monitoring and analytics
- Markdown writing mixed with analytics
- No separation of concerns

## Target Architecture (After Refactor)

```
Trace Capture Pipeline (Real-time)
  ├─→ Monitors → Redis Queue
  └─→ Consumers → SQLite (raw_traces, conversations, sessions)

Analytics Service (Independent, Async)
  └─→ Reads from SQLite → Processes → DuckDB
```

**Benefits:**
- Analytics doesn't interfere with real-time capture
- Clear separation: capture vs. analytics
- Analytics can run on different schedule/frequency
- Can scale independently

## Implementation Plan

### Phase 1: Repository Structure & Deprecation

#### 1.1 Create Analytics Service Directory Structure

```
src/
├── analytics/                          # NEW: Dedicated analytics service
│   ├── __init__.py
│   ├── service.py                      # Main analytics service
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── sqlite_reader.py            # Read from SQLite
│   │   └── duckdb_writer.py           # Write to DuckDB (refactored)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── duckdb_schema.py           # DuckDB schema definitions
│   └── queries/
│       ├── __init__.py
│       └── analytics_queries.py        # Query functions
├── processing/                         # Existing processing layer
│   └── cursor/
│       ├── markdown_monitor.py         # DEPRECATED (markdown only)
│       └── markdown_writer.py          # DEPRECATED
```

**Tasks:**
- [ ] Create `src/analytics/` directory structure
- [ ] Move `duckdb_writer.py` to `src/analytics/workers/duckdb_writer.py`
- [ ] Update imports and references
- [ ] Add deprecation warnings to markdown components

#### 1.2 Deprecate Markdown Writing

**Tasks:**
- [ ] Add deprecation warnings to `CursorMarkdownWriter` and `CursorMarkdownMonitor`
- [ ] Document deprecation in code comments
- [ ] Update `server.py` to optionally disable markdown monitor
- [ ] Keep markdown code for now (remove in future PR)

**Deprecation Strategy:**
- Mark as deprecated but keep functional
- Add config flag to disable: `features.markdown_export.enabled: false`
- Log warnings when markdown is enabled
- Plan removal in future release

### Phase 2: SQLite Reader Implementation

#### 2.1 Create SQLite Reader Module

**File**: `src/analytics/workers/sqlite_reader.py`

**Responsibilities:**
- Connect to SQLite telemetry database
- Read raw traces from `cursor_raw_traces` and `claude_raw_traces`
- Read conversations from `conversations` table
- Read sessions from `cursor_sessions` table
- Track last processed sequence/offset
- Handle incremental processing

**Key Functions:**

```python
class SQLiteReader:
    def __init__(self, db_path: Path, last_processed: Optional[int] = None)
    def get_new_traces(self, platform: str, since_sequence: int) -> List[dict]
    def get_conversations(self, since_timestamp: Optional[datetime]) -> List[dict]
    def get_sessions(self, since_timestamp: Optional[datetime]) -> List[dict]
    def get_last_processed_sequence(self, platform: str) -> int
    def update_last_processed(self, platform: str, sequence: int)
```

**Data Extraction:**
- Decompress `event_data` BLOB (zlib)
- Parse JSON from compressed data
- Extract relevant fields for analytics
- Handle both Cursor and Claude Code traces

**Tasks:**
- [ ] Implement `SQLiteReader` class
- [ ] Add sequence tracking table: `analytics_processing_state`
- [ ] Implement incremental reading (process only new data)
- [ ] Add error handling and retry logic
- [ ] Add tests for SQLite reading

#### 2.2 Create Processing State Tracking

**New Table**: `analytics_processing_state`

```sql
CREATE TABLE analytics_processing_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,  -- 'cursor' or 'claude_code'
    last_processed_sequence INTEGER NOT NULL,
    last_processed_timestamp TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform)
);
```

**Purpose:**
- Track what data has been processed
- Enable incremental processing
- Prevent duplicate processing
- Support resume after restart

**Tasks:**
- [ ] Add schema migration for `analytics_processing_state` table
- [ ] Implement state tracking in SQLiteReader
- [ ] Add checkpoint/commit logic

### Phase 3: Refactor DuckDB Writer

#### 3.1 Refactor DuckDB Writer to Accept SQLite Data

**File**: `src/analytics/workers/duckdb_writer.py` (moved from `src/processing/cursor/`)

**Changes:**
- Remove dependency on ItemTable data dictionary
- Accept data from SQLite reader instead
- Process decompressed event_data from SQLite
- Extract analytics fields from raw traces

**New Interface:**

```python
class DuckDBWriter:
    def write_traces(self, traces: List[dict]) -> None
    def write_conversations(self, conversations: List[dict]) -> None
    def write_sessions(self, sessions: List[dict]) -> None
    def sync_workspace_metadata(self, workspace_hash: str, workspace_path: str) -> None
```

**Data Transformation:**
- Map SQLite raw_traces → DuckDB analytics tables
- Extract AI generations from cursor_raw_traces
- Extract composer sessions from cursor_raw_traces
- Extract file history from cursor_raw_traces
- Map conversations from SQLite → DuckDB

**Tasks:**
- [ ] Refactor `write_workspace_history()` → `write_traces()`
- [ ] Update data extraction to work with SQLite format
- [ ] Remove ItemTable parsing logic
- [ ] Add batch processing support
- [ ] Update schema if needed

#### 3.2 Update DuckDB Schema

**Considerations:**
- May need to adjust schema based on SQLite data structure
- Add fields for trace sequence tracking
- Support both Cursor and Claude Code data
- Add indexes for analytics queries

**Tasks:**
- [ ] Review current DuckDB schema
- [ ] Map SQLite fields to DuckDB fields
- [ ] Add any missing fields
- [ ] Update schema migration logic

### Phase 4: Analytics Service Implementation

#### 4.1 Create Main Analytics Service

**File**: `src/analytics/service.py`

**Responsibilities:**
- Orchestrate SQLite reading and DuckDB writing
- Manage processing loop
- Handle errors and retries
- Track processing state
- Support graceful shutdown

**Service Structure:**

```python
class AnalyticsService:
    def __init__(self, config: Config)
    async def start(self) -> None
    async def stop(self) -> None
    async def process_once(self) -> None  # Single processing cycle
    async def run(self) -> None  # Continuous loop
```

**Processing Flow:**

```
1. Read last processed state from SQLite
2. Query SQLite for new traces since last processed
3. Transform traces for DuckDB
4. Write to DuckDB
5. Update processing state
6. Repeat (with configurable interval)
```

**Tasks:**
- [ ] Implement `AnalyticsService` class
- [ ] Add configuration for processing interval
- [ ] Add error handling and logging
- [ ] Add health check endpoints (future)
- [ ] Add metrics/observability

#### 4.2 Integration with Server

**File**: `src/processing/server.py`

**Changes:**
- Remove DuckDB writer from markdown monitor
- Add analytics service as optional component
- Start analytics service independently
- Add config flag: `features.analytics_service.enabled`

**Tasks:**
- [ ] Remove DuckDB integration from `CursorMarkdownMonitor`
- [ ] Add analytics service initialization
- [ ] Add config options for analytics service
- [ ] Update server startup/shutdown logic

### Phase 5: Configuration & Testing

#### 5.1 Configuration Updates

**File**: `config/config.yaml`

**New Configuration:**

```yaml
analytics:
  enabled: false  # Feature flag
  processing_interval: 300  # seconds (5 minutes default)
  batch_size: 1000  # traces per batch
  sqlite:
    db_path: "~/.blueplane/telemetry.db"
  duckdb:
    db_path: "~/.blueplane/analytics.duckdb"
```

**Tasks:**
- [ ] Add analytics configuration section
- [ ] Update config schema
- [ ] Add validation

#### 5.2 Testing Strategy

**Unit Tests:**
- [ ] Test SQLiteReader data extraction
- [ ] Test DuckDBWriter data transformation
- [ ] Test AnalyticsService processing loop
- [ ] Test state tracking

**Integration Tests:**
- [ ] Test end-to-end: SQLite → DuckDB
- [ ] Test incremental processing
- [ ] Test error recovery
- [ ] Test with real data samples

**Tasks:**
- [ ] Create test fixtures with sample SQLite data
- [ ] Write unit tests for each component
- [ ] Write integration tests
- [ ] Add performance benchmarks

### Phase 6: Documentation & Cleanup

#### 6.1 Documentation

**Tasks:**
- [ ] Document analytics service architecture
- [ ] Update architecture diagrams
- [ ] Document configuration options
- [ ] Add developer guide for analytics service
- [ ] Document deprecation timeline for markdown

#### 6.2 Code Cleanup

**Tasks:**
- [ ] Remove unused imports
- [ ] Update docstrings
- [ ] Add type hints
- [ ] Run linters and fix issues
- [ ] Update CHANGELOG

## Migration Strategy

### Step-by-Step Migration

1. **Phase 1**: Create directory structure, move files, add deprecation warnings
2. **Phase 2**: Implement SQLite reader, test independently
3. **Phase 3**: Refactor DuckDB writer, test with SQLite data
4. **Phase 4**: Implement analytics service, test end-to-end
5. **Phase 5**: Update configuration, add tests
6. **Phase 6**: Documentation and cleanup

### Backward Compatibility

- Keep markdown writing functional (deprecated)
- Analytics service disabled by default
- Can run both old and new systems in parallel during transition
- Gradual migration path

### Rollback Plan

- Analytics service can be disabled via config
- Old markdown monitor still works
- No breaking changes to existing functionality

## Success Criteria

✅ **Analytics service runs independently from trace capture pipeline**
- Service can start/stop independently
- No coupling to monitor components
- Can process data on different schedule

✅ **Clear separation of concerns**
- Capture pipeline: Monitors → Redis → SQLite
- Analytics pipeline: SQLite → DuckDB
- No shared state or dependencies

✅ **Markdown writing deprecated**
- Deprecation warnings in place
- Config flag to disable
- Documentation updated

## Open Questions

### 1. Processing Frequency

**Question**: How often should analytics service run?
- Default: 5 minutes
- Configurable per workspace?
- Event-driven vs. scheduled?

**Answer**: ✅ Scheduled batch processing, default 5 minutes, configurable globally (not per-workspace initially). See [ADR-0001 Decision #1](docs/adr/0001-analytics-service-architecture-decisions.md#1-processing-frequency-scheduled-batch-processing).

### 2. Data Retention

**Question**: How long to keep data in DuckDB?
- Same as SQLite?
- Aggregated summaries only?
- Time-based partitioning?

**Answer**: ✅ Match SQLite retention, no separate policy initially. Future: may add aggregated summaries and time-based partitioning. See [ADR-0001 Decision #2](docs/adr/0001-analytics-service-architecture-decisions.md#2-data-retention-match-sqlite-retention).

### 3. Performance

**Question**: How to handle large datasets?
- Batch size limits?
- Streaming processing?
- Parallel processing per platform?

**Answer**: ✅ Batch processing with configurable size (default 1000 traces), sequential per platform. See [ADR-0001 Decision #3](docs/adr/0001-analytics-service-architecture-decisions.md#3-performance-batch-processing-with-configurable-size).

### 4. Monitoring

**Question**: How to monitor analytics service health?
- Health check endpoint?
- Metrics/observability?
- Alerting on failures?

**Answer**: ✅ Logging + state tracking in SQLite initially, extensible for future metrics/health endpoints. See [ADR-0001 Decision #4](docs/adr/0001-analytics-service-architecture-decisions.md#4-monitoring-logging--state-tracking).

**Note**: These are initial best-guess decisions. Implementation will validate them, and they can be refined based on real-world usage and team feedback.

## GitHub Issue Open Questions

### Conversation Replay

**Question**: How should conversation replay be created and stored? Should it be done on-demand, dynamically with views, or with a data processing layer? If it's persisted, should it live in SQLite or DuckDB?

**Answer**: ⚠️ **Out of scope for this refactor** (per issue #28 scope). Architecture informs future work:

- **Storage**: Conversation data exists in SQLite (`conversations` table). Replay would query SQLite, not DuckDB.
- **Approach**: Not decided. Options: on-demand (reconstruct from SQLite), views (SQLite views), or pre-processed (SQLite/DuckDB if performance needed).
- **Recommendation**: Start with on-demand from SQLite. Create separate ADR when implementing replay.

**Relevant to This Plan**:
- SQLite stores conversation data: `conversations` table (see [Phase 2.1](#21-create-sqlite-reader-module))
- Raw traces available: `cursor_raw_traces` and `claude_raw_traces` (see [Database Schema](src/processing/database/schema.py))
- SQLite reader could be extended for conversation queries (see [Phase 2](#phase-2-sqlite-reader-implementation))

## Next Steps

1. **Record Architecture Decisions**: Create ADR documenting best-guess answers to open questions
   - See `docs/adr/0001-analytics-service-architecture-decisions.md`
   - Decisions include: processing frequency, data retention, performance strategy, monitoring approach

2. **Implement Based on ADR Decisions**: Proceed with implementation using decisions from ADR
   - Start with Phase 1 (structure & deprecation)
   - Iterate through phases with testing at each step
   - Follow decisions documented in ADR

3. **Demonstrate Implementation**: Build working solution based on initial decisions
   - Create testable implementation
   - Document how it works
   - Show separation of concerns achieved

4. **Gather Feedback**: Present implementation and rationale to team
   - Share ADR with team for review
   - Demonstrate working solution
   - Collect feedback on decisions and implementation
   - Iterate based on feedback (create new ADRs if decisions change)

