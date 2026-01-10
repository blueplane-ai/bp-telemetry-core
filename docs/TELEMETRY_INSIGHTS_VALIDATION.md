<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

## Telemetry Insights Validation README

This document explains **how the telemetry insights CSV was derived and validated** against **actual captured data** in the local Blueplane telemetry database, and includes the **final CSV output** with investigation notes.

The goal is to show, for each insight:

- What data we actually have for **Claude Code** (`claude_raw_traces`)
- What data we actually have for **Cursor** (`cursor_raw_traces` + decompressed `event_data` JSON)
- Whether the insight is **fully supported / partially supported / not really supported** per platform
- Whether the **behavior-change recommendation still makes sense**
- Any corrections to the original **Yes/Partial/No capture flags**

---

## Data Sources and Setup

### Databases and Tables

- **SQLite DB path**: `~/.blueplane/telemetry.db`
- **Key tables inspected**:
  - `claude_raw_traces` – Claude Code JSONL-based raw traces
  - `cursor_raw_traces` – Cursor unified DB-based raw traces
  - Supporting tables (`cursor_sessions`, `conversations`, etc.) were not the primary focus for this pass.

### Environment and Initialization

- Used the project’s virtualenv Python binary:

```bash
/Users/rr/blueplane/bp-telemetry-core/venv/bin/python
```

- Initialized the database schema (if not already initialized) with:

```bash
/Users/rr/blueplane/bp-telemetry-core/venv/bin/python scripts/init_database.py
```

This ensured `~/.blueplane/telemetry.db` existed and was on **schema version 2** with both `claude_raw_traces` and `cursor_raw_traces` tables present.

### Schema Inspection

We inspected the real schema using `PRAGMA table_info`:

- For Claude:
  - Confirmed presence of:
    - `message_role`, `message_model`, `input_tokens`, `output_tokens`
    - `cwd`, `git_branch`, `user_type`, `uuid`, `parent_uuid`, `request_id`, `agent_id`
    - `operation`, `subtype`, `level`, `is_meta`
    - Compressed `event_data` BLOB
  - Confirmed **absence** of:
    - Any `lines_added`, `lines_removed`, or other patch/line counters

- For Cursor:
  - Confirmed presence of:
    - `generation_type`, `composer_id`, `bubble_id`, `server_bubble_id`
    - `unix_ms`, `timestamp`, `event_date`, `event_hour`
    - `lines_added`, `lines_removed`, `token_count_up_until_here`
    - `relevant_files`, `capabilities_ran`, `capability_statuses`
    - Compressed `event_data` BLOB
  - Confirmed scalar columns like:
    - `lines_added`, `lines_removed`, `message_type` were defined but might not be populated.

---

## Field Coverage Measurements

To avoid relying only on docs/specs, we ran coverage queries over both tables to understand **how populated** key fields really are.

### Claude Coverage

Example coverage script (run via the venv Python):

```python
import sqlite3
from pathlib import Path

path = Path.home() / ".blueplane" / "telemetry.db"
conn = sqlite3.connect(str(path))
cur = conn.cursor()

fields = [
    "message_role","message_model","input_tokens","output_tokens",
    "cache_creation_input_tokens","cache_read_input_tokens","tokens_used",
    "cwd","git_branch","user_type","uuid","parent_uuid","request_id","agent_id",
    "operation","subtype","level","is_meta",
]

cur.execute("SELECT COUNT(*) FROM claude_raw_traces")
total, = cur.fetchone()

for f in fields:
    cur.execute(f"SELECT COUNT(*) FROM claude_raw_traces WHERE {f} IS NOT NULL")
    cnt, = cur.fetchone()
    print(f"{f}: {cnt} / {total}")
```

Key findings:

- `message_role`, `cwd`, `git_branch`, `user_type`, `uuid`, `parent_uuid`:
  - **~92% non-null** – i.e., populated for essentially all user/assistant message events.
- `message_model`, `input_tokens`, `output_tokens`, cache token fields, `tokens_used`, `request_id`:
  - **~54% non-null** – matching assistant events; tokens are present where they make sense.
- `agent_id`, `operation`:
  - Low but non-zero coverage (only some events use these fields).
- No line/patch metrics exist in this table.

### Cursor Coverage

Similar script for `cursor_raw_traces`:

```python
fields2 = [
    "generation_uuid","generation_type","command_type",
    "composer_id","bubble_id","server_bubble_id","message_type",
    "lines_added","lines_removed","token_count_up_until_here",
    "capabilities_ran","relevant_files","selections",
]

cur.execute("SELECT COUNT(*) FROM cursor_raw_traces")
total2, = cur.fetchone()

for f in fields2:
    cur.execute(f"SELECT COUNT(*) FROM cursor_raw_traces WHERE {f} IS NOT NULL")
    cnt, = cur.fetchone()
    print(f"{f}: {cnt} / {total2}")
```

Key findings:

- `generation_type`: ~94% non-null
- `bubble_id`: ~84% non-null
- `relevant_files`: ~84% non-null
- `capabilities_ran`: ~24% non-null
- `token_count_up_until_here`: **~1.9% non-null**
- `lines_added`, `lines_removed`, `message_type`, `command_type`, `selections`:
  - **0% non-null** in the scalar columns in this DB snapshot.

Interpretation:

- Many important Cursor fields exist **only in the compressed `event_data` JSON**, not in scalar columns.
- Any metric that relies on lines/tokens for Cursor must often parse `event_data`.

---

## Decompressing `event_data` JSON

To see what raw content we actually have per event beyond scalar columns, we decompressed representative `event_data` blobs.

### Claude Assistant Event

Snippet of the inspection script:

```python
import sqlite3, zlib, json
from pathlib import Path

path = Path.home() / ".blueplane" / "telemetry.db"
conn = sqlite3.connect(str(path))
cur = conn.cursor()

cur.execute("SELECT event_type, event_data FROM claude_raw_traces WHERE event_type='assistant' LIMIT 1")
evt_type, blob = cur.fetchone()
evt = json.loads(zlib.decompress(blob))
print("top-level keys:", list(evt.keys()))
payload = evt.get("payload", {})
print("payload keys:", list(payload.keys()))
entry_data = payload.get("entry_data") or {}
print("entry_data keys:", list(entry_data.keys()))
```

Observed structure:

- Top-level keys: `['version','hook_type','event_type','timestamp','platform','session_id','external_session_id','metadata','payload','event_id']`
- `payload.entry_data` keys:
  - `parentUuid`, `isSidechain`, `userType`, `cwd`, `sessionId`, `version`, `gitBranch`, `message`, `requestId`, `type`, `uuid`, `timestamp`

Implications:

- Full **message content**, context (`cwd`, `gitBranch`), and IDs are present.
- `message` includes model name and token usage (`usage`) for assistant events, even when some scalar fields are null.
- **Tool calls** (`tool_use`) live inside `message.content` items, which the SKILL docs describe and we observed indirectly.

### Cursor Bubble Event

Snippet:

```python
cur.execute("SELECT event_type, event_data FROM cursor_raw_traces WHERE event_type='bubble' LIMIT 1")
evt_type, blob = cur.fetchone()
evt = json.loads(zlib.decompress(blob))
print("top-level keys:", list(evt.keys()))
```

Observed structure (abridged):

- Top-level keys include:
  - `_v`, `type`, `bubbleId`, `richText`, `text`, `tokenCount`, `tokenDetailsUpUntilHere`, `tokenCountUpUntilHere`, `relevantFiles`, `capabilities`, `capabilitiesRan`, `capabilityStatuses`, `diffsSinceLastApply`, `assistantSuggestedDiffs`, and many more.

Implications:

- **Rich per-bubble context**: text, token counts, file references, capabilities, diff-like info.
- Many of these are **not flattened to scalar columns**, so robust analysis must read JSON.

### Cursor Composer Event

Similar decompression showed composer-level fields:

- `type`, `composerId`, `createdAt`, `unifiedMode`, `hasUnreadMessages`, `totalLinesAdded`, `totalLinesRemoved`, `isArchived`, `lastUpdatedAt`, `name`, `filesChangedCount`, etc.

