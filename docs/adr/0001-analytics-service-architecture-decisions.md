# ADR-0001: Analytics Service Architecture Decisions

**Status**: Proposed  
**Date**: 2025-11-25  
**Deciders**: Development Team  
**Context**: Refactoring DuckDB analytics pipeline to read from SQLite instead of monitor queue

## Context

The current DuckDB implementation reads directly from the monitor queue, which creates tight coupling between real-time trace capture and analytics processing. Issue #28 requires refactoring to:

1. Read from SQLite instead of monitor queue
2. Create dedicated analytics service
3. Deprecate markdown writing
4. Achieve clear separation of concerns

Several architectural decisions need to be made to proceed with implementation.

## Decisions

### 1. Processing Frequency: Scheduled Batch Processing

**Decision**: Analytics service will run on a configurable schedule (default: 5 minutes) using batch processing.

**Rationale**:
- **Predictable load**: Scheduled processing avoids spikes during high capture activity
- **Resource efficiency**: Batch processing is more efficient than event-driven for analytics
- **Simplicity**: Easier to reason about and debug than event-driven
- **Configurable**: Can be adjusted per deployment (faster for dev, slower for production)

**Default**: 5 minutes (300 seconds)
- Fast enough for near-real-time analytics
- Slow enough to avoid interfering with capture pipeline
- Can be tuned based on data volume

**Alternatives Considered**:
- Event-driven: Too complex, risk of interference with capture
- Continuous streaming: Higher resource usage, unnecessary for analytics
- Hourly/daily: Too slow for useful analytics

### 2. Data Retention: Match SQLite Retention

**Decision**: DuckDB will retain data for the same duration as SQLite, with no separate retention policy initially.

**Rationale**:
- **Consistency**: Analytics should reflect all available data
- **Simplicity**: Single source of truth for data lifecycle
- **Future flexibility**: Can add aggregation/summarization later without breaking changes
- **Storage efficiency**: DuckDB is columnar and compresses well

**Future Considerations**:
- May add aggregated summaries for older data
- May implement time-based partitioning
- Can add retention policies later without breaking changes

**Alternatives Considered**:
- Shorter retention: Loses historical analytics capability
- Longer retention: Unnecessary complexity, storage concerns
- Aggregated-only: Too restrictive, loses detail for recent analysis

### 3. Performance: Batch Processing with Configurable Size

**Decision**: Process traces in configurable batches (default: 1000 traces per batch) with sequential processing per platform.

**Rationale**:
- **Memory efficiency**: Batch size limits memory usage
- **Progress tracking**: Easier to track and resume processing
- **Error recovery**: Can retry failed batches without reprocessing everything
- **Sequential per platform**: Simpler than parallel, avoids race conditions

**Default Batch Size**: 1000 traces
- Large enough for efficiency
- Small enough to avoid memory issues
- Can be tuned based on available resources

**Processing Order**:
1. Process Cursor traces (cursor_raw_traces)
2. Process Claude Code traces (claude_raw_traces)
3. Process conversations
4. Process sessions

**Alternatives Considered**:
- Parallel processing: More complex, potential race conditions
- Streaming: Higher memory usage, harder to track progress
- Single large batch: Memory concerns, harder error recovery

### 4. Monitoring: Logging + State Tracking

**Decision**: Use structured logging for observability and track processing state in SQLite for health checks.

**Rationale**:
- **Simplicity**: Logging is sufficient for initial implementation
- **State tracking**: `analytics_processing_state` table provides health check data
- **Future extensibility**: Can add metrics/alerting later without breaking changes
- **Debugging**: Logs provide sufficient information for troubleshooting

**Health Indicators**:
- Last processed sequence per platform
- Last processing timestamp
- Processing errors logged with context

**Future Enhancements**:
- Add metrics endpoint (Prometheus format)
- Add health check HTTP endpoint
- Add alerting on processing failures

**Alternatives Considered**:
- Full observability stack (Prometheus/Grafana): Overkill for initial implementation
- No monitoring: Insufficient for production use
- External monitoring service: Unnecessary complexity

### 5. Error Handling: Graceful Degradation with Retry

**Decision**: Implement retry logic with exponential backoff, log errors, and continue processing other data.

**Rationale**:
- **Resilience**: Service should continue operating despite individual failures
- **Recovery**: Retry logic handles transient failures
- **Observability**: Logging provides visibility into issues
- **Data integrity**: Failed batches can be retried on next cycle

**Retry Strategy**:
- Retry failed batches up to 3 times
- Exponential backoff: 1s, 2s, 4s
- Log all failures with context
- Continue processing other batches/platforms

**Alternatives Considered**:
- Fail fast: Too brittle, stops all processing
- Infinite retry: Risk of getting stuck
- Manual intervention: Too slow for production

### 6. State Management: SQLite Table for Processing State

**Decision**: Use dedicated `analytics_processing_state` table in SQLite to track processing progress.

**Rationale**:
- **Persistence**: State survives service restarts
- **Atomicity**: SQLite transactions ensure consistency
- **Simplicity**: Single source of truth, no external dependencies
- **Queryable**: Can query state for health checks

**Schema**:
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

**Alternatives Considered**:
- External state store (Redis): Unnecessary complexity, another dependency
- File-based state: Less reliable, harder to query
- In-memory only: Lost on restart, no persistence

### 7. Data Transformation: Extract from Decompressed event_data

**Decision**: Read `event_data` BLOB from SQLite, decompress (zlib), parse JSON, and extract analytics fields.

**Rationale**:
- **Single source**: event_data contains complete event information
- **Consistency**: Same data structure as capture pipeline
- **Flexibility**: Can extract any fields needed for analytics
- **Future-proof**: New fields in event_data automatically available

**Transformation Flow**:
1. Read trace from SQLite (with indexed fields)
2. Decompress `event_data` BLOB
3. Parse JSON
4. Extract analytics-relevant fields
5. Transform to DuckDB schema format

**Alternatives Considered**:
- Use only indexed fields: Too limiting, loses detail
- Store duplicate data: Wastes storage, sync issues
- Separate analytics capture: Duplicates capture pipeline

### 8. Service Integration: Optional Component in Main Server

**Decision**: Analytics service will be an optional component that can be enabled/disabled via configuration.

**Rationale**:
- **Flexibility**: Can run analytics separately or together with capture
- **Resource control**: Can disable if resources are constrained
- **Development**: Easier to develop/test independently
- **Deployment**: Can deploy as separate service later

**Configuration**:
```yaml
analytics:
  enabled: false  # Feature flag
  processing_interval: 300  # seconds
  batch_size: 1000
```

**Alternatives Considered**:
- Always enabled: Less flexible, harder to disable if issues
- Separate service only: More complex deployment initially
- Required component: Too rigid

## Consequences

### Positive
- Clear separation of concerns
- Analytics doesn't interfere with capture
- Configurable and flexible
- Can scale independently
- Simple to understand and maintain

### Negative
- Analytics data may lag by up to processing interval (default 5 min)
- Additional SQLite read load (but reads are efficient)
- More components to manage

### Risks
- **Data lag**: Mitigated by configurable interval
- **SQLite contention**: Mitigated by separate read connections, WAL mode
- **Processing failures**: Mitigated by retry logic and error handling

## Notes

- These decisions are based on best-guess assumptions
- Can be refined based on real-world usage
- Implementation will validate these decisions
- Future ADRs can document changes if needed

## References

- Issue #28: Analytics Service Architecture & Implementation
- Implementation Plan: `docs/ANALYTICS_SERVICE_REFACTOR_PLAN.md`

