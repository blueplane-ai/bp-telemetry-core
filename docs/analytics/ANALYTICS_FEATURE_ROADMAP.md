# Analytics Feature Roadmap

**Document Status**: Draft for Review  
**Version**: 0.1.0  
**Last Updated**: December 3, 2025

---

## Executive Summary

This roadmap outlines the phased development of Blueplane Telemetry Analytics features, starting with high-impact "no brainer" analytics that every user will want, progressing through team-level features, and culminating in advanced organizational insights.

**Philosophy**: Start with immediate personal value, build trust through privacy, then expand to team and organizational insights.

---

## Current State Assessment

### Data Available Today

Based on the current instrumentation of Claude Code and Cursor, we capture:

| Platform | Data Type | Fields Available | Analytics Potential |
|----------|-----------|------------------|---------------------|
| **Cursor** | Sessions | session_id, workspace_hash, timestamps | ⭐⭐⭐ High |
| **Cursor** | AI Generations | generationUUID, type, textDescription, unixMs | ⭐⭐⭐ High |
| **Cursor** | Composer Sessions | composerId, lines_added, lines_removed, mode | ⭐⭐⭐ High |
| **Cursor** | File History | file_path, accessed_at | ⭐⭐ Medium |
| **Claude** | Transcripts | model, tokens (input/output/cache), timestamps | ⭐⭐⭐ High |
| **Claude** | Tool Usage | tool_name, tool_result, is_error | ⭐⭐⭐ High |
| **Claude** | Sessions | session_id, git_branch, cwd | ⭐⭐⭐ High |

### Current Gaps

| Data Type | Status | Impact |
|-----------|--------|--------|
| Cursor model name | ❌ Not available from Cursor | Can't track model preferences |
| Cursor token usage | ❌ Not available from Cursor | Can't calculate costs |
| Interaction success/failure | ⚠️ Partial (errors only) | Limited quality metrics |
| User identity | ⚠️ Workspace-based only | Team features limited |

---

## Phase 1: Personal Productivity MVP (Weeks 1-4)

### Theme: "How Am I Doing?"

Deliver immediate personal value with no privacy concerns—all data is local, all insights are personal.

### Features

#### 1.1 Daily Activity Dashboard
**What it shows**: Your AI-assisted coding activity for today

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 TODAY'S ACTIVITY                               Dec 3, 2025  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Sessions: 8          Interactions: 47        Code Changes: 156│
│  ▲ +2 from avg        ▲ +12 from avg          ▲ +23 from avg  │
│                                                                 │
│  🔷 Cursor: 32 interactions (68%)                               │
│  🔶 Claude: 15 interactions (32%)                               │
│                                                                 │
│  📁 Most Active Project: bp-telemetry-core (23 interactions)    │
│                                                                 │
│  ⏰ Peak Hour: 2:00 PM - 3:00 PM (12 interactions)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**CLI Commands**:
```bash
blueplane stats today
blueplane stats yesterday
blueplane stats --date 2025-12-01
```

**Data Sources**: raw_traces, composer_sessions

**Implementation Priority**: P0 - Must have for launch

---

#### 1.2 Weekly Productivity Trends
**What it shows**: How your productivity changed over the past 7 days

