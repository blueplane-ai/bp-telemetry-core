<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Cursor Composer Data Capture - GitHub Examples & Schema Analysis

## Overview

This document compiles findings from GitHub repositories that capture Cursor composer/chat data, including complete schema definitions for conversations, messages, tool calls, and metadata.

## Database Structure

### Storage Location

Cursor persists all chat and composer data in SQLite databases:

- **macOS**: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- **Windows**: `%APPDATA%\Cursor\User\workspaceStorage\*/state.vscdb`
- **Linux**: `~/.config/Cursor/User/workspaceStorage\*/state.vscdb`

### Table Schema

All data is stored in key-value tables:

```sql
-- Main table structure
CREATE TABLE ItemTable (
    key TEXT UNIQUE ON CONFLICT REPLACE,
    value BLOB
);

-- Alternative table name in some versions
CREATE TABLE cursorDiskKV (
    key TEXT UNIQUE ON CONFLICT REPLACE,
    value BLOB
);
```

### Key Database Keys

| Key Pattern | Content | Location |
|-------------|---------|----------|
| `workbench.panel.aichat.view.aichat.chatdata` | Chat history (older format) | ItemTable |
| `composerData:<composerId>` | Individual composer metadata | cursorDiskKV (global) |
| `composer.composerData` | All composers list | ItemTable (project) |
| `aiService.prompts` | User prompts | ItemTable |

## ComposerData Schema (Version 3)

### Top-Level Structure

```json
{
  "_v": 3,
  "composerId": "string",
  "createdAt": 1234567890123,
  "lastUpdatedAt": 1234567890456,
  "status": "completed | aborted",
  "isAgentic": true,
  "name": "Conversation Title",
  "fullConversationHeadersOnly": [...],
  "latestConversationSummary": {...},
  "usageData": {...},
  "context": {...}
}
```

### Full Conversation Array

The `fullConversationHeadersOnly` field contains the complete message history:

```json
"fullConversationHeadersOnly": [
  {
    "bubbleId": "uuid-1",
    "type": 1,  // User message
    "serverBubbleId": "optional-server-id"
  },
  {
    "bubbleId": "uuid-2",
    "type": 2   // AI response
  }
]
```

**Message Types:**
- `type: 1` = User message
- `type: 2` = AI/Assistant response

### Conversation Summary

```json
"latestConversationSummary": {
  "summary": "Natural language summary of conversation",
  "truncationLastBubbleIdInclusive": "uuid",
  "clientShouldStartSendingFromInclusiveBubbleId": "uuid",
  "lastBubbleId": "uuid"
}
```

### Usage Data (Cost Tracking)

```json
"usageData": {
  "gpt-4": {
    "costInCents": 125,
    "amount": 1
  },
  "claude-sonnet-3.5": {
    "costInCents": 89,
    "amount": 3
  }
}
```

### Context Data

```json
"context": {
  "attachedFiles": [...],
  "selections": [...],
  "externalLinks": [...],
  "cursorRules": "...",
  "directoryContext": {...}
}
```

## BubbleData Schema (Individual Messages)

### Message Structure (Version 2)

Each bubble (message) has its own database entry:

```json
{
  "_v": 2,
  "bubbleId": "uuid",
  "type": 1,  // or 2
  "text": "Displayed message content with formatting",
  "rawText": "Plain text version",
  "richText": {
    // Lexical editor state for rich formatting
    "root": {
      "children": [...]
    }
  },
  "thinking": "Content from thinking tags (AI only)",
  "toolFormerdata": {...},
  "tokenCount": {
    "inputTokens": 1234,
    "outputTokens": 5678
  },
  "relevantFiles": [...],
  "context": {...},
  "capabilities": [...],
  "modelType": "claude-sonnet-3.5",
  "selections": [...]
}
```

### User Message Fields

