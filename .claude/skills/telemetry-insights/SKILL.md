---
name: telemetry-insights
description: Analyze AI coding session telemetry to extract raw metrics, derived insights, and session summaries. Supports current session analysis (default) or historical time periods. Use when user wants to understand their AI usage patterns, token efficiency, prompting behavior, or workflow optimization opportunities.
---

# Telemetry Insights Analyst

## Overview

This skill transforms raw telemetry data from AI-assisted coding sessions (Cursor, Claude Code) into actionable insights. It extracts structured metrics, derives higher-order analytical conclusions, and produces narrative summaries.

## When to Use This Skill

### Use this skill when:
- User asks about their AI usage patterns or efficiency
- User wants to understand token consumption
- User requests analysis of their prompting behavior
- User wants workflow optimization recommendations
- User asks "how efficient am I?" or similar questions

### Prerequisites:
- Blueplane telemetry database exists at `~/.blueplane/telemetry.db`
- Database contains `cursor_raw_traces` and/or `claude_raw_traces` tables
- Bubble events (conversations) have been captured

---

## Analysis Scope

### Default: Current Session

By default, analyze only the **current chat session** (the active conversation).

### Optional: Historical Time Period

If the user specifies a time range, analyze that period instead:
- "this week" / "last 7 days"
- "today"
- "yesterday"
- "last 24 hours"
- "last month"
- Custom date range

### Scope Detection

| User Request | Analysis Scope |
|--------------|----------------|
| "How efficient am I?" | Current session |
| "Analyze this conversation" | Current session |
| "How's my token usage?" | Current session |
| "How efficient was I this week?" | Last 7 days |
| "Analyze my usage from last month" | Last 30 days |
| "Show me yesterday's stats" | Previous 24 hours |

---

## Analysis Protocol

### Step 1: Determine Analysis Scope

```python
import sqlite3, zlib, json
from datetime import datetime, timedelta

conn = sqlite3.connect('~/.blueplane/telemetry.db')

# Determine scope based on user request
def get_analysis_scope(user_request):
    """
    Returns: ('current_session', None) or ('time_period', start_datetime)
    """
    request_lower = user_request.lower()
    
    # Time period indicators
    if any(term in request_lower for term in ['week', '7 days', 'past week']):
        return ('time_period', datetime.now() - timedelta(days=7))
    elif any(term in request_lower for term in ['today', '24 hours']):
        return ('time_period', datetime.now() - timedelta(days=1))
    elif 'yesterday' in request_lower:
        return ('time_period', datetime.now() - timedelta(days=2))
    elif any(term in request_lower for term in ['month', '30 days']):
        return ('time_period', datetime.now() - timedelta(days=30))
    else:
        # Default: current session
        return ('current_session', None)
```

### Step 2a: Current Session Extraction (Default)

When analyzing the current session, identify by `composer_id`:

```python
def get_current_session_events(conn):
    """
    Get all events from the current conversation.
    Sessions are identified by composer_id extracted from item_key.
    item_key format: bubbleId:{composerId}:{bubbleId}
    """
    # Find the most recent composer_id
    row = conn.execute('''
        SELECT item_key, timestamp 
        FROM cursor_raw_traces 
        WHERE event_type='bubble' AND item_key LIKE 'bubbleId:%'
        ORDER BY timestamp DESC
        LIMIT 1
    ''').fetchone()
    
    if not row:
        return [], None, None
    
    # Extract composer_id from item_key
    parts = row[0].split(':')
    composer_id = parts[1] if len(parts) >= 2 else None
    
    # Get all bubbles for this composer
    rows = conn.execute('''
        SELECT event_data, timestamp, item_key 
        FROM cursor_raw_traces 
        WHERE event_type='bubble' 
        AND item_key LIKE ?
        ORDER BY timestamp
    ''', (f'bubbleId:{composer_id}:%',)).fetchall()
    
    # Parse events
    events = []
    for row in rows:
        try:
            data = json.loads(zlib.decompress(row[0]))
            events.append({'data': data, 'timestamp': row[1]})
        except:
            pass
    
    # Session boundaries
    session_start = events[0]['timestamp'] if events else None
    session_end = events[-1]['timestamp'] if events else None
    
    return events, session_start, session_end
```

### Step 2b: Historical Time Period Extraction

