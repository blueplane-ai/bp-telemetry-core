# Analytics Materialized Views Design

## Overview

This document outlines the design for materialized views in DuckDB to optimize common analytics queries and improve query performance.

## Purpose

Materialized views pre-compute aggregations and common query patterns, providing:
- **Performance**: Faster queries for common analytics patterns
- **Consistency**: Pre-aggregated data ensures consistent metrics
- **Efficiency**: Reduces computation load for repeated queries

## Design Principles

1. **Incremental Updates**: Views should support incremental refresh, not full recomputation
2. **Query-Driven**: Views should match actual query patterns from `analytics_queries.py`
3. **Storage Efficiency**: Balance between pre-computation and storage costs
4. **Freshness**: Views should be refreshed on a schedule (e.g., every processing cycle)

## Proposed Materialized Views

### 1. `workspace_daily_summary`

**Purpose**: Pre-aggregate daily workspace activity metrics.

**Query Pattern**: Used by `query_workspace_activity()` for time-series analysis.

**Schema**:
```sql
CREATE MATERIALIZED VIEW workspace_daily_summary AS
SELECT 
    workspace_hash,
    DATE(timestamp) as activity_date,
    COUNT(DISTINCT trace_sequence) as trace_count,
    COUNT(DISTINCT g.generation_id) as generation_count,
    COUNT(DISTINCT c.composer_id) as composer_session_count,
    COUNT(DISTINCT f.id) as file_count,
    SUM(c.lines_added) as total_lines_added,
    SUM(c.lines_removed) as total_lines_removed,
    COUNT(DISTINCT platform) as platform_count
FROM raw_traces t
LEFT JOIN ai_generations g ON t.trace_sequence = g.trace_sequence AND t.platform = g.platform
LEFT JOIN composer_sessions c ON t.trace_sequence = c.trace_sequence AND t.platform = c.platform
LEFT JOIN file_history f ON t.trace_sequence = f.trace_sequence AND t.platform = f.platform
GROUP BY workspace_hash, DATE(timestamp);
```

**Refresh Strategy**: Incremental refresh by date (only refresh new/updated dates).

**Indexes**: `(workspace_hash, activity_date)` for fast lookups.

### 2. `platform_hourly_activity`

**Purpose**: Aggregate activity by platform and hour for trend analysis.

**Query Pattern**: Used for platform comparison and time-of-day analysis.

**Schema**:
```sql
CREATE MATERIALIZED VIEW platform_hourly_activity AS
SELECT 
    platform,
    DATE_TRUNC('hour', timestamp) as activity_hour,
    COUNT(DISTINCT trace_sequence) as trace_count,
    COUNT(DISTINCT workspace_hash) as workspace_count,
    AVG(duration_ms) as avg_duration_ms,
    SUM(tokens_used) as total_tokens
FROM raw_traces t
GROUP BY platform, DATE_TRUNC('hour', timestamp);
```

**Refresh Strategy**: Incremental refresh by hour (only refresh new/updated hours).

**Indexes**: `(platform, activity_hour)` for fast lookups.

### 3. `workspace_recent_activity`

**Purpose**: Fast lookup of recent activity (last 7 days) per workspace.

**Query Pattern**: Used for dashboard queries showing recent activity.

**Schema**:
```sql
CREATE MATERIALIZED VIEW workspace_recent_activity AS
SELECT 
    workspace_hash,
    MAX(timestamp) as last_activity,
    COUNT(DISTINCT trace_sequence) as recent_trace_count,
    COUNT(DISTINCT DATE(timestamp)) as active_days
FROM raw_traces t
WHERE timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY workspace_hash;
```

**Refresh Strategy**: Full refresh on each processing cycle (small dataset, fast refresh).

**Indexes**: `(workspace_hash)` for fast lookups.

### 4. `generation_type_summary`

**Purpose**: Aggregate AI generation statistics by type.

**Query Pattern**: Used for analyzing generation patterns and types.

**Schema**:
```sql
CREATE MATERIALIZED VIEW generation_type_summary AS
SELECT 
    generation_type,
    platform,
    COUNT(*) as generation_count,
    COUNT(DISTINCT workspace_hash) as workspace_count,
    AVG(EXTRACT(EPOCH FROM (generation_time - created_at))) as avg_generation_time_seconds,
    MIN(generation_time) as first_generation,
    MAX(generation_time) as last_generation
FROM ai_generations
GROUP BY generation_type, platform;
```

**Refresh Strategy**: Incremental refresh (only update changed generation types).

**Indexes**: `(generation_type, platform)` for fast lookups.

## Implementation Plan

### Phase 1: Basic Materialized Views (Future)

**Tasks**:
- [ ] Design view schemas based on query patterns
- [ ] Implement view creation in `DuckDBWriter`
- [ ] Add refresh logic to `AnalyticsService`
- [ ] Add tests for view correctness
- [ ] Document refresh strategies

### Phase 2: Incremental Refresh (Future)

**Tasks**:
- [ ] Implement incremental refresh logic
- [ ] Add refresh tracking (last refresh timestamp per view)
- [ ] Optimize refresh queries
- [ ] Add refresh monitoring/logging

### Phase 3: Query Optimization (Future)

**Tasks**:
- [ ] Update query functions to use materialized views
- [ ] Add fallback to base tables if views not available
- [ ] Benchmark query performance improvements
- [ ] Document query patterns

## Refresh Strategy

### Refresh Timing

- **On Processing Cycle**: Refresh views after processing new traces
- **Scheduled**: Optional scheduled refresh (e.g., hourly) for time-based aggregations
- **On-Demand**: Support manual refresh via API/CLI

### Refresh Methods

1. **Incremental Refresh** (Preferred):
   - Only refresh data for new/updated time periods
   - Track last refresh timestamp per view
   - More efficient for large datasets

2. **Full Refresh** (Fallback):
   - Recompute entire view
   - Simpler but slower
   - Use for small views or when incremental is not feasible

### Refresh Implementation

```python
class MaterializedViewManager:
    """Manage materialized view creation and refresh."""
    
    def create_views(self, connection):
        """Create all materialized views."""
        pass
    
    def refresh_view(self, view_name: str, incremental: bool = True):
        """Refresh a materialized view."""
        pass
    
    def refresh_all_views(self, incremental: bool = True):
        """Refresh all materialized views."""
        pass
```

## Performance Considerations

### Storage

- Materialized views increase storage requirements
- Estimate: ~10-20% overhead for common aggregations
- Monitor storage usage and adjust view selection

### Refresh Cost

- Incremental refresh: O(n) where n = new data
- Full refresh: O(N) where N = total data
- Balance refresh frequency with query performance

### Query Performance

- Expected improvement: 10-100x faster for aggregated queries
- Depends on data volume and query complexity
- Benchmark before/after to validate

## Future Enhancements

1. **Automatic View Selection**: Analyze query patterns and suggest views
2. **View Partitioning**: Partition views by date for better performance
3. **View Compression**: Compress older partitions in views
4. **View Versioning**: Support view schema evolution

## Status

**Current Status**: ⚠️ **Design Phase** - Not yet implemented

**Next Steps**:
1. Validate query patterns from actual usage
2. Implement basic materialized views
3. Measure performance improvements
4. Iterate based on results

## Related Documents

- [Analytics Queries](src/analytics/queries/analytics_queries.py) - Current query functions
- [DuckDB Schema](src/analytics/workers/duckdb_writer.py) - Base table schemas
- [Analytics Service](src/analytics/service.py) - Processing service