```json
{
  "type": 1,
  "text": "User message content",
  "delegate": "Alternative text field",
  "initText": "{\"root\":{\"children\":[...]}}",  // JSON-encoded rich text
  "relevantFiles": [
    {
      "path": "/path/to/file.ts",
      "content": "..."
    }
  ],
  "selections": [
    {
      "text": "Selected code snippet",
      "path": "/path/to/file.ts",
      "range": {...}
    }
  ],
  "image": {
    "path": "/path/to/screenshot.png"
  }
}
```

### AI Response Fields

```json
{
  "type": 2,
  "modelType": "claude-sonnet-3.5",
  "rawText": "AI response content",
  "thinking": "Reasoning content from thinking blocks",
  "toolFormerdata": {
    // Tool call information
  },
  "capabilities": [
    {
      "type": "tool_use",
      "bubbleDataMap": {...}
    }
  ],
  "tokenCount": {
    "inputTokens": 1234,
    "outputTokens": 5678
  }
}
```

## Tool Usage Data (toolFormerdata)

### Structure

Tool calls are captured in the `toolFormerdata` field:

```json
"toolFormerdata": {
  "toolCalls": [
    {
      "id": "call_abc123",
      "type": "edit_file",
      "status": "completed | pending | failed",
      "arguments": {
        "path": "/path/to/file.ts",
        "edits": [
          {
            "oldText": "const x = 1;",
            "newText": "const x = 2;",
            "line": 42
          }
        ]
      },
      "result": {
        "success": true,
        "diff": "...",
        "linesAdded": 5,
        "linesRemoved": 3
      }
    }
  ]
}
```

### Known Tool Types

Based on Cursor documentation and training:

- `tool_7`: edit_file
- `read_file`
- `grep_search`
- `semantic_search`
- `terminal_command`
- `browser_action`

### Capabilities Metadata

```json
"capabilities": [
  {
    "type": "codebase_search",
    "bubbleDataMap": {
      "searchQuery": "...",
      "resultsCount": 15,
      "filesScanned": 234
    }
  },
  {
    "type": "tool_execution",
    "bubbleDataMap": {
      "toolName": "edit_file",
      "executionTime": 123,
      "tokensUsed": 456
    }
  }
]
```

## Model Configuration

### Per-Message Model Info

```json
{
  "modelType": "claude-sonnet-3.5",
  "aiStreamingSettings": {
    "model": "claude-sonnet-3.5",
    "temperature": 0.7,
    "maxTokens": 4096,
    "thinkingEnabled": true
  }
}
```

## Thinking/Reasoning Content

AI responses can include reasoning content:

```json
{
  "thinking": "Step-by-step reasoning content that appears in thinking blocks",
  "rawText": "The actual response shown to the user"
}
```

For thinking-enabled models (like Claude 3.7 Sonnet):
- Thinking content is captured separately
- Costs 2x fast premium requests
- Not shown in main response text

## Message Metadata

### Timing Information

```json
{
  "createdAt": 1234567890123,
  "lastUpdatedAt": 1234567890456,
  "completedAt": 1234567890789,
  "streamStartTime": 1234567890200,
  "streamEndTime": 1234567890700
}
```

### Bubble IDs

```json
{
  "bubbleId": "client-generated-uuid",
  "serverBubbleId": "server-assigned-id",
  "truncationLastBubbleIdInclusive": "for conversation summaries",
  "clientShouldStartSendingFromInclusiveBubbleId": "for context window management"
}
```

### Capability Types

```json
{
  "capabilityType": "agent | composer | chat",
  "isAgentic": true,
  "agentWorkspace": "/path/to/worktree"
}
```

## GitHub Repository Examples

### 1. cursor-db-mcp (Most Complete)

**Repository**: https://github.com/jbdamask/cursor-db-mcp

**Language**: Python

**Key Features**:
- Model Context Protocol server for querying Cursor databases
- Automatic database discovery
- SQL query tool for any table
- Resources for projects and composers
- Composer-specific data access

