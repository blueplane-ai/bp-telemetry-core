# Telemetry Insights Skill

A Claude skill for analyzing AI-assisted coding session telemetry to extract actionable insights about usage patterns, token efficiency, and workflow optimization.

## What is This?

This is a [Claude Code](https://claude.com/claude-code) skill that teaches Claude how to analyze telemetry data captured by Blueplane Telemetry Core. It transforms raw session data into structured metrics, derived insights, and narrative summaries.

## What Does It Provide?

**The skill enables Claude to:**
- Extract 8 categories of raw metrics from telemetry data
- Compute 11 derived analytical insights
- Generate comprehensive session summaries
- Provide actionable recommendations for efficiency improvement

**Analysis Categories:**
1. **Flow & Structure** - Session duration, phases, context switches
2. **Prompting Patterns** - Length, complexity, reprompt loops
3. **Commands & Actions** - Capabilities invoked, success rates
4. **Skill Usage** - Agentic vs standard mode distribution
5. **Patch Behavior** - Lines added/removed, edit patterns
6. **Task & Outcome** - Inferred task types, completion signals
7. **Behavioral Signals** - Delegation style, confidence patterns
8. **Token Economics** - Input/output tokens, cost estimates

## Analysis Scope

The skill supports two analysis modes:

### Default: Current Session
Analyzes only the active conversation (identified by `composer_id`). Use this for real-time feedback on the current coding session.

### Optional: Historical Time Period
Analyzes a specified time range when the user requests it:
- "this week" / "last 7 days"
- "today" / "last 24 hours"
- "yesterday"
- "last month"

| User Request | Analysis Scope |
|--------------|----------------|
| "How efficient am I?" | Current session |
| "Analyze this conversation" | Current session |
| "How efficient was I this week?" | Last 7 days |
| "Show me yesterday's stats" | Previous 24 hours |

## Prerequisites

1. Blueplane Telemetry Core is installed and running
2. Telemetry database exists at `~/.blueplane/telemetry.db`
3. Session data (bubbles/conversations) has been captured

## Usage Examples

Once the skill is loaded, Claude will respond to queries like:

**Current Session (Default):**
```
How efficient am I being?
```
```
Analyze this conversation
```
```
What's my token efficiency look like?
```

**Historical Analysis:**
```
How efficient was I this week?
```
```
Analyze my prompting patterns from the last 7 days
```
```
Show me my usage stats for today
```

## Output Format

The skill produces a structured report with three sections:

### 1. RAW_METRICS
JSON object containing all extracted metrics organized by category (A through H), including `analysis_scope` to indicate whether it's current session or a time period.

### 2. DERIVED_INSIGHTS
JSON object with 11 computed analytical insights:
- Effort vs Progress Score
- Context Sufficiency Index
- AI Utilization Quality Score
- Predicted Task Difficulty
- AI vs Human Burden Ratio
- Persistence vs Abandonment Pattern
- Patch Efficiency Curve
- Intent Shift Map
- Prompt Quality vs Result Correlation
- Confidence Trajectory
- Stuckness Prediction

### 3. SESSION_SUMMARY
A 6-10 sentence narrative describing the session flow, patterns, and recommendations. The first sentence always clarifies the analysis scope.

## Integration with Blueplane

This skill is designed to work with data captured by the Blueplane Telemetry Core system:

- **Cursor**: Data captured from `cursor_raw_traces` table
- **Claude Code**: Data captured from `claude_raw_traces` table

The skill queries the SQLite database directly and decompresses zlib-encoded event payloads.

## How Session Identification Works

For **current session** analysis, the skill:
1. Finds the most recent `composer_id` from the `item_key` field
2. `item_key` format: `bubbleId:{composerId}:{bubbleId}`
3. Queries all bubbles for that composer (the current conversation)
4. Uses first/last bubble timestamps as session boundaries

For **historical** analysis, the skill:
1. Calculates the start datetime based on user's request
2. Queries all bubbles since that datetime
3. Aggregates across all conversations in that period

## Files

```
telemetry-insights/
├── README.md       # This file - overview and usage
└── SKILL.md        # Main skill definition with full methodology
```

## License

Same as Blueplane Telemetry Core - AGPL-3.0-only.
