# Analytics Near-Term Focus

**Based on**: Aaron/Ryan 1:1 Discussion (December 3, 2025)  
**Document Status**: Active Priorities  
**Last Updated**: December 4, 2025

---

## Executive Summary

This document distills the Aaron/Ryan conversation into concrete near-term priorities. It supersedes generic persona-based analytics planning with a focus on **what actually matters** to developers using AI coding tools.

**Core Insight**: The previous analytics docs were too generic. The meeting revealed that developers don't want dashboards—they want **pattern detection that tells them "why" not "what"**.

> *"I don't want a processing layer that just tells me three files were created and three were deleted. I want it to tell me hey, these files were created and deleted in the same PR. Kind of weird."* — Ryan

---

## What Changed After the Meeting

### ❌ Deprioritized (From Previous Docs)

| Feature | Why Deprioritized |
|---------|-------------------|
| Team Pulse Dashboard | "Single-player introspection first" |
| ROI Calculator | Too enterprise-focused, not useful for individual devs |
| Generic Persona Matrix | "The recipe for the thing for us NOT to do" |
| Abstract Growth Metrics | "Competence feelings more important than growth metrics" |
| Executive Reporting | Not near-term focus |

### ✅ Elevated (From the Discussion)

| Feature | Why Prioritized |
|---------|-----------------|
| **Anti-Pattern Detection** | "These are the nuggets I need to extract" |
| **Workflow Quality Signals** | Read-before-edit ratios, context sufficiency |
| **Skills-First Delivery** | Ryan prototyping insights as Claude skills |
| **Journaling Integration** | "Pair human sentiment with coding session metrics" |
| **Semantic "Why" Analysis** | "I care about the WHY. What does that mean semantically?" |

---

## Near-Term Priority Stack

### 🔥 Tier 1: "Can't Live Without It" (Next 2 Weeks)

These are the features that create the **"I need this!"** moment.

#### 1. **Anti-Pattern Detection Engine**

The single most valuable insight from the meeting: detecting wasteful AI patterns.

**Patterns to Detect**:

| Pattern | Signal | What It Means | Action |
|---------|--------|---------------|--------|
| **File Churn** | Files created then deleted in same session/PR | AI tried something that didn't work | Review prompting strategy |
| **Trial-and-Error Loops** | Same bash command tried 3+ times with variations | Thrashing, not progressing | Take a step back, re-think approach |
| **Write-Delete-Write** | File written, deleted, then recreated | Indecision or wrong approach taken | Improve upfront context |
| **Correction Cascades** | Multiple sequential "fix" or "undo" prompts | AI output wasn't right first time | Context may be insufficient |

**Implementation Approach**:

```python
# Pseudo-code for pattern detection
def detect_file_churn(session_traces):
    """
    Detect files created then deleted in same session.
    This signals AI tried something that didn't work.
    """
    created = set()
    deleted = set()
    
    for trace in session_traces:
        if trace.event_type == 'file_create':
            created.add(trace.file_path)
        if trace.event_type == 'file_delete':
            deleted.add(trace.file_path)
    
    churned = created & deleted
    if churned:
        return AntiPattern(
            type="file_churn",
            severity="warning",
            files=churned,
            insight="These files were created and deleted in the same session. This suggests trial-and-error rather than deliberate development.",
            suggestion="Consider providing more context upfront to avoid exploratory file creation."
        )
```

**Output Format** (Skills-consumable JSON):

```json
{
  "anti_patterns": [
    {
      "type": "file_churn",
      "severity": "warning",
      "count": 3,
      "files": ["temp_fix.py", "test_helper.py", "debug.log"],
      "session_id": "abc123",
      "insight": "3 files created and deleted in same session",
      "suggestion": "Consider more upfront planning before creating files"
    },
    {
      "type": "trial_error_loop",
      "severity": "info", 
      "count": 4,
      "commands": ["npm run build", "npm run build --verbose", "npm run build:debug"],
      "session_id": "abc123",
      "insight": "Same command tried 4 times with variations",
      "suggestion": "Check error messages more carefully before retrying"
    }
  ],
  "workflow_quality_score": 0.72,
  "development_discipline": "reactive"
}
```

**Why This First**: Ryan specifically identified these as "the nuggets I need to extract."

---

#### 2. **Workflow Quality Signals**

Positive patterns that indicate good AI-assisted development practices.

**Signals to Track**:

