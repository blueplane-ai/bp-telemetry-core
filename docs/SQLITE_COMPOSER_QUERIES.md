# SQLite Composer Data Query Patterns

This document provides SQL query patterns for extracting composer and bubble data from Cursor's SQLite databases.

## Database Locations

### Workspace Storage
- **macOS**: `~/Library/Application Support/Cursor/User/workspaceStorage/{hash}/state.vscdb`
- **Linux**: `~/.config/Cursor/User/workspaceStorage/{hash}/state.vscdb`
- **Windows**: `%APPDATA%\Cursor\User\workspaceStorage\{hash}\state.vscdb`

### Global Storage
- **macOS**: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- **Linux**: `~/.config/Cursor/User/globalStorage/state.vscdb`
- **Windows**: `%APPDATA%\Cursor\User\globalStorage\state.vscdb`

## Table Structure

```sql
-- Main tables
CREATE TABLE ItemTable (
    key TEXT UNIQUE ON CONFLICT REPLACE,
    value BLOB
);

CREATE TABLE cursorDiskKV (
    key TEXT UNIQUE ON CONFLICT REPLACE,
    value BLOB
);
```

## Query Patterns

### 1. Discover All Databases

```python
from pathlib import Path
import platform

def discover_databases():
    home = Path.home()
    system = platform.system()
    
    databases = []
    
    # Workspace storage
    if system == "Darwin":
        base = home / "Library/Application Support/Cursor/User/workspaceStorage"
    elif system == "Linux":
        base = home / ".config/Cursor/User/workspaceStorage"
    else:  # Windows
        base = home / "AppData/Roaming/Cursor/User/workspaceStorage"
    
    if base.exists():
        for workspace_dir in base.iterdir():
            db_file = workspace_dir / "state.vscdb"
            if db_file.exists():
                databases.append(db_file)
    
    # Global storage
    global_paths = [
        home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        home / ".config/Cursor/User/globalStorage/state.vscdb",
        home / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
    ]
    
    for path in global_paths:
        if path.exists():
            databases.append(path)
    
    return databases
```

### 2. Get Composer Metadata from ItemTable

```sql
-- Get composer list metadata
SELECT value FROM ItemTable WHERE key = 'composer.composerData';
```

**Returns**: JSON object with structure:
```json
{
  "allComposers": [
    {
      "composerId": "uuid",
      "createdAt": 1234567890123,
      "name": "Conversation Title",
      ...
    }
  ],
  "selectedComposerIds": [...],
  "lastFocusedComposerIds": [...]
}
```

**Python Example**:
```python
import sqlite3
import json

conn = sqlite3.connect("file:state.vscdb?mode=ro", uri=True)
cursor = conn.cursor()
cursor.execute("SELECT value FROM ItemTable WHERE key = ?", ('composer.composerData',))
row = cursor.fetchone()

if row and row[0]:
    value = row[0]
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    composer_data = json.loads(value)
    composer_ids = [c['composerId'] for c in composer_data.get('allComposers', [])]
```

### 3. Get Full Composer Data from cursorDiskKV

```sql
-- Get specific composer by ID
SELECT value FROM cursorDiskKV WHERE key = 'composerData:{composerId}';

-- Get all composers
SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%';
```

**Returns**: Full composer object with:
- `composerId`, `name`, `createdAt`, `lastUpdatedAt`
- `fullConversationHeadersOnly` (array of bubble references)
- `latestConversationSummary`
- `usageData` (model costs)
- `context` (attached files, selections)

**Python Example**:
```python
cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'composerData:{composer_id}',))
row = cursor.fetchone()

if row and row[0]:
    value = row[0]
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    composer = json.loads(value)
    
    # Extract bubble IDs
    bubble_ids = [
        bubble['bubbleId'] 
        for bubble in composer.get('fullConversationHeadersOnly', [])
    ]
```

### 4. Get Bubble (Message) Data

```sql
-- Get specific bubble
SELECT value FROM cursorDiskKV WHERE key = 'bubbleData:{bubbleId}';

-- Get multiple bubbles (requires multiple queries)
-- Use Python loop:
for bubble_id in bubble_ids:
    cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'bubbleData:{bubble_id}',))
```

**Returns**: Full bubble object with:
- **Message Content**: `text`, `rawText`, `richText`, `delegate`
- **Message Type**: `type` (1=user, 2=ai)
- **Model Config**: `modelType`, `aiStreamingSettings`
- **Thinking**: `thinking`
- **Tool Usage**: `toolFormerdata.toolCalls[]`
- **Capabilities**: `capabilities[]` with `bubbleDataMap`
- **Metadata**: `bubbleId`, `createdAt`, `tokenCount`, etc.

**Python Example**:
```python
def get_bubble_data(db_path, bubble_id):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'bubbleData:{bubble_id}',))
    row = cursor.fetchone()
    
    if row and row[0]:
        value = row[0]
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return json.loads(value)
    
    return None
```

### 5. Extract Full Conversation

