# Telemetry Insights Skill

Interactive analysis of AI-assisted coding telemetry. Extracts metrics, derives insights, and generates narrative summaries.

## When to Use

User asks about:
- AI usage patterns or efficiency
- Token consumption
- Prompting behavior
- Workflow optimization

## Scope

| Request | Scope |
|---------|-------|
| "How efficient am I?" | Current session |
| "Analyze this conversation" | Current session |
| "How efficient was I this week?" | Last 7 days |
| "Analyze my productivity" | Last 7-30 days |

## Output

1. **RAW_METRICS** – JSON with flow, prompting, tokens, patches, behavioral signals
2. **DERIVED_INSIGHTS** – JSON with efficiency scores, patterns, predictions
3. **SESSION_SUMMARY** – 6-10 sentence narrative with recommendations

## Prerequisites

- Blueplane server running
- Database at `~/.blueplane/telemetry.db`
- Captured session data

See `SKILL.md` for full methodology.
