<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Blueplane Telemetry Core - Claude Code Project Instructions

## Project Overview

Blueplane Telemetry Core is a **privacy-first, local-only telemetry and analytics system** for AI-assisted coding. It captures, processes, and analyzes telemetry from platforms like Claude Code and Cursor while ensuring all data stays on the developer's local machine.

### Core Philosophy

1. **Privacy-First**: No code content, no cloud transmission, all local storage
2. **Developer-Owned**: Users own and control all their data
3. **Zero Configuration**: Embedded databases with no setup required
4. **High Performance**: Sub-millisecond ingestion, eventual consistency for analytics
5. **Extensible**: Plugin architecture for new platforms and metrics

## Architecture Overview

The system is built on a **three-layer architecture**:

### Layer 1: Capture

- **Purpose**: Lightweight telemetry capture from IDEs
- **Components**: IDE hooks, database monitors, transcript monitors
- **Output**: Events written to file-based message queue
- **Performance**: <1ms overhead per event

### Layer 2: Processing

- **Purpose**: High-performance async event processing
- **Pattern**: Fast path (writes only) + Slow path (async enrichment)
- **Databases**: DuckDB (raw traces), SQLite (conversations), Redis (metrics)
- **Performance**: <1ms ingestion, <5s metric updates

### Layer 3: Interfaces

- **Purpose**: Multiple access methods for telemetry data
- **Components**: CLI (Rich/Plotext), MCP Server, Web Dashboard
- **Access**: Only processed data (SQLite + Redis), never raw traces

## Key Design Decisions

### Why Three Layers?

1. **Separation of Concerns**: Capture, process, and access are independent
2. **Performance Isolation**: Slow processing doesn't block fast capture
3. **Privacy Boundaries**: Raw traces stay in Layer 2, Layer 3 gets processed data only
4. **Extensibility**: Easy to add new capture sources or interfaces

### Why Fast Path / Slow Path?

**Problem**: Traditional synchronous processing blocks event ingestion under load.

**Solution**:

- **Fast Path**: Zero-read writes, batched inserts, fire-and-forget CDC
- **Slow Path**: Async workers read from DuckDB, enrich, and update SQLite/Redis

**Benefits**:

- Zero-latency ingestion even with complex enrichment
- Graceful degradation under load
- Eventual consistency is acceptable for analytics

### Why File-Based Message Queue?

**Alternatives Considered**: RabbitMQ, Kafka, Redis Streams

**Why Files Won**:

- Atomic writes prevent partial messages
- Automatic retry via filesystem
- No network dependency or daemon required
- Simple and reliable
- Easy to debug (just cat the JSON files)

### Why DuckDB, SQLite, and Redis?

**DuckDB** (Raw Traces):

- In-process OLAP database
- Columnar storage with excellent compression (10:1)
- Fast analytical queries
- Easy archival to Parquet

**SQLite** (Conversations):

- Embedded relational database
- ACID transactions for data integrity
- Rich query capabilities for structured data
- Zero configuration

**Redis** (Real-Time Metrics):

- Sub-millisecond latency
- Built-in time-series support
- Streams for CDC work queue
- Automatic aggregation and expiry

## Implementation Guidelines

### Code Style

- **Python**: Follow PEP 8, use type hints, async/await for I/O
- **Documentation**: Pseudocode in architecture docs, docstrings in code
- **Testing**: pytest with async support, 80%+ coverage for core paths
- **Logging**: Structured logging with context (session_id, platform, etc.)

### Performance Requirements

**Fast Path** (Critical):

- <1ms P95 for event ingestion
- Zero database reads
- Batched writes (100 events or 100ms)
- Errors logged but never block

**Slow Path** (Important):

- <5s P95 for metric updates
- Can read from any database
- Backpressure monitoring and graceful degradation
- Worker failures don't crash the system

**Layer 3** (User-Facing):

- <100ms P95 for CLI queries
- Only access SQLite and Redis (never DuckDB)
- Proper pagination for large result sets
- Beautiful terminal output with Rich

### Error Handling

**Fast Path**:

- Log errors but never block ingestion
- Move failed messages to DLQ (dead letter queue)
- Emit error metrics for monitoring

**Slow Path**:

- Retry with exponential backoff
- Log errors and XACK to prevent reprocessing
- Emit worker health metrics

**Layer 3**:

- User-friendly error messages
- Suggest fixes when possible
- Never expose internal stack traces to users

## Directory Structure

```
blueplane-telemetry-core/
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # System overview
│   └── architecture/        # Design specifications
│       ├── layer1_capture.md
│       ├── layer2_async_pipeline.md
│       ├── layer2_conversation_reconstruction.md
│       ├── layer2_db_architecture.md
│       ├── layer2_local_server.md
│       ├── layer2_metrics_derivation.md
│       ├── layer3_cli_interface.md
│       ├── layer3_local_dashboard.md
│       └── layer3_mcp_server.md
├── src/                     # Implementation (to be developed)
├── LICENSE
├── README.md
└── CLAUDE.md                # This file
```

### Essential Reading

1. [Architecture Overview](./docs/ARCHITECTURE.md) - System design and rationale
2. [Layer 2 Async Pipeline](./docs/architecture/layer2_async_pipeline.md) - Fast/slow path pattern
3. [Database Architecture](./docs/architecture/layer2_db_architecture.md) - Storage design
4. [Layer 1 Capture](./docs/architecture/layer1_capture.md) - Event capture specifications

### External Resources

- [DuckDB Documentation](https://duckdb.org/docs/)
- [Redis Streams](https://redis.io/docs/data-types/streams/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Rich Documentation](https://rich.readthedocs.io/)

## Contributing

We welcome contributions! Please:

1. Read this CLAUDE.md thoroughly
2. Review the architecture documentation
3. Start with a small, focused change
4. Add tests for new functionality
5. Update documentation as needed
6. Submit a PR with a clear description

## Support

- **Questions**: Open a GitHub Discussion
- **Bugs**: File a GitHub Issue

- **General**: Check docs first, then ask!

---
