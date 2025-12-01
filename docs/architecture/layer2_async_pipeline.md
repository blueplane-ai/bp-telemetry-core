<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Layer 2: Async Processing Pipeline Architecture

> Non-blocking Event Processing with Fast and Slow Paths
> Version: 1.0.0
> Date: November 2025

---

## Executive Summary

This document specifies the asynchronous, non-blocking processing pipeline for Layer 2 (Local Telemetry Server). The architecture ensures zero-latency raw trace ingestion while maintaining eventual consistency for derived metrics and conversation data.

## Problem Statement

The original synchronous pipeline created a critical bottleneck:
- Event processing required reads from multiple databases before writing
- This blocked the message queue consumer
- Under load, the message queue could overflow, losing events
- Latency increased linearly with enrichment complexity

## Solution: Fast/Slow Path Architecture

### Core Design Principles

1. **Write-First**: Raw events are written immediately with zero reads
2. **Async Enrichment**: Context lookups happen on separate threads
3. **Eventual Consistency**: Metrics update within seconds, not milliseconds
4. **Backpressure Management**: Graceful degradation under load
5. **Failure Isolation**: Problems in slow path don't affect fast path

### High-Level Architecture

```mermaid
graph TB
    subgraph "Layer 1: Capture"
        HOOKS[IDE Hooks]
        DBMON[DB Monitor]
    end

    subgraph "Message Queue (Redis Streams)"
        MQSTREAM[telemetry:message_queue<br/>Stream]
        DLQ[telemetry:dlq<br/>Dead Letter Queue]
    end

    subgraph "Fast Path (Non-blocking)"
        CONSUMER[MQ Consumer<br/>XREADGROUP]
        WRITER[SQLite Writer<br/>Batch + Compress]
        CDC[CDC Publisher]
    end

    subgraph "CDC Queue (Redis Streams)"
        CDCSTREAM[cdc:events<br/>Work Queue]
        PRIORITY[Consumer Groups<br/>by Worker Type]
    end

    subgraph "Slow Path (Async Workers)"
        MW[Metrics Workers<br/>2-4 threads]
        CW[Conversation Workers<br/>2-4 threads]
        AW[AI Workers<br/>1-2 threads]
    end

    subgraph "Storage (Single SQLite DB)"
        SQRAW[(SQLite raw_traces<br/>Compressed)]
        SQCONV[(SQLite conversations<br/>Same DB)]
        REDIS[(Redis<br/>Metrics + TimeSeries)]
    end

    HOOKS --> MQSTREAM
    DBMON --> MQSTREAM

    MQSTREAM --> CONSUMER
    CONSUMER --> WRITER
    WRITER --> SQRAW
    WRITER --> CDC
    CDC --> CDCSTREAM

    CDCSTREAM --> MW
    CDCSTREAM --> CW
    CDCSTREAM --> AW

    MW --> REDIS
    CW --> SQCONV
    AW --> SQCONV

    MW -.->|Read| SQRAW
    CW -.->|Read| SQRAW
    CW -.->|Read| SQCONV
    AW -.->|Read| SQRAW
    AW -.->|Read| SQCONV
    AW -.->|Read| REDIS

    style CONSUMER fill:#90EE90
    style WRITER fill:#90EE90
    style CDC fill:#90EE90
    style MW fill:#87CEEB
    style CW fill:#87CEEB
    style AW fill:#87CEEB
    style MQSTREAM fill:#FFD700
```

## Fast Path Implementation

### Message Queue Consumer

