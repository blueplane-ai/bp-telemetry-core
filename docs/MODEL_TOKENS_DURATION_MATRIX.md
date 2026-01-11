# Model, Tokens, and Duration Implementation Matrix

**Generated**: November 12, 2025  
**Status**: Current Implementation Status

---

## Overview

This matrix documents where `model`, `tokens_used` (or `tokens`), and `duration_ms` fields are currently implemented across hooks and traces for both **Cursor** and **Claude Code** platforms.

**Legend**:

- ✅ **Implemented** - Code attempts to capture field
- ⚠️ **Partial** - Code captures but data may be empty/0 (not provided by IDE)
- ❌ **Not Implemented** - Field not captured
- 🔍 **In Data** - Field exists in actual database records
- 📝 **In Code** - Field extraction logic exists

---

## Cursor Platform

### Hooks (Real-time Interception)

| Hook Type             | Event Type           | Model | Tokens | Duration | Notes                                                                                                                                                                                                                                                                               |
| --------------------- | -------------------- | ----- | ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `afterAgentResponse`  | `assistant_response` | ❌    | ❌     | ❌       | **Code**: Attempts to extract from `input_data.get('model')`, `input_data.get('tokens')`, `input_data.get('duration_ms')`<br>**Data**: ❌ **VERIFIED** - Cursor not providing in hook input (all empty/0)<br>**Location**: `src/capture/cursor/hooks/after_agent_response.py:33-35` |
| `afterShellExecution` | `shell_execution`    | ❌    | ❌     | ❌       | **Code**: Attempts to extract `duration_ms` from hook input<br>**Data**: ❌ **VERIFIED** - Cursor not providing (0/5 events have duration_ms > 0)<br>**Location**: `src/capture/cursor/hooks/after_shell_execution.py:35`                                                           |
| `afterMCPExecution`   | `mcp_execution`      | ❌    | ❌     | ❌       | **Code**: Attempts to extract `duration_ms` if provided<br>**Data**: ❌ **VERIFIED** - Cursor not providing (0/5 events have duration_ms > 0)<br>**Location**: `src/capture/cursor/hooks/after_mcp_execution.py`                                                                    |
| `afterFileEdit`       | `file_edit`          | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                                                                                                                     |
| `beforeReadFile`      | `file_read`          | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                                                                                                                     |
| `beforeSubmitPrompt`  | `user_prompt`        | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                                                                                                                     |
| `session`             | `session_start`      | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                                                                                                                     |
| `stop`                | `session_end`        | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                                                                                                                     |

### Database Traces (Polling)