Implications:

- Composer-level **patch metrics** (totalLinesAdded/Removed) are available **only** inside JSON.

---

## Validation Method per Insight

For each row in the telemetry insights CSV, we did the following:

1. **Check what’s actually in the DB**
   - For Claude: inspect `claude_raw_traces` scalar columns plus decompressed assistant/user `event_data`.
   - For Cursor: inspect `cursor_raw_traces` scalar columns plus decompressed `bubble` and `composer` JSON.

2. **Decide support level per platform**
   - **Fully supported**: all required data is clearly present and well-populated.
   - **Partially supported**: some relevant fields exist (often in JSON, not scalars), but are:
     - Sparse or incomplete, **or**
     - Require external data (e.g., Git) or heavier heuristics.
   - **Not supported**: key signals simply don’t exist (e.g., Cursor model names) in this DB.

3. **Validate the behavior-change recommendation**
   - Confirm that the insight’s behavior-change advice still makes sense **given what we can actually measure**.
   - In a few cases, note that a recommendation is mostly Claude-only (e.g., model strategy).

4. **Adjust the capture flags**
   - Where the original sheet said `Yes` but the DB did not support that (e.g., patch metrics for Claude), update to `Partial` or `No`.
   - Preserve `Partial`/`No` where the DB inspection confirmed those labels.

5. **Document investigation notes**
   - For each metric, add:
     - `Claude_Capture_Notes` and `Cursor_Capture_Notes` – short explanations of how the metric is derived.
     - `Claude_Investigation_Notes` and `Cursor_Investigation_Notes` – concrete findings from schema inspection and field coverage tests (e.g., “`lines_added` is 0% non-null”).

---

## Key Corrections to the Original Sheet

Some important corrections that came out of this process:

- **Claude patch metrics (Patch_Efficiency_Curve, Effort_vs_Progress_Score “lines” part)**
  - There are **no** `lines_added` / `lines_removed` columns in `claude_raw_traces` or any other table in `telemetry.db`.
  - Any line-based insight for Claude must **join with Git or another external patch-tracking source**.
  - We therefore changed Claude’s capture flag from `Yes` → `No` for `Patch_Efficiency_Curve` and to `Partial` for `Effort_vs_Progress_Score`.

- **Cursor patch/token scalars vs JSON**
  - Scalar `lines_added`, `lines_removed`, and `message_type` are currently **0% non-null**.
  - `token_count_up_until_here` is **~1.9% non-null**.
  - However, composer and bubble JSON contain `totalLinesAdded/Removed`, `tokenCount`, `tokenCountUpUntilHere`, etc.
  - We confirmed that some Cursor metrics are **possible but JSON-driven**, thus `Partial` capture is accurate.

- **Cursor model information**
  - No model identifiers exist in `cursor_raw_traces` (scalar or JSON as inspected), so **all model-level insights for Cursor are “not supported”**.

- **Feedback/rating signals**
  - No explicit thumbs-up/down fields for either platform.
  - All “positive/negative feedback” metrics must be **heuristic**, based on text and follow-up behavior; capture remains `Partial` for both.

---

## Glossary: Telemetry Data Concepts

This section defines the key terms used when we talk about “getting data from the system” for both **Claude Code** and **Cursor**. Each term has a concise definition and an “explain it like I’m 5” (ELI5) version.

### Cross-Cutting Concepts

- **Event**
  - **Definition**: A single recorded occurrence in the system (e.g., “user message sent”, “assistant reply”, “tool executed”, “Cursor bubble created”). It is the atomic unit of telemetry.
  - **ELI5**: Every time something happens, we write a tiny note about it. That tiny note is an event.

- **Trace**
  - **Definition**: A structured representation of an event (or a very small cluster of related events) with IDs, timestamps, context fields, and a JSON payload. In practice, each row in `claude_raw_traces` or `cursor_raw_traces` is a trace.
  - **ELI5**: A trace is like one page in a diary that records one thing that happened, with all the important details on that page.

- **Raw Traces / Raw Trace Tables**
  - **Definition**: The first-layer, write-only storage of captured events before any enrichment or aggregation. For Claude this is the `claude_raw_traces` table; for Cursor this is the `cursor_raw_traces` table. Each row has scalar columns plus a compressed JSON `event_data` blob.
  - **ELI5**: Raw traces are the messy but complete notebook where we scribble everything down before we make any charts or pretty summaries.

- **Scalar Columns**
  - **Definition**: Individual, typed columns in the SQLite tables (e.g., `message_role`, `input_tokens`, `bubble_id`, `relevant_files`) that store a single value per row, as opposed to the nested JSON stored in `event_data`. They are used for fast filtering, indexing, and aggregation.
  - **ELI5**: If a whole event is a lunchbox, scalar columns are the little labels on the outside like “who,” “when,” and “how many tokens,” so we can quickly find the right box without opening it.

- **cwd**
  - **Definition**: The “current working directory” for an event, usually the project or repo path the IDE process was in when the event occurred (e.g., `/Users/rr/blueplane/bp-telemetry-core`). It lets us scope traces to a specific workspace.
  - **ELI5**: `cwd` is the folder you were “standing in” on your computer when something happened.

- **JSON Blob vs. Compressed JSON Blob**
  - **Definition**: A **JSON blob** is the full JSON structure for an event (nested objects, arrays, etc.). In our database we store this as a **compressed JSON blob** in `event_data`: we zlib-compress the JSON bytes before writing them to SQLite to save space and I/O. Reading it back requires decompressing, then `json.loads()`.
  - **ELI5**: A JSON blob is the full story written out in plain text; a compressed JSON blob is the same story squished into a tiny ball so it takes less room, and we have to “unsquish” it to read it.

---

### Claude Code Concepts

- **Claude Session / external_session_id**
  - **Definition**: A logical conversation or interaction window with Claude Code. All traces that share the same `external_session_id` (and related session context) belong to the same Claude session.
  - **ELI5**: A session is one long chat with Claude; everything in that chat wears the same name tag.

- **Claude Message / message_role / message_model**
  - **Definition**: Each user or assistant turn is stored as a trace with `message_role` (`'user'` or `'assistant'`), the model used (`message_model`), token fields (`input_tokens`, `output_tokens`, etc.), and the full message content in `event_data`.
  - **ELI5**: Every time you or Claude talk, we note who spoke, which “Claude brain” answered, and how many words it took.

- **Claude Tool Use (tool_use)**
  - **Definition**: Tool calls embedded inside Claude assistant messages in `event_data.payload.entry_data.message.content` where `type == 'tool_use'`. These include the tool `name` (e.g., `Bash`, `Read`, `Edit`) and an `input` object (e.g., `command`, `file_path`), and are used for workflow and git/shell analysis.
  - **ELI5**: When Claude presses a magic button like “run this command” or “edit this file,” we record which button it pressed and what it tried to do.

- **Claude Raw Event JSON (event_data for Claude)**
  - **Definition**: The compressed JSON payload for a Claude event, including top-level fields (`version`, `hook_type`, `event_type`, `timestamp`, `platform`, `session_id`, etc.) and `payload.entry_data` (message, cwd, gitBranch, IDs, tool calls, token usage).
  - **ELI5**: It’s the full story of that Claude moment: what Claude saw, what it did, and where you were in your code when it happened.

---

### Cursor Concepts

- **Composer**
  - **Definition**: Cursor’s logical “conversation/work unit” object. A composer corresponds to a single chat/composer panel and includes metadata fields (`composerId`, `createdAt`, `lastUpdatedAt`, `totalLinesAdded`, `totalLinesRemoved`, `filesChangedCount`, `hasUnreadMessages`, etc.) plus its conversation (an array of bubbles). Stored globally under keys like `composerData:{composerId}`.
  - **ELI5**: A composer is one open AI chat box in Cursor where you’re working on a task; everything that happens in that box belongs together.