```python
def extract_full_conversation(db_path, composer_id):
    """Extract complete conversation with all messages."""
    
    # 1. Get composer metadata
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'composerData:{composer_id}',))
    row = cursor.fetchone()
    composer = json.loads(row[0].decode('utf-8') if isinstance(row[0], bytes) else row[0])
    
    # 2. Get all bubbles
    conversation = {
        'composerId': composer['composerId'],
        'name': composer.get('name'),
        'createdAt': composer['createdAt'],
        'messages': []
    }
    
    for bubble_ref in composer.get('fullConversationHeadersOnly', []):
        bubble_id = bubble_ref['bubbleId']
        
        cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'bubbleData:{bubble_id}',))
        bubble_row = cursor.fetchone()
        
        if bubble_row:
            bubble = json.loads(bubble_row[0].decode('utf-8') if isinstance(bubble_row[0], bytes) else bubble_row[0])
            
            message = {
                'bubbleId': bubble['bubbleId'],
                'type': 'user' if bubble['type'] == 1 else 'ai',
                'content': bubble.get('text') or bubble.get('rawText'),
                'model': bubble.get('modelType'),
                'thinking': bubble.get('thinking'),
                'toolCalls': bubble.get('toolFormerdata', {}).get('toolCalls', []),
                'capabilities': bubble.get('capabilities', []),
                'createdAt': bubble.get('createdAt'),
            }
            
            conversation['messages'].append(message)
    
    conn.close()
    return conversation
```

## Performance Notes

### Read-Only Mode
Always open databases in read-only mode to avoid locking:
```python
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
```

### PRAGMA Settings
For better performance and compatibility:
```sql
PRAGMA read_uncommitted=1;
PRAGMA journal_mode=WAL;
```

### Batch Queries
When fetching multiple bubbles, consider batching:
```python
# Instead of individual queries, use IN clause (if supported)
bubble_ids_str = ','.join(f"'{bid}'" for bid in bubble_ids)
cursor.execute(f"SELECT key, value FROM cursorDiskKV WHERE key IN ({bubble_ids_str})")
```

## Error Handling

### Database Lock Errors
```python
import time
import random

def query_with_retry(db_path, query, params, max_retries=3):
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            conn.close()
            return result
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt) + random.uniform(0, 0.1))
                continue
            raise
```

### JSON Parse Errors
```python
def safe_json_loads(value):
    try:
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Error parsing JSON: {e}")
        return None
```

### Missing Keys
```python
def get_value_safe(cursor, table, key):
    try:
        cursor.execute(f'SELECT value FROM "{table}" WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"Error querying {table} for key {key}: {e}")
        return None
```

## Schema Version Differences

### Composer Schema Version 3
```json
{
  "_v": 3,
  "composerId": "...",
  "fullConversationHeadersOnly": [...],
  "latestConversationSummary": {...}
}
```

### Bubble Schema Version 2
```json
{
  "_v": 2,
  "bubbleId": "...",
  "type": 1,
  "text": "...",
  "toolFormerdata": {...}
}
```

Always check `_v` field to handle schema differences.

## Example: Complete Extraction Pipeline

```python
import sqlite3
import json
from pathlib import Path

def extract_all_composers(db_path):
    """Extract all composers with full conversation data."""
    
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    
    # 1. Get composer list
    cursor.execute("SELECT value FROM ItemTable WHERE key = ?", ('composer.composerData',))
    row = cursor.fetchone()
    composer_list = json.loads(row[0].decode('utf-8'))
    
    composers = []
    
    # 2. For each composer, get full data
    for composer_ref in composer_list.get('allComposers', []):
        composer_id = composer_ref['composerId']
        
        # Get full composer data
        cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'composerData:{composer_id}',))
        composer_row = cursor.fetchone()
        
        if not composer_row:
            continue
        
        composer = json.loads(composer_row[0].decode('utf-8'))
        
        # 3. Get all bubbles
        messages = []
        for bubble_ref in composer.get('fullConversationHeadersOnly', []):
            bubble_id = bubble_ref['bubbleId']
            
            cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'bubbleData:{bubble_id}',))
            bubble_row = cursor.fetchone()
            
            if bubble_row:
                bubble = json.loads(bubble_row[0].decode('utf-8'))
                messages.append(bubble)
        
        composer['messages'] = messages
        composers.append(composer)
    
    conn.close()
    return composers
```

## Key Patterns Summary

| Data Type | Table | Key Pattern | Notes |
|-----------|-------|-------------|-------|
| Composer list | ItemTable | `composer.composerData` | Workspace storage |
| Full composer | cursorDiskKV | `composerData:{id}` | Global storage |
| Bubble data | cursorDiskKV | `bubbleData:{id}` | Global storage |
| AI generations | ItemTable | `aiService.generations` | Workspace storage |
| Prompts | ItemTable | `aiService.prompts` | Workspace storage |

## References

- Research document: `docs/research/cursor-composer-data-capture-examples.md`
- Database audit: `docs/CURSOR_DISK_KV_AUDIT.md`
- GitHub examples: See research document for repository links






