# Implementation Plan: Cursor Hooks and Traces to SQL

**Status**: Planning  
**Target**: Layer 2 Processing Pipeline  
**Date**: January 2025

---

## Executive Summary

This document outlines the steps required to implement **Layer 2: Processing Pipeline** that consumes cursor hook events from Redis Streams and writes them to SQLite. Currently, Layer 1 (capture) is complete - hooks write events to Redis Streams. Layer 2 needs to be built from scratch.

## Current State

### ✅ What Exists (Layer 1 - Complete)

1. **Cursor Hooks** (`src/capture/cursor/hooks/`)
   - 9 hook scripts that capture events
   - Write events to Redis Streams via `MessageQueueWriter`
   - Events are in Redis Stream `telemetry:events`

2. **Event Schema** (`src/capture/shared/event_schema.py`)
   - Standardized event format
   - Event types, hook types, metadata structures

3. **Redis Configuration** (`config/redis.yaml`)
   - Stream configurations
   - Consumer group settings
   - Connection pooling

### ❌ What's Missing (Layer 2 - Not Implemented)

1. **Fast Path Consumer** - Reads from Redis Streams
2. **SQLite Writer** - Writes compressed events to SQLite
3. **CDC Publisher** - Publishes change events for slow path
4. **Database Initialization** - Creates SQLite schema
5. **Slow Path Workers** - Process events asynchronously
6. **Main Server** - Orchestrates fast and slow paths

---

## Implementation Steps

### Phase 1: Database Setup and Schema

#### Step 1.1: Create Database Module Structure
```
src/
  processing/
    __init__.py
    database/
      __init__.py
      sqlite_client.py      # SQLite connection and operations
      schema.py             # Schema definitions and migrations
      writer.py             # Batch writer for raw_traces
```

#### Step 1.2: Implement SQLite Client
**File**: `src/processing/database/sqlite_client.py`

**Requirements**:
- Initialize database at `~/.blueplane/telemetry.db`
- Set WAL mode: `PRAGMA journal_mode=WAL`
- Set synchronous: `PRAGMA synchronous=NORMAL`
- Set cache size: `PRAGMA cache_size=-64000` (64MB)
- Connection pooling with context managers
- Error handling and retry logic

**Key Functions**:
```python
class SQLiteClient:
    def __init__(self, db_path: str)
    def initialize_database(self) -> None
    def get_connection(self) -> sqlite3.Connection
    def execute(self, query: str, params: tuple) -> None
    def executemany(self, query: str, params: List[tuple]) -> None
```

#### Step 1.3: Create Database Schema
**File**: `src/processing/database/schema.py`

**Schema to Create**:
1. **raw_traces** table (from `docs/architecture/layer2_db_architecture.md`)
   - sequence (PRIMARY KEY AUTOINCREMENT)
   - ingested_at (TIMESTAMP)
   - event_id, session_id, event_type, platform, timestamp
   - workspace_hash, model, tool_name
   - duration_ms, tokens_used, lines_added, lines_removed
   - event_data (BLOB - compressed JSON)
   - event_date, event_hour (generated columns)

2. **conversations** table (for future use)
3. **conversation_turns** table (for future use)
4. **code_changes** table (for future use)

**Key Functions**:
```python
def create_schema(db_path: str) -> None
def create_raw_traces_table(conn: sqlite3.Connection) -> None
def create_conversations_table(conn: sqlite3.Connection) -> None
def create_indexes(conn: sqlite3.Connection) -> None
def migrate_schema(conn: sqlite3.Connection, from_version: int, to_version: int) -> None
```

#### Step 1.4: Implement Batch Writer
**File**: `src/processing/database/writer.py`

**Requirements**:
- Batch insert with `executemany()` for performance
- zlib compression (level 6) for event_data BLOB
- Extract indexed fields from event JSON
- Prepared statements for speed
- Transaction batching (100 events per batch)
- Target: <8ms P95 for 100 events

**Key Functions**:
```python
class SQLiteBatchWriter:
    def __init__(self, db_path: str)
    async def write_batch(self, events: List[Dict]) -> None
    def _compress_event(self, event: Dict) -> bytes
    def _extract_indexed_fields(self, event: Dict) -> Dict[str, Any]
```

---

### Phase 2: Fast Path Consumer

