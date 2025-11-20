<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Session and Conversation Schema Design

> Design rationale and migration strategy for handling sessions and conversations across Claude Code and Cursor platforms

## Table of Contents

- [Overview](#overview)
- [Platform Differences](#platform-differences)
- [Schema Design](#schema-design)
- [Migration Strategy](#migration-strategy)
- [Query Patterns](#query-patterns)
- [Implementation Notes](#implementation-notes)
- [Data Integrity](#data-integrity)

## Overview

The telemetry system handles sessions and conversations differently across platforms:

- **Claude Code**: Sessions and conversations are 1:1. A new Claude Code session is essentially a new conversation.
- **Cursor**: Sessions represent IDE window instances, which can contain multiple chat conversations over time.

This document describes the unified schema design that accommodates both models while maintaining clarity and query efficiency.

## Platform Differences

### Claude Code

- **Session = Conversation** (1:1 mapping)
- When a Claude Code session starts, a conversation is created immediately
- No separate session concept needed
- Session lifecycle is conversation lifecycle

### Cursor

- **Session ≠ Conversation** (1:many mapping)
- Session represents an IDE window/workspace instance
- Multiple chat conversations can occur within a single session
- Session lifecycle is independent of individual conversations

## Schema Design

### Core Principle

**Sessions only exist for Cursor.** Claude Code has no session concept—only conversations exist.

### Schema Structure

```sql
-- Cursor Sessions Table
-- Only Cursor has sessions (IDE window instances)
CREATE TABLE IF NOT EXISTS cursor_sessions (
    id TEXT PRIMARY KEY,                          -- Internal session ID (UUID)
    external_session_id TEXT NOT NULL UNIQUE,     -- From Cursor extension
    workspace_hash TEXT NOT NULL,                  -- Workspace identifier
    workspace_name TEXT,                           -- Human-readable name
    workspace_path TEXT,                           -- Full workspace path
    started_at TIMESTAMP NOT NULL,                -- Session start time
    ended_at TIMESTAMP,                           -- Session end time (NULL if active)
    metadata TEXT DEFAULT '{}',                   -- JSON metadata
    
    INDEX idx_cursor_sessions_workspace ON cursor_sessions(workspace_hash),
    INDEX idx_cursor_sessions_time ON cursor_sessions(started_at DESC),
    INDEX idx_cursor_sessions_external ON cursor_sessions(external_session_id)
);

-- Conversations Table
-- Unified table for both platforms
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,                          -- Internal conversation ID (UUID)
    session_id TEXT,                              -- NULL for Claude, references cursor_sessions.id for Cursor
    external_id TEXT NOT NULL,                    -- Platform-specific external ID
    platform TEXT NOT NULL,                       -- 'claude_code' or 'cursor'
    workspace_hash TEXT,                          -- Workspace identifier
    workspace_name TEXT,                          -- Human-readable workspace name
    started_at TIMESTAMP NOT NULL,                -- Conversation start time
    ended_at TIMESTAMP,                           -- Conversation end time
    
    -- JSON fields
    context TEXT DEFAULT '{}',                    -- Conversation context
    metadata TEXT DEFAULT '{}',                   -- Additional metadata
    tool_sequence TEXT DEFAULT '[]',              -- Tool usage sequence
    acceptance_decisions TEXT DEFAULT '[]',       -- Code acceptance decisions
    
    -- Metrics
    interaction_count INTEGER DEFAULT 0,           -- Number of interactions
    acceptance_rate REAL,                         -- Code acceptance rate
    total_tokens INTEGER DEFAULT 0,               -- Total tokens used
    total_changes INTEGER DEFAULT 0,              -- Total code changes
    
    -- Foreign key constraint (only enforced when session_id IS NOT NULL)
    FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
    
    -- Data integrity constraint
    CHECK (
        (platform = 'cursor' AND session_id IS NOT NULL) OR
        (platform = 'claude_code' AND session_id IS NULL)
    ),
    
    -- Unique constraint: external_id must be unique per platform
    UNIQUE(external_id, platform)
);

-- Indexes for optimal query performance
CREATE INDEX IF NOT EXISTS idx_conversations_session_cursor 
    ON conversations(session_id) WHERE platform = 'cursor';
    
CREATE INDEX IF NOT EXISTS idx_conversations_external 
    ON conversations(external_id, platform);
    
CREATE INDEX IF NOT EXISTS idx_conversations_platform_time 
    ON conversations(platform, started_at DESC);
    
CREATE INDEX IF NOT EXISTS idx_conversations_workspace 
    ON conversations(workspace_hash) WHERE workspace_hash IS NOT NULL;
```

### Field Semantics

#### `conversations.session_id`

- **Cursor**: References `cursor_sessions.id` (NOT NULL)
- **Claude Code**: NULL (no session concept)

#### `conversations.external_id`

- **Cursor**: Conversation-specific external identifier (e.g., from Cursor's internal systems)
- **Claude Code**: Claude session/conversation ID (acts as both session and conversation identifier)

#### `cursor_sessions.external_session_id`

- **Cursor**: Session ID from Cursor extension (e.g., `curs_1731283200000_abc123`)
- Used to match incoming events to existing sessions

## Migration Strategy

### Current State

The existing schema has:
- `conversations.session_id` (NOT NULL) - Currently set for both platforms
- `conversations.external_session_id` (NOT NULL) - Platform-specific external ID

### Migration Steps

#### Step 1: Create `cursor_sessions` Table

```sql
-- Create cursor_sessions table
CREATE TABLE IF NOT EXISTS cursor_sessions (
    id TEXT PRIMARY KEY,
    external_session_id TEXT NOT NULL UNIQUE,
    workspace_hash TEXT NOT NULL,
    workspace_name TEXT,
    workspace_path TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_cursor_sessions_workspace 
    ON cursor_sessions(workspace_hash);
CREATE INDEX IF NOT EXISTS idx_cursor_sessions_time 
    ON cursor_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cursor_sessions_external 
    ON cursor_sessions(external_session_id);
```

#### Step 2: Migrate Existing Cursor Sessions

```sql
-- Extract unique Cursor sessions from conversations table
-- This assumes we can identify Cursor conversations by platform='cursor'
INSERT INTO cursor_sessions (
    id,
    external_session_id,
    workspace_hash,
    workspace_name,
    workspace_path,
    started_at,
    ended_at,
    metadata
)
SELECT DISTINCT
    -- Generate new UUID for internal session ID
    lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-' || 
          hex(randomblob(2)) || '-' || hex(randomblob(2)) || '-' || 
          hex(randomblob(6))) as id,
    session_id as external_session_id,  -- Use current session_id as external_session_id
    workspace_hash,
    workspace_name,
    json_extract(context, '$.workspace_path') as workspace_path,
    started_at,
    ended_at,
    metadata
FROM conversations
WHERE platform = 'cursor'
GROUP BY session_id, workspace_hash, workspace_name, started_at;
```

**Note**: This step requires careful handling if there are duplicate `session_id` values. Adjust the GROUP BY as needed.

#### Step 3: Rename Column and Update Constraints

```sql
-- SQLite doesn't support ALTER TABLE RENAME COLUMN directly
-- We need to:
-- 1. Create new table with correct schema
-- 2. Copy data
-- 3. Drop old table
-- 4. Rename new table

-- Create new conversations table with updated schema
CREATE TABLE conversations_new (
    id TEXT PRIMARY KEY,
    session_id TEXT,  -- Now nullable
    external_id TEXT NOT NULL,  -- Renamed from external_session_id
    platform TEXT NOT NULL,
    workspace_hash TEXT,
    workspace_name TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    context TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    tool_sequence TEXT DEFAULT '[]',
    acceptance_decisions TEXT DEFAULT '[]',
    interaction_count INTEGER DEFAULT 0,
    acceptance_rate REAL,
    total_tokens INTEGER DEFAULT 0,
    total_changes INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
    CHECK (
        (platform = 'cursor' AND session_id IS NOT NULL) OR
        (platform = 'claude_code' AND session_id IS NULL)
    ),
    UNIQUE(external_id, platform)
);

-- Copy data with transformation
INSERT INTO conversations_new (
    id,
    session_id,
    external_id,
    platform,
    workspace_hash,
    workspace_name,
    started_at,
    ended_at,
    context,
    metadata,
    tool_sequence,
    acceptance_decisions,
    interaction_count,
    acceptance_rate,
    total_tokens,
    total_changes
)
SELECT 
    id,
    -- For Cursor: Look up cursor_sessions.id by external_session_id
    CASE 
        WHEN platform = 'cursor' THEN (
            SELECT cs.id 
            FROM cursor_sessions cs 
            WHERE cs.external_session_id = c.session_id
        )
        -- For Claude: Set to NULL
        WHEN platform = 'claude_code' THEN NULL
        ELSE NULL
    END as session_id,
    external_session_id as external_id,  -- Rename column
    platform,
    workspace_hash,
    workspace_name,
    started_at,
    ended_at,
    context,
    metadata,
    tool_sequence,
    acceptance_decisions,
    interaction_count,
    acceptance_rate,
    total_tokens,
    total_changes
FROM conversations c;

-- Drop old table
DROP TABLE conversations;

-- Rename new table
ALTER TABLE conversations_new RENAME TO conversations;
```

#### Step 4: Create Indexes

```sql
-- Create optimized indexes
CREATE INDEX IF NOT EXISTS idx_conversations_session_cursor 
    ON conversations(session_id) WHERE platform = 'cursor';
    
CREATE INDEX IF NOT EXISTS idx_conversations_external 
    ON conversations(external_id, platform);
    
CREATE INDEX IF NOT EXISTS idx_conversations_platform_time 
    ON conversations(platform, started_at DESC);
    
CREATE INDEX IF NOT EXISTS idx_conversations_workspace 
    ON conversations(workspace_hash) WHERE workspace_hash IS NOT NULL;
```

#### Step 5: Update Foreign Key Relationships

```sql
-- Verify foreign keys are intact
PRAGMA foreign_key_check;
```

### Migration Script Implementation

A Python migration script should:

1. **Backup database** before migration
2. **Validate data** (check for orphaned records, duplicates)
3. **Execute migration** in transaction
4. **Verify integrity** after migration
5. **Report results** (rows migrated, errors, etc.)

Example migration script structure:

```python
def migrate_sessions_and_conversations(db_path: str):
    """
    Migrate to new session/conversation schema.
    
    Steps:
    1. Create cursor_sessions table
    2. Migrate Cursor sessions from conversations
    3. Rename external_session_id to external_id
    4. Update session_id references
    5. Add constraints and indexes
    """
    # Implementation details...
```

### Rollback Strategy

If migration fails:

1. **Restore from backup** (if transaction rolled back)
2. **Manual rollback**:
   ```sql
   -- Drop new tables
   DROP TABLE IF EXISTS cursor_sessions;
   DROP TABLE IF EXISTS conversations_new;
   
   -- Restore original schema (if needed)
   -- Recreate conversations table with old schema
   ```

## Query Patterns

### Claude Code Queries

```sql
-- Get conversation by external_id (Claude session/conversation ID)
SELECT * FROM conversations 
WHERE external_id = ? AND platform = 'claude_code';

-- Get all Claude conversations for a workspace
SELECT * FROM conversations 
WHERE platform = 'claude_code' AND workspace_hash = ?
ORDER BY started_at DESC;

-- Get active Claude conversations (not ended)
SELECT * FROM conversations 
WHERE platform = 'claude_code' AND ended_at IS NULL
ORDER BY started_at DESC;
```

### Cursor Queries

```sql
-- Get all conversations in a Cursor session
SELECT c.* FROM conversations c
WHERE c.session_id = ? AND c.platform = 'cursor'
ORDER BY c.started_at ASC;

-- Get Cursor session with all its conversations
SELECT 
    s.*,
    COUNT(c.id) as conversation_count,
    SUM(c.total_tokens) as total_tokens,
    SUM(c.interaction_count) as total_interactions
FROM cursor_sessions s
LEFT JOIN conversations c ON c.session_id = s.id
WHERE s.external_session_id = ?
GROUP BY s.id;

-- Get active Cursor sessions
SELECT s.*, COUNT(c.id) as active_conversations
FROM cursor_sessions s
LEFT JOIN conversations c ON c.session_id = s.id AND c.ended_at IS NULL
WHERE s.ended_at IS NULL
GROUP BY s.id;
```

### Cross-Platform Queries

```sql
-- Get all conversations for a workspace (both platforms)
SELECT * FROM conversations 
WHERE workspace_hash = ?
ORDER BY platform, started_at DESC;

-- Get recent conversations across platforms
SELECT * FROM conversations 
ORDER BY started_at DESC 
LIMIT 50;

-- Platform-aware conversation lookup
SELECT * FROM conversations 
WHERE 
    (platform = 'cursor' AND session_id = ?) OR
    (platform = 'claude_code' AND external_id = ?);
```

## Implementation Notes

### Application Logic

#### Creating Conversations

**Claude Code:**
```python
# Claude Code: No session, just create conversation
conversation_id = str(uuid.uuid4())
cursor.execute("""
    INSERT INTO conversations (
        id, session_id, external_id, platform,
        workspace_hash, workspace_name, started_at, ...
    ) VALUES (?, NULL, ?, 'claude_code', ?, ?, ?, ...)
""", (conversation_id, claude_session_id, workspace_hash, ...))
```

**Cursor:**
```python
# Cursor: First ensure session exists, then create conversation
session_id = ensure_cursor_session(external_session_id, workspace_hash, ...)
conversation_id = str(uuid.uuid4())
cursor.execute("""
    INSERT INTO conversations (
        id, session_id, external_id, platform,
        workspace_hash, workspace_name, started_at, ...
    ) VALUES (?, ?, ?, 'cursor', ?, ?, ?, ...)
""", (conversation_id, session_id, conversation_external_id, workspace_hash, ...))
```

#### Querying Conversations

Always check platform before assuming `session_id` exists:

```python
def get_conversation(conversation_id: str, platform: str):
    if platform == 'claude_code':
        # Use external_id lookup
        return db.execute("""
            SELECT * FROM conversations 
            WHERE external_id = ? AND platform = 'claude_code'
        """, (conversation_id,))
    else:
        # Use session_id lookup
        return db.execute("""
            SELECT c.* FROM conversations c
            JOIN cursor_sessions s ON c.session_id = s.id
            WHERE c.id = ? AND c.platform = 'cursor'
        """, (conversation_id,))
```

### Session Management (Cursor Only)

```python
def create_cursor_session(external_session_id: str, workspace_hash: str, ...):
    """Create or get existing Cursor session."""
    session_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT OR IGNORE INTO cursor_sessions (
            id, external_session_id, workspace_hash, ...
        ) VALUES (?, ?, ?, ...)
    """, (session_id, external_session_id, workspace_hash, ...))
    return session_id

def get_cursor_session_by_external(external_session_id: str):
    """Get Cursor session by external ID."""
    cursor.execute("""
        SELECT * FROM cursor_sessions 
        WHERE external_session_id = ?
    """, (external_session_id,))
    return cursor.fetchone()
```

## Data Integrity

### Constraints

1. **CHECK Constraint**: Ensures `session_id` is NULL for Claude, NOT NULL for Cursor
2. **FOREIGN KEY**: Ensures `session_id` references valid `cursor_sessions.id` (when not NULL)
3. **UNIQUE Constraint**: `external_id` must be unique per platform

### Validation Queries

```sql
-- Check for invalid session_id values
SELECT * FROM conversations 
WHERE (platform = 'cursor' AND session_id IS NULL) OR
      (platform = 'claude_code' AND session_id IS NOT NULL);

-- Check for orphaned Cursor conversations
SELECT c.* FROM conversations c
LEFT JOIN cursor_sessions s ON c.session_id = s.id
WHERE c.platform = 'cursor' AND s.id IS NULL;

-- Verify external_id uniqueness per platform
SELECT external_id, platform, COUNT(*) as count
FROM conversations
GROUP BY external_id, platform
HAVING count > 1;
```

### Error Handling

Application code should handle:

1. **NULL session_id for Claude**: Expected behavior, not an error
2. **Missing cursor_sessions**: Create session before creating conversation
3. **Duplicate external_id**: Handle gracefully (INSERT OR IGNORE or UPDATE)

## Summary

This schema design:

- ✅ **Aligns with domain models**: Sessions only exist where they matter (Cursor)
- ✅ **Maintains simplicity**: Claude Code doesn't need session abstraction
- ✅ **Enables efficient queries**: Platform-specific indexes optimize common patterns
- ✅ **Ensures data integrity**: CHECK constraints and foreign keys prevent invalid states
- ✅ **Supports future growth**: Easy to extend with additional platforms

The migration strategy ensures a smooth transition from the current schema while preserving all existing data.

