<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Layer 2: Conversation Reconstruction

> Data Processing for AI-Assisted Coding Sessions
> Part of the Blueplane MVP Architecture
> [Back to Main Architecture](./BLUEPLANE_MVP_ARCHITECTURE.md)

---

## Overview

Conversation reconstruction is a **Layer 2 data processing** function that combines raw events from Layer 1 (hooks and database traces) to rebuild complete AI-assisted coding sessions with full context. This enables analysis of developer workflows, acceptance patterns, and multi-turn interactions.

## Architecture Context

This specification details the conversation reconstruction algorithms that are executed by Layer 2's async processing pipeline:

- **Input**: Raw events from Layer 1 via message queue and CDC stream
- **Processing**: Async workers in Layer 2 (ConversationWorker pool)
- **Output**: Structured conversation data in SQLite with relationships and metrics

## Integration with Async Pipeline

The ConversationWorker (defined in [layer2_async_pipeline.md](./layer2_async_pipeline.md)) implements these reconstruction algorithms:

```python
# server/slow_path/conversation_worker.py (pseudocode)

class ConversationWorker:
    """
    Implements the reconstruction algorithms defined in this specification.
    See layer2_async_pipeline.md for the worker implementation.
    """

    async def process(cdc_event: Dict) -> None:
        """
        Process CDC event to update conversation structure.

        - Read full event from SQLite raw_traces table (decompress event_data)
        - Route to platform-specific reconstruction based on platform field
        - Update SQLite conversation tables with new turn/event
        """
```

## Cursor Platform Reconstruction

### Data Sources

1. **Hooks Events (via Layer 1 Message Queue)**:
   - `BeforeSubmitPrompt`: User prompt submission
   - `AfterAgentResponse`: AI response text and metadata
   - `BeforeMCPExecution`/`AfterMCPExecution`: Tool calls
   - `AfterFileEdit`: File modifications with full edit details

2. **Database Traces (via Layer 2 Database Monitor)**:
   - Database monitor reads from Cursor's `ItemTable` key-value pairs
   - `aiService.prompts`: Complete prompt history (JSON array in `ItemTable`)
   - `aiService.generations`: Generation metadata with UUIDs (JSON array in `ItemTable`)
   - `composer.composerData`: Session grouping and state (if available)
   - Note: These are converted to `database_trace` events and stored in `raw_traces` table

### Reconstruction Algorithm

```python
# server/slow_path/cursor_reconstruction.py (pseudocode)

async def reconstruct_cursor_conversation(session_id: str):
    """
    Cursor conversation reconstruction algorithm.
    Executed by ConversationWorker in Layer 2 slow path.
    """

    # 1. Load hook events from SQLite raw_traces table
    hook_events = await sqlite.get_session_events(
        session_id, platform='cursor', order_by='timestamp'
    )
    # Note: Each event's event_data BLOB is decompressed to get full payload

    # 2. Load database traces from SQLite raw_traces table
    # Note: These are captured by the database monitor which reads from
    # Cursor's ItemTable key-value pairs (aiService.generations, etc.)
    # and converts them to database_trace events
    db_traces = await sqlite.get_database_traces(
        session_id,
        event_types=['database_trace']  # Filter by event_type, not table names
    )

    # 3. Build conversation timeline
    conversation = []
    for event in hook_events:
        # Match hook events to database records via generation_id
        # Create timeline entries:
        # - BeforeSubmitPrompt → user_prompt entry
        # - AfterAgentResponse → ai_response entry
        # - AfterFileEdit → file_edit entry with lines_added/removed
        conversation.append(build_timeline_entry(event, db_traces))

    # 4. Enrich with composer session metadata
    composer = find_composer_for_session(db_traces['composer.composerData'])

    # 5. Store in SQLite
    # Note: For Cursor, session_id references cursor_sessions.id (internal UUID)
    # The external_session_id from events maps to cursor_sessions.external_session_id
    await sqlite.store_conversation({
        'session_id': internal_session_id,  # References cursor_sessions.id
        'external_id': conversation_external_id,  # Conversation-specific external ID
        'platform': 'cursor',
        'timeline': conversation,
        'composer_metadata': composer,
        'metrics': calculate_metrics(conversation)
    })
```