When analyzing a time period:

```python
def get_time_period_events(conn, start_datetime):
    """
    Get all events from a specified time period.
    """
    period_start = start_datetime.isoformat()
    
    rows = conn.execute('''
        SELECT event_data, timestamp, event_type 
        FROM cursor_raw_traces 
        WHERE timestamp > ? AND event_type = 'bubble'
        ORDER BY timestamp
    ''', (period_start,)).fetchall()
    
    # Parse events
    events = []
    for row in rows:
        try:
            data = json.loads(zlib.decompress(row[0]))
            events.append({'data': data, 'timestamp': row[1]})
        except:
            pass
    
    session_start = events[0]['timestamp'] if events else None
    session_end = events[-1]['timestamp'] if events else None
    
    return events, session_start, session_end
```

### Step 3: Classify Messages

Separate user prompts from AI responses:

```python
# type=1 is user message, type=2 is AI response
user_msgs = [e for e in events if e['data'].get('type') == 1]
ai_msgs = [e for e in events if e['data'].get('type') == 2]
```

---

## Raw Metrics Extraction

### A. Flow & Structure Metrics

| Metric | Source | Calculation |
|--------|--------|-------------|
| analysis_scope | User request | "current_session" or "time_period: X days" |
| session_duration | `min(timestamp)` to `max(timestamp)` | Time span of events |
| active_exchanges | Count of `user_msgs` | Number of user prompts |
| total_ai_responses | Count of `ai_msgs` | Number of AI responses |
| context_switch_count | Task type transitions | Count changes in inferred task type |

**Task type inference keywords:**
```python
task_keywords = {
    'debug': ['error', 'bug', 'fix', 'issue', 'broken', 'fail'],
    'feature': ['add', 'create', 'implement', 'build', 'new'],
    'query': ['what', 'how', 'why', 'where', 'show', 'check'],
    'setup': ['install', 'setup', 'configure', 'init'],
    'test': ['test', 'spec', 'coverage', 'assert'],
    'refactor': ['refactor', 'clean', 'reorganize', 'improve'],
    'docs': ['document', 'readme', 'comment', 'explain']
}
```

### B. Prompting Patterns Metrics

| Metric | Source | Calculation |
|--------|--------|-------------|
| prompt_count | `len(user_msgs)` | Total user messages |
| average_prompt_length | `text` field | Mean character count |
| median_prompt_length | `text` field | Median character count |
| prompt_complexity_score | Length buckets | low(<100), medium(100-500), high(>500) |
| reprompt_loop_count | Text analysis | Count of "again", "retry", "still" patterns |

### C. Token Economics Metrics

| Metric | Source | Calculation |
|--------|--------|-------------|
| total_input_tokens | `tokenCount.inputTokens` | Sum across AI responses |
| total_output_tokens | `tokenCount.outputTokens` | Sum across AI responses |
| input_output_ratio | Computed | `input / output` |
| estimated_cost_usd | Computed | `(input/1M * $3) + (output/1M * $15)` |

**Token extraction:**
```python
for e in ai_msgs:
    tokens = e['data'].get('tokenCount', {})
    input_tokens += tokens.get('inputTokens', 0)
    output_tokens += tokens.get('outputTokens', 0)
```

### D. Patch/Edit Behavior Metrics

| Metric | Source | Calculation |
|--------|--------|-------------|
| patch_count | Composer events | Count where lines_added > 0 or lines_removed > 0 |
| total_lines_added | `totalLinesAdded` | Sum from composer events |
| total_lines_removed | `totalLinesRemoved` | Sum from composer events |
| add_remove_ratio | Computed | `lines_added / lines_removed` |

### E. Behavioral Signal Metrics

**Delegation style detection:**
```python
high_level_indicators = ['please', 'can you', 'could you', 'help me', 'i want']
step_by_step_indicators = ['first', 'then', 'next', 'step', 'after that']
```

**Confidence signals:**
```python
positive_signals = ['great', 'perfect', 'awesome', 'excellent', 'thanks', 'works']
negative_signals = ['wrong', 'not what', 'doesn\'t work', 'failed', 'try again']
```

### F. Capability Usage Metrics

| Metric | Source | Calculation |
|--------|--------|-------------|
| capabilities_invoked | `capabilitiesRan` field | Count and list |
| agentic_mode_usage | `isAgentic` field | Count where true |

