# Telemetry PR Insights Skill

Concise, PR-friendly telemetry reports. Designed for CI/automation.

## When to Use

- CI job posting telemetry comment on PR
- Quick view of AI usage during PR review
- Compact report (not deep-dive)

For interactive questions, use `telemetry-insights` instead.

## Scope

**Default**: Branch lifetime (merge-base to now) for the current workspace.

**Fallback**: Last 7 days if Git info unavailable.

## Output

1. **Executive Summary** (2-4 sentences) – time frame, activity, efficiency
2. **Key Metrics** – prompts, tokens, per-day breakdown
3. **Recommendations** (3-5 bullets)

See `SKILL.md` for full methodology.