| Signal | Good | Concerning | What It Measures |
|--------|------|------------|------------------|
| **Read-Before-Edit Ratio** | >0.7 | <0.3 | Do you read code before editing? |
| **Context Sufficiency Index** | >0.8 | <0.5 | Do prompts work first time? |
| **Correction Rate** | <0.2 | >0.5 | How often do you need to fix AI output? |
| **Deliberate Cycle Detection** | High | Low | Read → Edit → Improve patterns |

**Workflow Quality Score** (0-1):

```python
def calculate_workflow_quality(session):
    """
    Based on read-before-edit ratio, productive vs wasteful churn.
    Higher is better.
    """
    read_before_edit = session.read_events_before_edits / session.total_edits
    correction_penalty = 1 - (session.correction_prompts / session.total_prompts)
    churn_penalty = 1 - (session.files_deleted / session.files_created)
    
    return weighted_average([
        (read_before_edit, 0.4),
        (correction_penalty, 0.4),
        (churn_penalty, 0.2)
    ])
```

**Output Format**:

```json
{
  "workflow_quality": {
    "score": 0.78,
    "label": "deliberate",
    "components": {
      "read_before_edit_ratio": 0.82,
      "context_sufficiency": 0.71,
      "correction_rate": 0.15
    },
    "positive_patterns": [
      "You read files before editing 82% of the time",
      "Your prompts work first-time 71% of the time"
    ],
    "improvement_areas": [
      "Correction rate of 15% suggests room to improve initial context"
    ]
  }
}
```

---

#### 3. **Session/Day Summary API**

The **API contract** that Ryan's skills will consume.

**Endpoint Design**:

```python
# Query function for skills to consume
def get_daily_summary(date: str) -> DailySummary:
    """
    Returns everything a skill needs to generate insights for a day.
    """
    return DailySummary(
        date=date,
        sessions=[SessionSummary(...)],
        
        # Basic metrics
        total_interactions=47,
        total_sessions=8,
        total_lines_added=156,
        total_lines_removed=42,
        
        # Platform breakdown
        platform_breakdown={"cursor": 32, "claude": 15},
        
        # Model usage (when available)
        model_usage={"claude-sonnet-4.5": 10, "claude-opus-4.1": 5},
        
        # Time patterns
        peak_hours=[14, 15, 16],
        
        # The good stuff - pattern detection
        anti_patterns=[...],
        workflow_quality=WorkflowQuality(score=0.78, ...),
        
        # Workspace activity
        workspace_activity={"bp-telemetry-core": 23, "other": 12}
    )
```

**Why This Matters**: Ryan's skills need a clean API to consume. Without this contract, skills have to query SQLite directly (fragile).

---

### ⭐ Tier 2: High Value (Weeks 2-4)

#### 4. **Journaling Integration**

Ryan emphasized journaling as **high-signal input** that traces can't capture.

**What Journaling Captures**:
- Developer sentiment ("frustrated", "flowing", "stuck")
- Context that traces miss ("waited 2 hours for build")
- Lessons learned ("parables" not exact details)
- Goals and outcomes ("tried to fix X, ended up doing Y")

**Storage Design**:

```sql
CREATE TABLE journaling_entries (
    id INTEGER PRIMARY KEY,
    session_id TEXT,           -- Link to session (optional)
    date TEXT NOT NULL,        -- Calendar date
    created_at TEXT NOT NULL,
    
    -- Structured fields (optional)
    mood TEXT,                 -- frustrated/neutral/flowing
    energy_level INTEGER,      -- 1-5
    accomplishment_score INTEGER, -- 1-5
    
    -- Free-form
    notes TEXT,                -- Developer's own notes
    lessons_learned TEXT,      -- "Parables" - extracted insights
    
    -- Links
    pr_id TEXT,               -- If associated with a PR
    workspace_hash TEXT
);
```

**Journaling-Enhanced Insights**:

```json
{
  "daily_summary": {
    "date": "2025-12-03",
    "trace_insights": {
      "sessions": 8,
      "anti_patterns": [...]
    },
    "journal_context": {
      "mood": "frustrated",
      "notes": "Spent 2 hours debugging Redis connection issue",
      "lesson": "Should have checked Docker containers first"
    },
    "combined_insight": "High file churn (3 files deleted) correlates with frustrated journal entry. The Redis debugging may have caused exploratory code that didn't pan out."
  }
}
```

---

#### 5. **PR-Level Insights**

Ryan wants quick insights at PR boundaries, but **we don't have PR tracking yet**.

**MVP Approach** (Manual PR ID):

```bash
# User provides PR context manually
blueplane pr-insight --pr "feat/analytics-api" --start "2025-12-01 09:00"
```