```python
# Platform-specific event consumers (e.g., claude_code/event_consumer.py)
# Pseudocode:

class EventConsumer:
    """
    High-throughput consumer that writes raw events with zero blocking.
    Target: <10ms per batch at P95.
    """

    batch_size = 100
    batch_timeout = 0.1  # 100ms
    stream_name = 'telemetry:message_queue'
    consumer_group = 'processors'
    consumer_name = 'fast-path-1'

    async def run():
        """
        Main consumer loop using Redis Streams XREADGROUP.

        While True:
        - Read from Redis Streams (blocking 1 second if no messages)
        - Use XREADGROUP for consumer group pattern
        - For each message:
          - Parse event data from stream entry
          - Add _sequence (auto-increment via SQLite) and _ingested_at
          - Append to batch
          - Track message ID for later XACK
          - Flush if batch_size reached
        - Time-based flush if batch_timeout exceeded
        - On successful flush: XACK all processed message IDs
        - On error: Don't XACK (messages will retry via PEL)
        """

    async def flush_batch():
        """
        Write batch to SQLite (compressed) and publish CDC events.

        - writer.write_batch(batch)  # SQLite insert with zlib compression
        - For each event: cdc.publish(...)  # Fire-and-forget to CDC stream
        - XACK all message IDs in batch (mark as processed)
        - Clear batch and message_ids list
        - On error: Log but don't XACK (automatic retry via PEL)
        - Handle DLQ: if retry_count >= 3, XADD to telemetry:dlq and XACK
        """

    def calculate_priority(event: Dict) -> int:
        """
        Assign priority for async processing.

        Priority levels (1=highest):
        1 - user_prompt, acceptance_decision
        2 - tool_use, completion
        3 - performance, latency
        4 - session_start, session_end
        5 - debug/trace events
        """
```

### Batch Writer for SQLite

```python
# Platform-specific raw traces writers (e.g., claude_code/raw_traces_writer.py)
# Pseudocode:

class SQLiteBatchWriter:
    """
    Optimized batch writer for SQLite with zlib compression and zero reads.
    Uses WAL mode and prepared statements for speed.
    """

    db_path = '~/.blueplane/telemetry.db'

    def __init__():
        """
        Initialize SQLite connection with performance settings.

        - Enable WAL mode: PRAGMA journal_mode=WAL
        - Set synchronous=NORMAL for speed
        - Set cache_size=-64000 (64MB cache)
        - Prepare INSERT statement for raw_traces table
        """

    async def write_batch(events: List[Dict]) -> None:
        """
        Write batch of events to SQLite - no reads, no lookups, pure writes.

        - For each event:
          - Compress full event dict with zlib (level 6)
          - Extract indexed fields (session_id, event_type, etc.)
          - Build row tuple with compressed event_data BLOB
        - Single executemany() with INSERT statement
        - Commit transaction
        - Target: <8ms for 100 events at P95

        Schema: See layer2_db_architecture.md (raw_traces table)
        Compression: zlib level 6 provides 7-10x compression ratio
        """
```

### CDC Publisher

```python
# Shared CDC publisher (common/cdc_publisher.py)
# Pseudocode:

class CDCPublisher:
    """
    Publishes change data capture events to Redis Streams.
    Fire-and-forget pattern for maximum throughput.
    """

    stream_key = 'cdc:events'
    max_stream_length = 100000

    async def publish(event: Dict) -> None:
        """
        Publish CDC event to Redis Stream (fire-and-forget).

        - Connect to Redis (lazy initialization)
        - XADD with MAXLEN=100000, approximate=True
        - Serialize event to JSON
        - Log warning on error but don't block
        - CDC failures don't affect fast path
        """
```

## Slow Path Implementation

### Worker Pool Manager

```python
# server/slow_path/worker_pool.py (pseudocode)

class WorkerPoolManager:
    """
    Manages pools of async workers for different processing types.
    Handles scaling, priority, and backpressure.
    """

    worker_config = {
        'metrics': {'count': 2, 'priority': [1, 2, 3]},
        'conversation': {'count': 2, 'priority': [1, 2]},
        'ai_insights': {'count': 1, 'priority': [4, 5]}
    }

    async def start() -> None:
        """
        Start all worker pools.

        - Create MetricsWorker instances (2x)
        - Create ConversationWorker instances (2x)
        - Create AIInsightsWorker instances (1x)
        - Start async task for each worker with _run_worker()
        - Start _monitor_backpressure() task
        """

    async def run_worker(worker, worker_type: str) -> None:
        """
        Run single worker with error handling.

        While running:
        - XREADGROUP from 'cdc:events' (block 1000ms)
        - Check event priority matches worker type
        - Call worker.process(event)
        - XACK on success
        - Track stats (processed, failed)
        - On error: Log and XACK (prevent reprocessing)
        """

    async def monitor_backpressure() -> None:
        """
        Monitor queue depth and adjust workers.

        Every 5 seconds:
        - Check stream length with XINFO STREAM
        - Calculate lag from oldest message timestamp
        - Log warnings if length > 10000
        - Log critical if length > 50000
        - Could scale workers or pause AI workers
        """
```

