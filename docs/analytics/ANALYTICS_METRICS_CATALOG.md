# Analytics Metrics Catalog

**Document Status**: Draft for Review  
**Version**: 0.1.0  
**Last Updated**: December 3, 2025

---

## Overview

This catalog documents all metrics available in Blueplane Telemetry Analytics, their data sources, calculation methods, and intended use cases.

---

## Metrics by Category

### Activity Metrics

#### M001: Session Count
**Definition**: Number of AI-assisted coding sessions  
**Formula**: `COUNT(DISTINCT session_id) WHERE date = <target_date>`  
**Data Source**: `raw_traces` table (both platforms)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: All  

```sql
-- Daily session count
SELECT 
    DATE(timestamp) as date,
    COUNT(DISTINCT external_session_id) as session_count
FROM raw_traces
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

---

#### M002: Interaction Count
**Definition**: Total number of AI interactions (messages, tool calls, etc.)  
**Formula**: `COUNT(*) WHERE event_type IN ('generation', 'prompt', 'tool_use', 'transcript_trace')`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: All  

```sql
-- Daily interaction count by platform
SELECT 
    DATE(timestamp) as date,
    platform,
    COUNT(*) as interaction_count
FROM raw_traces
WHERE event_type IN ('generation', 'prompt', 'tool_use', 'assistant_response', 'transcript_trace')
GROUP BY DATE(timestamp), platform
ORDER BY date DESC;
```

---

#### M003: Active Days
**Definition**: Number of days with at least one interaction  
**Formula**: `COUNT(DISTINCT DATE(timestamp))`  
**Data Source**: `raw_traces` table  
**Granularity**: Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead  

---

#### M004: Daily Active Sessions
**Definition**: Average number of sessions started per active day  
**Formula**: `session_count / active_days`  
**Data Source**: Derived from M001, M003  
**Granularity**: Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead  

---

### Productivity Metrics

#### M010: Lines Added
**Definition**: Total lines of code added through AI-assisted composer sessions  
**Formula**: `SUM(lines_added)` from composer_sessions  
**Data Source**: `composer_sessions` table (Cursor)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead, Manager  

```sql
-- Weekly lines added
SELECT 
    workspace_hash,
    DATE_TRUNC('week', created_at) as week,
    SUM(lines_added) as total_lines_added,
    SUM(lines_removed) as total_lines_removed,
    SUM(lines_added) - SUM(lines_removed) as net_change
FROM composer_sessions
GROUP BY workspace_hash, DATE_TRUNC('week', created_at)
ORDER BY week DESC;
```

---

#### M011: Lines Removed
**Definition**: Total lines of code removed through AI-assisted composer sessions  
**Formula**: `SUM(lines_removed)` from composer_sessions  
**Data Source**: `composer_sessions` table (Cursor)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead  

---

#### M012: Net Code Change
**Definition**: Net change in lines of code (added - removed)  
**Formula**: `lines_added - lines_removed`  
**Data Source**: Derived from M010, M011  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead, Manager  

---

#### M013: Composer Sessions
**Definition**: Number of Cursor composer sessions  
**Formula**: `COUNT(DISTINCT composer_id)`  
**Data Source**: `composer_sessions` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer (Cursor users)  

```sql
-- Composer session metrics
SELECT 
    workspace_hash,
    COUNT(DISTINCT composer_id) as session_count,
    AVG(lines_added + lines_removed) as avg_lines_per_session,
    MAX(lines_added + lines_removed) as max_lines_session
FROM composer_sessions
GROUP BY workspace_hash;
```

---

#### M014: AI Generations
**Definition**: Number of AI code generation events  
**Formula**: `COUNT(*) WHERE event_type = 'generation'`  
**Data Source**: `ai_generations` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer (Cursor users)  

---

### Token & Cost Metrics (Claude Only)

#### M020: Input Tokens
**Definition**: Total input tokens consumed  
**Formula**: `SUM(input_tokens)` from Claude transcripts  
**Data Source**: Claude `raw_traces` (message.usage.input_tokens)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Manager  

```sql
-- Token usage by model
SELECT 
    model,
    DATE(timestamp) as date,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(cache_read_input_tokens) as cache_hits
