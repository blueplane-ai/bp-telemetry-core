# Cursor Database Audit: cursorDiskKV and ItemTable Traces

**Date**: January 2025  
**Database**: `/Users/bbalaran/Library/Application Support/Cursor/User/workspaceStorage/66b4e47d8cd79622d5b1b18f44882398/state.vscdb`  
**Status**: Audit Complete

---

## Executive Summary

This audit examines the `cursorDiskKV` and `ItemTable` tables in Cursor's workspace storage database to identify what telemetry traces should be captured.

**Key Findings:**

- `cursorDiskKV` table exists but is **empty** (0 rows)
- `ItemTable` contains **73 key-value entries** with trace-relevant data
- Current implementation expects `aiService.generations` as a **table**, but it exists as a **key** in `ItemTable`
- Multiple trace-relevant keys are not currently monitored

---

## Database Schema

### Tables

```sql
CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
```

**Current State:**

- `ItemTable`: 73 entries
- `cursorDiskKV`: 0 entries (empty)

---

## Trace-Relevant Keys in ItemTable

### 🔴 **Critical: AI Service Traces** (Currently Expected as Tables)

These keys are referenced in code as **tables** but exist as **keys** in `ItemTable`:

| Key                     | Value Size | Status          | Notes                                                                         |
| ----------------------- | ---------- | --------------- | ----------------------------------------------------------------------------- |
| `aiService.generations` | 2 bytes    | ⚠️ **Mismatch** | Code expects TABLE with columns: `uuid`, `data_version`, `value`, `timestamp` |
| `aiService.prompts`     | 2 bytes    | ⚠️ **Mismatch** | Code expects TABLE for joining with generations                               |

**Issue**: Current implementation (`database_monitor.py`, `databaseMonitor.ts`) queries these as SQL tables:

```sql
SELECT * FROM "aiService.generations" WHERE data_version > ?
```

But they are actually **keys** in `ItemTable`. The values are currently minimal (2 bytes), suggesting they may be empty arrays `[]` or placeholders.

**Action Required**:

- Verify if these should be tables (schema change in Cursor?)
- Or adapt code to read from `ItemTable` key-value structure
- Check if there's a different database file with actual table structure

---

### 🟡 **High Priority: Composer & Agent Traces**

| Key                                                    | Value Size | Trace Type              | What to Capture                                                                         |
| ------------------------------------------------------ | ---------- | ----------------------- | --------------------------------------------------------------------------------------- |
| `composer.composerData`                                | 726 bytes  | **Composer Sessions**   | Composer IDs, modes (agent/chat/edit), creation timestamps, line counts, archive status |
| `workbench.backgroundComposer.workspacePersistentData` | 329 bytes  | **Background Composer** | Setup steps, terminal commands, git state, Docker config                                |
| `workbench.agentMode.exitInfo`                         | 67 bytes   | **Agent Mode**          | Panel visibility state when agent mode exits                                            |
| `agentLayout.shared.v6`                                | Unknown    | **Agent Layout**        | Agent UI layout configuration                                                           |

**Sample Data Structure** (`composer.composerData`):

```json
{
  "allComposers": [
    {
      "type": "head",
      "composerId": "a444abdd-2743-4711-b38f-207c8c7427dc",
      "createdAt": 1762033584314,
      "unifiedMode": "agent",
      "forceMode": "edit",
      "hasUnreadMessages": false,
      "totalLinesAdded": 0,
      "totalLinesRemoved": 0,
      "isArchived": false,
      "isWorktree": false,
      "isSpec": false
    }
  ],
  "selectedComposerIds": ["..."],
  "lastFocusedComposerIds": ["..."]
}
```

**Trace Events to Capture:**

- `composer_created` - When new composer session starts
- `composer_mode_changed` - When unifiedMode or forceMode changes
- `composer_archived` - When composer is archived
- `composer_lines_changed` - When totalLinesAdded/Removed changes
- `agent_mode_exited` - When agent mode exits (with visibility state)

---

### 🟢 **Medium Priority: Session & History Traces**

| Key                              | Value Size | Trace Type               | What to Capture                      |
| -------------------------------- | ---------- | ------------------------ | ------------------------------------ |
| `interactive.sessions`           | 2 bytes    | **Interactive Sessions** | Session metadata (currently minimal) |
| `history.entries`                | 268 bytes  | **Editor History**       | Recently opened files, editor state  |
| `cursorAuth/workspaceOpenedDate` | Unknown    | **Workspace Lifecycle**  | When workspace was first opened      |

**Sample Data Structure** (`history.entries`):

```json
[
  {
    "editor": {
      "resource": "file:///Users/.../CLAUDE.md",
      "forceFile": true,
      "options": { "override": "default" }
    }
  }
]
```

**Trace Events to Capture:**