### Metrics Worker

```python
# server/slow_path/metrics_worker.py (pseudocode)

class MetricsWorker:
    """Calculates metrics from raw events. Can read from any store since it's async."""

    async def process(cdc_event: Dict) -> None:
        """
        Process single CDC event to calculate metrics.

        1. Read full event from sqlite.get_by_sequence(sequence) and decompress
        2. Get recent session stats from sqlite.get_session_stats(session_id, window=5min)
        3. Calculate metrics based on event_type:
           - 'tool_use': Calculate latency percentiles (p50, p95, p99)
           - 'acceptance_decision': Calculate acceptance rate (sliding window of 100)
           - 'session_start': Count active sessions in last 60 minutes
        4. Write all metrics to redis_metrics.record_metric()

        Note: SQLite queries on raw_traces require decompression (10-40ms for session queries)
        but this is acceptable in async slow path with eventual consistency.

        See layer2_metrics_derivation.md for detailed metric calculations
        """
```

### Conversation Worker

```python
# server/slow_path/conversation_worker.py (pseudocode)

class ConversationWorker:
    """
    Builds and updates conversation structure from events.
    Implements detailed reconstruction algorithms from layer2_conversation_reconstruction.md
    """

    async def process(cdc_event: Dict) -> None:
        """
        Process event to update conversation structure.

        1. Read full event from sqlite.get_by_sequence(sequence) and decompress
        2. Get or create conversation in SQLite (same database, conversations table)
        3. Update based on event_type:
           - 'user_prompt': Add turn with content_hash
           - 'assistant_response': Add turn with tokens and latency
           - 'tool_use': Update tool_sequence and add turn
           - 'code_change': Add code change with acceptance tracking
        4. Update conversation metrics (acceptance rate, total changes)

        Benefits of single SQLite database:
        - Can use transactions across raw_traces and conversations tables
        - No cross-database joins needed
        - Simpler connection management

        For platform-specific reconstruction:
        - See layer2_conversation_reconstruction.md#cursor-platform-reconstruction
        - See layer2_conversation_reconstruction.md#claude-code-platform-reconstruction
        """
```

## Performance Characteristics

### Latency Targets

| Component | Operation | Target P50 | Target P95 | Target P99 |
|-----------|----------|------------|------------|------------|
| **Fast Path** | | | | |
| MQ Read | Redis XREADGROUP | 0.5ms | 1ms | 2ms |
| Parse | JSON decode | 0.1ms | 0.2ms | 0.5ms |
| Compress | zlib level 6 (100 events) | 2ms | 3ms | 5ms |
| Batch Write | SQLite insert (100 events, compressed) | 5ms | 8ms | 15ms |
| CDC Publish | Redis XADD | 0.5ms | 1ms | 2ms |
| XACK | Acknowledge messages | 0.5ms | 1ms | 2ms |
| **Total Fast Path** | End-to-end per batch | **5ms** | **10ms** | **20ms** |
| | | | | |
| **Slow Path** | | | | |
| Decompress | zlib decompress per event | 0.1ms | 0.2ms | 0.5ms |
| Metrics Calculation | Per event | 10ms | 50ms | 100ms |
| Conversation Update | Per event | 10ms | 50ms | 100ms |
| AI Insights | Per event | 100ms | 500ms | 1000ms |
| **Total Lag** | From ingest to metrics | **<1s** | **<5s** | **<10s** |

### Throughput Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Fast path events/sec | 10,000 | Single consumer |
| SQLite writes/sec | 10,000 | Batched inserts with WAL mode |
| Redis Streams writes/sec | 100,000 | Message queue + CDC |
| CDC publishes/sec | 10,000 | Change data capture |
| Metrics updates/sec | 1,000 | 2-4 workers |
| Conversation updates/sec | 500 | 2-4 workers |

## Backpressure Management

### Queue Depth Thresholds