FROM claude_raw_traces
WHERE type = 'assistant'
GROUP BY model, DATE(timestamp);
```

---

#### M021: Output Tokens
**Definition**: Total output tokens generated  
**Formula**: `SUM(output_tokens)` from Claude transcripts  
**Data Source**: Claude `raw_traces` (message.usage.output_tokens)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Manager  

---

#### M022: Cache Efficiency
**Definition**: Percentage of tokens served from cache  
**Formula**: `cache_read_tokens / (cache_read_tokens + input_tokens) * 100`  
**Data Source**: Claude `raw_traces`  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Manager  

---

#### M023: Estimated Cost
**Definition**: Estimated API cost based on token usage  
**Formula**: `(input_tokens * input_rate) + (output_tokens * output_rate)`  
**Data Source**: Derived from M020, M021 + configurable rates  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Manager  
**Notes**: Requires rate configuration; Cursor cost not available  

---

### Time-Based Metrics

#### M030: Hourly Activity Distribution
**Definition**: Distribution of interactions by hour of day  
**Formula**: `COUNT(*) GROUP BY HOUR(timestamp)`  
**Data Source**: `raw_traces` table  
**Granularity**: Hourly (aggregated over period)  
**Persona Relevance**: Developer  

```sql
-- Hourly activity pattern
SELECT 
    EXTRACT(HOUR FROM timestamp) as hour,
    COUNT(*) as interaction_count,
    COUNT(DISTINCT DATE(timestamp)) as active_days,
    COUNT(*) * 1.0 / COUNT(DISTINCT DATE(timestamp)) as avg_per_day
FROM raw_traces
WHERE timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY EXTRACT(HOUR FROM timestamp)
ORDER BY hour;
```

---

#### M031: Day of Week Distribution
**Definition**: Distribution of interactions by day of week  
**Formula**: `COUNT(*) GROUP BY DAYOFWEEK(timestamp)`  
**Data Source**: `raw_traces` table  
**Granularity**: Day of week (aggregated over period)  
**Persona Relevance**: Developer, Team Lead  

---

#### M032: Peak Productivity Hour
**Definition**: Hour of day with highest average interaction count  
**Formula**: `MAX(avg_hourly_interactions)`  
**Data Source**: Derived from M030  
**Granularity**: Single value (per period)  
**Persona Relevance**: Developer  

---

#### M033: Peak Productivity Day
**Definition**: Day of week with highest average interaction count  
**Formula**: `MAX(avg_daily_interactions)`  
**Data Source**: Derived from M031  
**Granularity**: Single value (per period)  
**Persona Relevance**: Developer  

---

### Platform Metrics

#### M040: Platform Distribution
**Definition**: Distribution of interactions by platform (Cursor vs. Claude)  
**Formula**: `COUNT(*) GROUP BY platform`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead  

```sql
-- Platform distribution
SELECT 
    platform,
    COUNT(*) as total_interactions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM raw_traces
GROUP BY platform;
```

---

#### M041: Event Type Distribution
**Definition**: Distribution of interactions by event type  
**Formula**: `COUNT(*) GROUP BY event_type`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, PM  

---

### Workspace Metrics

#### M050: Workspace Activity
**Definition**: Interaction count per workspace  
**Formula**: `COUNT(*) GROUP BY workspace_hash`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, Team Lead  

```sql
-- Workspace activity summary
SELECT 
    workspace_hash,
    workspace_path,
    COUNT(*) as total_interactions,
    COUNT(DISTINCT DATE(timestamp)) as active_days,
    MAX(timestamp) as last_activity
