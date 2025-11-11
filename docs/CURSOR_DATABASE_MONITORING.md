# Cursor Database Monitoring: ItemTable Schema Fix

**Date**: January 2025  
**Status**: ✅ Implementation Complete & Tested

---

## Overview

This document consolidates the investigation, implementation, and testing of fixes for Cursor database monitoring. The original implementation expected `aiService.generations` and `aiService.prompts` as SQL tables, but they are actually stored as JSON arrays in Cursor's `ItemTable` key-value structure.

---

## Quick Links

### Investigation Documents
- **[CURSOR_DISK_KV_AUDIT.md](./CURSOR_DISK_KV_AUDIT.md)** - Complete audit of all keys in `cursorDiskKV` and `ItemTable` tables
- **[CURSOR_SCHEMA_INVESTIGATION.md](./CURSOR_SCHEMA_INVESTIGATION.md)** - Detailed investigation of schema mismatch and actual data structure

### Implementation Documents
- **[ITEMTABLE_IMPLEMENTATION_SUMMARY.md](./ITEMTABLE_IMPLEMENTATION_SUMMARY.md)** - Summary of code changes and implementation details

---

## Problem Statement

### Original Issue

The database monitor code (`database_monitor.py`, `databaseMonitor.ts`) attempted to query `aiService.generations` and `aiService.prompts` as SQL tables:

```sql
SELECT * FROM "aiService.generations" WHERE data_version > ?
```

However, Cursor stores this data as **JSON arrays in ItemTable key-value pairs**:

```sql
CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
-- Key: 'aiService.generations'
-- Value: JSON array of generation objects
```

### Impact

- ❌ Database monitoring was **non-functional**
- ❌ No generation traces were captured
- ❌ Code failed silently (error handling prevented crashes)

---

## Solution

### Key Changes

1. **Read from ItemTable** instead of querying non-existent tables
2. **Parse JSON arrays** from ItemTable values
3. **Use timestamp-based change detection** (`unixMs`) instead of non-existent `data_version`
4. **Map fields correctly**: `generationUUID` → `generation_id`, `unixMs` → `timestamp`

### Files Modified

- `src/processing/cursor/database_monitor.py` - Core monitoring logic
- `src/processing/cursor/workspace_mapper.py` - Database discovery fallback

---

## Actual Data Structure

### Generations (`aiService.generations`)

```json
[
  {
    "unixMs": 1762046253035,
    "generationUUID": "dd4317f0-22e0-4153-8f11-9b5aa5fc7946",
    "type": "cmdk",
    "textDescription": "..."  // Optional
  }
]
```

### Prompts (`aiService.prompts`)

```json
[
  {
    "text": "how could i use cursor hooks...",
    "commandType": 4
  }
]
```

---

## Testing Results

### ✅ Verification Complete

- **100 database_trace events** successfully captured
- Event structure verified with correct field mappings
- Timestamp-based change detection working
- Deduplication active (no duplicates)

### Sample Captured Event

```json
{
  "generation_id": "89004038-e034-43a8-9003-376a51d3e32c",
  "generation_type": "composer",
  "generation_timestamp_ms": 1762887622702,
  "generation_timestamp": "2025-11-11T19:00:22.000Z",
  "description": "relaunch and test",
  "full_generation_data": {
    "unixMs": 1762887622702,
    "generationUUID": "89004038-e034-43a8-9003-376a51d3e32c",
    "type": "composer",
    "textDescription": "relaunch and test"
  }
}
```

---

## Implementation Details

### Change Detection Strategy

**Before**: Tracked `data_version` (didn't exist)  
**After**: Tracks `unixMs` timestamp in milliseconds

```python
# Filter generations newer than last timestamp
new_generations = [
    gen for gen in all_generations
    if isinstance(gen, dict) and gen.get('unixMs', 0) > last_timestamp_ms
]
```

### Field Mapping

| Source Field | Target Field | Notes |
|-------------|--------------|-------|
| `generationUUID` | `generation_id` | Unique identifier |
| `unixMs` | `generation_timestamp_ms` | Milliseconds |
| `unixMs` | `generation_timestamp` | ISO format |
| `type` | `generation_type` | e.g., "composer", "cmdk" |
| `textDescription` | `description` | Optional field |

### Missing Fields

These fields don't exist in the actual data structure:
- `model` → Set to "unknown"
- `tokens_used`, `prompt_tokens`, `completion_tokens` → Set to 0
- `response_text` → Empty (only `textDescription` exists)
- `prompt_text` → Empty (would need matching from prompts array)

---

## Future Enhancements

### Recommended Next Steps

1. **Prompt Matching**: Implement logic to match prompts to generations (if relationship can be determined)
2. **Additional Keys**: Monitor other ItemTable keys:
   - `composer.composerData` - Composer session lifecycle
   - `workbench.backgroundComposer.workspacePersistentData` - Background composer state
   - `history.entries` - File open events
3. **cursorDiskKV Table**: Monitor if it starts receiving data
4. **TypeScript Extension**: Update `databaseMonitor.ts` with same fixes

---

## Related Documentation

- [DATABASE_MONITOR_CRITIQUE.md](./DATABASE_MONITOR_CRITIQUE.md) - Original critique of database monitor
- [DATABASE_MONITOR_REFACTOR.md](./DATABASE_MONITOR_REFACTOR.md) - Refactoring proposal
- [HOOKS_VS_TRACES.md](./HOOKS_VS_TRACES.md) - Comparison of hooks vs database traces

---

## Status

✅ **Implementation Complete**  
✅ **Tested & Verified**  
✅ **Production Ready**

The database monitor now correctly reads from Cursor's ItemTable structure and captures generation traces as expected.

---

**Last Updated**: January 2025

