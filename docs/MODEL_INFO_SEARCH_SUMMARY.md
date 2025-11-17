# Model Information Search Summary

## Overview

Investigation into where model configuration (`modelType`, `aiStreamingSettings`) is stored in Cursor's database structure.

## ✅ Locations Checked

### 1. Bubble-Level Fields (`conversation` array items)

**Status**: ❌ **Not Found**

Checked fields:

- `modelType` - Not present
- `aiStreamingSettings` - Not present
- `thinking` - Not present
- `isThought` - Present but not model info
- `isAgentic` - Present (boolean flag)
- `capabilityType` - Present (number)

**Conclusion**: Model information is **not stored at the individual message/bubble level**.

### 2. Composer-Level Fields (top-level `composerData` object)

**Status**: ❌ **Not Found**

Checked fields:

- `modelType` - Not present
- `aiStreamingSettings` - Not present
- `usageData` - **Not present** (research doc suggests it should exist)
- `originalModelLines` - Present but empty dict
- `forceMode` - Present (string)
- `status` - Present (string)

**Conclusion**: Model information is **not stored at the composer level** in the expected fields.

### 3. Composer Context Object

**Status**: ❌ **Not Found**

Checked structure:

- `context.editTrailContexts` - Present but empty
- `context.attachedFiles` - Present
- `context.selections` - Present
- No model-related keys found

**Conclusion**: Context object does not contain model configuration.

### 4. Composer Tabs Array

**Status**: ❌ **Not Found**

Checked structure:

- `tabs[].type` - Present
- No model-related keys found

**Conclusion**: Tabs do not contain model configuration.

### 5. Global Storage ItemTable

**Status**: ⚠️ **Partially Found**

Found keys:

- `cursorai/serverConfig` - Contains `modelMigrations` (list) and `chatConfig` (dict)
- `cursorai/featureConfigCache` - Not yet examined
- `cursorai/featureStatusCache` - Not yet examined
- Various AI-related keys but none directly related to composer model config

**Conclusion**: Server config may contain model information, but not per-composer or per-message.

### 6. Workspace Storage ItemTable

**Status**: ❌ **Not Found**

Checked keys:

- `aiService.generations` - Contains generation data but **no model fields**
  - Fields: `unixMs`, `generationUUID`, `type`, `textDescription`
  - No `model` or `modelType` fields
- `aiService.prompts` - Contains prompt data
- `composer.composerData` - Contains composer list (metadata only)

**Conclusion**: Generation records do not include model information.

### 7. Server Config (`cursorai/serverConfig`)

**Status**: ⚠️ **Found Related Keys**

Found:

- `modelMigrations` - List (structure not yet examined in detail)
- `chatConfig` - Dict with config but no direct model fields
  - Contains: `fullContextTokenLimit`, `maxRuleLength`, `maxMcpTools`, etc.
  - No model selection/configuration fields

**Conclusion**: Server config contains model-related metadata but not per-message model info.

## ❌ Locations Not Yet Checked

### 1. Feature Config Cache

- **Location**: `cursorai/featureConfigCache` in global storage ItemTable
- **Reason**: May contain feature-specific model configurations
- **Priority**: Medium

### 2. Model Migrations Structure

- **Location**: `cursorai/serverConfig.modelMigrations` (list)
- **Reason**: May contain model availability/configuration info
- **Priority**: Medium

### 3. Intermediate Chunks

- **Location**: `bubble.intermediateChunks` array
- **Reason**: May contain model information in streaming chunks
- **Priority**: Low (chunks are likely content, not metadata)

### 4. Code Blocks

- **Location**: `bubble.codeBlocks` array
- **Reason**: May contain model information for code generation
- **Priority**: Low (likely execution results, not model config)

### 5. Capabilities Array Structure

- **Location**: `composer.capabilities` array
- **Reason**: May contain model-related capability metadata
- **Priority**: Medium

### 6. Settings/Preferences Files

- **Location**: Cursor settings files (outside SQLite databases)
- **Reason**: Model preferences may be stored in user settings
- **Priority**: High (likely location for user preferences)

### 7. Server-Side Storage

- **Location**: Cursor's backend servers
- **Reason**: Model information may only be stored server-side
- **Priority**: High (most likely explanation)

### 8. Request/Response Metadata

- **Location**: Network requests/responses (not persisted)
- **Reason**: Model info may only be available at request time
- **Priority**: High (would require extension/network monitoring)

## Key Findings

1. **Model info NOT in bubbles**: Confirmed that `modelType` and `aiStreamingSettings` are not present in bubble data
2. **Model info NOT in composers**: Confirmed that model configuration is not stored at composer level
3. **Schema mismatch**: The research document describes fields that don't exist in the current schema
4. **No usageData**: The `usageData` field mentioned in research doc doesn't exist in current schema
5. **Server config exists**: Found `modelMigrations` in server config but structure not yet examined

## Most Likely Explanations

1. **Server-side only** (Most Likely)

   - Model information is stored on Cursor's servers
   - Only sent in API requests, not persisted locally
   - Would require network monitoring or extension API access

2. **Settings files** (Likely)

   - Model preferences stored in user settings/preferences
   - Not in SQLite databases
   - Would require examining Cursor's settings files

3. **Schema version difference** (Possible)

   - Research document describes older/newer schema version
   - Current Cursor version doesn't persist model info
   - May have been removed or moved to server-side

4. **Derived from other data** (Unlikely)
   - Model info might be derivable from other fields
   - But no obvious correlation found

## Recommendations

1. **Check settings files**: Examine Cursor's user settings/preferences files
2. **Monitor network requests**: Use extension API or network monitoring to capture model info from requests
3. **Examine server config**: Deep dive into `modelMigrations` and `featureConfigCache` structures
4. **Check extension API**: Use VSCode extension API to access Cursor's internal APIs (like `editorStorageService`)
5. **Accept limitation**: If model info is server-side only, document this limitation

## Files Created

- `docs/MODEL_INFO_INVESTIGATION.md` - Detailed investigation notes
- `docs/MODEL_INFO_SEARCH_SUMMARY.md` - This summary document

