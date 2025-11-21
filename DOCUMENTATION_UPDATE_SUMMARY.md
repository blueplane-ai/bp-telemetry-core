# Documentation Update Summary: raw_traces Deprecation

**Date**: November 20, 2025
**Purpose**: Update all documentation to remove references to deprecated `raw_traces` table and replace with platform-specific tables

## Changes Overview

The system has migrated from a generic `raw_traces` table to platform-specific tables:
- **cursor_raw_traces** - For Cursor IDE events
- **claude_raw_traces** - For Claude Code events

This change provides better schema optimization for each platform's unique data structures.

## Files Updated

### 1. docs/architecture/layer2_db_architecture.md ✅

**Changes Made**:
- Updated executive summary to reference "platform-specific raw traces tables"
- Updated Database Technology Stack table to mention both cursor_raw_traces and claude_raw_traces
- Replaced schema examples with platform-specific examples
- Added references to CURSOR_RAW_TRACES_CAPTURE.md and CLAUDE_JSONL_SCHEMA.md
- Updated all code examples to use platform parameter and platform-specific table names
- Updated performance notes to reference platform-specific tables
- Updated health check and maintenance task documentation
- Updated conclusion to highlight platform-specific storage benefits

**Key Updates**:
- Schema Design section now shows cursor_raw_traces as example
- SQLiteTraceStorage methods now include `platform` parameter
- Worker code examples updated to query platform-specific tables
- Health checks now count both cursor_raw_trace_count and claude_raw_trace_count

### 2. docs/ARCHITECTURE.md ✅

**Changes Made**:
- Updated Data Isolation section to reference platform-specific tables
- Updated Storage Technology Selection table
- Updated SQL schema example to show cursor_raw_traces with Cursor-specific fields
- Added note about claude_raw_traces table existence
- Updated layer access descriptions

**Key Updates**:
- Fast path writes to cursor_raw_traces and claude_raw_traces
- Layer 3 restrictions updated to mention both platform tables
- Schema example now shows Cursor-specific fields (storage_level, generation_uuid, composer_id, etc.)

### 3. docs/architecture/layer2_conversation_reconstruction.md ✅

**Changes Made**:
- Updated Cursor reconstruction algorithm to reference cursor_raw_traces
- Updated Claude Code reconstruction algorithm to reference claude_raw_traces
- Updated comments about database trace storage

**Key Updates**:
- get_session_events() calls now specify platform
- Comments updated to mention specific platform tables
- Database trace notes updated to reference cursor_raw_traces

### 4. Remaining Files (To Be Updated)

The following files still contain references to `raw_traces` and need updates:

#### High Priority:
- **docs/TROUBLESHOOTING.md** - Status check queries reference raw_traces
- **docs/IMPLEMENTATION_PLAN_SQL.md** - Schema examples use raw_traces
- **README.md** - Quick verification examples query raw_traces

#### Medium Priority:
- **docs/HOOKS_VS_TRACES.md** - Extensive raw_traces table documentation
- **docs/CLAUDE_JSONL_SCHEMA.md** - Schema mapping references
- **src/capture/claude_code/README.md** - Event flow references
- **IMPLEMENTATION_SUMMARY.md** - Historical implementation notes

#### Low Priority:
- **OUTPUTS_AND_MODELS.md** - Query examples and schema documentation
- **docs/CURSOR_RAW_TRACES_CAPTURE.md** - Already uses cursor_raw_traces (no changes needed)

## Pattern for Remaining Updates

For each remaining file, apply these changes:

1. **Table Name References**:
   - `raw_traces` → `cursor_raw_traces` or `claude_raw_traces` (context dependent)
   - "raw_traces table" → "platform-specific raw traces tables (cursor_raw_traces and claude_raw_traces)"

2. **SQL Queries**:
   ```sql
   -- Old:
   SELECT COUNT(*) FROM raw_traces;

   -- New:
   SELECT COUNT(*) FROM cursor_raw_traces;
   -- Or if showing both platforms:
   SELECT COUNT(*) FROM cursor_raw_traces
   UNION ALL
   SELECT COUNT(*) FROM claude_raw_traces;
   ```

3. **Code Examples**:
   ```python
   # Old:
   sqlite.get_session_events(session_id, ...)

   # New:
   sqlite.get_session_events(session_id, platform='cursor', ...)
   ```

4. **Index Names**:
   - `idx_session_time` → `idx_cursor_session_time` (for Cursor)
   - `idx_raw_*` → `idx_cursor_*` or `idx_claude_*`

5. **Access Descriptions**:
   - "Layer 2 accesses raw_traces" → "Layer 2 accesses platform-specific raw traces tables"
   - "Layer 3 never accesses raw_traces" → "Layer 3 never accesses platform-specific raw traces tables"

## Important Notes

1. **No Migration Required**: The deprecated raw_traces table is not migrated. Platform-specific tables start fresh.

2. **cursor_raw_traces References**: DO NOT change existing references to cursor_raw_traces or claude_raw_traces - those should remain.

3. **Layer 2 Internal**: All platform-specific raw traces tables remain Layer 2 internal only.

4. **Schema Documentation**: Point to platform-specific schema docs:
   - Cursor: docs/CURSOR_RAW_TRACES_CAPTURE.md
   - Claude Code: docs/CLAUDE_JSONL_SCHEMA.md

## Next Steps

1. Complete updates to high-priority files
2. Test all SQL queries in documentation
3. Update any code examples to match new patterns
4. Verify cross-references between documents are correct

## Status

- ✅ docs/architecture/layer2_db_architecture.md - Complete
- ✅ docs/ARCHITECTURE.md - Complete
- ✅ docs/architecture/layer2_conversation_reconstruction.md - Complete
- ⏳ docs/TROUBLESHOOTING.md - In progress
- ⏳ docs/IMPLEMENTATION_PLAN_SQL.md - Pending
- ⏳ README.md - Pending
- ⏳ docs/HOOKS_VS_TRACES.md - Pending
- ⏳ docs/CLAUDE_JSONL_SCHEMA.md - Pending
- ⏳ src/capture/claude_code/README.md - Pending
- ⏳ IMPLEMENTATION_SUMMARY.md - Pending
- ⏳ OUTPUTS_AND_MODELS.md - Pending