### Example Reconstructed Conversation

```json
{
  "session_id": "curs_abc123",
  "platform": "cursor",
  "composer_name": "File creation task",
  "composer_mode": "agent",
  "context_usage": 45,
  "total_lines_added": 20,
  "total_lines_removed": 0,
  "files_changed": 1,
  "timeline": [
    {
      "type": "user_prompt",
      "timestamp": "2025-11-06T14:37:50Z",
      "generation_id": "0e30c239-7324-424c-a422-7b248abc9c26",
      "prompt_text": "write a new file...i'm a little teapot",
      "prompt_length": 87,
      "context_files": 0
    },
    {
      "type": "ai_response",
      "timestamp": "2025-11-06T14:37:52Z",
      "generation_id": "0e30c239-7324-424c-a422-7b248abc9c26",
      "response_text": "Created cursor-write-trace-test.md...",
      "response_length": 73,
      "model": "claude-sonnet-3.5",
      "tokens_used": 45,
      "duration_ms": 1850
    },
    {
      "type": "file_edit",
      "timestamp": "2025-11-06T14:37:53Z",
      "generation_id": "0e30c239-7324-424c-a422-7b248abc9c26",
      "file_path": "/path/to/cursor-write-trace-test.md",
      "edits": [
        {
          "old_string": "",
          "new_string": "i'm a little teapot\n"
        }
      ],
      "lines_added": 1,
      "lines_removed": 0
    }
  ]
}
```

## Claude Code Platform Reconstruction

### Data Sources

1. **Hooks Events (via Layer 1 Message Queue)**:
   - `SessionStart`: Session initialization with `transcript_path`
   - `UserPromptSubmit`: User prompt events
   - `PreToolUse`/`PostToolUse`: Tool execution with parameters and results
   - `PreCompact`: Context compaction events
   - `Stop`: Session completion

2. **Transcript Files (via Layer 1 Transcript Monitor)**:
   - Located at path provided by `transcript_path` in SessionStart hook
   - **User messages**: Full prompt text, IDE context, timestamps
   - **Assistant messages**: Model name, token usage, message IDs
   - **Tool calls**: Tool use blocks with names and full parameters
   - **Tool results**: Complete tool outputs and error messages
   - **Metadata**: Session ID, CWD, git branch, Claude Code version
   - **Note**: Session ID is directly provided in hook events, no state file needed

### Reconstruction Algorithm

```python
# server/slow_path/claude_reconstruction.py (pseudocode)

async def reconstruct_claude_code_conversation(session_id: str):
    """
    Claude Code conversation reconstruction algorithm.
    Executed by ConversationWorker in Layer 2 slow path.
    """

    # 1. Load all hook events from SQLite raw_traces table
    events = await sqlite.get_session_events(
        session_id, platform='claude', order_by='sequence'
    )
    # Note: Each event's event_data BLOB is decompressed to get full payload

    # 2. Get transcript path from SessionStart event
    transcript_path = extract_transcript_path(events)

    # 3. Load transcript data if available
    transcript_data = await sqlite.get_transcript_events(transcript_path) if transcript_path else []
    # Note: Transcript events are also stored in raw_traces with decompression

    # 4. Build conversation timeline
    conversation = []
    current_turn = None

    for event in events:
        # Process different hook types:
        # - SessionStart → session_start entry
        # - UserPromptSubmit → start new user_turn
        # - PreToolUse/PostToolUse → add to current_turn.tools_used
        # - PreCompact → context_compaction entry
        # - Stop → session_end entry
        entry = build_timeline_entry(event, current_turn)
        if entry:
            conversation.append(entry)

    # 5. Enrich with transcript data (model, tokens)
    model_usage = extract_model_usage(transcript_data)

    # 6. Store in SQLite
    # Note: For Claude Code, session_id is NULL (no session concept)
    # The session_id from Claude Code becomes external_id in conversations table
    await sqlite.store_conversation({
        'session_id': None,  # NULL for Claude Code (no session concept)
        'external_id': session_id,  # Claude session/conversation ID becomes external_id
        'platform': 'claude_code',
        'timeline': conversation,
        'model_usage': model_usage,
        'metrics': calculate_metrics(conversation, events)
    })

def extract_model_usage(transcript_data: List[Dict]) -> Dict:
    """
    Extract model and token information from transcript.

    - Parse assistant messages for model names
    - Sum input_tokens and output_tokens from usage fields
    - Detect model switches
    - Return: models_used, primary_model, model_switches, total_tokens
    """
```