**SQL Queries Used**:
```python
# Get all composers
SELECT key, value FROM ItemTable WHERE key = 'composer.composerData'

# Get specific composer
SELECT key, value FROM cursorDiskKV WHERE key = 'composerData:{composer_id}'

# Get chat data
SELECT key, value FROM ItemTable WHERE key = 'workbench.panel.aichat.view.aichat.chatdata'

# Generic query
SELECT key, value FROM ItemTable WHERE key LIKE ? LIMIT ?
```

### 2. cursor-chat-export

**Repository**: https://github.com/somogyijanos/cursor-chat-export

**Language**: Python

**Key Features**:
- CLI tool for exporting chats to Markdown
- Platform-specific path discovery
- Tab-based organization
- Image extraction and copying
- Rich terminal output

**Key Code Patterns**:
```python
# Database access
db = VSCDBQuery(db_path)
chat_data = db.query_aichat_data()

# Parse structure
for tab in chat_data['tabs']:
    for bubble in tab.get('bubbles', []):
        if bubble['type'] == 'user':
            # Extract user text from multiple possible fields
            text = bubble.get('text') or bubble.get('delegate') or ...
        elif bubble['type'] == 'ai':
            # Extract AI response
            text = bubble.get('rawText')
            model = bubble.get('modelType')
```

### 3. Cursor-export-extension

**Repository**: https://github.com/TsekaLuk/Cursor-export-extension

**Language**: TypeScript (VSCode Extension)

**Key Features**:
- One-click export from Cursor IDE
- Preserves formatting, metadata, timestamps
- Thinking blocks preservation
- Code snippet formatting
- Customizable save locations

**Integration Point**:
- Uses VSCode extension APIs
- Accesses Cursor's internal storage
- Formats to structured Markdown

### 4. vscode-cursorchat-downloader

**Repository**: https://github.com/abakermi/vscode-cursorchat-downloader

**Language**: TypeScript

**Key Features**:
- Access conversations across workspaces
- Full conversation history view
- Model identifiers included
- Code snippet preservation
- Currently macOS-only

**Path Access**:
```typescript
const cursorPath = `~/Library/Application Support/Cursor/User/workspaceStorage`;
```

### 5. composer-web (Different Purpose - Data Forwarding)

**Repository**: https://github.com/saketsarin/composer-web

**Language**: TypeScript

**Key Features**:
- Forwards browser data TO Composer (not extracting FROM it)
- Screenshot capture
- Console log capture
- Network request monitoring
- Chrome DevTools Protocol integration

**Relevant for**:
- Understanding how to send data to Composer programmatically
- Remote debugging protocol usage

## Data Access Patterns

### Pattern 1: Direct SQLite Query

```python
import sqlite3
import json

db_path = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
cursor = conn.cursor()

# Get composer data
cursor.execute("SELECT value FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
for row in cursor.fetchall():
    data = json.loads(row[0])
    print(f"Composer: {data['composerId']}")
    print(f"Messages: {len(data['fullConversationHeadersOnly'])}")
```

### Pattern 2: Iterate All Messages

```python
# Get composer metadata
composer_data = get_composer_data(composer_id)

# Get individual bubble data
for bubble_ref in composer_data['fullConversationHeadersOnly']:
    bubble_id = bubble_ref['bubbleId']

    # Fetch full bubble data
    cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?",
                   (f"bubbleData:{bubble_id}",))
    bubble_data = json.loads(cursor.fetchone()[0])

    # Access message content
    if bubble_data['type'] == 1:  # User
        print(f"User: {bubble_data['text']}")
    elif bubble_data['type'] == 2:  # AI
        print(f"AI ({bubble_data['modelType']}): {bubble_data['rawText']}")

        # Access tool calls
        if 'toolFormerdata' in bubble_data:
            for tool_call in bubble_data['toolFormerdata']['toolCalls']:
                print(f"  Tool: {tool_call['type']}")
                print(f"  Args: {tool_call['arguments']}")
```