| Source                                          | Event Type       | Model | Tokens | Duration | Notes                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------------------------------- | ---------------- | ----- | ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **TypeScript Extension** (`databaseMonitor.ts`) | `database_trace` | ❌    | ❌     | ❌       | **Code**: Attempts to extract from `value?.model` and `value?.tokensUsed`<br>**Issue**: Tries to query non-existent SQL table `"aiService.generations"`<br>**Data**: ❌ **VERIFIED** - Not producing traces (all traces from python_monitor)<br>**Location**: `src/capture/cursor/extension/src/databaseMonitor.ts:348-351`                                                                                       |
| **Python Monitor** (`database_monitor.py`)      | `database_trace` | ❌    | ❌     | ❌       | **Code**: ✅ **VERIFIED** - Correctly reads from ItemTable<br>**Code**: Hardcoded `model = "unknown"`, `tokens_used = 0` (because data doesn't exist)<br>**Data**: ❌ **VERIFIED** - ItemTable structure only contains `unixMs`, `generationUUID`, `type`, `textDescription`<br>**Note**: Hardcoded values are placeholders, not actual data<br>**Location**: `src/processing/cursor/database_monitor.py:446-447` |

**Cursor Database Structure** (VERIFIED from `ItemTable`):

- ✅ Generations stored as JSON array in `aiService.generations` key (ItemTable, not SQL table)
- ✅ **Actual fields**: `unixMs`, `generationUUID`, `type`, `textDescription`
- ❌ **VERIFIED**: `model` field does NOT exist in ItemTable structure
- ❌ **VERIFIED**: `tokens`/`usage` fields do NOT exist in ItemTable structure
- ❌ **VERIFIED**: `duration_ms` field does NOT exist in ItemTable structure
- ❌ **VERIFIED**: No `value` field with nested JSON (TypeScript extension expects this but it doesn't exist)
- **Note**: Python monitor correctly reads from ItemTable and correctly identifies missing fields. TypeScript extension attempts to query non-existent SQL table structure.

---

## Claude Code Platform

### Hooks (Real-time Interception)

| Hook Type          | Event Type           | Model | Tokens | Duration | Notes                                                                                                                                                                                  |
| ------------------ | -------------------- | ----- | ------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Stop`             | `assistant_response` | ❌    | ❌     | ❌       | **Code**: No model/tokens/duration extraction<br>**Location**: `src/capture/claude_code/hooks/stop.py`<br>**Note**: Hook fires at end of response but doesn't receive model/token data |
| `PostToolUse`      | `tool_use`           | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                        |
| `PreToolUse`       | `tool_use`           | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                        |
| `UserPromptSubmit` | `user_prompt`        | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                        |
| `SessionStart`     | `session_start`      | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                        |
| `SessionEnd`       | `session_end`        | ❌    | ❌     | ❌       | No model/tokens/duration fields                                                                                                                                                        |

**Claude Code Hook Input** (from docs):

- Hooks receive minimal data (session_id, prompt text, tool names)
- **No model/token/duration data** provided in hook inputs
- Claude Code doesn't expose this metadata via hooks

### Transcript Traces (File Monitoring)

| Source                                           | Event Type         | Model  | Tokens | Duration | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------ | ------------------ | ------ | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Transcript Monitor** (`transcript_monitor.py`) | `transcript_trace` | ✅📝🔍 | ✅📝🔍 | ❌       | **Code**: ✅ **FIXED** - Extracts `model` from `entry['message']['model']`<br>**Code**: ✅ **FIXED** - Extracts `tokens_used` from `entry['message']['usage']` (calculates `input_tokens + output_tokens`)<br>**Data**: ✅ **VERIFIED**: Model and usage fields exist in `message` object (70% of entries have them)<br>**Actual Format**: Entries contain `message` object with nested `model` and `usage` fields<br>**Usage structure**: `usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens`, etc.<br>**Location**: `src/processing/claude_code/transcript_monitor.py:300-320` |

**Claude Code Transcript Format** (VERIFIED):

- ✅ **`model` field**: Located in `entry['message']['model']` (e.g., `"claude-sonnet-4-5-20250929"`)
- ✅ **`usage` field**: Located in `entry['message']['usage']` with structure:
  - `input_tokens`: Prompt tokens
  - `output_tokens`: Completion tokens
  - `cache_creation_input_tokens`: Cache creation tokens
  - `cache_read_input_tokens`: Cache read tokens
  - `service_tier`: Service tier used
- ✅ **`role` field**: Located in `entry['message']['role']` (e.g., `"assistant"`, `"user"`)
- **Top-level fields**: `parentUuid`, `isSidechain`, `userType`, `cwd`, `sessionId`, `version`, `gitBranch`, `message`, `requestId`, `type`, `uuid`, `timestamp`
- **Note**: Model/usage are nested in `message` object, not at top level. Code has been fixed to extract from correct location.

---

## Database Extraction Logic

### Writer Implementation

**Location**: `src/processing/database/writer.py:_extract_indexed_fields()`

| Field         | Extraction Logic                                                                                                                                                       | Status                                                 |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `model`       | `payload.get('model') or metadata.get('model')`<br>Empty strings converted to `None`                                                                                   | ✅ **Fixed** - Handles empty strings correctly         |
| `tokens_used` | `payload.get('tokens_used') or payload.get('tokens') or metadata.get('tokens_used') or metadata.get('tokens')`<br>Supports both field names for backward compatibility | ✅ **Fixed** - Handles both `tokens` and `tokens_used` |
| `duration_ms` | `payload.get('duration_ms') or metadata.get('duration_ms')`<br>0 is valid value (not converted to None)                                                                | ✅ **Working** - Correctly preserves 0 values          |

---

## Current Database State

**Query Results** (as of validation):

```
Total Events: 3,909
Events with model (non-empty): 438 (all "unknown" from database_trace)
Events with tokens_used > 0: 0
Events with duration_ms > 0: 0
```

**Breakdown by Platform**:

| Platform        | Event Type           | Total | Has Model       | Has Tokens | Has Duration |
| --------------- | -------------------- | ----- | --------------- | ---------- | ------------ |
| **Cursor**      | `assistant_response` | 126   | 0               | 0          | 0            |
| **Cursor**      | `database_trace`     | 438   | 438 ("unknown") | 0          | 0            |
| **Cursor**      | `shell_execution`    | 1,920 | 0               | 0          | 0            |
| **Claude Code** | `assistant_response` | 12    | 0               | 0          | 0            |
| **Claude Code** | `transcript_trace`   | 545   | 0               | 0          | 0            |

---

## Summary by Field

### Model Field

| Platform        | Source                    | Status | Notes                                                                                     |
| --------------- | ------------------------- | ------ | ----------------------------------------------------------------------------------------- |
| **Cursor**      | `afterAgentResponse` hook | ❌     | ❌ **VERIFIED** - Cursor not providing in hook input (all empty)                          |
| **Cursor**      | Database trace (TS)       | ❌     | ❌ **VERIFIED** - Not producing traces (tries to query non-existent table)                |
| **Cursor**      | Database trace (Python)   | ✅📝🔍 | ✅ **FIXED** - Model extracted from `composerData.usageData` (model name is dictionary KEY!) |
| **Cursor**      | `usageData` in composer   | ✅📝🔍 | ✅ **NEW** - Model, cost, and response count available per-composer |
| **Claude Code** | `Stop` hook               | ❌     | Not provided in hook input                                                                |
| **Claude Code** | Transcript trace          | ✅📝🔍 | ✅ **FIXED** - Extracts from `entry['message']['model']` (70% of entries have model)      |

### Tokens Field

| Platform        | Source                    | Status | Notes                                                                                                |
| --------------- | ------------------------- | ------ | ---------------------------------------------------------------------------------------------------- |
| **Cursor**      | `afterAgentResponse` hook | ❌     | ❌ **VERIFIED** - Cursor not providing in hook input (all 0)                                         |
| **Cursor**      | Database trace (TS)       | ❌     | ❌ **VERIFIED** - Not producing traces (tries to query non-existent table)                           |
| **Cursor**      | Database trace (Python)   | ❌     | ❌ **VERIFIED** - ItemTable doesn't contain tokens field (hardcoded 0 placeholder)                   |
| **Claude Code** | `Stop` hook               | ❌     | Not provided in hook input                                                                           |
| **Claude Code** | Transcript trace          | ✅📝🔍 | ✅ **FIXED** - Extracts from `entry['message']['usage']` (calculates `input_tokens + output_tokens`) |

### Duration Field

| Platform        | Source                     | Status | Notes                                                                    |
| --------------- | -------------------------- | ------ | ------------------------------------------------------------------------ |
| **Cursor**      | `afterAgentResponse` hook  | ❌     | ❌ **VERIFIED** - Cursor not providing in hook input (all 0)             |
| **Cursor**      | `afterShellExecution` hook | ❌     | ❌ **VERIFIED** - Cursor not providing (0/5 events have duration_ms > 0) |
| **Cursor**      | `afterMCPExecution` hook   | ❌     | ❌ **VERIFIED** - Cursor not providing (0/5 events have duration_ms > 0) |
| **Cursor**      | Database trace             | ❌     | ❌ **VERIFIED** - ItemTable doesn't contain duration_ms field            |
| **Claude Code** | Hooks                      | ❌     | Not provided in any hook inputs                                          |
| **Claude Code** | Transcript trace           | ❌     | Not extracted from transcript entries                                    |

---

## Key Findings

### ✅ What's Working

1. **Extraction Logic**: Database writer correctly handles both `tokens` and `tokens_used` field names
2. **Empty String Handling**: Model empty strings are converted to `NULL` in database
3. **Zero Value Preservation**: `duration_ms` and `tokens_used` correctly preserve 0 as valid value
4. **Cursor Model Extraction**: ✅ **NEW** - Model info extracted from `composerData.usageData` field

### 🆕 Cursor Model Discovery (December 2025)

**Key Finding**: Cursor DOES store model information, just in a different location than originally expected!

**Location**: `composerData.{composerId}.usageData` in `cursorDiskKV` table

**Data Structure**:
```json
{
  "usageData": {
    "claude-4.5-opus-high-thinking": {
      "costInCents": 141,
      "amount": 23
    }
  }
}
```

**Key Insight**: The model name is stored as the **KEY** of the `usageData` dictionary, not as a value!

**What's Available**:
- `model_name` - The model used (e.g., "claude-4.5-opus-high-thinking", "composer-1", "gemini-3-pro")
- `costInCents` - Cost in cents for this model in this conversation
- `amount` - Number of AI responses using this model

**Scope**: Per-composer (conversation-level), not per-message like Claude Code

**Implementation**: See `src/processing/cursor/data_extractors.py::ComposerDataExtractor._extract_model_usage()`

### ⚠️ Current Limitations

1. **Cursor Hooks**: ❌ **VERIFIED** - Cursor IDE does NOT provide `model`, `tokens`, or `duration_ms` in hook inputs. Code attempts extraction but all values are empty/0.
2. **Cursor Database**: ❌ **VERIFIED** - Cursor's `ItemTable` structure does NOT include model/token/duration fields. Actual structure: `unixMs`, `generationUUID`, `type`, `textDescription`. Python monitor hardcodes "unknown"/0 as placeholders, not actual data.
3. **TypeScript Extension**: ❌ **VERIFIED** - Attempts to query non-existent SQL table `"aiService.generations"` and expects `value` field with nested JSON. Not producing any traces (all traces come from python_monitor).
4. **Claude Code Hooks**: No hooks receive model/token/duration data (not exposed by Claude Code)
5. **Claude Code Transcripts**: ✅ **VERIFIED & FIXED** - `model` and `usage` fields exist but are nested in `entry['message']` object, not at top level. Code has been updated to extract from correct location.

### 🔧 Recommendations

1. **Monitor Cursor Updates**: If Cursor adds model/token data to hook inputs or ItemTable structure, it will be automatically captured
2. **Claude Code Transcripts**: ✅ **VERIFIED & FIXED** - Model and usage fields exist but are nested in `entry['message']` object. Code has been updated to extract from `message.model` and `message.usage` (70% of entries contain these fields)
3. **Cursor Database Traces**: ✅ **VERIFIED** - ItemTable structure confirmed to NOT contain model/tokens. Python monitor correctly handles this. TypeScript extension needs fix to read from ItemTable instead of querying non-existent table.
4. **Consider Alternative Sources**: For Cursor, may need to parse response headers, API responses, or Cursor's internal state for model/token data since neither hooks nor database contain it

---

## Code References

### Cursor Hooks

- `src/capture/cursor/hooks/after_agent_response.py` - Attempts model/tokens/duration extraction (not provided by Cursor)
- `src/capture/cursor/hooks/after_shell_execution.py` - Attempts duration extraction (not provided by Cursor)

### Cursor Traces

- `src/capture/cursor/extension/src/databaseMonitor.ts` - TypeScript database monitor
- `src/processing/cursor/database_monitor.py` - Python database monitor

### Claude Code Traces

- `src/processing/claude_code/transcript_monitor.py` - Transcript parsing with model/tokens extraction

### Database Writer

- `src/processing/database/writer.py` - Field extraction logic (recently fixed)

---

**Last Updated**: November 12, 2025  
**Related Docs**:

- [HOOKS_VS_TRACES.md](./HOOKS_VS_TRACES.md)
- [CURSOR_SCHEMA_INVESTIGATION.md](./CURSOR_SCHEMA_INVESTIGATION.md)
- [layer1_cursor_hook_output.md](./architecture/layer1_cursor_hook_output.md)
- [layer1_claude_hook_output.md](./architecture/layer1_claude_hook_output.md)
