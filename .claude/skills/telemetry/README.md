# Telemetry Skill (Parent)

Routes between telemetry sub-skills based on context:

- **`telemetry-pr-insights`** – PR/CI default: concise, branch-scoped reports
- **`telemetry-insights`** – Interactive: deep-dive analysis for user questions

## Routing Rules

| Context | Use |
|---------|-----|
| PR review, CI automation | `telemetry-pr-insights` |
| User asks about efficiency, usage, productivity | `telemetry-insights` |

See `SKILL.md` for detailed routing heuristics.