```
┌─────────────────────────────────────────────────────────────────┐
│  📈 WEEKLY TRENDS                           Nov 27 - Dec 3     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Interactions by Day:                                           │
│                                                                 │
│  Mon ████████████████████ 45                                    │
│  Tue ██████████████████████████ 62                              │
│  Wed ████████████████████ 47                                    │
│  Thu ████████████████████████████████ 78  ← Peak day           │
│  Fri ██████████████████ 42                                      │
│  Sat ███████ 18                                                 │
│  Sun ████████████ 28                                            │
│                                                                 │
│  Total: 320 interactions   Avg: 46/day   Best Day: Thursday     │
│                                                                 │
│  📊 This week vs last week: ▲ +15% more interactions           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**CLI Commands**:
```bash
blueplane stats week
blueplane stats week --compare  # Compare to previous week
```

**Implementation Priority**: P0 - Must have for launch

---

#### 1.3 Platform Usage Breakdown
**What it shows**: How you use Claude Code vs. Cursor

```
┌─────────────────────────────────────────────────────────────────┐
│  🔀 PLATFORM USAGE                          Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Overall Distribution:                                          │
│  ═══════════════════════════════════════════════════════════   │
│  Cursor     ████████████████████████████░░░░░░  68%  (890)     │
│  Claude     ░░░░░░░░░░░░████████████████████░░  32%  (420)     │
│                                                                 │
│  Event Types by Platform:                                       │
│  ┌──────────────┬────────────┬────────────┐                    │
│  │ Event Type   │   Cursor   │   Claude   │                    │
│  ├──────────────┼────────────┼────────────┤                    │
│  │ Generation   │    312     │     -      │                    │
│  │ Composer     │    245     │     -      │                    │
│  │ Shell/Tool   │    198     │    156     │                    │
│  │ Transcript   │     -      │    264     │                    │
│  │ Other        │    135     │     -      │                    │
│  └──────────────┴────────────┴────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**CLI Commands**:
```bash
blueplane platforms
blueplane platforms --period 7d
```

**Implementation Priority**: P0 - Must have for launch

---

#### 1.4 Workspace Activity Summary
**What it shows**: Activity across your projects/workspaces

```
┌─────────────────────────────────────────────────────────────────┐
│  📁 WORKSPACE ACTIVITY                      Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Workspace                       Sessions   Events   Last Active│
│  ───────────────────────────────────────────────────────────── │
│  1. bp-telemetry-core              45       890      2h ago    │
│  2. frontend-app                   23       456      1d ago    │
│  3. api-service                    18       234      3d ago    │
│  4. documentation                  12       145      1w ago    │
│  5. scripts                         8        67      2w ago    │
│                                                                 │
│  Total: 5 active workspaces                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**CLI Commands**:
```bash
blueplane workspaces
blueplane workspaces --sort events
blueplane workspace <hash> --details
```

**Implementation Priority**: P1 - Should have for launch

---

#### 1.5 Code Output Metrics
**What it shows**: Lines of code generated/modified with AI assistance

```
┌─────────────────────────────────────────────────────────────────┐
│  📝 CODE OUTPUT                             Last 7 Days         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Lines Added:    1,245  ▲                                       │
│  Lines Removed:    456  ▼                                       │
│  Net Change:      +789                                          │
│                                                                 │
│  By Workspace:                                                  │
│  ┌──────────────────────┬─────────┬─────────┬──────────┐       │
│  │ Workspace            │  Added  │ Removed │   Net    │       │
│  ├──────────────────────┼─────────┼─────────┼──────────┤       │
│  │ bp-telemetry-core    │   567   │   123   │  +444    │       │
│  │ frontend-app         │   345   │   234   │  +111    │       │
│  │ api-service          │   333   │    99   │  +234    │       │
│  └──────────────────────┴─────────┴─────────┴──────────┘       │
│                                                                 │
│  Trend: ▲ +23% from last week                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Data Source**: composer_sessions (lines_added, lines_removed)

**CLI Commands**:
```bash
blueplane code
blueplane code --workspace <hash>
```

**Implementation Priority**: P1 - Should have for launch

---

### Phase 1 Implementation Checklist

- [ ] DuckDB schema finalization
- [ ] CLI framework setup (Rich library for beautiful output)
- [ ] Query functions for each metric
- [ ] Daily aggregation logic
- [ ] Weekly comparison logic
- [ ] Platform breakdown logic
- [ ] Workspace summary logic
- [ ] Code metrics extraction from composer_sessions
- [ ] Documentation and help text
- [ ] Unit tests for all queries

---

## Phase 2: Deep Personal Insights (Weeks 5-8)

### Theme: "When Am I At My Best?"

Provide insights that help developers optimize their workflow and identify patterns.

### Features

#### 2.1 Peak Productivity Hours
**What it shows**: When you're most productive with AI tools