### Example Reconstructed Conversation

```json
{
  "session_id": "sess_xyz789",
  "platform": "claude",
  "event_count": 12,
  "transcript_messages": 8,
  "user_turns": 3,
  "tools_executed": 5,
  "compactions": 1,
  "model_usage": {
    "models_used": ["claude-opus-4-1-20250805"],
    "primary_model": "claude-opus-4-1-20250805",
    "model_switches": 0,
    "total_tokens": 3847
  },
  "timeline": [
    {
      "type": "session_start",
      "timestamp": "2025-11-06T10:00:00Z",
      "source": "startup",
      "workspace_hash": "a1b2c3d4",
      "transcript_path": "/Users/user/.claude/projects/.../sess_xyz789.jsonl"
    },
    {
      "type": "user_turn",
      "timestamp": "2025-11-06T10:05:12Z",
      "sequence_num": 1,
      "prompt_length": 156,
      "word_count": 28,
      "tools_used": [
        {
          "tool": "Read",
          "start_time": "2025-11-06T10:05:13Z",
          "end_time": "2025-11-06T10:05:14Z",
          "parameters": {"file_path": "/path/to/file.py"},
          "success": true,
          "result_length": 2048
        },
        {
          "tool": "Edit",
          "start_time": "2025-11-06T10:05:15Z",
          "end_time": "2025-11-06T10:05:16Z",
          "parameters": {
            "file_path": "/path/to/file.py",
            "old_string": "def old_function():",
            "new_string": "def new_function():"
          },
          "success": true,
          "result_length": 45
        }
      ]
    },
    {
      "type": "context_compaction",
      "timestamp": "2025-11-06T10:15:30Z",
      "trigger": "auto",
      "messages_before": 15,
      "messages_after": 8
    },
    {
      "type": "session_end",
      "timestamp": "2025-11-06T11:00:00Z",
      "reason": "user_stopped"
    }
  ]
}
```

### Unique Data from Transcript Files

The transcript file provides critical data not available through hooks alone:

1. **Model Information**:
   - Exact Claude model used (e.g., `claude-opus-4-1-20250805`)
   - Model switches during conversation
   - Primary model for the session

2. **Token Usage**:
   - `input_tokens`: Tokens consumed by prompts
   - `output_tokens`: Tokens generated in responses
   - `cache_creation_input_tokens`: Cache-related token counts
   - `cache_read_input_tokens`: Tokens read from cache

3. **Full Conversation Content**:
   - Complete user prompt text (not just metadata)
   - Full assistant responses including thinking blocks
   - Tool use details with complete parameters
   - Tool results with full output content

4. **Additional Metadata**:
   - Git branch at time of interaction
   - Claude Code version
   - Message IDs for correlation
   - Request IDs for API tracking

This rich data enables accurate model tracking, cost calculation, and complete conversation replay that wouldn't be possible with hooks alone.

## Cross-Platform Alignment

For analysis across both platforms, align conversations using:

