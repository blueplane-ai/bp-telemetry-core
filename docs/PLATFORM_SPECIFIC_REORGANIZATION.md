<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Platform-Specific Processing Reorganization

**Status**: Completed
**Created**: November 21, 2025
**Completed**: November 21, 2025
**Goal**: Reorganize processing code into parallel platform-specific structures

## Problem Statement

The current code structure has asymmetric organization for platform-specific processing:
- Cursor has a dedicated `cursor/` directory with `event_consumer.py` and `raw_traces_writer.py`
- Claude Code processing is scattered across `fast_path/` and `database/writer.py`
- The `fast_path/consumer.py` claims to be generic but only processes Claude events
- Shared utilities (batch_manager, cdc_publisher) are in `fast_path/` but used by both platforms

This creates confusion about code ownership and makes the architecture harder to understand.

## Implemented Solution

Created parallel platform-specific directory structures with shared common utilities:

```
src/processing/
├── claude_code/                  # Claude Code processing (consolidated)
│   ├── __init__.py
│   ├── event_consumer.py         # Moved from fast_path/consumer.py
│   ├── raw_traces_writer.py     # Extracted from database/writer.py
│   ├── jsonl_monitor.py         # File monitoring
│   ├── session_monitor.py       # Session management
│   └── [other monitors...]      # Transcript, timeout, etc.
│
├── cursor/                       # Cursor-specific processing
│   ├── __init__.py
│   ├── event_consumer.py
│   ├── raw_traces_writer.py
│   ├── database_monitor.py
│   └── [other monitors...]
│
├── common/                       # Shared components
│   ├── __init__.py
│   ├── batch_manager.py         # Moved from fast_path/
│   └── cdc_publisher.py         # Moved from fast_path/
│
└── database/
    ├── __init__.py
    ├── sqlite_client.py
    ├── schema.py
    └── writer.py                # Generic compression utilities only
```

**Note**: Initially proposed a separate `claude/` directory, but consolidated into `claude_code/`
for better clarity (combines event processing + file monitoring in one place).

## Benefits

1. **Consolidation**: claude_code/ contains all Claude Code logic (event processing + file monitoring)
2. **Clarity**: Platform-specific code is self-contained in platform directories
3. **Maintainability**: Easy to add new platforms (e.g., `github_copilot/`)
4. **Separation**: Common utilities (batch_manager, cdc_publisher) clearly separated
5. **Discoverability**: Developers can easily find all Claude Code logic in one place
6. **DRY**: Eliminated 715 lines of duplicate consumer code

## Implementation Phases

### Phase 1: Create Claude Platform Directory

**Goal**: Create parallel structure for Claude without breaking existing code

