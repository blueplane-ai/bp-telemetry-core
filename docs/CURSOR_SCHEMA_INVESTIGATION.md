# Cursor Database Schema Investigation Report

**Date**: January 2025  
**Status**: Investigation Complete - Schema Mismatch Confirmed

---

## Executive Summary

**Critical Finding**: The current implementation expects `aiService.generations` and `aiService.prompts` as **SQL tables**, but they are actually stored as **JSON arrays in ItemTable key-value pairs**. The code will **fail** when trying to query these as tables.

**Impact**: Database monitoring is currently **non-functional** for capturing AI generation traces.

---

## Investigation Results

### 1. Database Structure

**All Cursor workspace databases** (`state.vscdb`) contain only two tables:
```sql
CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
```

**No separate tables exist** for `aiService.generations` or `aiService.prompts`.

### 2. Actual Data Structure

#### `aiService.generations` (in ItemTable)

**Location**: `ItemTable` key = `'aiService.generations'`  
**Value Type**: JSON array (stored as BLOB/text)  
**Sample Database**: `8ac955efa11cefbcd695924c7885fce9/state.vscdb`  
**Item Count**: 100 items

**Actual Schema**:
```json
[
  {
    "unixMs": 1762046253035,
    "generationUUID": "dd4317f0-22e0-4153-8f11-9b5aa5fc7946",
    "type": "cmdk",
    "textDescription": "..."  // Optional, appears in 96% of items
  }
]
```

**Key Fields**:
- `unixMs` (number): Unix timestamp in milliseconds
- `generationUUID` (string): Unique generation identifier
- `type` (string): Generation type (e.g., "cmdk")
- `textDescription` (string, optional): Description text

**What Code Expects** (WRONG):
```sql
SELECT uuid, data_version, value, timestamp 
FROM "aiService.generations"
WHERE data_version > ?
```

**Mismatch**:
- ❌ No `uuid` column → Use `generationUUID` from JSON
- ❌ No `data_version` column → **No versioning field exists**
- ❌ No `value` column → Entire object IS the value
- ❌ No `timestamp` column → Use `unixMs` from JSON
- ❌ Not a table → It's a JSON array in ItemTable

---

#### `aiService.prompts` (in ItemTable)

**Location**: `ItemTable` key = `'aiService.prompts'`  
**Value Type**: JSON array (stored as BLOB/text)  
**Item Count**: 84 items

**Actual Schema**:
```json
[
  {
    "text": "how could i use cursor hooks to capture meaningful telemetry...",
    "commandType": 4
  }
]
```

**Key Fields**:
- `text` (string): Prompt text
- `commandType` (number): Command type identifier

**What Code Expects** (WRONG):
```sql
SELECT uuid, text, timestamp 
FROM "aiService.prompts"
```

**Mismatch**:
- ❌ No `uuid` column → **No UUID field exists**
- ❌ No `timestamp` column → **No timestamp field exists**
- ❌ Not a table → It's a JSON array in ItemTable

---

### 3. Change Detection Problem

**Current Approach** (BROKEN):
- Queries `MAX(data_version)` to detect changes
- Uses `data_version` to track what's been synced

**Reality**:
- ❌ No `data_version` field exists
- ❌ No versioning mechanism in the data structure
- ✅ Array is replaced entirely (`ON CONFLICT REPLACE`)

**Change Detection Strategy Needed**:
1. **Track array length** - If length increases, new items added
2. **Track last seen UUIDs** - Compare `generationUUID` sets
3. **Track last timestamp** - Use `unixMs` to find new items
4. **Full array comparison** - Hash the entire array (expensive)

**Recommended**: Use `unixMs` timestamp + `generationUUID` set tracking

---

### 4. Data Availability

**Database**: `66b4e47d8cd79622d5b1b18f44882398/state.vscdb`
- `aiService.generations`: `[]` (empty array, 2 bytes)
- `aiService.prompts`: `[]` (empty array, 2 bytes)

**Database**: `8ac955efa11cefbcd695924c7885fce9/state.vscdb`
- `aiService.generations`: 100 items (15,477 bytes)
- `aiService.prompts`: 84 items (6,196 bytes)

**Conclusion**: Data exists in some workspaces but not others (likely based on usage).

---

## Code Impact Analysis

### Files Affected