**What We CAN Provide**:
- All traces within time window
- Sessions during that period
- Anti-patterns detected
- Workflow quality for PR work

**What We CAN'T Provide Yet**:
- Automatic PR detection
- Git commit correlation
- PR-to-traces automatic mapping

**Future Enhancement Path**:
1. Manual PR input (MVP) ← **Start here**
2. Git branch tracking (detect branch name changes)
3. Git hooks for commit correlation
4. GitHub integration (if needed)

---

### 📋 Tier 3: Foundation (Ongoing)

#### 6. **Model Awareness**

Track which models are used per interaction.

**Current State**:
- Cursor: `model_name` field exists (extraction in progress)
- Claude: `message_model` field exists

**Use Cases**:
- "Which model produces better first-time results?"
- "Am I using expensive models for simple tasks?"
- "Error attribution by model"

---

## Derived Metrics Framework

From the meeting, these 17 metrics were identified as the **core framework**:

| # | Metric | Formula | Insight |
|---|--------|---------|---------|
| 1 | **Effort vs Progress** | lines_added / total_tokens | Are you getting output for your input? |
| 2 | **Context Sufficiency** | 1 - (corrections / prompts) | Do prompts work first time? |
| 3 | **AI Utilization Quality** | weighted(agentic + efficiency + success) | Overall AI tool effectiveness |
| 4 | **Predicted Task Difficulty** | based on query rate, switches | Was this easy/moderate/hard? |
| 5 | **AI vs Human Burden** | ai_output_chars / user_input_chars | Who's doing the work? |
| 6 | **Persistence vs Abandonment** | reprompt loops vs topic changes | Sticking with it or giving up? |
| 7 | **Patch Efficiency** | lines_per_prompt, clean vs thrashy | How efficiently are changes made? |
| 8 | **Intent Shift Map** | task type transition count | How focused vs scattered? |
| 9 | **Prompt Quality vs Result** | success rate by prompt length | Better prompts = better results? |
| 10 | **Confidence Trajectory** | improving/declining/mixed | Gaining or losing confidence? |
| 11 | **Stuckness Prediction** | risk based on correction rate, loops | When to take a break? |
| 12 | **Prompt Pacing Profile** | rapid/balanced/deliberate | What's your prompting style? |
| 13 | **Model Strategy** | single/tiered, cost awareness | How do you choose models? |
| 14 | **Peak Performance Windows** | top hours UTC | When are you most effective? |
| 15 | **Session Focus Profile** | short bursts/long deep work/mixed | How do you work? |
| 16 | **Workflow Quality Score** | read-before-edit, churn | Deliberate vs reactive? |
| 17 | **Development Discipline** | careful vs reactive | Planning or firefighting? |

**Implementation Priority**:
- **Phase 1**: #1, #2, #7, #16, #17 (core workflow quality)
- **Phase 2**: #4, #6, #11, #14, #15 (patterns and predictions)
- **Phase 3**: #3, #5, #8, #9, #10, #12, #13 (advanced insights)

---

## Delivery Strategy: Skills-First

From the meeting, the agreed approach is **skills-first prototyping**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Ryan's Skills Layer (Rapid Prototyping)                            │
│  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐ │
│  │ Long-Form Report  │  │ PR Quick Insight  │  │ Anti-Pattern    │ │
│  │ Skill             │  │ Skill             │  │ Alert Skill     │ │
│  └────────┬──────────┘  └────────┬──────────┘  └────────┬────────┘ │
│           │                      │                      │          │
│           └──────────────────────┼──────────────────────┘          │
│                                  │                                  │
│                          ┌───────▼───────┐                         │
│                          │  Analytics API │                         │
│                          │  (JSON output) │                         │
│                          └───────┬───────┘                         │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│  Aaron's Analytics Layer (Production Infrastructure)                │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Pattern Detection Engine                                      │ │
│  │  • Anti-pattern detection                                      │ │
│  │  • Workflow quality signals                                    │ │
│  │  • Session/Day aggregation                                     │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  DuckDB Analytics + SQLite Raw Traces                         │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**Why This Works**:
- Ryan can prototype insight formats quickly with skills
- Aaron builds production-grade pattern detection
- Skills validate what's valuable before we build CLI/dashboard
- Fast iteration loop

---

## API Contract: Skills ↔ Analytics

### Request: Get Daily Summary

```json
{
  "method": "get_daily_summary",
  "params": {
    "date": "2025-12-03",
    "include_traces": false,
    "include_anti_patterns": true,
    "include_workflow_quality": true
  }
}
```