- `file_opened` - When file appears in history.entries
- `workspace_opened` - When workspaceOpenedDate is set/updated
- `interactive_session_started` - When interactive.sessions changes

---

### 🔵 **Low Priority: UI State Traces**

| Key Category       | Keys                  | Trace Type      | What to Capture                   |
| ------------------ | --------------------- | --------------- | --------------------------------- |
| **Panel State**    | `workbench.panel.*`   | UI Visibility   | Panel open/close events           |
| **Sidebar State**  | `workbench.sideBar.*` | UI Visibility   | Sidebar position/visibility       |
| **Editor State**   | `workbench.editor.*`  | Editor Config   | Editor layout, language detection |
| **Terminal State** | `terminal.*`          | Terminal Config | Terminal layout, environment vars |
| **View State**     | `workbench.view.*`    | View Config     | Extension views, explorer state   |

**Note**: These are primarily UI state and may not be critical for telemetry unless tracking user behavior patterns.

---

### ⚪ **Not Trace-Relevant: Configuration & Cache**

These keys contain configuration or cache data that don't need tracing:

- `__$__isNewStorageMarker`, `__$__targetStorageMarker` - Internal markers
- `codelens/cache2` - Code lens cache
- `anysphere.cursor-retrieval`, `anysphere.cursorpyright` - Extension config
- `ms-python.*`, `ms-toolsai.jupyter` - Extension configs
- `eamodio.gitlens` - GitLens extension config
- `memento/*` - VS Code memento storage
- `debug.*` - Debugger state
- `output.activechannel` - Output channel selection

---

## Recommended Trace Capture Strategy

### 1. **Fix Schema Mismatch** (Critical)

**Problem**: Code expects `aiService.generations` as a table, but it's a key in `ItemTable`.

**Options:**

- **Option A**: Verify if Cursor uses a different database file for generations
- **Option B**: Adapt code to read from `ItemTable` key-value structure
- **Option C**: Check if Cursor version changed schema (table → key-value)

**Action**: Investigate Cursor's database structure to determine correct approach.

---

### 2. **Monitor ItemTable Key Changes** (High Priority)

Implement change detection for trace-relevant keys in `ItemTable`:

```python
# Pseudo-code for monitoring ItemTable
TRACE_RELEVANT_KEYS = [
    'aiService.generations',
    'aiService.prompts',
    'composer.composerData',
    'workbench.backgroundComposer.workspacePersistentData',
    'workbench.agentMode.exitInfo',
    'interactive.sessions',
    'history.entries',
    'cursorAuth/workspaceOpenedDate',
]

# Track last seen values
last_values = {}

# On change detection
for key in TRACE_RELEVANT_KEYS:
    current_value = get_item_table_value(key)
    if current_value != last_values.get(key):
        capture_trace_event(key, current_value, last_values.get(key))
        last_values[key] = current_value
```

---

### 3. **Implement Change Detection**

Since `ItemTable` uses `UNIQUE ON CONFLICT REPLACE`, we need to:

1. **Polling Approach**: Periodically query `ItemTable` for trace-relevant keys
2. **File Watcher**: Watch database file for changes, then query changed keys
3. **Version Tracking**: Track value hashes or full content to detect changes

**Recommended**: Use file watcher + polling (similar to current `databaseMonitor.ts` approach).

---

### 4. **Trace Event Types to Implement**

| Event Type                    | Source Key                                             | Payload Fields                                                    |
| ----------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------- |
| `composer_created`            | `composer.composerData`                                | composerId, createdAt, unifiedMode, forceMode                     |
| `composer_updated`            | `composer.composerData`                                | composerId, totalLinesAdded, totalLinesRemoved, hasUnreadMessages |
| `composer_archived`           | `composer.composerData`                                | composerId, isArchived                                            |
| `agent_mode_exited`           | `workbench.agentMode.exitInfo`                         | wasVisible (panel, auxiliaryBar, sideBar)                         |
| `background_composer_updated` | `workbench.backgroundComposer.workspacePersistentData` | setupStep, terminals, ranTerminalCommands, gitState               |
| `file_opened`                 | `history.entries`                                      | resource, forceFile, options                                      |
| `workspace_opened`            | `cursorAuth/workspaceOpenedDate`                       | timestamp                                                         |
| `generation_created`          | `aiService.generations`                                | (if table structure exists) uuid, data_version, value             |
| `prompt_created`              | `aiService.prompts`                                    | (if table structure exists) uuid, text, timestamp                 |

---

### 5. **cursorDiskKV Table**

**Current State**: Empty (0 rows)

**Action**:

- Monitor for future data
- May be used by newer Cursor versions
- Implement same monitoring strategy if data appears

---

## Implementation Checklist

### Phase 1: Schema Investigation

- [ ] Verify if `aiService.generations` exists as a table in other database files
- [ ] Check Cursor version and schema documentation
- [ ] Test if current table-based queries work in different workspaces