#### Step 2.1: Create Fast Path Module Structure
```
src/processing/
  fast_path/
    __init__.py
    consumer.py          # Redis Streams consumer
    cdc_publisher.py    # CDC event publisher
    batch_manager.py    # Batch accumulation logic
```

#### Step 2.2: Implement Redis Streams Consumer
**File**: `src/processing/fast_path/consumer.py`

**Requirements**:
- Use Redis Streams `XREADGROUP` with consumer groups
- Consumer group: `processors`
- Consumer name: `fast-path-1` (configurable)
- Blocking read with 1-second timeout
- Read up to 100 messages per batch
- Track message IDs for XACK
- Handle Pending Entries List (PEL) for retries
- Dead Letter Queue (DLQ) for failed messages after 3 retries

**Key Functions**:
```python
class FastPathConsumer:
    def __init__(self, redis_client, sqlite_writer, cdc_publisher)
    async def run(self) -> None
    async def _read_messages(self) -> List[Dict]
    async def _process_batch(self, messages: List[Dict]) -> None
    async def _ack_messages(self, message_ids: List[str]) -> None
    async def _handle_failed_message(self, message: Dict, retry_count: int) -> None
```

**Dependencies**:
- `redis` Python package (redis-py)
- `asyncio` for async operations
- Configuration from `config/redis.yaml`

#### Step 2.3: Implement Batch Manager
**File**: `src/processing/fast_path/batch_manager.py`

**Requirements**:
- Accumulate events until batch_size (100) or timeout (100ms)
- Thread-safe batch collection
- Time-based flushing
- Size-based flushing

**Key Functions**:
```python
class BatchManager:
    def __init__(self, batch_size: int = 100, batch_timeout: float = 0.1)
    def add_event(self, event: Dict) -> bool  # Returns True if batch ready
    def get_batch(self) -> List[Dict]
    def clear(self) -> None
    def should_flush(self) -> bool
```

#### Step 2.4: Implement CDC Publisher
**File**: `src/processing/fast_path/cdc_publisher.py`