### Response: Daily Summary

```json
{
  "date": "2025-12-03",
  "meta": {
    "generated_at": "2025-12-04T10:30:00Z",
    "data_complete": true
  },
  
  "activity": {
    "total_sessions": 8,
    "total_interactions": 47,
    "total_duration_minutes": 234,
    "platform_breakdown": {
      "cursor": {"sessions": 5, "interactions": 32},
      "claude": {"sessions": 3, "interactions": 15}
    }
  },
  
  "code_output": {
    "lines_added": 156,
    "lines_removed": 42,
    "net_change": 114,
    "by_workspace": {
      "bp-telemetry-core": {"added": 120, "removed": 30}
    }
  },
  
  "patterns": {
    "anti_patterns": [
      {
        "type": "file_churn",
        "severity": "warning",
        "count": 3,
        "details": "3 files created and deleted in same session",
        "sessions": ["session_abc"]
      }
    ],
    "workflow_quality": {
      "score": 0.72,
      "label": "mostly_deliberate",
      "read_before_edit_ratio": 0.78,
      "context_sufficiency": 0.68,
      "correction_rate": 0.22
    }
  },
  
  "time_patterns": {
    "peak_hours": [14, 15, 16],
    "total_active_hours": 6.5
  },
  
  "models_used": {
    "claude-sonnet-4.5": 8,
    "claude-opus-4.1": 2
  }
}
```

### Request: Get Session Details

```json
{
  "method": "get_session",
  "params": {
    "session_id": "abc123",
    "include_traces": true,
    "include_anti_patterns": true
  }
}
```

### Request: Get PR Summary (MVP - Manual Input)

```json
{
  "method": "get_pr_summary",
  "params": {
    "pr_identifier": "feat/analytics-api",
    "start_time": "2025-12-01T09:00:00Z",
    "end_time": "2025-12-03T17:00:00Z",
    "workspace_hash": "abc123"
  }
}
```

---

## Implementation Roadmap

### Week 1-2: Foundation

- [ ] **Anti-pattern detection** for file churn
- [ ] **Anti-pattern detection** for trial-error loops
- [ ] **Workflow quality score** calculation
- [ ] **Daily summary API** endpoint
- [ ] **Session summary API** endpoint

### Week 3-4: Integration

- [ ] **Skills integration** - Ryan tests with his skills
- [ ] **Journaling table** schema and storage
- [ ] **PR summary MVP** (manual PR input)
- [ ] **CLI commands** for anti-patterns

### Week 5-6: Refinement

- [ ] **Iterate on API** based on skills feedback
- [ ] **Additional anti-patterns** (correction cascades, etc.)
- [ ] **Journaling-trace correlation**
- [ ] **Git branch tracking** (basic)

---

## Success Criteria

### What "Done" Looks Like for Near-Term

1. **Ryan can run a skill** that calls the analytics API and gets useful pattern detection
2. **Anti-patterns are surfaced** that Ryan says "I didn't know that, but now I can't unsee it"
3. **Workflow quality score** correlates with Ryan's subjective experience
4. **Daily summary** is useful enough that Ryan checks it regularly

### Validation Questions

- "Did you know this was happening?" → Anti-pattern value
- "Is this actionable?" → Pattern → behavior change
- "Would you miss this if it was gone?" → Stickiness

---

## Key Quotes from Meeting

> *"I care about the WHY. Like, why did that happen? Semantically, what does that mean?"* — Aaron

> *"These are the nuggets that I need to extract from this."* — Ryan (on anti-patterns)

> *"We're not just trying to make a better analytics tool. I think there's something else that I can't even articulate yet."* — Aaron

> *"Competence feelings more important than growth metrics."* — Meeting notes

> *"What excites users so much they can't live without it?"* — Key product question

---

## Related Documents

- [Meeting Notes: Ryan/Aaron 1:1](./ryan-aaron-2025-12-03.md) - Full meeting transcript
- [Meeting Prep](./ryan-1on1-prep-2025-12-03.md) - Pre-meeting analysis
- Previous analytics docs (superseded for near-term priorities):
  - `docs/analytics/ANALYTICS_USER_PERSONAS.md`
  - `docs/analytics/ANALYTICS_FEATURE_ROADMAP.md`
  - `docs/analytics/ANALYTICS_WOW_FACTOR.md`

---

*This document represents the focused near-term priorities derived from the Aaron/Ryan strategic discussion. It intentionally narrows scope to deliver maximum value quickly.*