### Pattern 3: Extract Full Conversation with Metadata

```python
def extract_full_conversation(composer_id):
    """Extract complete conversation with all metadata."""

    # Get composer metadata
    composer = get_composer_metadata(composer_id)

    conversation = {
        'id': composer['composerId'],
        'created_at': composer['createdAt'],
        'name': composer['name'],
        'is_agentic': composer['isAgentic'],
        'status': composer['status'],
        'usage': composer['usageData'],
        'messages': []
    }

    # Get all messages
    for bubble_ref in composer['fullConversationHeadersOnly']:
        bubble = get_bubble_data(bubble_ref['bubbleId'])

        message = {
            'id': bubble['bubbleId'],
            'type': 'user' if bubble['type'] == 1 else 'ai',
            'content': bubble.get('text') or bubble.get('rawText'),
            'timestamp': bubble.get('createdAt'),
        }

        # Add AI-specific fields
        if bubble['type'] == 2:
            message['model'] = bubble.get('modelType')
            message['thinking'] = bubble.get('thinking')
            message['tokens'] = bubble.get('tokenCount')

            # Add tool calls
            if 'toolFormerdata' in bubble:
                message['tool_calls'] = bubble['toolFormerdata']['toolCalls']

            # Add capabilities
            if 'capabilities' in bubble:
                message['capabilities'] = bubble['capabilities']

        # Add user-specific fields
        elif bubble['type'] == 1:
            message['files'] = bubble.get('relevantFiles', [])
            message['selections'] = bubble.get('selections', [])
            if 'image' in bubble:
                message['image_path'] = bubble['image']['path']

        conversation['messages'].append(message)

    return conversation
```

## Implementation Recommendations for bp-telemetry-core

Based on these examples, here are recommendations for our telemetry system:

### 1. Database Monitoring Approach

Monitor Cursor's `state.vscdb` files for changes:

```python
# Watch for database modifications
watch_paths = [
    "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    "~/.config/Cursor/User/workspaceStorage/*/state.vscdb"
]

# On change, query for new data
for change in watch_database_changes():
    if change.key.startswith('composerData:'):
        capture_composer_event(change)
    elif change.key.startswith('bubbleData:'):
        capture_message_event(change)
```

### 2. Event Capture Schema

Align our schema with Cursor's structure:

```sql
-- Raw events table (Layer 2)
CREATE TABLE raw_traces (
    id INTEGER PRIMARY KEY,
    platform TEXT DEFAULT 'cursor',
    event_type TEXT,  -- 'composer_created', 'message_sent', 'tool_call', etc.
    composer_id TEXT,
    bubble_id TEXT,
    data BLOB,  -- Compressed JSON
    captured_at INTEGER
);

-- Processed conversations (Layer 2 & 3)
CREATE TABLE conversations (
    composer_id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'cursor',
    name TEXT,
    created_at INTEGER,
    last_updated_at INTEGER,
    status TEXT,
    is_agentic BOOLEAN,
    message_count INTEGER,
    total_cost_cents INTEGER,
    models_used TEXT,  -- JSON array
    metadata TEXT  -- JSON
);

-- Messages table
CREATE TABLE messages (
    bubble_id TEXT PRIMARY KEY,
    composer_id TEXT,
    type INTEGER,  -- 1=user, 2=ai
    content TEXT,
    thinking TEXT,
    model_type TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    tool_calls TEXT,  -- JSON
    capabilities TEXT,  -- JSON
    created_at INTEGER,
    FOREIGN KEY (composer_id) REFERENCES conversations(composer_id)
);
```

### 3. Privacy Filtering

Implement the privacy-first filtering as per our architecture:

```python
def filter_for_privacy(bubble_data):
    """Remove code content, keep only metadata."""

    filtered = {
        'bubble_id': bubble_data['bubbleId'],
        'type': bubble_data['type'],
        'timestamp': bubble_data.get('createdAt'),
    }

    if bubble_data['type'] == 2:  # AI message
        filtered['model'] = bubble_data.get('modelType')
        filtered['tokens'] = bubble_data.get('tokenCount')

        # Keep tool call metadata, not content
        if 'toolFormerdata' in bubble_data:
            filtered['tool_calls'] = [
                {
                    'type': tc['type'],
                    'status': tc['status'],
                    'execution_time': tc.get('executionTime'),
                    # EXCLUDE: arguments, result, diff
                }
                for tc in bubble_data['toolFormerdata']['toolCalls']
            ]

        # Keep capability types, not bubbleDataMap
        if 'capabilities' in bubble_data:
            filtered['capability_types'] = [
                cap['type']
                for cap in bubble_data['capabilities']
            ]

    return filtered
```

### 4. Fast Path Ingestion

```python
async def ingest_cursor_event(event_data):
    """Fast path: write to queue, no reads."""

    # Compress event data
    compressed = zlib.compress(json.dumps(event_data).encode())

    # Write to SQLite (no reads)
    await db.execute(
        "INSERT INTO raw_traces (platform, event_type, composer_id, data, captured_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ('cursor', event_data['type'], event_data['composer_id'], compressed, time.time_ns())
    )

    # Publish to Redis stream for async processing
    await redis.xadd(
        'cursor:events',
        {'event_id': event_data['id'], 'type': event_data['type']}
    )
```

### 5. Slow Path Processing

```python
async def process_composer_event(event_id):
    """Slow path: read from raw_traces, enrich, update conversations."""

    # Read raw event
    event = await get_raw_trace(event_id)
    data = json.loads(zlib.decompress(event['data']))

    # Enrich with derived metrics
    metrics = {
        'message_count': len(data['fullConversationHeadersOnly']),
        'total_tokens': sum_tokens(data),
        'tool_call_count': count_tool_calls(data),
        'models_used': extract_models(data),
        'duration_seconds': calculate_duration(data)
    }

    # Update conversations table (Layer 2 & 3 accessible)
    await update_conversation(data['composerId'], metrics)

    # Update Redis metrics
    await update_redis_metrics(metrics)
```

## Notes on bubbleDataMap

The term "bubbleDataMap" appears in the `capabilities` array but is not extensively documented in the repositories found. Based on the limited references:

```json
"capabilities": [
  {
    "type": "tool_use",
    "bubbleDataMap": {
      // Context-specific metadata about tool execution
      // May include: execution time, token usage, result metadata
      // NOT code content or specific arguments
    }
  }
]
```

This appears to be tool usage metadata specifically, tracking execution characteristics rather than the actual tool call content.

## References

1. **jacquesverre.com** - Detailed schema breakdown: https://jacquesverre.com/blog/cursor-extension
2. **cursor-db-mcp** - MCP server implementation: https://github.com/jbdamask/cursor-db-mcp
3. **cursor-chat-export** - Python export tool: https://github.com/somogyijanos/cursor-chat-export
4. **Cursor-export-extension** - VSCode extension: https://github.com/TsekaLuk/Cursor-export-extension
5. **Cursor Forum** - Export guide: https://forum.cursor.com/t/guide-5-steps-exporting-chats-prompts-from-cursor/2825

## Next Steps for Implementation

1. **Monitor Database Changes**: Implement file watcher for `state.vscdb` modifications
2. **Parse Composer Events**: Extract composer and bubble data using SQL queries from examples
3. **Apply Privacy Filters**: Strip code content, keep only metadata as per schema above
4. **Ingest to Fast Path**: Compress and write to `raw_traces` table
5. **Process in Slow Path**: Enrich and update `conversations` and metrics
6. **Test with Real Data**: Use examples from GitHub repos to validate schema

---

*Document compiled from GitHub research on 2025-11-15*