**Requirements**:
- Fire-and-forget pattern (don't block fast path)
- Publish to Redis Stream `cdc:events`
- Include event sequence number from SQLite
- Include priority level for worker routing
- Auto-trim stream with MAXLEN ~100000

**Key Functions**:
```python
class CDCPublisher:
    def __init__(self, redis_client)
    async def publish(self, sequence: int, event: Dict, priority: int) -> None
    def _calculate_priority(self, event: Dict) -> int
```

**Priority Levels**:
- 1: user_prompt, acceptance_decision
- 2: tool_use, completion
- 3: performance, latency
- 4: session_start, session_end
- 5: debug/trace events

---

### Phase 3: Slow Path Workers (Optional for MVP)

#### Step 3.1: Create Slow Path Module Structure
```
src/processing/
  slow_path/
    __init__.py
    worker_pool.py       # Worker pool manager
    metrics_worker.py    # Metrics calculation worker
    conversation_worker.py  # Conversation reconstruction worker
```

**Note**: Slow path can be implemented later. For MVP, focus on fast path (writing traces to SQL).

---

### Phase 4: Main Server and Orchestration

#### Step 4.1: Create Main Server
**File**: `src/processing/server.py`

**Requirements**:
- Initialize Redis connection
- Initialize SQLite database
- Start fast path consumer
- Graceful shutdown handling
- Health check endpoints (optional)
- Logging configuration

**Key Functions**:
```python
class TelemetryServer:
    def __init__(self, config_path: str = None)
    async def start(self) -> None
    async def stop(self) -> None
    async def run(self) -> None
```

#### Step 4.2: Create CLI Entry Point
**File**: `src/processing/cli.py` or `scripts/start_server.py`

**Requirements**:
- Parse command-line arguments
- Load configuration
- Start server
- Handle signals (SIGINT, SIGTERM)

**Usage**:
```bash
python -m src.processing.cli start
python -m src.processing.cli start --config ~/.blueplane/config.yaml
```

---

### Phase 5: Configuration and Integration

#### Step 5.1: Update Configuration Loading
**File**: `src/capture/shared/config.py` (extend existing)

**Add**:
- SQLite database path configuration
- Fast path batch settings
- Consumer group settings
- CDC stream settings

#### Step 5.2: Create Database Initialization Script
**File**: `scripts/init_database.py`

**Requirements**:
- Create `~/.blueplane/` directory if needed
- Initialize SQLite database
- Run schema migrations
- Verify database is ready

**Usage**:
```bash
python scripts/init_database.py
```

#### Step 5.3: Update Installation Scripts
**File**: `scripts/install_cursor.py` (update existing)

**Add**:
- Database initialization step
- Verify SQLite is accessible
- Check Redis connection

---

### Phase 6: Testing and Verification

#### Step 6.1: Create Unit Tests
```
tests/
  processing/
    test_sqlite_client.py
    test_sqlite_writer.py
    test_fast_path_consumer.py
    test_cdc_publisher.py
```

#### Step 6.2: Create Integration Tests
```
tests/
  integration/
    test_end_to_end.py  # Hook → Redis → SQLite
```

#### Step 6.3: Create Verification Script
**File**: `scripts/verify_processing.py`

**Requirements**:
- Check Redis Stream has messages
- Verify SQLite database exists
- Query raw_traces table
- Verify events are compressed correctly
- Check CDC stream has events

---

## Implementation Order (Recommended)

### MVP (Minimum Viable Product)
1. ✅ **Phase 1**: Database setup and schema
2. ✅ **Phase 2**: Fast path consumer
3. ✅ **Phase 4**: Main server
4. ✅ **Phase 5**: Configuration and integration
5. ✅ **Phase 6**: Basic testing

### Full Implementation
6. **Phase 3**: Slow path workers
7. **Phase 6**: Comprehensive testing

---

## Technical Dependencies

### Python Packages Needed
```python
# Add to requirements.txt
redis>=5.0.0          # Redis Streams support
aioredis>=2.0.0       # Async Redis (optional, can use redis with asyncio)
```

### Existing Dependencies (Already in requirements.txt)
- `pyyaml` - Configuration loading
- `sqlite3` - Built-in Python library

---

## Key Design Decisions

### 1. Async vs Sync
- **Fast Path**: Use `asyncio` for Redis Streams reading (non-blocking)
- **SQLite Writes**: Can be sync (SQLite handles concurrency with WAL mode)
- **CDC Publishing**: Async fire-and-forget

### 2. Batch Size
- **Default**: 100 events per batch
- **Timeout**: 100ms (flush even if <100 events)
- **Rationale**: Balance between latency and throughput

### 3. Compression
- **Algorithm**: zlib level 6
- **Target**: 7-10x compression ratio
- **Trade-off**: CPU vs storage (level 6 is good balance)

### 4. Error Handling
- **Fast Path**: Never block, log errors, retry via PEL
- **DLQ**: After 3 retries, move to dead letter queue
- **CDC Failures**: Log but don't block fast path

### 5. Database Location
- **Path**: `~/.blueplane/telemetry.db`
- **Rationale**: User's home directory, easy to find/backup

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Fast Path Latency (P95) | <10ms | Per batch of 100 events |
| SQLite Write Latency (P95) | <8ms | Batch insert with compression |
| Throughput | 10,000 events/sec | Single consumer |
| Compression Ratio | 7-10x | zlib level 6 |
| Redis Stream Read Latency | <1ms | XREADGROUP blocking |

---

## Verification Checklist

After implementation, verify:

- [ ] Redis Stream `telemetry:events` is being consumed
- [ ] SQLite database `~/.blueplane/telemetry.db` exists
- [ ] `raw_traces` table has rows
- [ ] Events are compressed (check BLOB size)
- [ ] Indexed fields are populated correctly
- [ ] CDC stream `cdc:events` has entries
- [ ] Consumer group `processors` is tracking progress
- [ ] Failed messages go to DLQ after retries
- [ ] No blocking of hook execution
- [ ] Performance targets are met

---

## Next Steps After MVP

1. **Slow Path Workers**: Implement metrics and conversation workers
2. **Monitoring**: Add metrics, health checks, observability
3. **Archival**: Implement Parquet export for old traces
4. **Retention**: Auto-delete traces older than 90 days
5. **Layer 3**: Build CLI, MCP server, dashboard

---

## Related Documentation

- `docs/architecture/layer2_async_pipeline.md` - Full architecture spec
- `docs/architecture/layer2_db_architecture.md` - Database schema details
- `docs/ARCHITECTURE.md` - Overall system architecture
- `src/capture/shared/event_schema.py` - Event format specification