1. **Temporal Alignment**: Match by timestamp windows
2. **File Path Matching**: Link operations on same files
3. **Semantic Matching**: Compare prompt text similarity
4. **Workspace Correlation**: Link by workspace hash/path

```python
# server/analysis/cross_platform_aligner.py (pseudocode)

class CrossPlatformAligner:
    """
    Layer 2 service for aligning conversations across platforms.
    Executed by dedicated alignment workers or on-demand.
    """

    async def align_conversations(claude_external_id: str, cursor_session_id: str):
        """
        Align conversations from different platforms.

        Note: 
        - Claude Code: Use external_id (session/conversation ID) to look up conversation
        - Cursor: Use session_id (internal UUID) or external_session_id to look up session, then conversations

        1. Load both conversations from SQLite:
           - Claude: SELECT * FROM conversations WHERE external_id = ? AND platform = 'claude_code'
           - Cursor: SELECT c.* FROM conversations c JOIN cursor_sessions s ON c.session_id = s.id WHERE s.external_session_id = ?
        2. Find temporal correlations:
           - Match events within 5-second window
           - Calculate confidence based on time_diff
        3. Find file path correlations:
           - Extract file paths from both timelines
           - Match operations on same files
        4. Find semantic correlations (optional):
           - Compare prompt text similarity
           - Match workspace context
        5. Store alignment in SQLite

        Returns alignment with correlations array
        """
```

## Storage Schema

The reconstructed conversations are stored in SQLite (Layer 2) with the following schema:

**Important**: See [SESSION_CONVERSATION_SCHEMA.md](../../SESSION_CONVERSATION_SCHEMA.md) for the complete schema design.

```sql
-- Cursor Sessions Table (Cursor only - Claude Code has no session concept)
CREATE TABLE cursor_sessions (
    id TEXT PRIMARY KEY,
    external_session_id TEXT NOT NULL UNIQUE,
    workspace_hash TEXT NOT NULL,
    workspace_name TEXT,
    workspace_path TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Conversations table (unified for both platforms)
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT,  -- NULL for Claude Code, references cursor_sessions.id for Cursor
    external_id TEXT NOT NULL,  -- Platform-specific external ID
    platform TEXT NOT NULL,
    workspace_hash TEXT,
    workspace_name TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,

    -- Metrics
    interaction_count INTEGER DEFAULT 0,
    acceptance_rate REAL,
    total_tokens INTEGER DEFAULT 0,
    total_changes INTEGER DEFAULT 0,

    -- JSON fields
    context TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    tool_sequence TEXT DEFAULT '[]',
    acceptance_decisions TEXT DEFAULT '[]',

    FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
    CHECK (
        (platform = 'cursor' AND session_id IS NOT NULL) OR
        (platform = 'claude_code' AND session_id IS NULL)
    ),
    UNIQUE(external_id, platform)
);

-- Note: conversation_turns table not yet implemented

-- Cross-platform alignments
CREATE TABLE conversation_alignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claude_conversation_id TEXT,
    cursor_conversation_id TEXT,
    correlation_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (claude_conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (cursor_conversation_id) REFERENCES conversations(id)
);
```

## Performance Considerations

- **Async Processing**: All reconstruction happens in Layer 2's slow path, not blocking ingestion
- **Batch Processing**: ConversationWorker can batch multiple events before reconstruction
- **Caching**: Recent conversations cached in Redis for fast access
- **Incremental Updates**: Conversations updated incrementally as new events arrive
- **Eventual Consistency**: Reconstruction may lag behind real-time by seconds to minutes

## Related Documentation

- [Layer 2 Async Pipeline](./layer2_async_pipeline.md) - Worker implementation
- [Layer 2 Local Server](./layer2_local_server.md) - Server architecture
- [Layer 1 Capture](./layer1_capture.md) - Raw event sources
- [Database Architecture](./database_architecture_detailed.md) - Storage details

---

[Back to Main Architecture](./BLUEPLANE_MVP_ARCHITECTURE.md)