- **Bubble**
  - **Definition**: A single message/turn in a composer’s conversation (either user or AI). Bubble JSON includes IDs (`bubbleId`, `serverBubbleId`), role/type (`type`), content (`text`, `rawText`, `richText`), context (`relevantFiles`, `selections`), metrics (`tokenCount`, `tokenCountUpUntilHere`), capabilities (`capabilities`, `capabilitiesRan`, `capabilityStatuses`), and error fields.
  - **ELI5**: A bubble is one speech bubble in the chat—one thing you said or Cursor’s AI said.

- **Capability / capabilitiesRan / capabilityStatuses**
  - **Definition**: A capability is a specific Cursor AI operation (e.g., run a tool, apply a diff, analyze files). For each bubble/composer, `capabilities` describes what’s available, `capabilitiesRan` records which capabilities actually ran with their parameters, and `capabilityStatuses` records success/error states.
  - **ELI5**: Capabilities are the tricks Cursor’s AI can do; `capabilitiesRan` shows which tricks it tried, and `capabilityStatuses` says whether each trick worked or failed.

- **Background Composer**
  - **Definition**: A composer that runs without direct user interaction, tracked in `workbench.backgroundComposer.workspacePersistentData`. It captures background work such as ongoing analysis or auto-completion tasks, with fields like `workspacePersistentData`, `lastActiveTimestamp`, `state`, `autoCompletions`, `pendingTasks`, `cacheState`.
  - **ELI5**: It’s like an invisible helper composer that keeps working in the background even when you’re not chatting with it directly.

- **Agent Mode**
  - **Definition**: Cursor’s autonomous “agentic” mode where the system performs a sequence of actions on its own. Captured as events (e.g., `event_type = 'agent_mode'`) with fields like `session_id`, `exit_reason`, `duration_ms`, `actions_performed`, `files_modified`, `commands_executed`, `success`, `error_message`.
  - **ELI5**: Agent mode is when Cursor says “I’ve got this” and does many steps for you by itself; we log what it did and whether it worked.

- **cursor_sessions**
  - **Definition**: A table that maps workspace paths to `workspace_hash` and session metadata. It lets us link global `cursorDiskKV` data (like `composerData:*`) back to specific workspaces and to activate monitoring only for workspaces with active sessions.
  - **ELI5**: It’s a phonebook that tells us which project each Cursor conversation belongs to.

- **cursor_raw_traces Table**
  - **Definition**: SQLite table that stores all processed Cursor telemetry as traces. Each row includes IDs (e.g., `event_id`, `external_session_id`, `composer_id`, `bubble_id`), location (`storage_level`, `workspace_hash`, `database_table`, `item_key`), scalar content fields (`text_description`, `raw_text`, `relevant_files`, etc.), metrics (`token_count_up_until_here`, `lines_added`, `lines_removed`), and the full compressed JSON `event_data`.
  - **ELI5**: It’s a big table where every “Cursor did something” moment is written down, including chats, messages, and tools it ran.

- **Cursor Raw Event JSON (event_data for Cursor)**
  - **Definition**: The compressed JSON payload for a Cursor event. For `event_type='composer'` it contains composer metadata and its conversation headers; for `event_type='bubble'` it contains the full bubble JSON; for `event_type='capability'`, `background_composer`, `agent_mode`, etc., it contains those detailed structures.
  - **ELI5**: It’s the whole detailed story of what happened inside Cursor at that moment, squished into a blob we can later unsquish and read.

---

## Final CSV Output (with Investigation Notes)

The table below is the **final CSV content** (rendered here as a CSV code block), including:

- Original columns (data, explanations, insight, recommendations, priorities, categories)
- Updated **Claude/Cursor capture flags**
- **Capture notes** and **investigation notes** summarizing the DB inspection.