```
┌─────────────────────────────────────────────────────────────────┐
│  ⏰ PRODUCTIVITY BY HOUR                    Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Hour   Activity                                                │
│  ────   ────────────────────────────────────────────           │
│  06:00  ██                                                      │
│  07:00  ████                                                    │
│  08:00  ████████                                                │
│  09:00  ████████████████  ← Morning Peak                        │
│  10:00  ██████████████████████  ← YOUR BEST HOUR (10-11am)     │
│  11:00  ████████████████████                                    │
│  12:00  ████████                                                │
│  13:00  ██████████                                              │
│  14:00  ████████████████████████  ← Afternoon Peak             │
│  15:00  ██████████████████████                                  │
│  16:00  ████████████████                                        │
│  17:00  ██████████                                              │
│  18:00  ████████                                                │
│  19:00  ████████                                                │
│  20:00  ██████                                                  │
│                                                                 │
│  💡 Insight: Your best 3 hours account for 45% of all activity │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Priority**: P1

---

#### 2.2 Day-of-Week Patterns
**What it shows**: Which days you're most productive

```
┌─────────────────────────────────────────────────────────────────┐
│  📅 DAY OF WEEK PATTERNS                    Last 90 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Day        Avg Interactions    Sessions    Best Feature       │
│  ────────   ────────────────    ────────    ────────────       │
│  Monday          42              4.2        Code Generation    │
│  Tuesday         48              4.8        ← Highest Sessions │
│  Wednesday       45              4.5        Tool Usage         │
│  Thursday        52 ⭐           5.1        ← Most Productive  │
│  Friday          38              3.8        Code Review        │
│  Saturday        18              1.8        Documentation      │
│  Sunday          22              2.2        Planning           │
│                                                                 │
│  💡 Thursday is your most productive day (avg 52 interactions) │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Priority**: P1

---

#### 2.3 Token Usage & Cost Tracking (Claude Only)
**What it shows**: Token consumption and estimated costs

```
┌─────────────────────────────────────────────────────────────────┐
│  💰 TOKEN USAGE                             Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Total Tokens:                                                  │
│  ├─ Input:           1,245,678                                  │
│  ├─ Output:            234,567                                  │
│  └─ Cache Hits:        890,123 (58% efficiency!)               │
│                                                                 │
│  By Model:                                                      │
│  ┌─────────────────────┬───────────┬─────────┬──────────┐      │
│  │ Model               │  Input    │ Output  │ Sessions │      │
│  ├─────────────────────┼───────────┼─────────┼──────────┤      │
│  │ claude-sonnet-4.5   │  845K     │  178K   │    89    │      │
│  │ claude-opus-4.1     │  400K     │   56K   │    23    │      │
│  └─────────────────────┴───────────┴─────────┴──────────┘      │
│                                                                 │
│  Estimated Cost: ~$12.45 (at current rates)                    │
│                                                                 │
│  💡 Cache usage saved you ~$8.90 this month!                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Note**: Cursor token data not available from IDE

**Implementation Priority**: P1

---

#### 2.4 Interaction Type Analysis
**What it shows**: Breakdown of how you interact with AI tools

```
┌─────────────────────────────────────────────────────────────────┐
│  🔧 INTERACTION TYPES                       Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Distribution:                                                  │
│                                                                 │
│  Code Generation    ████████████████████████░░░░░░  45%  (567)│
│  Tool/Shell Exec    ██████████████████░░░░░░░░░░░░  32%  (398)│
│  Chat/Q&A           █████████░░░░░░░░░░░░░░░░░░░░░  15%  (189)│
│  File Operations    ████░░░░░░░░░░░░░░░░░░░░░░░░░░   8%   (98)│
│                                                                 │
│  Trend vs Last Month:                                          │
│  • Code Generation ▲ +12%                                      │
│  • Tool/Shell Exec ▼ -5%                                       │
│  • Chat/Q&A ◆ no change                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Priority**: P1

---

