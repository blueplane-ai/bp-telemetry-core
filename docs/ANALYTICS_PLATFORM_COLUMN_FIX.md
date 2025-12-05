# Platform-Specific Column Handling Fix

## Issue

The `get_new_traces()` method in `SQLiteReader` was attempting to select both `external_id` and `external_session_id` columns from both platform tables, but:

- **`cursor_raw_traces`** table only has `external_session_id` column
- **`claude_raw_traces`** table only has `external_id` column

This would cause SQL errors: `"no such column: external_id"` when querying Cursor traces, or `"no such column: external_session_id"` when querying Claude Code traces.

## Solution

Implemented platform-specific SQL queries that select the correct column for each platform:

### Cursor Platform Query (lines 121-135)
```python
if platform == 'cursor':
    cursor = conn.execute(f"""
        SELECT 
            sequence,
            event_id,
            external_session_id,  # ← Cursor-specific column
            event_type,
            timestamp,
            workspace_hash,
            event_data
        FROM cursor_raw_traces
        WHERE sequence > ?
        ORDER BY sequence ASC
        LIMIT ?
    """, (since_sequence, limit))
```

### Claude Code Platform Query (lines 136-150)
```python
else:  # claude_code
    cursor = conn.execute(f"""
        SELECT 
            sequence,
            event_id,
            external_id,  # ← Claude Code-specific column
            event_type,
            timestamp,
            workspace_hash,
            event_data
        FROM claude_raw_traces
        WHERE sequence > ?
        ORDER BY sequence ASC
        LIMIT ?
    """, (since_sequence, limit))
```

### Trace Construction (lines 163-186)
The trace dictionaries are also constructed with platform-specific field mapping:

**Cursor traces:**
```python
trace = {
    'sequence': row[0],
    'event_id': row[1],
    'external_id': None,  # ← Not available for Cursor
    'external_session_id': row[2],  # ← From SQL query
    'event_type': row[3],
    'timestamp': row[4],
    'workspace_hash': row[5],
    'event_data': event_data,
    'platform': platform
}
```

**Claude Code traces:**
```python
trace = {
    'sequence': row[0],
    'event_id': row[1],
    'external_id': row[2],  # ← From SQL query
    'external_session_id': None,  # ← Not available for Claude Code
    'event_type': row[3],
    'timestamp': row[4],
    'workspace_hash': row[5],
    'event_data': event_data,
    'platform': platform
}
```

## Verification

✅ **Tests Passing:**
- `test_get_new_traces_cursor` - Verifies Cursor traces are read correctly
- `test_get_new_traces_claude` - Verifies Claude Code traces are read correctly
- `test_mixed_platforms` - Verifies both platforms work together

✅ **Manual Verification:**
```python
# Both queries execute without SQL errors
reader.get_new_traces('cursor', since_sequence=0)  # ✓ Works
reader.get_new_traces('claude_code', since_sequence=0)  # ✓ Works
```

## Status

**Status:** ✅ **FIXED AND VERIFIED**

The platform-specific column handling is correctly implemented and all tests pass. The fix ensures that:
1. Each platform's table is queried with the correct column names
2. Trace dictionaries have consistent structure regardless of platform
3. Missing columns are set to `None` for consistency

