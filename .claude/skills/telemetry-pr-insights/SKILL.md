---
name: telemetry-pr-insights
description: Concise, PR-friendly telemetry reports scoped to current branch lifetime. For CI/automation.
---

# Telemetry PR Insights

## Scope

### Default: Branch Lifetime

1. Find merge-base: `git merge-base HEAD origin/main`
2. Get timestamp: `git show -s --format=%cI <merge_base>`
3. Query events where `timestamp >= branch_start` for current workspace

### Fallback: Last 7 Days

If Git unavailable or merge-base fails.

---

## Data Access (Combined Platforms)

**Database**: `~/.blueplane/telemetry.db`

- **Claude Code** (`claude_raw_traces`):
  - Filter by `cwd LIKE '/path/to/workspace%'`
  - Tokens: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`
  - Model: `message_model`, Role: `message_role`, Branch: `git_branch`

- **Cursor** (`cursor_sessions` + `cursor_raw_traces`):
  - Get `composer_id`s from `cursor_sessions` for the workspace (`workspace_path LIKE '/path/to/workspace%'`)
  - Bubbles: filter by composer_id extracted from `item_key = "bubbleId:{composerId}:{bubbleId}"`
  - Tokens: `token_count_up_until_here` (cumulative only; use for activity, not precise totals)
  - Message type: `message_type` (often NULL; use heuristics)
  - Model: **not stored** (always treated as unknown)

For full schema details, see the **Data Access / Schema Reference** section in `telemetry-insights/SKILL.md`. This skill uses the same combined Cursor + Claude access patterns, but scoped to the PR branch window.

---

## Metrics (Lean Subset)

```json
{
  "window": {
    "analysis_scope": "branch_pr|time_period",
    "branch_name": "...",
    "branch_start": "YYYY-MM-DD",
    "days_active": N
  },
  "activity": {
    "total_prompts": N,
    "total_responses": N,
    "breakdown": {
      "claude_code": {"prompts": N, "responses": N},
      "cursor": {"prompts": N, "responses": N}
    },
    "active_days": N
  },
  "tokens": {
    "note": "Claude Code only - Cursor does not provide per-message token counts",
    "total_input": N,
    "total_output": N,
    "ratio": X.XX
  },
  "models": {
    "note": "Claude Code only - Cursor does not persist model names",
    "breakdown": {"model-name": N}
  },
  "daily": {
    "YYYY-MM-DD": {"input": N, "output": N, "prompts": N}
  }
}
```

---

## Derived Insights (3-5 max)

- **Efficiency**: token ratio, cache usage, assessment (Claude Code only)
- **Activity Pattern**: steady/bursty/spiky, platform distribution
- **Model Strategy**: dominant model, cost awareness (Claude Code only)
- **Platform Usage**: Claude Code vs Cursor breakdown, workflow insights

---

## Output Format

### Executive Summary (2-4 sentences)

**First sentence MUST state time frame**:
- "Since this branch diverged from `main` on YYYY-MM-DD, ..."
- "Over the last 7 days, ..."

Then: activity level, efficiency, standout patterns.

### Key Metrics (compact)

**Activity** (combined across platforms)
- Total prompts / responses
- Breakdown by platform (Claude Code vs Cursor)
- Active days

**Tokens** (Claude Code only)
- Input/output tokens and ratio
- Per-day snapshot (3-5 days max)

**Models** (Claude Code only)
- Model distribution
- Strategic usage patterns

### Recommendations (3-5 bullets)

Pragmatic, low-risk suggestions. No personal commentary.

---

## Privacy

- Never include raw code content
- No verbatim prompts/responses
- Focus on aggregated metrics only