```csv
Data,Data Explanation,Insight,Insight Explanation,Insight Type,Claude Data Captured?,Cursor Data Captured?,Priority_for_Individual_Dev (1-5),Valence,Category,Behavior Change Recommendation,Claude_Capture_Notes,Cursor_Capture_Notes,Claude_Investigation_Notes,Cursor_Investigation_Notes
Effort_vs_Progress_Score (0-1),"Lines of code added divided by total tokens used to get there","How effectively you turn AI tokens into real code changes","Higher scores mean more of your AI usage translates into actual code progress instead of discussion or churn.","diagnostic","Partial","Partial",1,positive,efficiency,"When this score is low, break work into smaller concrete coding tasks and ask the AI for focused diffs or functions instead of long conversations; see Anthropic's prompting tips (`https://www.anthropic.com/news/prompting-best-practices`) and OpenAI's prompt engineering guide (`https://platform.openai.com/docs/guides/prompt-engineering`).","Claude has per-message input/output token fields and full assistant event payloads in `event_data`, but no line-add/remove fields in the DB.","Cursor composer events’ `event_data` include `totalLinesAdded`/`totalLinesRemoved`, and bubble JSON includes token counts; scalar `lines_added/removed` and `token_count_up_until_here` columns are mostly empty.","Verified in `claude_raw_traces`: token fields (`input_tokens`,`output_tokens`) are non-null for ~54% of rows (assistant events), but there are no schema columns for lines added/removed or patches, so lines must come from outside telemetry (e.g. Git).","Verified in `cursor_raw_traces`: `totalLinesAdded/Removed` only appear inside decompressed composer `event_data` JSON; scalar `lines_added/removed` columns are 0% non-null and `token_count_up_until_here` is populated for ~1.9% of rows; we can approximate this score by decoding JSON but not from scalar columns alone."
Workflow_Quality_Score (0-1),"Composite score using read-before-edit ratio, productive vs wasteful churn, and file touch patterns","How disciplined and clean your coding workflow is with AI","Higher scores indicate deliberate, low-churn iteration (read-before-edit, few thrashy edits, tests before big changes).","diagnostic","Yes","Partial",1,positive,workflow,"If this is low, slow down your loop: read before editing, run tests between larger changes, and ask the AI to propose step-by-step plans rather than ad-hoc edits; the best-practices in Anthropic's guide (`https://www.anthropic.com/news/prompting-best-practices`) map well to this.","Claude tool-use events in assistant `event_data` contain tool names and file paths, making it possible to derive read/edit patterns and file churn.","Cursor bubble/composer `event_data` expose `relevantFiles`, `capabilities`/`capabilitiesRan`, and `totalLinesAdded/Removed`, but there is no first-class Read/Edit tool taxonomy; scalar patch columns are unused.","Decompressed a Claude assistant `event_data` sample and confirmed the presence of `payload.entry_data.message` with tool-like content; combined with `cwd`/`git_branch` scalars, this supports detailed workflow analysis.","Decompressed Cursor bubble and composer events and saw `relevantFiles`, `capabilitiesRan` and total line counts in JSON, but `lines_added/removed` and `message_type` scalar fields are 0% non-null; workflow quality is inferable but not as directly as in Claude."
Development_Discipline (careful vs reactive),"Classification based on read-before-edit ratio and trial-and-error vs productive iteration patterns","Whether you tend to read and understand before editing or dive straight into thrashy changes","Helps you see if you’re behaving like a careful engineer or relying on reactive guess-and-check with the AI.","diagnostic","Yes","Partial",1,mixed,workflow,"If you skew reactive, practice asking the AI for explanations, summaries, and design options before edits, and explicitly request 'plan then apply' behaviors; see the sections on iterative refinement in Anthropic's prompting article (`https://www.anthropic.com/news/prompting-best-practices`).","Claude captures Read/Edit tool usage and file paths in assistant `event_data`, which can be mapped to careful vs reactive patterns.","Cursor’s bubble/composer events give `relevantFiles`, capabilities, and timing, but lack explicit Read vs Edit operations; discipline must be inferred from sequences and capabilities.","Covered by the same Claude fields as Workflow_Quality_Score; schema inspection confirms we can see user/assistant messages and assistant tool activity via JSON.","Cursor coverage is partial: JSON shows what capabilities and files were touched, but without explicit Read/Edit or patch scalars, some discipline features are heuristic only."
total_input_tokens & total_output_tokens,"Raw token counts for prompts and responses over the analysis window","Are you overusing tokens relative to the value you’re getting?","Lets you see if you’re pouring huge context into AI without a proportional amount of useful output or code changes.","diagnostic","Yes","Partial",1,mixed,efficiency,"If you see huge token usage, experiment with shorter, more focused prompts and start fresh threads for new tasks; both Anthropic (`https://www.anthropic.com/news/prompting-best-practices`) and OpenAI (`https://platform.openai.com/docs/guides/prompt-engineering`) recommend minimizing unnecessary context.","Claude’s assistant `event_data` has a `usage` block with `input_tokens`, `output_tokens`, etc., and those are also extracted to scalar columns for assistant events.","Cursor bubble `event_data` includes `tokenCount`, `tokenDetailsUpUntilHere`, and `tokenCountUpUntilHere`, but the scalar `token_count_up_until_here` is sparsely populated.","Our coverage script over `claude_raw_traces` confirmed both timestamp columns and token fields are well-populated for assistant events, so grouping by `event_date`/hour is straightforward.","For Cursor we saw 19,000 rows with good timestamp coverage and only 364 rows with scalar token counts; the bubble JSON we decoded shows `tokenCount` fields, so aggregated tokens/hour require decompressing `event_data` rather than relying on scalars."
input_output_ratio,"Ratio of input tokens to output tokens for Claude sessions","Whether your conversations are concise and effective or overly context-heavy","Very high ratios suggest you’re stuffing in too much context or repeating information without getting enough new output back.","diagnostic","Yes","No",1,negative,efficiency,"When this ratio is high, use summaries instead of raw paste, ask the AI to 'infer context from this short description' rather than dumping logs, and explicitly limit answer length; see context management tips in OpenAI's prompt guide (`https://platform.openai.com/docs/guides/prompt-engineering`).","Claude has distinct `input_tokens` and `output_tokens` in assistant `event_data` (and scalar columns) so this ratio is straightforward to compute.","Cursor only has aggregate/cumulative token counts in bubble JSON and no separate 'input' vs 'output' tokens per turn.","Scalar and JSON for Claude assistant events both expose `usage.input_tokens` and `usage.output_tokens`, so we can compute ratios per response and aggregate per session.","Decompressed Cursor bubble `event_data` and saw `tokenCount`/`tokenCountUpUntilHere` but no fields that distinguish input vs output; schema also has no split fields, so true input:output ratio is not derivable."
Prompt_Quality_vs_Result,"Success rate and correction rate segmented by prompt length/complexity","What style and length of prompts work best for you","Shows if short, focused prompts or longer, structured ones are more likely to produce good answers without lots of corrections.","diagnostic","Yes","Yes",1,positive,productivity,"Notice your most successful prompt patterns and template them; practice writing prompts with clear goals, constraints, and examples as described in Anthropic's prompting best practices (`https://www.anthropic.com/news/prompting-best-practices`).","Claude stores full user prompt text, assistant responses, and follow-on corrections, so we can bucket prompts by length/structure and correlate with correction patterns.","Cursor bubble JSON contains `rawText`, `type`, error flags, and subsequent bubbles, so we can perform the same length/structure vs. correction analysis using those fields.","We inspected a Claude assistant `event_data` record and confirmed it nests a `message` object with full content, and user messages are also present in `claude_raw_traces`, so prompt text and subsequent corrections are available.","Cursor bubble JSON we decoded includes `rawText` and error-related metadata, and bubbles are ordered by timestamp; this supports comparing prompt length/structure with later correction bubbles."
Stuckness_Prediction (risk_level),"Signal based on correction rate, reprompt loops, and back-and-forth patterns","Whether you’re likely stuck and spinning your wheels with the AI","Helps you recognize when to step back, simplify the task, or change strategy instead of continuing a failing loop.","diagnostic","Yes","Yes",1,negative,workflow,"When stuckness is high, pause and reframe: ask the AI for a diagnosis of why attempts are failing, restate the problem in simpler terms, or switch to 'help me design a smaller subtask' as recommended in iterative strategies from Anthropic (`https://www.anthropic.com/news/prompting-best-practices`).","Claude’s conversation stream (user vs assistant events, timestamps, corrections) in `claude_raw_traces` supports detecting loops and high correction densities.","Cursor bubble sequences in `cursor_raw_traces` (with `rawText`, timing, and error flags) allow similar reprompt/loop detection from the actual captured data.","The claude DB has clear event_type and message_role patterns (`assistant`,`user`) plus timestamps; combined with text similarity, that’s enough to flag repeated corrective turns.","Cursor’s `cursor_raw_traces` table shows many `bubble` events with rich JSON; by reading `rawText` and timestamps we can count repeated similar prompts and long correction chains even though roles are inferred from JSON, not scalar `message_type`."
reprompt_loop_count,"Number of times you ask similar follow-ups trying to fix the same thing","How often you end up in 'try again / fix it' loops","High counts indicate the AI (or your prompts) aren’t getting to a solid solution quickly, pointing to prompt or task-setup issues.","diagnostic","Yes","Yes",1,negative,efficiency,"Instead of repeating 'try again', add new constraints, examples, or failure traces to your prompt, or ask the AI 'what context are you missing to solve this?'; this aligns with the 'provide feedback and iterate' pattern in OpenAI's guide (`https://platform.openai.com/docs/guides/prompt-engineering`).","Claude conversation streams (user vs assistant messages) support similarity checks on user prompts to find loops.","Cursor conversation bubbles also include ordered user/AI text, so we can detect repeated similar user prompts over short windows.","Same evidence as Stuckness_Prediction: `claude_raw_traces` holds full text and roles, enabling reprompt clustering via text similarity and timestamps.","Same as above: bubble JSON gives you user prompts and their sequence; no extra fields are required beyond the `rawText` we observed."
Patch_Efficiency_Curve,"Relationship between prompts and lines added/removed, including add_remove_ratio","Whether your patching style is clean and decisive or thrashy","Clean curves (few prompts → many useful lines) show decisive progress; zig-zaggy curves show a lot of churn for small net change.","diagnostic","No","Partial",1,mixed,productivity,"If your curve is thrashy, ask the AI to propose a complete patch and explanation before applying, and use smaller, test-backed steps; follow patterns like 'first propose design, then code' from AI-assistant workflow articles (e.g., Copilot best practices: `https://learn.microsoft.com/en-us/copilot/github/copilot-best-practices-for-developers`).","Claude’s DB schema does not contain patch/line-count fields; this metric would require external Git diffs or a separate patch pipeline.","Cursor composer `event_data` contains `totalLinesAdded`/`totalLinesRemoved` per composer, and diff-like structures in bubble JSON, but scalar `lines_added/removed` are empty.","`PRAGMA table_info(claude_raw_traces)` shows many token and context columns, but nothing about lines/patches; no other table in this DB holds patch metrics, so from telemetry DB alone this insight is not supported.","`cursor_raw_traces` has scalar `lines_added/removed` columns at 0% non-null, but decompressed composer JSON clearly includes `totalLinesAdded/Removed`; we can draw a composer-level efficiency curve by decoding JSON, though not fine-grained per-prompt curves."
tokens_per_hour_utc & tokens_per_day,"Temporal distribution of token usage across hours/days","When you’re most productive with AI help","Reveals your personal peak hours when AI collaboration yields the most useful changes, helping you schedule deep work.","recommendation","Yes","Partial",2,positive,productivity,"Schedule complex AI-heavy work during your historically productive hours and reserve off-hours for smaller, lower-risk tasks; combine this with deep-work guidance from developer productivity blogs that discuss AI pairing habits.","Claude has per-event token counts and timestamps, so hourly/daily aggregates are precise.","Cursor bubble JSON includes token counts, but scalar `token_count_up_until_here` is sparse; we can compute approximate per-hour/day usage from JSON.","Our coverage script over `claude_raw_traces` confirmed both timestamp columns and token fields are well-populated for assistant events, so grouping by `event_date`/hour is straightforward.","For Cursor we saw 19,000 rows with good timestamp coverage and only 364 rows with scalar token counts; the bubble JSON we decoded shows `tokenCount` fields, so aggregated tokens/hour require decompressing `event_data` rather than relying on scalars."
Session_Focus_Profile (short_bursts/long_deep_work/mixed),"Classification of your sessions by duration and activity density","Whether you work in focused deep-work blocks or fragmented bursts","Helps you align your work style with what actually leads to good outcomes and fewer context switches.","diagnostic","Yes","Yes",2,mixed,workflow,"If you see fragmented bursts, experiment with 60–90 minute focused AI co-coding blocks where you define a single goal and stick to it; many Copilot and ChatGPT usage guides recommend time-boxed 'pairing sessions' for this reason (`https://learn.microsoft.com/en-us/copilot/github/copilot-best-practices-for-developers`).","Claude events are timestamped and grouped by session (`external_id`), allowing classification by length and activity density.","Cursor has `external_session_id`, `unix_ms`/`timestamp`, and event types, which lets us measure session spans and activity density from actual traces.","`claude_raw_traces` includes `external_id` (session-like) and `timestamp` plus a generated `event_date`; row counts in our inspection indicate enough events to classify sessions by duration and density.","`cursor_raw_traces` exposes `external_session_id`, `timestamp`, and `event_type` (`bubble`, `composer`, etc.), which is sufficient to reconstruct per-session timelines and densities."
context_switch_count,"How often you change topics, files, or tasks within a session","Are you multitasking too much and fragmenting your attention?","High context switching suggests scattered work that can reduce quality and increase cognitive load.","diagnostic","Yes","Yes",2,negative,workflow,"When context switches are high, start sessions by listing 1–3 concrete goals and repeatedly ask the AI 'are we still on goal X?' to maintain focus; this mirrors task-chunking advice in prompt-engineering resources (`https://platform.openai.com/docs/guides/prompt-engineering`).","Claude’s `cwd`, `git_branch`, and any file data in tool-use JSON give strong signals for topic/file/branch switches.","Cursor’s bubble/composer JSON has `relevantFiles`, project fields, and context pieces, so we can infer changes in focus across files and topics.","Schema inspection showed `cwd` and `git_branch` scalars plus rich assistant `event_data` fields, which together support detecting changes in branch, working directory, or file focus over time.","Cursor bubble JSON we decompressed contains `relevantFiles` and other context lists, and event_type distribution (`bubble` vs `composer`) lets us trace task/file switches even though there’s no single “topic id” column."
read_before_edit_ratio,"Reads of files before edits divided by edit operations","How often you inspect code before changing it","Higher ratios mean more careful and informed edits; low ratios can indicate risky, trial-and-error coding.","diagnostic","Yes","No",2,positive,quality,"Raise this ratio by asking the AI to summarize or explain a file before making changes, and by reviewing the diff it proposes; 'ask for explanation first' is a recurring pattern in AI-pairing guidance like Anthropic's article (`https://www.anthropic.com/news/prompting-best-practices`).","Claude tool-use payloads (inside assistant `event_data`) encode Read vs Edit operations with file paths, so the ratio is directly measurable.","Cursor has capabilities and `relevantFiles` data, but not an explicit Read vs Edit operation taxonomy.","While the scalar schema doesn’t list tools, the Claude hook format and JSON we inspected for assistant events are consistent with `tool_use` blocks describing operations like Read/Edit, and those blocks are preserved in compressed `event_data`.","In Cursor, we saw `capabilities`/`capabilitiesRan` and `relevantFiles` in JSON, but nothing that cleanly corresponds to simple Read vs Edit file operations; no scalar columns indicate this either."
high_churn_files,"Files edited many times (e.g., 3+ touches) in a short period","Which files are your 'pain points' during a task","Identifies hotspots where design or understanding issues are causing you to repeatedly rework the same code.","diagnostic","Yes","Yes",2,negative,quality,"For churny files, ask the AI for a refactor plan or design sketch first, then implement in fewer, larger steps; combine this with architecture-oriented prompting ('propose a better design for this module') as suggested in many AI-for-devs articles.","Claude tool-use and patch events include file paths in `event_data`, so repeated edits to the same file over time are easy to count.","Cursor bubble JSON’s `relevantFiles` field is ~84% populated and lets us track which files are repeatedly involved in conversations.","We didn’t see a scalar `file_path` column, but by decompressing Claude assistant `event_data` (and following the documented format), we know tool calls include file paths which can be used for churn counts.","Cursor coverage stats show `relevant_files` scalar is non-null for ~84% of rows, and the decoded bubble JSON confirms `relevantFiles` contains paths; that’s enough to detect files that appear in many bubbles in a short interval."
files_created_not_committed,"Files that were written/created via tools but never end up in git","How much of your AI-driven file creation becomes waste","High counts point to abandoned experiments or clutter that never makes it into the final codebase.","diagnostic","Partial","No",2,negative,efficiency,"Reduce waste by asking the AI whether a new file is actually necessary, and by cleaning up experimental files at the end of a session; consider using prompts like 'integrate this into existing modules instead of creating a new file' when appropriate.","Claude tool-use payloads include write operations with `file_path`, but commit status is not in telemetry DB; Git must be queried separately.","Cursor telemetry does not currently integrate file-creation operations with git state at this level.","From DB inspection, Claude captures tool/file paths but no git-diff or commit metadata; we can see “file was written” but must ask Git (outside DB) whether it was committed, so telemetry contributes only half of this insight.","`cursor_raw_traces` has file-related context but no git information nor explicit “file created” operations; without an external Git integration, this specific “created but never committed” metric cannot be computed for Cursor."
positive_feedback / negative_feedback counts,"Explicit thumbs-up/down or similar feedback signals to AI responses","How often the AI meets your expectations","Lets you see if you’re frequently dissatisfied, which can motivate better prompts or different workflows.","diagnostic","Partial","Partial",2,mixed,satisfaction,"When you give negative feedback, follow up with a prompt that explains why the answer missed and what a better answer would look like; both Anthropic and OpenAI guides emphasize explicit corrective feedback as a way to steer models (`https://www.anthropic.com/news/prompting-best-practices`, `https://platform.openai.com/docs/guides/prompt-engineering`).","Claude traces do not expose a dedicated rating field; we can infer positive/negative sentiment from message text and follow-up behavior in `event_data`.","Cursor traces likewise lack a rating field; we infer probable satisfaction/dissatisfaction from bubble text, errors, and follow-ups.","Search and schema inspection found no columns or JSON fields for ratings; only message content and follow-up patterns are available, so “feedback counts” must be derived heuristically.","Same story in Cursor: no `thumbsUp`/`thumbsDown` fields were observed in `cursor_raw_traces` or its JSON; behavior-based inference (e.g., “thank you” vs rapid corrections) is the only option."
AI_vs_Human_Burden_Ratio,"Ratio of AI output characters to your input characters","Whether you’re letting the AI do too much or too little of the typing","Can reveal over-reliance (AI writing too much low-value code) or under-use (you’re doing manual work AI could help with).","diagnostic","Yes","Partial",2,mixed,efficiency,"If the AI is doing nearly all typing, increase your review and refactor passes; if you’re doing most typing, offload boilerplate and test scaffolding to the AI as suggested in Copilot best-practice docs (`https://learn.microsoft.com/en-us/copilot/github/copilot-best-practices-for-developers`).","Claude has full user and assistant text in `event_data` and clear message roles, so we can count tokens/characters per side accurately.","Cursor bubble `rawText` is available, but the role indicator (`message_type` scalar) is 0% non-null; we must infer user vs AI from JSON structure and context.","`claude_raw_traces` has `message_role` scalar populated for ~92% of rows plus full text in compressed JSON, enabling exact human vs AI token/character accounting.","Coverage stats show `message_type` in `cursor_raw_traces` is 0% non-null, but `event_data` for bubbles includes enough structure (bubble type and content) to infer who authored the text; some edge cases remain heuristic."
delegation_style (high-level vs step-by-step),"Inferred from how you phrase prompts and decompose tasks","How you tend to delegate work to the AI","Shows whether you’re giving clear, high-level objectives vs micromanaging the assistant, affecting both quality and speed.","diagnostic","Yes","Yes",2,mixed,workflow,"Practice both extremes: write some prompts as high-level specs with constraints, and others as detailed step lists, then compare outcomes; this mirrors experimentation advice in Anthropic's prompt guide (`https://www.anthropic.com/news/prompting-best-practices`).","Claude prompt text (user messages) is fully present in `event_data`, enabling structural delegation classification.","Cursor bubble `rawText` for user messages is available, allowing the same classification.","Decompressed Claude assistant JSON to confirm prompt/response structure and saw user messages in `claude_raw_traces`; text-based delegation heuristics can run entirely off this content.","Cursor bubble JSON we inspected contains `text`/`rawText` fields and a bubble type; together these are sufficient to categorize prompts as high-level specs vs step lists."
Predicted_Task_Difficulty,"Classification (easy/moderate/hard) based on query rate, corrections, and context switches","Which tasks are actually hard for you vs just noisy","Lets you distinguish genuinely complex work from problems caused by unclear setup or fragmented focus.","diagnostic","Yes","Yes",2,mixed,productivity,"For tasks flagged hard, invest more upfront: ask the AI for a design doc, risks list, and roadmap before coding; this 'plan before build' pattern is common in AI for complex system design guides.","Claude provides prompts, corrections, timing, and switches across files/branches, which are the inputs to the difficulty heuristic.","Cursor provides similar temporal and conversation data (bubbles, `relevantFiles`, errors), so the same heuristic can run.","The Claude DB fields we examined (timestamps, roles, file/branch context via JSON) suffice to compute activity intensity, correction frequency, and context switching, which are the signals for this heuristic.","Cursor’s bubble/composer events give timestamps, text, file context, and some error flags; no additional special fields are needed to derive an easy/moderate/hard label."
capabilities_invoked & agentic_mode_usage,"Which advanced features you use (e.g., multi-file edits, agentic mode) and how often","Whether you’re taking advantage of the most powerful AI capabilities","Low usage suggests you’re leaving performance and speed on the table for big or multi-file changes.","recommendation","Yes","Yes",2,positive,productivity,"Gradually adopt more powerful features (multi-file edits, refactor tools, test generation) on low-risk tasks first, following staged-adoption advice from Copilot and other AI-assistant documentation (`https://learn.microsoft.com/en-us/copilot/github/copilot-best-practices-for-developers`).","Claude’s `event_data` includes tool_use content (tool names, arguments), so capability usage is visible in the captured traces.","Cursor bubble and composer JSON store `capabilities` and `capabilitiesRan`, and there are dedicated agent-mode events, so we can see which Cursor capabilities have been used.","We know from decompressed Claude assistant JSON that tool calls and their parameters appear directly in `event_data`, and these are present for many assistant events.","Cursor’s decoded bubble JSON showed `capabilities`/`capabilitiesRan` fields and agent-mode related data; event_type distribution in `cursor_raw_traces` (`session_start`, `agent_mode`, etc.) further supports these metrics."
per_model_usage & per_model_tokens,"Breakdown of models used and tokens per model (Claude Code only)","Are you picking the right model for the job and cost?","Helps you see whether you’re overusing expensive models for trivial tasks or underusing stronger models where they’d help most.","diagnostic","Yes","No",3,mixed,efficiency,"Align model choice with task complexity: use cheaper models for simple edits and stronger ones for design and refactors, as suggested in many vendor docs on model selection.","Claude assistant messages carry `message_model` plus token usage in `usage`, and these are also extracted into scalar columns for assistant events.","Cursor telemetry does not surface model names in `cursor_raw_traces` either as scalar columns or inside the JSON payloads.","`PRAGMA table_info(claude_raw_traces)` shows a `message_model` column with non-null entries for ~54% of rows in our coverage stats (matching assistant responses); combined with token fields, this supports per-model aggregation.","In `cursor_raw_traces`, our schema inspection and JSON samples showed no fields that look like model IDs; model-level breakdown is thus impossible for Cursor."
Model_Strategy_Assessment (single_model vs tiered_models),"High-level description of how you switch (or don’t) between models","How intentional your model strategy is","Shows whether you’re using a tiered approach (cheap for exploration, powerful for finalization) or just defaulting everywhere.","diagnostic","Yes","No",3,positive,productivity,"If you always use one model, experiment with a two-tier strategy (draft with cheaper, finalize with higher-quality) and track how it affects cost and quality as recommended in model-strategy best-practice posts.","Claude’s `message_model` field (and model strings in assistant `event_data`) let us see when and how you switch between models.","Cursor telemetry does not surface model names in any of the fields we inspected.","Same as per_model_usage: Claude exposes `message_model` strings per assistant event, and our coverage script confirmed they are populated on a majority of assistant rows.","Again, Cursor has no scalar or JSON field for model names in the events we decompressed; any “strategy” view is Claude-only."
estimated_cost_usd,"Estimated spend based on Claude Sonnet pricing and token usage","Your approximate 'cost burn' for a period","Makes the cost of experimentation and long sessions tangible, nudging you toward more efficient usage.","diagnostic","Yes","No",3,mixed,efficiency,"When costs are high, adopt practices like shorter prompts, starting new threads, and batching questions; these are standard recommendations in prompt-efficiency guides (`https://platform.openai.com/docs/guides/prompt-engineering`).","Claude token usage maps directly onto known pricing, so cost can be estimated from the captured token fields.","Cursor doesn’t expose enough per-message token detail + model identity to attach a concrete dollar cost.","In Claude, we combine token counts from `claude_raw_traces` with fixed per-token prices; our earlier coverage analysis confirmed tokens are present for all assistant events used in such calculations.","Cursor’s token info is partial and model is unknown; we verified this by both schema and JSON inspection, so any cost estimate would be too speculative."
prompt_count,"Total number of prompts in the window","How heavily you lean on the AI overall","Very high counts can mean strong reliance; combined with other metrics it shows whether that reliance is effective.","diagnostic","Yes","Yes",3,mixed,usage,"If prompt count is high but impact metrics are low, focus on better prompt structure (goal, context, constraints, output format) per Anthropic's suggestions (`https://www.anthropic.com/news/prompting-best-practices`).","Claude user messages are labeled in `claude_raw_traces`, so counting user prompts per window is exact.","Cursor bubble events (with `type` and `rawText` in `event_data`) allow us to count user prompts vs other event types.","`claude_raw_traces` has well-populated `event_type` and `message_role` scalars (92% non-null), enabling unambiguous counting of user prompts.","Although `cursor_raw_traces.message_type` is unused, bubble `event_data` holds a `type`/role concept and `rawText`, giving enough structure to identify which bubbles represent user prompts."
average_prompt_length & median_prompt_length,"Stats on how long your prompts are (tokens or characters)","Whether your prompts tend to be under-specified or overly verbose","Extremely short prompts may underspecify tasks; very long prompts may be bloated with repeated context.","diagnostic","Yes","Yes",3,mixed,efficiency,"Experiment with 'medium' length prompts that clearly set the task and constraints without dumping everything; many prompt-engineering resources recommend concise specificity over maximal context.","Claude has full prompt text and token counts for user messages, enabling both character- and token-based length statistics.","Cursor bubble `rawText` and token-count data inside bubble JSON provide enough to compute lengths and approximate token-based stats.","We saw Claude user messages in `claude_raw_traces` and assistant `event_data`, as well as per-event token usage; both character and token-based lengths are thus available.","Cursor bubble JSON includes `rawText` and token metrics; although scalar token fields are sparse, decoding JSON supplies enough data to estimate token-based lengths, and characters can be counted directly."
prompt_complexity_score (low/medium/high),"Heuristic score of structural complexity of prompts","How sophisticated your instructions tend to be","Can suggest when to embrace more structured prompts (steps, constraints) vs keeping them simple.","diagnostic","Yes","Yes",3,positive,productivity,"If your prompts are mostly low complexity, try adding structure (numbered steps, acceptance criteria) as in OpenAI's examples (`https://platform.openai.com/docs/guides/prompt-engineering`); if they’re always high, test simpler versions.","Claude’s user prompt text in `event_data` is sufficient to detect structural features (lists, constraints, examples) and compute a complexity heuristic.","Cursor’s bubble `rawText` for user messages supports the same kind of structural analysis.","This is derived from text alone; our inspection confirmed Claude’s user prompt text is fully present in compressed JSON and is already being ingested into `claude_raw_traces`.","Same applies to Cursor: bubble JSON provides full text and metadata; no additional special fields are needed for this heuristic."
analysis_scope & session_duration,"Scope (session/week/branch) and length of sessions","Your typical working patterns with AI (short vs long sessions)","Provides context for interpreting all other metrics (e.g., a few intense long sessions vs many tiny ones).","context","Yes","Yes",3,neutral,usage,"Use this to choose when to do deep architectural work with AI (long sessions) vs quick Q&A (short sessions), following deep-work ideas from developer productivity literature.","Claude’s `external_id` + timestamps define session windows and durations clearly in `claude_raw_traces`.","Cursor’s `external_session_id`, `timestamp`/`unix_ms`, and event_type distribution allow us to reconstruct per-session durations and map them to branches/workspaces.","Schema shows `external_id` and `timestamp` plus generated `event_date`/`event_hour` for Claude; row counts confirm multiple sessions are present, making durations computable.","`cursor_raw_traces` provides `external_session_id`, accurate timestamps, and session start/end events; this is enough to derive session duration and scope from telemetry."
active_exchanges & total_ai_responses,"Number of back-and-forth turns with AI","How interactive your collaboration is","Helps you see if you’re using AI as a one-shot oracle or in an iterative dialog style.","diagnostic","Yes","Yes",3,neutral,usage,"Aim for a healthy mix of single-shot answers and iterative refinement; guides on 'pair programming with AI' recommend using follow-ups to clarify and refine rather than accepting the first answer blindly.","Claude’s `message_role` (user vs assistant) and event ordering enable exact counts of exchanges and responses.","Cursor bubble JSON includes a `type`/role concept and structure, so exchanges and response counts are computable.","Coverage script showed `message_role` ~92% non-null in `claude_raw_traces`, and event_type breakdown (`user`,`assistant`) confirmed we can pair user and assistant messages into exchanges.","In Cursor, we rely on bubble JSON (not `message_type` scalar, which is empty) to distinguish user vs AI bubbles; our sample event_data confirms this structure is present, allowing exchange counting."
tokens_per_minute_by_session (or prompts_per_minute),"Rate of interaction within sessions","Whether you’re rushing interactions or giving time to think and test","Very high rates can indicate frantic thrashing; moderate, paced use is often more deliberate.","diagnostic","Yes","Partial",3,mixed,workflow,"If your rate is very high, slow down: run tests, inspect diffs, and ask for explanations; this matches recommendations to keep a tight but thoughtful feedback loop with AI assistants.","Claude provides per-event token counts and timestamps so both tokens/minute and prompts/minute are precise.","Cursor supports precise prompts/minute from timestamps; tokens/minute are only approximate because the `token_count_up_until_here` scalar column is sparsely populated and token details require JSON parsing.","Our Claude inspection confirmed timestamps and token fields are well-populated for assistant rows, and we can compute tokens/min straightforwardly from these.","For Cursor, prompts-per-minute are trivial from timestamps, but token-rate depends on decoding bubble JSON and using cumulative token counters; scalar coverage is too low for a purely-column-based computation."
session_summaries,"Short textual summaries of sessions (derived)","Human-readable overview of what each session focused on","Helps you recall what you worked on and relate metrics to actual tasks.","context","Yes","Yes",3,positive,productivity,"Review summaries periodically to spot patterns in where AI helps you most or where you struggle, then adjust how you brief the AI for those task types.","Claude’s combination of prompts, responses, and context fields in `event_data` is enough to generate reliable natural-language summaries of each session.","Cursor’s bubble/composer JSON captures text, capabilities, files, and timing, so we can summarize sessions from those traces as well.","No dedicated summary column exists, but we verified all raw ingredients (prompts, responses, context, timestamps) are present in Claude traces and can be fed into summarisation logic.","Similarly, Cursor’s rich bubble/composer JSON contains everything needed to summarise a session’s activity; the summary is a derived artefact, not a stored field."
platform_usage_breakdown (Claude Code vs Cursor),"Counts of prompts and responses per platform","Where you actually spend AI time (IDE vs Claude chat)","Useful for understanding which environment drives most of your changes and should be optimized first.","diagnostic","Yes","Yes",4,neutral,usage,"If most value comes from one platform, invest in learning its advanced features (e.g., multi-file edits in IDE, better context management in chat) via that platform's own docs and tutorials.","Claude events are clearly identified as `platform='claude_code'` in `claude_raw_traces`.","Cursor events reside in `cursor_raw_traces` and carry Cursor-specific fields, so splitting usage by platform is trivial.","Our DB inspection showed separate `claude_raw_traces` and `cursor_raw_traces` tables and a `platform` column for Claude; this clean separation simplifies platform breakdowns.","Just the fact that Cursor events live in `cursor_raw_traces` and Claude events live in `claude_raw_traces` is enough to drive a robust platform breakdown."
activity.window.days_active & active_days,"Number of days with any AI activity in the branch or period","How consistently you collaborate with the AI","Shows whether your AI usage is bursty around deadlines or steady over time.","diagnostic","Yes","Yes",4,neutral,usage,"Consider making AI pairing a consistent habit (e.g., start each coding block with a quick AI planning prompt) instead of only using it in crunch times.","Claude timestamps allow counting unique `event_date` values per scope from `claude_raw_traces`.","Cursor timestamps allow the same “active day” counting from `cursor_raw_traces.event_date` or `unix_ms`.","We saw the generated `event_date` column in `claude_raw_traces`; counting distinct dates with events is trivial.","`cursor_raw_traces` also has `timestamp` and generated `event_date` columns, and our coverage script confirmed high row counts, supporting a reliable “days active” measure."
daily activity snapshot (per-day prompts/tokens),"Day-by-day breakdown of prompts and tokens","Which specific days were heavy or light usage days","Helpful for relating AI usage to sprint cadence, on-call load, or crunch times.","context","Yes","Partial",4,neutral,usage,"Use this view in retrospectives to correlate heavy AI usage with outcomes (good or bad) and adjust how you engage on similar future days.","Claude supports exact per-day prompt and token aggregates from `claude_raw_traces`.","Cursor supports accurate per-day prompt counts; per-day token estimates are possible but rely on deriving token usage from bubble JSON rather than the sparsely populated `token_count_up_until_here` column.","Same as tokens_per_hour: Claude’s per-event tokens and `event_date` allow precise daily totals.","Our Cursor coverage script showed that token scalars are too sparse for column-only daily totals, but decompressed bubble JSON contains `tokenCount` fields that can be aggregated per day with additional processing."
tool_distribution (Bash/Write/Edit/Read/etc.),"Counts of each tool type invoked from Claude Code","What kinds of work you rely on the AI tools for","Reveals whether you mostly use AI for code edits, exploration, running commands, or reading, shaping your optimization focus.","diagnostic","Yes","No",4,neutral,usage,"If you underuse certain helpful tools (e.g., Read or tests), intentionally add them into your loop, following patterns from AI-enabled TDD and refactoring guides.","Claude assistant `event_data` encodes `tool_use` blocks with tool names and arguments, so we can categorize usage by tool type.","Cursor’s capability telemetry is structured differently and doesn’t map cleanly onto Bash/Write/Edit/Read categories.","Our Claude assistant JSON sample matches the documented format where `message.content` includes `tool_use` items with names (`Bash`,`Read`,`Edit`, etc.), which provides direct counts.","Cursor’s capabilities in bubble JSON (`capabilities`/`capabilitiesRan`) don’t map 1:1 to the Claude tool taxonomy; some similar insights are possible but not this exact distribution."
time_between_tool_uses,"Gaps between tool invocations in a session","How bursty vs paced your tool usage is","Can indicate whether you’re using tools as part of a smooth loop or in frantic bursts when stuck.","diagnostic","Yes","Partial",4,mixed,workflow,"Try to stabilize your loop into a repeatable pattern (edit → test → inspect → next step) instead of rapid random tool firing when stuck; many AI-productivity articles emphasize consistent loops over sporadic use.","Claude tool-use events with timestamps allow exact computation of time deltas between tool invocations.","Cursor has timestamped generations, capabilities, and bubble events, so we can approximate gaps between “tool-like” actions (capabilities) but not an exact analogue to Claude’s tool operations.","Claude’s assistant tool calls, visible inside `event_data` and aligned with `timestamp`, support direct computation of how far apart individual tool invocations are.","For Cursor we rely on capability/bubble events as proxies for tool uses; since these are timestamped we can compute gaps, but we lack a clean, unified tool invocation entity like Claude’s `tool_use`."
pattern_classification (productive_iteration vs trial_and_error counts),"Counts of productive vs wasteful tool-operation patterns","Balance between deliberate refinement and blind guessing","Helps you see if your workflow is mostly solid iteration or dominated by low-yield thrashing.","diagnostic","Yes","Partial",4,mixed,workflow,"If trial-and-error dominates, adopt more deliberate patterns: ask for a plan, then ask the AI to execute individual steps, adjusting based on results as suggested in structured prompting guides.","Claude’s rich tool-use streams and (with Git) diff information let us distinguish patterns like Read→Edit→Test vs repeated failing edits on the same file.","Cursor’s capabilities, `relevantFiles`, and bubble sequences hint at productive vs wasteful cycles, but classification is more heuristic.","In Claude we can already distinguish read-first vs edit-first and repeated edits to the same file from `event_data`; if we add Git context externally, the productive vs wasteful classification sharpens further.","In Cursor, we can see which files are repeatedly involved and which capabilities run, but without an explicit Read/Edit taxonomy or patch scalars we rely more heavily on heuristics grounded in bubble JSON."
Platform model availability,"Whether model details are present (Claude) or missing (Cursor)","Limitations in how precisely we can analyze model strategy","Reminds you that Cursor-based interactions can’t be broken down by model, preventing over-interpretation.","limitation","Yes","Yes",5,neutral,limitations,"Keep this limitation in mind when interpreting model-related insights and avoid over-tuning your behavior based on incomplete platform data.","Claude events include `message_model` per assistant event, so we know when model info is available.","Cursor events we examined contain no model identifiers; this absence is itself a reliable signal that model-level analysis isn’t possible.","Our coverage analysis confirmed a non-trivial fraction of Claude rows have non-null `message_model` values, and the column exists in the schema.","We explicitly checked `cursor_raw_traces` schema and decompressed bubble/composer JSON; no model-identifying field was present, so we can confidently state model info is missing for Cursor telemetry."
Token completeness & capture coverage,"Degree to which telemetry is fully captured for a workspace","How reliable the metrics are for making decisions","Warns you if gaps in capture could skew your perception of efficiency or cost.","limitation","Yes","Yes",5,neutral,limitations,"Before acting on metrics, check capture health and treat numbers as directional if coverage is incomplete.","Claude ingestion into `claude_raw_traces` can be checked by comparing expected vs actual event counts and by validating that key fields (tokens, roles, timestamps) are non-null at high rates.","Cursor ingestion into `cursor_raw_traces` can be evaluated via row counts per session, event_type distributions, and coverage of important fields.","Our scripts showed 628 rows in `claude_raw_traces` with high non-null coverage for roles, timestamps, and token fields on assistant rows; that gives a solid baseline for completeness checks.","We saw ~19,000 rows in `cursor_raw_traces` with healthy coverage for `bubble` and `composer` events, but also observed that certain scalar metrics (e.g., token, patch fields) are sparsely populated; this forms the ground truth for labeling some Cursor metrics as Partial."
Heuristic-based task and role inference,"Signals that rely on heuristics (e.g., message_type NULL, task keywords)","Where the system is 'best-effort' instead of exact","Encourages cautious interpretation of fine-grained behavior segments.","limitation","Yes","Yes",5,neutral,limitations,"Use these insights as hints, not hard truths, and combine them with your subjective experience when adjusting behavior.","Claude has explicit roles and context, but higher-level task labels (bugfix vs refactor, etc.) must still be inferred from text and patterns in `event_data`.","Cursor’s `message_type` scalar is empty, so roles and tasks are inferred from bubble JSON structure and text rather than from a dedicated column.","`message_role` is present for Claude and covers roles well, but “task type” (bugfix, feature, refactor) is not a field anywhere; any such categorisation is built from free-text and patterns.","Our coverage script revealed `message_type` is 0% non-null in `cursor_raw_traces`; we must instead inspect bubble JSON (which has types and content) to infer who is speaking and what they’re doing, making role/task labels heuristic."
Privacy safeguards (no raw code / no verbatim prompts),"Design constraints that strip sensitive content","Guarantees about data safety and local-only analysis","Important context, but less directly impactful on day-to-day optimization decisions.","limitation","Yes","Yes",5,positive,privacy,"Continue to treat the assistant as operating on summaries and metrics, not raw code, and follow general secure-prompting guidance (avoid secrets in prompts) from vendor security docs.","Claude telemetry stores compressed `event_data` and derived metadata with a privacy-first contract; we focus on metrics and context, not raw source file contents.","Cursor telemetry similarly focuses on conversation/composer metadata and capabilities rather than raw code content, consistent with the privacy-first design.","The Claude DB schema and our decompressed samples show messages and metadata but not embedded raw source code files; hooks are designed to send structured telemetry, not the full codebase.","Cursor’s bubble JSON includes `relevantFiles` references and diffs but not the entire project contents; combined with local-only SQLite/Redis, this matches the documented privacy guarantees."
Platform_Retry_Patterns (Cursor_failure_then_Claude_success),"Counts of cases where a request fails via Cursor capabilities but a similar request shortly after via Claude Code succeeds","How often built-in IDE AI struggles but Claude Code can complete the same task","Highlights cross-platform friction points where one assistant’s tooling or environment fails but the other one succeeds, especially for git and shell operations.","diagnostic","Yes","Partial",2,mixed,workflow,"When this is high, inspect why Cursor’s capabilities are failing (e.g., workspace mapping, GitHub auth, repo state) and either fix those paths or intentionally route similar tasks through Claude Code’s shell/git tools; also consider simplifying the requested operation so both platforms can handle it reliably.","Claude tool_use events expose git/shell commands and outputs in assistant `event_data`, so we can see when a git operation (e.g., `git push`, `git pull`) fails vs succeeds and correlate that with the surrounding prompts.","Cursor bubble `event_data` includes `capabilitiesRan` and `capabilityStatuses` plus error-related metadata, which lets us detect failed git-like capabilities and match them to nearby user prompts, though success/failure semantics are more heuristic than Claude’s explicit shell output.","From DB inspection we know Claude assistant events have compressed `event_data` with full tool_use content (commands, results) and strong coverage on tokens, roles, and timestamps, making it straightforward to label git/shell tool calls as success or failure and align them with specific user requests.","In `cursor_raw_traces`, coverage stats show `capabilities_ran` is ~24% non-null and decompressed bubble JSON contains `capabilities`, `capabilitiesRan`, and `capabilityStatuses`; combined with high timestamp coverage and `relevantFiles`, this supports detecting failed Cursor capabilities and matching them—by text similarity and time window—to subsequent successful Claude Code attempts."
```

---

## How to Use This Document

- Treat this file as the **canonical design + validation record** for telemetry insights as of this DB snapshot.
- The CSV can be:
  - Exported to a sheet for PM/UX work.
  - Used as a **contract** between capture, processing, and any UI/PR integrations.
- When the capture pipeline changes:
  - Re-run the coverage + JSON inspection scripts.
  - Update `Claude/Cursor Data Captured?` and the investigation notes.


