# Cursor Data Location Master README

This document provides a comprehensive guide to where all Cursor composer and bubble data is located, both at the user (global) and workspace levels. It also identifies what information is missing and cannot be retrieved from the database.

## Table of Contents

1. [Database Locations](#database-locations)
2. [Data Storage Architecture](#data-storage-architecture)
3. [Field Location Reference](#field-location-reference)
4. [Missing Fields](#missing-fields)
5. [Scripts Reference](#scripts-reference)
6. [Query Patterns](#query-patterns)

---

## Database Locations

### User-Level (Global Storage)

**Location**: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (macOS)

**Contains**:

- Full composer data with embedded bubbles
- All composer conversations across all workspaces
- Global user settings and configuration

**Tables**:

- `cursorDiskKV` - Primary storage for composer data
- `ItemTable` - May contain global configuration

### Workspace-Level (Per-Workspace Storage)

**Location**: `~/Library/Application Support/Cursor/User/workspaceStorage/{hash}/state.vscdb` (macOS)

**Contains**:

- Composer metadata (IDs, names, timestamps) - **NOT full conversations**
- Workspace-specific AI service data
- Workspace-specific settings

**Tables**:

- `ItemTable` - Contains `composer.composerData` (metadata only)
- `cursorDiskKV` - May contain workspace-specific data

**Key Finding**: Bubbles are **NOT** stored in workspace storage. They are only in global storage.

---

## Data Storage Architecture

### Composer Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Workspace Storage (ItemTable)                               │
│ Key: composer.composerData                                  │
│ Contains: Metadata only (IDs, names, timestamps)            │
│                                                             │
│ Structure:                                                  │
│ {                                                           │
│   "allComposers": [                                         │
│     { composerId, name, createdAt, lastUpdatedAt }          │
│   ]                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ composerId references
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Global Storage (cursorDiskKV)                               │
│ Key: composerData:{composerId}                              │
│ Contains: Full composer data WITH embedded bubbles          │
│                                                             │
│ Structure:                                                  │
│ {                                                           │
│   composerId, name, createdAt, lastUpdatedAt,              │
│   conversation: [                                           │
│     { bubbleId, type, text, ... }  ← Bubbles embedded here  │
│   ]                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### Key Discovery

**Bubbles are embedded in composer data**, not stored as separate `bubbleData:{id}` entries.

- ❌ **NOT**: `bubbleData:{bubbleId}` keys in cursorDiskKV
- ✅ **ACTUAL**: Bubbles embedded in `composerData:{composerId}.conversation` array

---

## Field Location Reference

### Composer-Level Fields

| Field                         | Location           | Table                    | Key Pattern                                   | Status     | Notes                                                    |
| ----------------------------- | ------------------ | ------------------------ | --------------------------------------------- | ---------- | -------------------------------------------------------- |
| `composerId`                  | Workspace + Global | ItemTable / cursorDiskKV | `composer.composerData` / `composerData:{id}` | ✅ Found   | UUID identifier                                          |
| `name`                        | Workspace + Global | ItemTable / cursorDiskKV | `composer.composerData` / `composerData:{id}` | ✅ Found   | Conversation title (may be null)                         |
| `createdAt`                   | Workspace + Global | ItemTable / cursorDiskKV | `composer.composerData` / `composerData:{id}` | ✅ Found   | Unix timestamp (ms)                                      |
| `lastUpdatedAt`               | Workspace + Global | ItemTable / cursorDiskKV | `composer.composerData` / `composerData:{id}` | ✅ Found   | Unix timestamp (ms), may be null                         |
| `status`                      | Global             | cursorDiskKV             | `composerData:{id}`                           | ⚠️ Partial | Not always present                                       |
| `isAgentic`                   | Global             | cursorDiskKV             | `composerData:{id}`                           | ⚠️ Partial | Boolean flag, not always present                         |
| `_v`                          | Global             | cursorDiskKV             | `composerData:{id}`                           | ⚠️ Partial | Schema version, not always present                       |
| `fullConversationHeadersOnly` | Global             | cursorDiskKV             | `composerData:{id}`                           | ✅ Found   | Array of bubble references (may be empty)                |
| `conversation`                | Global             | cursorDiskKV             | `composerData:{id}`                           | ✅ Found   | Alternative field name, contains embedded bubbles        |
| `latestConversationSummary`   | Global             | cursorDiskKV             | `composerData:{id}`                           | ⚠️ Partial | Summary object, not always present                       |
| `usageData`                   | Global             | cursorDiskKV             | `composerData:{id}`                           | ❌ Missing | Expected but not found in current schema                 |
| `context`                     | Global             | cursorDiskKV             | `composerData:{id}`                           | ⚠️ Partial | Context object (attachedFiles, selections), may be empty |

**Extraction Path**:

1. Query `ItemTable` in workspace storage: `SELECT value FROM ItemTable WHERE key = 'composer.composerData'`
2. Parse JSON to get `allComposers` array
3. For each composer, query global storage: `SELECT value FROM cursorDiskKV WHERE key = 'composerData:{composerId}'`
4. Parse JSON to get full composer data with embedded bubbles

---

### Bubble-Level Fields

Bubbles are embedded in the `conversation` array within `composerData:{composerId}` entries in global storage.

#### Basic Identification Fields

| Field            | Location | Path                                              | Status     | Notes                              |
| ---------------- | -------- | ------------------------------------------------- | ---------- | ---------------------------------- |
| `bubbleId`       | Global   | `composerData:{id}.conversation[].bubbleId`       | ✅ Found   | UUID identifier                    |
| `serverBubbleId` | Global   | `composerData:{id}.conversation[].serverBubbleId` | ✅ Found   | Server-side identifier             |
| `type`           | Global   | `composerData:{id}.conversation[].type`           | ✅ Found   | 1=user, 2=ai                       |
| `_v`             | Global   | `composerData:{id}.conversation[]._v`             | ⚠️ Partial | Schema version, not always present |

#### Message Content Fields

| Field      | Location | Path                                        | Status     | Notes                                    |
| ---------- | -------- | ------------------------------------------- | ---------- | ---------------------------------------- |
| `text`     | Global   | `composerData:{id}.conversation[].text`     | ✅ Found   | Displayed message content                |
| `rawText`  | Global   | `composerData:{id}.conversation[].rawText`  | ⚠️ Partial | Plain text version, not always present   |
| `richText` | Global   | `composerData:{id}.conversation[].richText` | ⚠️ Partial | Lexical editor state, not always present |
| `delegate` | Global   | `composerData:{id}.conversation[].delegate` | ⚠️ Partial | Delegate content, not always present     |

**Content Availability**: At least one of `text`, `rawText`, or `delegate` is typically present.

#### Model Configuration Fields

| Field                 | Location | Path                                                   | Status     | Notes                       |
| --------------------- | -------- | ------------------------------------------------------ | ---------- | --------------------------- |
| `modelType`           | Global   | `composerData:{id}.conversation[].modelType`           | ❌ Missing | Not found in current schema |
| `aiStreamingSettings` | Global   | `composerData:{id}.conversation[].aiStreamingSettings` | ❌ Missing | Not found in current schema |

**Status**: Model information is **NOT stored at the bubble level**. See [Missing Fields](#missing-fields) section.

#### Thinking/Reasoning Fields

| Field                | Location | Path                                                  | Status     | Notes                                                     |
| -------------------- | -------- | ----------------------------------------------------- | ---------- | --------------------------------------------------------- |
| `thinking`           | Global   | `composerData:{id}.conversation[].thinking`           | ❌ Missing | Not found in current schema                               |
| `isThought`          | Global   | `composerData:{id}.conversation[].isThought`          | ⚠️ Partial | Boolean flag, not always present                          |
| `intermediateChunks` | Global   | `composerData:{id}.conversation[].intermediateChunks` | ⚠️ Partial | Array, may contain thinking content (needs investigation) |

**Status**: Thinking content is **NOT reliably available**. `intermediateChunks` may contain it but structure needs investigation.

#### Tool Usage Fields

| Field                        | Location | Path                                                        | Status     | Notes                                                                  |
| ---------------------------- | -------- | ----------------------------------------------------------- | ---------- | ---------------------------------------------------------------------- |
| `toolFormerdata`             | Global   | `composerData:{id}.conversation[].toolFormerdata`           | ❌ Missing | Expected format not found                                              |
| `toolFormerdata.toolCalls[]` | Global   | `composerData:{id}.conversation[].toolFormerdata.toolCalls` | ❌ Missing | Expected format not found                                              |
| `codeBlocks`                 | Global   | `composerData:{id}.conversation[].codeBlocks`               | ⚠️ Partial | Array, may contain tool execution results (needs investigation)        |
| `capabilitiesRan`            | Global   | `composerData:{id}.conversation[].capabilitiesRan`          | ✅ Found   | Dict with capability names as keys (different structure than expected) |

**Status**: Tool usage data exists but in a **different structure** than expected:

- Expected: `toolFormerdata.toolCalls[]` array
- Actual: `capabilitiesRan` dict with capability names as keys
- `codeBlocks` may contain execution results (needs investigation)

#### Capability Fields

| Field                                   | Location | Path                                                            | Status     | Notes                                          |
| --------------------------------------- | -------- | --------------------------------------------------------------- | ---------- | ---------------------------------------------- |
| `capabilities`                          | Global   | `composerData:{id}.conversation[].capabilities`                 | ⚠️ Partial | Array format, not always present               |
| `capabilitiesRan`                       | Global   | `composerData:{id}.conversation[].capabilitiesRan`              | ✅ Found   | Dict format (actual field name)                |
| `capabilityStatuses`                    | Global   | `composerData:{id}.conversation[].capabilityStatuses`           | ✅ Found   | Dict format (actual field name)                |
| `capabilities[].bubbleDataMap`          | Global   | `composerData:{id}.conversation[].capabilities[].bubbleDataMap` | ❌ Missing | Expected format not found                      |
| `capabilityStatuses` (as bubbleDataMap) | Global   | `composerData:{id}.conversation[].capabilityStatuses`           | ⚠️ Partial | May serve similar purpose, needs investigation |

**Status**: Capabilities exist but structure differs:

- Expected: `capabilities[]` array with `bubbleDataMap` inside
- Actual: `capabilitiesRan` dict and `capabilityStatuses` dict

#### Timing/Metadata Fields

| Field                          | Location | Path                                                            | Status     | Notes                           |
| ------------------------------ | -------- | --------------------------------------------------------------- | ---------- | ------------------------------- |
| `createdAt`                    | Global   | `composerData:{id}.conversation[].createdAt`                    | ⚠️ Partial | Not always present at top level |
| `lastUpdatedAt`                | Global   | `composerData:{id}.conversation[].lastUpdatedAt`                | ⚠️ Partial | Not always present at top level |
| `completedAt`                  | Global   | `composerData:{id}.conversation[].completedAt`                  | ⚠️ Partial | Not always present at top level |
| `timingInfo`                   | Global   | `composerData:{id}.conversation[].timingInfo`                   | ✅ Found   | Dict containing timing data     |
| `timingInfo.clientStartTime`   | Global   | `composerData:{id}.conversation[].timingInfo.clientStartTime`   | ✅ Found   | Unix timestamp (ms)             |
| `timingInfo.clientRpcSendTime` | Global   | `composerData:{id}.conversation[].timingInfo.clientRpcSendTime` | ✅ Found   | Unix timestamp (ms)             |
| `timingInfo.clientSettleTime`  | Global   | `composerData:{id}.conversation[].timingInfo.clientSettleTime`  | ✅ Found   | Unix timestamp (ms)             |
| `timingInfo.clientEndTime`     | Global   | `composerData:{id}.conversation[].timingInfo.clientEndTime`     | ✅ Found   | Unix timestamp (ms)             |

**Field Mapping**:

- `createdAt` → `timingInfo.clientStartTime` (if `createdAt` not present)
- `lastUpdatedAt` → `timingInfo.clientEndTime` (if `lastUpdatedAt` not present)
- `completedAt` → `timingInfo.clientSettleTime` (if `completedAt` not present)

#### Token Count Fields

| Field                     | Location | Path                                                       | Status     | Notes                                         |
| ------------------------- | -------- | ---------------------------------------------------------- | ---------- | --------------------------------------------- |
| `tokenCount`              | Global   | `composerData:{id}.conversation[].tokenCount`              | ❌ Missing | Expected object with inputTokens/outputTokens |
| `tokenCountUpUntilHere`   | Global   | `composerData:{id}.conversation[].tokenCountUpUntilHere`   | ⚠️ Partial | Cumulative token count, not always present    |
| `tokenDetailsUpUntilHere` | Global   | `composerData:{id}.conversation[].tokenDetailsUpUntilHere` | ⚠️ Partial | Detailed token info, not always present       |

**Status**: Token counts exist but in different format:

- Expected: `tokenCount.inputTokens` and `tokenCount.outputTokens`
- Actual: `tokenCountUpUntilHere` (cumulative, not per-message breakdown)

#### Other Metadata Fields

| Field            | Location | Path                                              | Status     | Notes                            |
| ---------------- | -------- | ------------------------------------------------- | ---------- | -------------------------------- |
| `capabilityType` | Global   | `composerData:{id}.conversation[].capabilityType` | ⚠️ Partial | Number, not always present       |
| `unifiedMode`    | Global   | `composerData:{id}.conversation[].unifiedMode`    | ⚠️ Partial | Number, not always present       |
| `isAgentic`      | Global   | `composerData:{id}.conversation[].isAgentic`      | ⚠️ Partial | Boolean flag, not always present |
| `relevantFiles`  | Global   | `composerData:{id}.conversation[].relevantFiles`  | ⚠️ Partial | Array, user messages only        |
| `selections`     | Global   | `composerData:{id}.conversation[].selections`     | ⚠️ Partial | Array, user messages only        |
| `image`          | Global   | `composerData:{id}.conversation[].image`          | ⚠️ Partial | Image data, user messages only   |

---

## Missing Fields

### Composer-Level Missing Fields

| Field       | Expected Location             | Reason                        | Alternative                                          |
| ----------- | ----------------------------- | ----------------------------- | ---------------------------------------------------- |
| `usageData` | `composerData:{id}.usageData` | Not present in current schema | May be server-side only or removed in newer versions |

### Bubble-Level Missing Fields

| Field                     | Expected Location                        | Reason                   | Alternative                                          |
| ------------------------- | ---------------------------------------- | ------------------------ | ---------------------------------------------------- |
| `modelType`               | `conversation[].modelType`               | Not persisted per bubble | Likely server-side only or in request metadata       |
| `aiStreamingSettings`     | `conversation[].aiStreamingSettings`     | Not persisted per bubble | Likely server-side only                              |
| `thinking`                | `conversation[].thinking`                | Not persisted            | May be in `intermediateChunks` (needs investigation) |
| `toolFormerdata`          | `conversation[].toolFormerdata`          | Different structure      | Use `capabilitiesRan` instead                        |
| `tokenCount.inputTokens`  | `conversation[].tokenCount.inputTokens`  | Different structure      | Use `tokenCountUpUntilHere` (cumulative)             |
| `tokenCount.outputTokens` | `conversation[].tokenCount.outputTokens` | Different structure      | Use `tokenCountUpUntilHere` (cumulative)             |

### Most Likely Explanations for Missing Fields

1. **Server-Side Only** (Most Likely for Model Info)

   - Model information (`modelType`, `aiStreamingSettings`) is stored on Cursor's servers
   - Only sent in API requests, not persisted locally
   - Would require network monitoring or extension API access

2. **Settings Files** (Likely for User Preferences)

   - Model preferences may be stored in user settings/preferences files
   - Not in SQLite databases
   - Would require examining Cursor's settings files

3. **Schema Version Differences** (Possible)

   - Research documents may describe older/newer schema versions
   - Current Cursor version may not persist certain fields
   - Some fields may have been removed or moved to server-side

4. **Derived from Other Data** (Unlikely)
   - Some information might be derivable from other fields
   - But no obvious correlation found

---

## Scripts Reference

### Phase 1: Database Discovery

**Script**: `scripts/test_composer_data_discovery.py`

**Purpose**: Discovers all Cursor database files and analyzes their structure.

**Output**: `docs/composer_data_discovery_report.json`

**Key Functions**:

- `discover_cursor_databases()` - Finds all workspace and global storage databases
- `analyze_database(db_path)` - Analyzes table structure and key patterns

**Usage**:

```bash
python3 scripts/test_composer_data_discovery.py
```

---

### Phase 2: Composer Metadata Extraction

**Script**: `scripts/test_composer_metadata.py`

**Purpose**: Extracts composer metadata from both workspace and global storage.

**Output**: `docs/composer_metadata_report.json`

**Key Functions**:

- `get_composer_metadata_from_itemtable(db_path)` - Gets metadata from workspace storage
- `get_composer_metadata_from_cursordiskkv(db_path, composer_id)` - Gets full composer data from global storage
- `extract_composer_fields(composer)` - Extracts and validates composer fields

**Usage**:

```bash
python3 scripts/test_composer_metadata.py
```

**Dependencies**: Requires Phase 1 output (optional)

---

### Phase 3: Bubble Data Extraction

**Script**: `scripts/test_bubble_data.py`

**Purpose**: Extracts full bubble (message) data from composer conversations.

**Output**: `docs/bubble_data_report.json`

**Key Functions**:

- `get_bubble_data(db_path, bubble_id)` - Gets bubble from separate entry (deprecated - bubbles are embedded)
- `extract_bubble_fields(bubble)` - Extracts and validates bubble fields

**Usage**:

```bash
python3 scripts/test_bubble_data.py
```

**Dependencies**: Requires Phase 2 output (`composer_metadata_report.json`)

**Key Finding**: Bubbles are embedded in `composerData:{id}.conversation` array, not stored as separate entries.

---

### Phase 4: Schema Validation

**Script**: `scripts/validate_composer_schema.py`

**Purpose**: Validates that all required fields are present in extracted data.

**Output**: `docs/composer_schema_validation_report.md`

**Key Functions**:

- `validate_composer_fields(composer)` - Validates composer field presence
- `validate_bubble_fields(bubble)` - Validates bubble field presence

**Usage**:

```bash
python3 scripts/validate_composer_schema.py
```

**Dependencies**: Requires Phase 2 and Phase 3 outputs

---

## Query Patterns

### Get All Composers

```python
import sqlite3
import json
from pathlib import Path

def get_all_composers():
    """Get all composers from workspace storage."""
    workspace_db = Path.home() / "Library/Application Support/Cursor/User/workspaceStorage"

    composers = []
    for workspace_dir in workspace_db.iterdir():
        db_file = workspace_dir / "state.vscdb"
        if not db_file.exists():
            continue

        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM ItemTable WHERE key = ?", ('composer.composerData',))
        row = cursor.fetchone()

        if row and row[0]:
            value = row[0]
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            data = json.loads(value)
            composers.extend(data.get('allComposers', []))

        conn.close()

    return composers
```

### Get Full Composer with Bubbles

```python
def get_composer_with_bubbles(composer_id):
    """Get full composer data with embedded bubbles from global storage."""
    global_db = Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"

    if not global_db.exists():
        return None

    conn = sqlite3.connect(f"file:{global_db}?mode=ro", uri=True)
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f'composerData:{composer_id}',))
    row = cursor.fetchone()

    if row and row[0]:
        value = row[0]
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        composer = json.loads(value)

        # Bubbles are embedded in conversation array
        bubbles = composer.get('conversation', []) or composer.get('fullConversationHeadersOnly', [])
        composer['bubbles'] = bubbles

        conn.close()
        return composer

    conn.close()
    return None
```

### Extract Bubble Fields

```python
def extract_bubble_fields(bubble):
    """Extract fields from a bubble object."""
    return {
        # Basic
        'bubbleId': bubble.get('bubbleId'),
        'type': bubble.get('type'),  # 1=user, 2=ai

        # Content
        'text': bubble.get('text'),
        'rawText': bubble.get('rawText'),

        # Timing (check timingInfo if top-level fields missing)
        'createdAt': bubble.get('createdAt') or bubble.get('timingInfo', {}).get('clientStartTime'),
        'completedAt': bubble.get('completedAt') or bubble.get('timingInfo', {}).get('clientSettleTime'),

        # Capabilities (actual field names)
        'capabilitiesRan': bubble.get('capabilitiesRan', {}),
        'capabilityStatuses': bubble.get('capabilityStatuses', {}),

        # Tokens (different structure)
        'tokenCountUpUntilHere': bubble.get('tokenCountUpUntilHere'),

        # Missing fields
        'modelType': bubble.get('modelType'),  # Will be None
        'thinking': bubble.get('thinking'),  # Will be None
    }
```

---

## Summary Tables

### Data Availability by Location

| Data Type                      | Workspace Storage | Global Storage              | Status    |
| ------------------------------ | ----------------- | --------------------------- | --------- |
| Composer metadata (IDs, names) | ✅ ItemTable      | ✅ cursorDiskKV             | Available |
| Full composer data             | ❌                | ✅ cursorDiskKV             | Available |
| Bubbles (messages)             | ❌                | ✅ Embedded in composerData | Available |
| Model configuration            | ❌                | ❌                          | Missing   |
| Thinking content               | ❌                | ❌                          | Missing   |
| Tool usage data                | ❌                | ⚠️ Different structure      | Partial   |
| Token counts                   | ❌                | ⚠️ Different structure      | Partial   |
| Timing information             | ❌                | ✅ timingInfo dict          | Available |

### Field Coverage Summary

| Category          | Fields Found | Fields Missing | Coverage |
| ----------------- | ------------ | -------------- | -------- |
| Composer Basic    | 5/5          | 0              | 100%     |
| Composer Extended | 2/4          | 2              | 50%      |
| Bubble Basic      | 4/4          | 0              | 100%     |
| Bubble Content    | 4/4          | 0              | 100%     |
| Model Config      | 0/2          | 2              | 0%       |
| Thinking          | 0/1          | 1              | 0%       |
| Tool Usage        | 1/2          | 1              | 50%      |
| Capabilities      | 2/4          | 2              | 50%      |
| Timing            | 4/4          | 0              | 100%     |
| Tokens            | 1/3          | 2              | 33%      |

---

## Next Steps / Recommendations

1. **Investigate Missing Fields**:

   - Check `intermediateChunks` structure for thinking content
   - Check `codeBlocks` structure for tool execution results
   - Examine `cursorai/serverConfig` in global storage ItemTable for model configuration
   - Check Cursor settings files for model preferences

2. **Network Monitoring**:

   - Use extension API or network monitoring to capture model info from API requests
   - Model information may only be available at request time

3. **Schema Version Handling**:

   - Check `_v` field in composer and bubble objects
   - Handle different schema versions gracefully

4. **Documentation Updates**:
   - Update extraction scripts to use actual field names
   - Document field mapping differences
   - Update validation scripts to check for actual fields

---

## Related Documentation

- [Bubble Storage Location](BUBBLE_STORAGE_LOCATION.md) - Detailed explanation of where bubbles are stored
- [Field Mapping Investigation](FIELD_MAPPING_INVESTIGATION.md) - Expected vs actual field names
- [Model Info Search Summary](MODEL_INFO_SEARCH_SUMMARY.md) - Investigation into missing model information
- [Composer Schema Validation Report](composer_schema_validation_report.md) - Validation results
- [SQLite Composer Queries](SQLITE_COMPOSER_QUERIES.md) - Query patterns and examples

---

## Script Execution Order

To extract all available data:

```bash
# 1. Discover databases
python3 scripts/test_composer_data_discovery.py

# 2. Extract composer metadata
python3 scripts/test_composer_metadata.py

# 3. Extract bubble data
python3 scripts/test_bubble_data.py

# 4. Validate schema
python3 scripts/validate_composer_schema.py
```

All reports are saved to the `docs/` directory.