1. Create `src/processing/claude/` directory
2. Create `src/processing/claude/__init__.py`
3. Copy `fast_path/consumer.py` → `claude/event_consumer.py`
4. Rename class `FastPathConsumer` → `ClaudeEventConsumer`
5. Remove all Cursor event routing logic (it's already skipped)
6. Update docstrings to be Claude-specific

**Files Created**:
- `src/processing/claude/__init__.py`
- `src/processing/claude/event_consumer.py`

**Changes**: None to existing files yet (parallel structure)

### Phase 2: Extract Claude Raw Traces Writer

**Goal**: Create dedicated writer for Claude events

1. Create `src/processing/claude/raw_traces_writer.py`
2. Move from `database/writer.py`:
   - `INSERT_CLAUDE_QUERY` constant
   - `_extract_claude_indexed_fields()` method
   - `write_claude_batch_sync()` method
3. Create `ClaudeRawTracesWriter` class
4. Update `claude/event_consumer.py` to use new writer
5. Clean `database/writer.py` to remove Claude-specific code

**Files Created**:
- `src/processing/claude/raw_traces_writer.py`

**Files Modified**:
- `src/processing/database/writer.py` (remove Claude-specific code)
- `src/processing/claude/event_consumer.py` (update imports)

### Phase 3: Move JSONL Monitor

**Goal**: Consolidate Claude-specific monitoring

1. Move `jsonl_monitor.py` → `claude/jsonl_monitor.py`
2. Update imports in server.py

**Files Moved**:
- `src/processing/jsonl_monitor.py` → `src/processing/claude/jsonl_monitor.py`

**Files Modified**:
- `src/processing/server.py` (update import)

### Phase 4: Create Common Utilities

**Goal**: Extract shared components

1. Create `src/processing/common/` directory
2. Create `src/processing/common/__init__.py`
3. Move `fast_path/batch_manager.py` → `common/batch_manager.py`
4. Move `fast_path/cdc_publisher.py` → `common/cdc_publisher.py`
5. Update imports in both platform-specific consumers

**Files Created**:
- `src/processing/common/__init__.py`

**Files Moved**:
- `src/processing/fast_path/batch_manager.py` → `src/processing/common/batch_manager.py`
- `src/processing/fast_path/cdc_publisher.py` → `src/processing/common/cdc_publisher.py`

**Files Modified**:
- `src/processing/claude/event_consumer.py` (update imports)
- `src/processing/cursor/event_consumer.py` (update imports)

### Phase 5: Update Server Integration

**Goal**: Wire up new structure in server

1. Update `server.py` imports:
   - `from .claude.event_consumer import ClaudeEventConsumer`
   - `from .claude.raw_traces_writer import ClaudeRawTracesWriter`
2. Update initialization code to use new classes
3. Update tests to reference new locations

**Files Modified**:
- `src/processing/server.py`
- Test files that import these modules

### Phase 6: Cleanup

**Goal**: Remove old structure

1. Delete `src/processing/fast_path/consumer.py` (now in claude/)
2. Delete `src/processing/fast_path/` directory if empty
3. Update documentation to reflect new structure
4. Run tests to verify everything works

**Files Deleted**:
- `src/processing/fast_path/consumer.py`
- `src/processing/fast_path/` directory (if empty)

**Files Modified**:
- Documentation files

## Testing Strategy

After each phase:
1. Verify imports resolve correctly
2. Run unit tests if they exist
3. Check that server.py can still import required modules
4. Verify no breaking changes to public APIs

## Rollback Plan

If issues arise:
1. Each phase creates new files before modifying old ones
2. Can revert git commits phase by phase
3. Old structure remains until Phase 6

## Success Criteria

- [x] All platform-specific code is in `claude_code/` or `cursor/` directories
- [x] Shared utilities are in `common/` directory
- [x] `database/writer.py` contains only generic compression utilities
- [x] Server can initialize ClaudeEventConsumer and Cursor consumers
- [x] All imports resolve correctly
- [x] Documentation updated to reflect new structure

## Implementation Summary

Completed in three phases on November 21, 2025:

1. **Phase 1: Create Claude Platform Directory**
   - Created `src/processing/claude/` with event_consumer.py and raw_traces_writer.py
   - Extracted ClaudeRawTracesWriter from database/writer.py
   - Updated exports in claude/__init__.py

2. **Phase 2: Extract Platform Writers & Create Common**
   - Created `src/processing/common/` with shared utilities
   - Moved batch_manager.py and cdc_publisher.py from fast_path/
   - Consolidated FastPathConsumer into ClaudeEventConsumer
   - Deleted fast_path/ directory (eliminated 715 lines of duplicate code)
   - Both claude/ and cursor/ now use common/ utilities

3. **Phase 3: Consolidate into claude_code/**
   - Moved claude/event_consumer.py and raw_traces_writer.py into claude_code/
   - Updated claude_code/__init__.py to export all processing classes
   - Updated server.py imports to use claude_code/
   - Deleted claude/ directory
   - Final structure: claude_code/ contains both event processing and file monitoring

## Future Enhancements

Once this reorganization is complete:
- Consider creating a `PlatformConsumer` base class in `common/`
- Add more platform-specific processing (e.g., metrics derivation)
- Create platform-specific configuration classes