#### 2.5 Session Depth Analysis
**What it shows**: How deep/long your AI interactions typically go

```
┌─────────────────────────────────────────────────────────────────┐
│  🔄 SESSION DEPTH                           Last 30 Days        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Interactions per Session Distribution:                         │
│                                                                 │
│  1-5        ████████████████████████████████  42%  (quick)     │
│  6-15       ██████████████████████░░░░░░░░░░  35%  (medium)    │
│  16-30      ████████████░░░░░░░░░░░░░░░░░░░░  18%  (deep)      │
│  31+        ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   5%  (marathon)  │
│                                                                 │
│  Average: 12.3 interactions per session                        │
│  Median:  8 interactions per session                           │
│                                                                 │
│  💡 Your deep sessions (16+) produce 60% of code changes       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Priority**: P2

---

### Phase 2 Implementation Checklist

- [ ] Hourly aggregation views
- [ ] Day-of-week pattern analysis
- [ ] Token tracking from Claude transcripts
- [ ] Cost calculation with configurable rates
- [ ] Event type distribution queries
- [ ] Session depth analysis
- [ ] Trend comparison logic (vs. last week/month)
- [ ] Insight generation (automatic observations)

---

## Phase 3: Team Analytics (Weeks 9-12)

### Theme: "How Is My Team Doing?"

Enable team leads to understand adoption and identify support opportunities.

### Features

#### 3.1 Team Activity Dashboard
- Aggregate metrics across team workspaces
- Activity trends over time
- Platform adoption breakdown

#### 3.2 Anonymous Activity Distribution
- Show usage distribution (high/medium/low)
- Identify potential training opportunities
- No individual identification without consent

#### 3.3 Best Practice Identification
- Common successful patterns
- Exportable playbooks
- Team knowledge sharing

#### 3.4 Weekly Team Digest
- Automated weekly summary
- Key metrics and trends
- Anomaly highlighting

---

## Phase 4: Organizational Analytics (Weeks 13-16)

### Theme: "What's the Business Impact?"

Provide managers with ROI data and organizational insights.

### Features

#### 4.1 ROI Dashboard
- Cost per unit of output
- Productivity multipliers
- Budget optimization recommendations

#### 4.2 Cross-Team Comparison
- Team-level benchmarks
- Best practice propagation
- Resource allocation insights

#### 4.3 Executive Reporting
- One-page summaries
- Quarter-over-quarter trends
- Strategic recommendations

#### 4.4 Adoption Analytics
- Rollout tracking
- Feature utilization
- Training effectiveness

---

## Success Metrics

### Phase 1 Success Criteria

| Metric | Target |
|--------|--------|
| CLI response time | < 1 second |
| User engagement | 3+ queries/week |
| Feature coverage | All P0 stories |
| Documentation | Complete CLI help |

### Phase 2 Success Criteria

| Metric | Target |
|--------|--------|
| Insights delivered | 2+ actionable per user |
| Pattern recognition | Accurate hourly peaks |
| Token tracking | 95% accuracy |

### Phase 3-4 Success Criteria

| Metric | Target |
|--------|--------|
| Team adoption | 80% of target users |
| Report generation | < 5 seconds |
| Exec presentation ready | Yes |

---

## Technical Dependencies

### Phase 1 Requirements

- [x] DuckDB analytics database
- [x] SQLite raw traces
- [x] Analytics service running
- [ ] CLI framework (Rich)
- [ ] Query optimization

### Phase 2 Requirements

- [ ] Hourly aggregation views
- [ ] Token extraction from Claude
- [ ] Cost configuration

### Phase 3-4 Requirements

- [ ] Team/user mapping
- [ ] Privacy controls
- [ ] Report generation
- [ ] Email delivery

---

## Related Documents

- [Analytics User Personas](./ANALYTICS_USER_PERSONAS.md)
- [Analytics User Stories](./ANALYTICS_USER_STORIES.md)
- [Analytics Metrics Catalog](./ANALYTICS_METRICS_CATALOG.md)

---

*Document maintained by: Blueplane Analytics Team*