1. **`src/processing/cursor/database_monitor.py`**
   - Line 30: `GENERATIONS_TABLE = "aiService.generations"` (expects table)
   - Line 182-194: Checks for table existence (will fail)
   - Line 306-317: Queries `MAX(data_version)` (column doesn't exist)
   - Line 351-356: Queries table with wrong columns (table doesn't exist)

2. **`src/capture/cursor/extension/src/databaseMonitor.ts`**
   - Line 249: Queries `MAX(data_version)` (column doesn't exist)
   - Line 273-284: Joins tables (tables don't exist)
   - Line 291-297: Fallback query (table doesn't exist)

3. **`src/processing/cursor/workspace_mapper.py`**
   - Line 196-199: Checks for table existence (will always fail)
   - Line 204-206: Queries table (will always fail)

### Current Behavior

**Expected**: Code queries tables and captures generations  
**Actual**: 
- ❌ Table queries fail with "no such table" error
- ❌ No generations are captured
- ❌ Database monitor silently fails or logs errors
- ✅ Code has error handling, so it doesn't crash

---

## Recommended Solution

### Option 1: Adapt to ItemTable Structure (Recommended)

**Approach**: Read from `ItemTable` key-value pairs and parse JSON arrays.

**Implementation**:

```python
# Read from ItemTable instead of querying table
async def _get_generations_from_itemtable(self, conn):
    cursor = await conn.execute(
        'SELECT value FROM ItemTable WHERE key = ?',
        ('aiService.generations',)
    )
    row = await cursor.fetchone()
    if not row or not row[0]:
        return []
    
    # Parse JSON array
    generations = json.loads(row[0])
    return generations

# Change detection using timestamps
async def _get_new_generations(self, conn, last_timestamp_ms):
    all_generations = await self._get_generations_from_itemtable(conn)
    
    # Filter by timestamp
    new_generations = [
        gen for gen in all_generations
        if gen.get('unixMs', 0) > last_timestamp_ms
    ]
    
    return new_generations
```

**Pros**:
- ✅ Works with actual data structure
- ✅ Minimal code changes
- ✅ Uses existing `unixMs` for change detection

**Cons**:
- ⚠️ Must parse entire array each time (could be slow for large arrays)
- ⚠️ No `data_version` for efficient incremental sync

---

### Option 2: Hybrid Approach

**Approach**: Check if table exists, fall back to ItemTable if not.

**Implementation**:

```python
async def _get_generations(self, conn):
    # Try table first (for future compatibility)
    try:
        cursor = await conn.execute('SELECT * FROM "aiService.generations"')
        return await cursor.fetchall()
    except:
        # Fall back to ItemTable
        return await self._get_generations_from_itemtable(conn)
```

**Pros**:
- ✅ Backward compatible if Cursor changes schema
- ✅ Works with current structure

**Cons**:
- ⚠️ More complex code
- ⚠️ Still need to handle both schemas

---

### Option 3: Wait for Cursor Schema Update

**Approach**: Do nothing, wait for Cursor to change schema.

**Pros**:
- ✅ No code changes needed

**Cons**:
- ❌ Database monitoring doesn't work now
- ❌ Unknown timeline for schema change
- ❌ May never happen

---

## Implementation Plan

### Phase 1: Fix Core Query Logic

1. **Update `database_monitor.py`**:
   - Replace table queries with ItemTable key-value reads
   - Parse JSON arrays
   - Map `generationUUID` → `uuid`, `unixMs` → `timestamp`

2. **Update `databaseMonitor.ts`**:
   - Same changes as Python version
   - Handle JSON parsing in TypeScript

3. **Update `workspace_mapper.py`**:
   - Remove table existence checks
   - Check ItemTable for key existence instead

### Phase 2: Implement Change Detection

1. **Track last seen timestamp**:
   - Store `last_synced_timestamp_ms` per workspace
   - Filter generations by `unixMs > last_synced_timestamp_ms`

2. **Deduplication**:
   - Use `generationUUID` instead of generation_id
   - Track seen UUIDs per workspace

3. **Initial sync**:
   - On first connect, sync last N hours of data
   - Use `unixMs` to filter

### Phase 3: Handle Prompts

1. **Read prompts from ItemTable**:
   - Parse JSON array
   - Match to generations (if relationship exists)

2. **Note**: Prompts don't have UUIDs or timestamps
   - May need to match by array index or other heuristics
   - Or treat prompts as separate trace events

### Phase 4: Testing

1. Test with empty databases (`[]`)
2. Test with populated databases (100+ items)
3. Test change detection (new items added)
4. Test deduplication (same UUID seen twice)

---

## Data Mapping

### Generation Event Mapping

**From ItemTable JSON**:
```json
{
  "unixMs": 1762046253035,
  "generationUUID": "dd4317f0-22e0-4153-8f11-9b5aa5fc7946",
  "type": "cmdk",
  "textDescription": "..."
}
```

**To Trace Event**:
```json
{
  "event_type": "database_trace",
  "trace_type": "generation",
  "generation_id": "dd4317f0-22e0-4153-8f11-9b5aa5fc7946",  // from generationUUID
  "timestamp": 1762046253035,  // from unixMs (convert to ISO)
  "generation_type": "cmdk",  // from type
  "description": "...",  // from textDescription
  "full_generation_data": {...}  // entire object
}
```

**Missing Fields** (not available in data):
- `data_version` → Remove or use array index
- `model` → Not in data
- `tokens_used` → Not in data
- `response_text` → Not in data (only `textDescription`)
- `prompt_text` → Need to match from prompts array

---

## Questions & Unknowns

1. **How are prompts linked to generations?**
   - No UUID relationship visible
   - Array indices may correspond?
   - Or chronological matching?

2. **What does `type: "cmdk"` mean?**
   - Command type?
   - Generation source?
   - Need to investigate Cursor source code or docs

3. **Why is `textDescription` optional?**
   - Only 96% of items have it
   - What are the 4% missing?

4. **Is the array append-only or replaced?**
   - `ON CONFLICT REPLACE` suggests replacement
   - But array grows over time
   - May be replaced with new array containing old + new items

5. **What's the maximum array size?**
   - Currently 100 items
   - Does Cursor cap it?
   - Will performance degrade with large arrays?

---

## Next Steps

1. ✅ **Investigation Complete** - Schema mismatch confirmed
2. ⏭️ **Implement ItemTable reader** - Read JSON arrays from ItemTable
3. ⏭️ **Implement timestamp-based change detection** - Use `unixMs`
4. ⏭️ **Update event mapping** - Map to existing trace event format
5. ⏭️ **Test with real data** - Verify capture works
6. ⏭️ **Update documentation** - Reflect actual schema

---

**End of Investigation Report**