FROM raw_traces
JOIN workspaces USING (workspace_hash)
GROUP BY workspace_hash, workspace_path
ORDER BY total_interactions DESC;
```

---

#### M051: Active Workspaces
**Definition**: Count of workspaces with activity in period  
**Formula**: `COUNT(DISTINCT workspace_hash)`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer  

---

### Session Depth Metrics

#### M060: Interactions per Session
**Definition**: Average number of interactions per session  
**Formula**: `COUNT(interactions) / COUNT(DISTINCT session_id)`  
**Data Source**: `raw_traces` table  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer  

```sql
-- Session depth analysis
SELECT 
    session_id,
    COUNT(*) as interaction_count,
    MIN(timestamp) as session_start,
    MAX(timestamp) as session_end,
    DATEDIFF('minute', MIN(timestamp), MAX(timestamp)) as duration_minutes
FROM raw_traces
WHERE session_id IS NOT NULL
GROUP BY session_id
HAVING COUNT(*) > 1
ORDER BY interaction_count DESC;
```

---

#### M061: Session Duration
**Definition**: Duration of AI-assisted sessions  
**Formula**: `MAX(timestamp) - MIN(timestamp)` per session  
**Data Source**: `raw_traces` table  
**Granularity**: Per session  
**Persona Relevance**: Developer  

---

#### M062: Session Depth Distribution
**Definition**: Distribution of sessions by interaction count  
**Formula**: Bucket sessions by interaction count  
**Data Source**: Derived from M060  
**Granularity**: Aggregated over period  
**Persona Relevance**: Developer, Team Lead  

---

### Quality Metrics

#### M070: Tool Success Rate
**Definition**: Percentage of tool calls that succeed (Claude)  
**Formula**: `COUNT(WHERE NOT is_error) / COUNT(*) * 100`  
**Data Source**: Claude tool_result events  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, PM  

```sql
-- Tool success rate
SELECT 
    tool_name,
    COUNT(*) as total_calls,
    SUM(CASE WHEN NOT is_error THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN NOT is_error THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM tool_usage
GROUP BY tool_name
ORDER BY total_calls DESC;
```

---

#### M071: Retry Rate
**Definition**: Percentage of interactions that required retry  
**Formula**: `COUNT(retries) / COUNT(total) * 100`  
**Data Source**: `raw_traces` (pattern detection)  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Developer, PM  
**Notes**: Requires pattern detection logic  

---

### Team Metrics (Future)

#### M080: Team Session Count
**Definition**: Total sessions across team workspaces  
**Formula**: `SUM(session_count)` for team workspaces  
**Data Source**: Aggregated from M001 with team filter  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Team Lead, Manager  

---

#### M081: Team Active Users
**Definition**: Count of active team members in period  
**Formula**: `COUNT(DISTINCT user_id)` with team filter  
**Data Source**: Requires user identification  
**Granularity**: Daily, Weekly, Monthly  
**Persona Relevance**: Team Lead, Manager  
**Notes**: Requires user mapping (future)  

---

#### M082: Adoption Rate
**Definition**: Percentage of team using AI tools actively  
**Formula**: `active_users / total_team_size * 100`  
**Data Source**: Derived from M081 + team roster  
**Granularity**: Weekly, Monthly  
**Persona Relevance**: Team Lead, Manager  
**Notes**: Requires team configuration (future)  

---

### System Health Metrics

#### M090: Processing Latency
**Definition**: Time from event capture to analytics availability  
**Formula**: `AVG(analytics_ingested_at - event_timestamp)`  
**Data Source**: System timestamps  
**Granularity**: Real-time, Daily  
**Persona Relevance**: DevOps  

---

#### M091: Queue Depth
**Definition**: Number of events pending processing  
**Formula**: Redis stream length  
**Data Source**: Redis XLEN  
**Granularity**: Real-time  
**Persona Relevance**: DevOps  

---

#### M092: Error Rate
**Definition**: Percentage of events failing processing  
**Formula**: `DLQ_count / total_events * 100`  
**Data Source**: Redis DLQ stream  
**Granularity**: Real-time, Daily  
**Persona Relevance**: DevOps  

---

#### M093: Storage Utilization
**Definition**: Size of SQLite and DuckDB databases  
**Formula**: File size queries  
**Data Source**: File system  
**Granularity**: Daily  
**Persona Relevance**: DevOps  

---

## Metrics by Data Availability

### Currently Available (Data Exists)

| Metric ID | Metric Name | Cursor | Claude |
|-----------|-------------|--------|--------|
| M001 | Session Count | ✅ | ✅ |
| M002 | Interaction Count | ✅ | ✅ |
| M003 | Active Days | ✅ | ✅ |
| M010 | Lines Added | ✅ | ❌ |
| M011 | Lines Removed | ✅ | ❌ |
| M013 | Composer Sessions | ✅ | ❌ |
| M014 | AI Generations | ✅ | ❌ |
| M020 | Input Tokens | ❌ | ✅ |
| M021 | Output Tokens | ❌ | ✅ |
| M022 | Cache Efficiency | ❌ | ✅ |
| M030 | Hourly Distribution | ✅ | ✅ |
| M031 | Day of Week Distribution | ✅ | ✅ |
| M040 | Platform Distribution | ✅ | ✅ |
| M041 | Event Type Distribution | ✅ | ✅ |
| M050 | Workspace Activity | ✅ | ✅ |
| M070 | Tool Success Rate | ❌ | ✅ |

### Requires Derivation (Calculation Needed)

| Metric ID | Metric Name | Dependency |
|-----------|-------------|------------|
| M004 | Daily Active Sessions | M001 / M003 |
| M012 | Net Code Change | M010 - M011 |
| M023 | Estimated Cost | M020, M021 + rates |
| M032 | Peak Productivity Hour | MAX(M030) |
| M033 | Peak Productivity Day | MAX(M031) |
| M060 | Interactions per Session | COUNT / session |
| M062 | Session Depth Distribution | Bucketed M060 |

### Future (Not Yet Captured)

| Metric ID | Metric Name | Blocker |
|-----------|-------------|---------|
| M081 | Team Active Users | User identification |
| M082 | Adoption Rate | Team roster |
| M071 | Retry Rate | Pattern detection |
| Cursor tokens | Token usage | Cursor doesn't expose |
| Cursor model | Model name | Cursor doesn't expose |

---

## Dashboard Placement

### Personal Dashboard (Developer)

| Section | Metrics |
|---------|---------|
| Today's Summary | M001, M002, M010-M012 |
| Weekly Trends | M001, M002 (7-day) |
| Platform Breakdown | M040, M041 |
| Workspace Activity | M050, M051 |
| Time Patterns | M030, M031, M032, M033 |
| Token Usage (Claude) | M020, M021, M022, M023 |

### Team Dashboard (Lead)

| Section | Metrics |
|---------|---------|
| Team Overview | M080, M081, M082 |
| Activity Trends | M002 (aggregated) |
| Platform Adoption | M040 (team) |
| Top Workspaces | M050 (team) |

### Executive Dashboard (Manager)

| Section | Metrics |
|---------|---------|
| ROI Summary | M023 (total), M010-M012 (total) |
| Adoption Trends | M082 (over time) |
| Team Comparison | M002 (per team) |

### System Health Dashboard (DevOps)

| Section | Metrics |
|---------|---------|
| Pipeline Status | M090, M091, M092 |
| Storage | M093 |
| Error Monitoring | M092 (detailed) |

---

## Related Documents

- [Analytics User Personas](./ANALYTICS_USER_PERSONAS.md)
- [Analytics User Stories](./ANALYTICS_USER_STORIES.md)
- [Analytics Feature Roadmap](./ANALYTICS_FEATURE_ROADMAP.md)

---

*Document maintained by: Blueplane Analytics Team*