---

## Derived Insights Generation

### 1. Effort_vs_Progress_Score (0-1)

```
score = (lines_added / total_tokens) * normalization_factor
```
- **0.8-1.0**: Excellent efficiency
- **0.5-0.8**: Moderate efficiency  
- **<0.5**: Room for improvement

### 2. Context_Sufficiency_Index (0-1)

```
score = 1 - (context_correction_prompts / total_prompts)
```
Context corrections detected by: "again", "still", "actually", "no,", "wrong"

### 3. AI_Utilization_Quality_Score (0-1)

```
score = (agentic_usage * 0.3) + (efficiency_ratio * 0.4) + (success_rate * 0.3)
```
Penalizes heavy context loading without proportional output.

### 4. Predicted_Task_Difficulty

Based on early signals:
- **Hard**: High query rate (>40%), many context switches, mixed completion signals
- **Moderate**: Balanced query/feature ratio, some context switches
- **Easy**: Low query rate, linear progression, clear completion

### 5. AI_vs_Human_Burden_Ratio

```
ratio = total_ai_output_chars / total_user_input_chars
```
Higher ratio = AI doing more of the work.

### 6. Persistence_vs_Abandonment_Pattern

Analyze:
- Reprompt loops (persistence)
- Stuck indicators followed by continuation (persistence)
- Topic abandonment without resolution (abandonment)

### 7. Patch_Efficiency_Curve

```
assessment = "clean" if add_remove_ratio > 3 else "thrashy"
lines_per_prompt = total_lines_added / prompt_count
```

### 8. Intent_Shift_Map

Track task type transitions:
```
query → feature → debug → query (natural cycle)
```
High shift count = exploratory session.

### 9. Prompt_Quality_vs_Result_Correlation

Compare success rates:
- Short prompts (<200 chars) success rate
- Long prompts (>=200 chars) success rate
- Success = positive feedback in next user message

### 10. Confidence_Trajectory

```
pattern = "improving" if positive_trend else "declining" if negative_trend else "mixed"
negative_to_positive_ratio = negative_signals / positive_signals
```

### 11. Stuckness_Prediction

Early warning signals:
- Context correction rate > 20%
- Reprompt loops > 3 in sequence
- Same task type repeated > 5 times without resolution

---

## Output Format

### Required Structure

```
1. RAW_METRICS: { ...JSON object with all extracted metrics... }

2. DERIVED_INSIGHTS: { ...JSON object with all computed insights... }

3. SESSION_SUMMARY: A concise 6-10 sentence narrative describing:
   - Analysis scope (current session or time period)
   - Session duration and activity level
   - Primary workflow patterns
   - Prompting style characteristics
   - Token efficiency assessment
   - Code output productivity
   - Key recommendations
```

### JSON Schema for RAW_METRICS

```json
{
  "A_Flow_Structure": {
    "analysis_scope": "current_session | time_period",
    "time_range": "string (e.g., 'current conversation' or 'last 7 days')",
    "session_duration": "string",
    "active_exchanges": "number",
    "total_ai_responses": "number",
    "session_phases": { "phase_name": "percentage" },
    "context_switch_count": "number"
  },
  "B_Prompting_Patterns": {
    "prompt_count": "number",
    "average_prompt_length": "number",
    "median_prompt_length": "number",
    "prompt_complexity_score": { "low": "n", "medium": "n", "high": "n" },
    "reprompt_loop_count": "number"
  },
  "C_Commands_Actions": {
    "capabilities_invoked_total": "number",
    "top_capabilities": ["array of {name, count}"]
  },
  "D_Skill_Usage": {
    "agentic_mode_usage": "number",
    "standard_mode_usage": "number"
  },
  "E_Patch_Behavior": {
    "patch_count": "number",
    "total_lines_added": "number",
    "total_lines_removed": "number",
    "add_remove_ratio": "string"
  },
  "F_Task_Outcome": {
    "inferred_task_types": { "task": "count" },
    "session_outcome": "success|partial_success|stuck",
    "completion_indicators": "number",
    "stuck_indicators": "number"
  },
  "G_Behavioral_Signals": {
    "user_understanding_level": "low|medium|high",
    "user_confidence_in_ai": "low|medium|high",
    "delegation_style": "high-level|step-by-step|balanced",
    "positive_feedback": "number",
    "negative_feedback": "number"
  },
  "H_Token_Economics": {
    "total_input_tokens": "number",
    "total_output_tokens": "number",
    "input_output_ratio": "string",
    "estimated_cost_usd": "number"
  }
}
```