```python
# server/config/backpressure.yaml

backpressure:
  thresholds:
    green:
      cdc_queue_depth: 1000
      actions: []

    yellow:
      cdc_queue_depth: 10000
      actions:
        - log_warning
        - add_metrics_worker
        - increase_batch_size

    orange:
      cdc_queue_depth: 50000
      actions:
        - log_error
        - pause_ai_workers
        - alert_user
        - add_all_workers

    red:
      cdc_queue_depth: 100000
      actions:
        - drop_low_priority
        - emergency_flush
        - page_on_call

  monitoring:
    check_interval_seconds: 5
    metrics_window_seconds: 60

  scaling:
    max_metrics_workers: 8
    max_conversation_workers: 4
    max_ai_workers: 2
    scale_up_threshold: 0.8  # 80% of threshold
    scale_down_threshold: 0.2  # 20% of threshold
```

### Graceful Degradation

1. **Priority Shedding**: Drop priority 5 events first, then 4, etc.
2. **Worker Reallocation**: Move AI workers to metrics processing
3. **Batch Size Increase**: Process more events per batch
4. **Timeout Reduction**: Reduce processing timeouts
5. **Circuit Breakers**: Disable non-critical enrichment

## Failure Recovery

### Component Failure Scenarios

#### Fast Path Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| MQ consumer crash | Events accumulate in Redis Stream | Restart consumer, process backlog via PEL |
| SQLite write failure | Events lost (critical!) | WAL mode with automatic recovery, retry with exponential backoff |
| CDC publish failure | No metrics updates | Non-critical, log and continue |

#### Slow Path Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| Metrics worker crash | Metrics lag increases | Restart worker, process from last checkpoint |
| SQLite corruption | No conversation updates | Rebuild from SQLite raw_traces table |
| Redis down | No real-time metrics | Cache locally, bulk update when recovered |

### Recovery Procedures

```python
# server/recovery/rebuilder.py (pseudocode)

class ConversationRebuilder:
    """Rebuilds conversation data from raw traces. Used for recovery after corruption or migration."""

    async def rebuild_session(session_id: str) -> None:
        """
        Rebuild single session from raw traces.

        - Get all events for session from SQLite raw_traces table (ordered by timestamp, decompress event_data)
        - Delete existing conversation data from SQLite conversations table
        - Replay events in order through ConversationWorker
        - Log completion
        """
```

## Monitoring and Observability

### Key Metrics

```python
# server/monitoring/metrics.py (pseudocode)

class PipelineMetrics:
    """Metrics exposed for monitoring."""

    def get_metrics() -> Dict:
        """
        Return pipeline health metrics.

        Categories:
        - fast_path: events/sec, batch_write_latency, cdc_publish_latency, queue_depth, dlq_depth
        - slow_path: cdc_queue_depth, processing_lag_ms, events_processed/failed, worker_utilization
        - storage: sqlite_db_size_mb, sqlite_wal_size_mb, redis_memory_mb, parquet_archives_count
        - health: fast_path_healthy, slow_path_healthy, backpressure_level, data_consistency
        """
```

### Alerting Rules

```yaml
# server/monitoring/alerts.yaml

alerts:
  - name: FastPathDown
    condition: rate(events_ingested) == 0
    duration: 30s
    severity: critical
    action: page

  - name: HighCDCQueueDepth
    condition: cdc_queue_depth > 50000
    duration: 5m
    severity: warning
    action: email

  - name: ProcessingLagHigh
    condition: processing_lag_ms > 30000
    duration: 10m
    severity: warning
    action: slack

  - name: SQLiteWriteFailures
    condition: rate(sqlite_write_errors) > 0
    duration: 1m
    severity: critical
    action: page
```

## Conclusion

This async pipeline architecture achieves:

1. ✅ **Low-latency raw ingestion** (<10ms P95 with compression)
2. ✅ **Eventual consistency** for derived data (<5s typical)
3. ✅ **Graceful degradation** under load
4. ✅ **Failure isolation** between fast and slow paths
5. ✅ **Horizontal scalability** via worker pools

The architecture prioritizes data durability and raw event capture above all else, while providing rich analytics through eventually-consistent async processing.