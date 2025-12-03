---
name: telemetry-insights
description: Analyze AI coding session telemetry for usage patterns, token efficiency, and workflow optimization. Supports current session or historical time periods.
---

# Telemetry Insights

## Scope Detection

| User Request | Scope |
|--------------|-------|
| "How efficient am I?" | Current session |
| "Analyze this conversation" | Current session |
| "this week" / "last 7 days" | 7 days |
| "today" / "last 24 hours" | 1 day |
| "last month" | 30 days |
| "productivity" / "project" / "traces" | 7 days (default historical) |

---

## Data Access

**Database**: `~/.blueplane/telemetry.db`

### Schema Reference

**Claude Code** (`claude_raw_traces` table):
- Workspace filter: `WHERE cwd LIKE '/path/to/workspace%'` (NOT workspace_hash)
- Token fields: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`
- Model field: `message_model` (e.g., "claude-sonnet-4-5-20250929")
- Role field: `message_role` ('user' | 'assistant')
- Branch field: `git_branch`

**Cursor** (`cursor_sessions` + `cursor_raw_traces` tables):
- Session lookup: `SELECT id, workspace_hash FROM cursor_sessions WHERE workspace_path LIKE '/path/to/workspace%'`
  - `cursor_sessions.id` IS the `composer_id` (same value)
- Bubble filtering: Extract composer_id from `item_key`: `"bubbleId:{composerId}:{bubbleId}"`
  - Bubbles have empty `workspace_hash` in global storage
  - Must join via composer_id extracted from item_key
- Token field: `token_count_up_until_here` (cumulative context, NOT per-message tokens)
- Message type: `message_type` (0=user, 1=assistant, often NULL - use heuristics)
- Model: ❌ Not stored in database

## Raw Metrics

### A. Flow & Structure
- `analysis_scope`, `session_duration`, `active_exchanges`, `total_ai_responses`
- `context_switch_count`, `prompt_timing_buckets`, `session_summaries`

### B. Prompting Patterns
- `prompt_count`, `average_prompt_length`, `median_prompt_length`
- `prompt_complexity_score` (low/medium/high), `reprompt_loop_count`

### C. Token Economics
- `total_input_tokens`, `total_output_tokens`, `input_output_ratio`
- `estimated_cost_usd`: `(input/1M × $3) + (output/1M × $15)`

### D. Patch Behavior
- `patch_count`, `total_lines_added`, `total_lines_removed`, `add_remove_ratio`

### E. Behavioral Signals
- `delegation_style`: high-level vs step-by-step indicators
- `positive_feedback` / `negative_feedback` counts

### F. Capability Usage
- `capabilities_invoked`, `agentic_mode_usage`

### G. Model Strategy (Claude Code only)
- `per_model_usage`, `per_model_tokens`, `dominant_model`

### H. Temporal Productivity
- `tokens_per_day`, `tokens_per_hour_utc`, `prompts_per_minute_by_session`

---

## Derived Insights

1. **Effort_vs_Progress_Score** (0-1): lines_added / total_tokens
2. **Context_Sufficiency_Index** (0-1): 1 - (corrections / prompts)
3. **AI_Utilization_Quality_Score** (0-1): weighted agentic + efficiency + success
4. **Predicted_Task_Difficulty**: easy/moderate/hard based on query rate, switches
5. **AI_vs_Human_Burden_Ratio**: ai_output_chars / user_input_chars
6. **Persistence_vs_Abandonment**: reprompt loops vs topic abandonment
7. **Patch_Efficiency_Curve**: clean (ratio>3) vs thrashy, lines_per_prompt
8. **Intent_Shift_Map**: task type transitions count
9. **Prompt_Quality_vs_Result**: success rate by prompt length
10. **Confidence_Trajectory**: improving/declining/mixed
11. **Stuckness_Prediction**: risk_level based on correction rate, loops
12. **Prompt_Pacing_Profile**: rapid_iterator/balanced/deliberate
13. **Model_Strategy_Assessment**: single_model/tiered_models, cost_awareness
14. **Peak_Performance_Windows**: top hours UTC
15. **Session_Focus_Profile**: short_bursts/long_deep_work/mixed

---

## Output Format

```
1. RAW_METRICS: { JSON with metrics A-H above }

2. DERIVED_INSIGHTS: { JSON with insights 1-15 above }

3. SESSION_SUMMARY: 6-10 sentences covering:
   - Analysis scope (first sentence)
   - Duration and activity level
   - Workflow patterns
   - Token efficiency
   - Key recommendations
```

---

## Interpretation Guidelines

| Input:Output Ratio | Assessment |
|--------------------|------------|
| < 10:1 | Excellent |
| 10-25:1 | Normal |
| 25-50:1 | Context-heavy |
| > 50:1 | Inefficient |

### Recommendation Triggers

| Signal | Recommendation |
|--------|----------------|
| 0% agentic usage | Enable agentic mode for multi-file tasks |
| >50:1 ratio frequently | Start new conversations for simple queries |
| High negative feedback | Provide more context upfront |
| High context switches | Consider task batching |

---

## Limitations

- Model info unavailable for Cursor (platform limitation)
- Token counts depend on capture completeness
- Task type inference is keyword-based (heuristic)
- Cost estimates based on Claude 3.5 Sonnet pricing