### Phase 2: ItemTable Monitoring

- [ ] Implement `ItemTable` key-value reader
- [ ] Add change detection for trace-relevant keys
- [ ] Create trace event generators for each key type
- [ ] Add deduplication logic (similar to current generation dedup)

### Phase 3: Trace Event Implementation

- [ ] Implement `composer_*` trace events
- [ ] Implement `agent_mode_*` trace events
- [ ] Implement `background_composer_*` trace events
- [ ] Implement `file_opened` trace events
- [ ] Implement `workspace_opened` trace events

### Phase 4: Integration

- [ ] Integrate with existing `database_monitor.py`
- [ ] Add to `databaseMonitor.ts` extension
- [ ] Update event schema to include new trace types
- [ ] Add tests for new trace capture logic

### Phase 5: cursorDiskKV Monitoring

- [ ] Add monitoring for `cursorDiskKV` table
- [ ] Implement same change detection strategy
- [ ] Document any keys found in future

---

## Current Implementation Gap

### What's Currently Captured

- ✅ `aiService.generations` (as table - **may not work**)
- ✅ `aiService.prompts` (as table - **may not work**)

### What's Missing

- ❌ `composer.composerData` - Composer session lifecycle
- ❌ `workbench.backgroundComposer.workspacePersistentData` - Background composer state
- ❌ `workbench.agentMode.exitInfo` - Agent mode transitions
- ❌ `history.entries` - File open events
- ❌ `interactive.sessions` - Interactive session metadata
- ❌ `cursorAuth/workspaceOpenedDate` - Workspace lifecycle
- ❌ `cursorDiskKV` table monitoring

---

## Recommendations

1. **Immediate**: Investigate schema mismatch for `aiService.generations`/`aiService.prompts`
2. **High Priority**: Implement `composer.composerData` monitoring (most valuable trace data)
3. **Medium Priority**: Add `history.entries` and `workbench.backgroundComposer.*` monitoring
4. **Low Priority**: Add UI state monitoring for user behavior analysis
5. **Future**: Monitor `cursorDiskKV` if it starts receiving data

---

## Appendix: All ItemTable Keys (73 total)

```
__$__isNewStorageMarker
__$__targetStorageMarker
agentLayout.shared.v6
aiService.generations
aiService.prompts
anysphere.cursor-retrieval
anysphere.cursorpyright
codelens/cache2
comments.continueOnComments
composer.composerData
cursor/needsComposerInitialOpening
cursor/planModeAutoApplied
cursor/planModeEnabled
cursor/sandboxSupported
cursorAuth/workspaceOpenedDate
debug.selectedroot
debug.uxstate
eamodio.gitlens
history.entries
interactive.sessions
lifecyle.lastShutdownReason
memento/workbench.editors.files.textFileEditor
memento/workbench.editors.textDiffEditor
ms-python.debugpy
ms-python.python
ms-toolsai.jupyter
notepad.reactiveStorageId
notepadData
output.activechannel
terminal
terminal.integrated.environmentVariableCollectionsV2
terminal.integrated.layoutInfo
terminal.numberOfVisibleViews
vscode.git
workbench.activityBar.hidden
workbench.agentMode.exitInfo
workbench.auxiliaryBar.hidden
workbench.auxiliarybar.activepanelid
workbench.auxiliarybar.initialViewContainers
workbench.auxiliarybar.viewContainersWorkspaceState
workbench.backgroundComposer.workspacePersistentData
workbench.editor.centered
workbench.editor.hidden
workbench.editor.languageDetectionOpenedLanguages.workspace
workbench.explorer.treeViewState
workbench.explorer.views.state
workbench.panel.aichat.a49cbff8-d7a9-4b17-bf79-171fdc5b2e44.numberOfVisibleViews
workbench.panel.composerChatViewPane.a49cbff8-d7a9-4b17-bf79-171fdc5b2e44
workbench.panel.hidden
workbench.panel.markers
workbench.panel.output
workbench.panel.position
workbench.panel.repl
workbench.panel.viewContainersWorkspaceState
workbench.panel.wasLastMaximized
workbench.scm.views.state
workbench.sideBar.hidden
workbench.sideBar.position
workbench.statusBar.hidden
workbench.view.agents
workbench.view.debug.state
workbench.view.explorer.numberOfVisibleViews
workbench.view.extension.containersView.state
workbench.view.extension.gitlens.state
workbench.view.extension.gitlensInspect.state
workbench.view.extension.gitlensPanel.state
workbench.view.extension.prismaActivitybar.state
workbench.view.extension.test.state
workbench.view.remote.state
workbench.view.search.state
workbench.zenMode.active
workbench.zenMode.exitInfo
~remote.forwardedPortsContainer
```

---

**End of Audit**