### JSON Schema for DERIVED_INSIGHTS

```json
{
  "1_Effort_vs_Progress_Score": { "score": "0-1", "assessment": "string" },
  "2_Context_Sufficiency_Index": { "score": "0-1", "issues_detected": "number" },
  "3_AI_Utilization_Quality_Score": { "score": "0-1", "recommendations": ["array"] },
  "4_Predicted_Task_Difficulty": { "assessment": "easy|moderate|hard" },
  "5_AI_vs_Human_Burden_Ratio": { "ratio": "string" },
  "6_Persistence_vs_Abandonment": { "pattern": "persistent|abandoning|mixed" },
  "7_Patch_Efficiency_Curve": { "assessment": "clean|thrashy", "lines_per_prompt": "number" },
  "8_Intent_Shift_Map": { "shifts": "number", "pattern": "string" },
  "9_Prompt_Quality_vs_Result": { "finding": "string" },
  "10_Confidence_Trajectory": { "pattern": "improving|declining|mixed" },
  "11_Stuckness_Prediction": { "risk_level": "low|medium|high", "early_warnings": ["array"] }
}
```

---

## Execution Checklist

When performing telemetry analysis:

```
Analysis Checklist:
- [ ] Verify telemetry database exists (~/.blueplane/telemetry.db)
- [ ] Determine analysis scope from user request (current session vs time period)
- [ ] If current session: Find composer_id from most recent bubble's item_key
- [ ] If time period: Calculate start datetime from user's request
- [ ] Query bubble events for the determined scope
- [ ] Determine session boundaries (first and last timestamps)
- [ ] Separate user messages (type=1) from AI responses (type=2)
- [ ] Extract token counts from AI responses
- [ ] Analyze prompt lengths and complexity
- [ ] Detect task types and context switches
- [ ] Calculate behavioral signals
- [ ] Compute all derived insights
- [ ] Generate JSON output for RAW_METRICS (include analysis_scope)
- [ ] Generate JSON output for DERIVED_INSIGHTS
- [ ] Write SESSION_SUMMARY narrative (mention scope in first sentence)
```

---

## Interpretation Guidelines

### Token Efficiency Thresholds

| Input:Output Ratio | Assessment | Action |
|--------------------|------------|--------|
| < 10:1 | Excellent | Maintain current approach |
| 10-25:1 | Normal | Acceptable for complex codebases |
| 25-50:1 | Context-heavy | Consider conversation resets |
| > 50:1 | Inefficient | Start new conversations for simple queries |

### Cost Estimation (Claude 3.5 Sonnet)

```
Input cost = (input_tokens / 1,000,000) × $3.00
Output cost = (output_tokens / 1,000,000) × $15.00
Total cost = input_cost + output_cost
```

### Recommendation Triggers

| Signal | Recommendation |
|--------|----------------|
| 0% agentic usage | "Enable agentic mode for multi-file tasks" |
| >50:1 ratio on >40% of exchanges | "Start new conversations for simple queries" |
| High negative feedback | "Provide more context upfront in prompts" |
| High context switch count | "Natural exploratory workflow - consider task batching" |
| Low lines per prompt | "Prompts may need more specificity" |

---

## Example Usage

### Current Session (Default)

**User**: "How efficient am I being in this conversation?"

**Agent**: Analyzes current session by composer_id, generates report.

### Historical Period

**User**: "How efficient was I this week?"

**Agent**: Analyzes last 7 days of data, generates report.

### Specific Comparison

**User**: "Compare my efficiency today vs this conversation"

**Agent**: Runs both analyses and compares metrics.

---

## Limitations

- Token counts depend on capture completeness
- Latency metrics not captured (sub-second assumed)
- Success correlation based on text pattern matching (heuristic)
- Task type inference is keyword-based (may misclassify)
- Cost estimates based on Claude 3.5 Sonnet pricing (may vary)
- Historical analysis requires telemetry server to have been running
