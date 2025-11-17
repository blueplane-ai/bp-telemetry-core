# Model Information Investigation

## Summary

Investigation into where model configuration information (`modelType`, `aiStreamingSettings`) might be stored in Cursor's database structure.

## Locations Checked

### ✅ Checked Locations

1. **Bubble-level fields** (`conversation` array items)
   - ❌ No `modelType` field found
   - ❌ No `aiStreamingSettings` field found
   - ✅ Found `isAgentic` flag
   - ✅ Found `capabilityType` field

2. **Composer-level fields** (top-level `composerData` object)
   - ❌ No `modelType` field found
   - ❌ No `aiStreamingSettings` field found
   - ✅ Found `originalModelLines` (empty dict)
   - ✅ Found `forceMode` field
   - ✅ Found `status` field
   - ✅ Found `context` object (13 keys)

3. **Composer context object**
   - ❌ No model-related keys found
   - Contains: attachedFiles, selections, externalLinks, cursorRules, etc.

4. **Composer tabs array**
   - ❌ No model-related keys found
   - Contains tab state information

5. **Global Storage ItemTable**
   - ✅ Found `cursorai/serverConfig` - may contain model settings
   - ✅ Found `cursorai/featureConfigCache` - may contain feature/model config
   - ✅ Found `cursorai/featureStatusCache` - may contain feature status
   - Found various AI-related keys but none directly related to composer model config

6. **Workspace Storage ItemTable**
   - ✅ Found `aiService.generations` - contains generation data (may have model info)
   - ✅ Found `aiService.prompts` - contains prompt data
   - Found various workbench panel keys but no direct model config

### ❌ Not Yet Checked

1. **aiService.generations structure**
   - Need to examine the actual structure of generation objects
   - May contain model information per generation

2. **cursorai/serverConfig**
   - May contain global model configuration
   - May contain default model settings

3. **cursorai/featureConfigCache**
   - May contain feature-specific model configurations
   - May contain model availability/feature flags

4. **Composer capabilities array**
   - May contain model-related capability metadata
   - Need to examine structure more deeply

5. **Intermediate chunks**
   - May contain model information in streaming chunks
   - Need to examine structure of intermediate chunks

6. **Code blocks**
   - May contain model information for code generation
   - Need to examine structure

7. **Settings/preferences files**
   - Cursor may store model preferences in separate settings files
   - Not in SQLite databases

8. **Server-side storage**
   - Model information may only be stored server-side
   - May be sent in API requests but not persisted locally

## Research Document Expectations vs Reality

The research document (`cursor-composer-data-capture-examples.md`) suggests:
- `modelType` should be at bubble level
- `aiStreamingSettings` should be at bubble level

**Reality:**
- These fields are **not present** in the actual database structure
- This suggests either:
  1. The schema has changed since the research document was written
  2. Model information is stored elsewhere (server-side, settings files, or different keys)
  3. Model information is only available at request time, not persisted

## Possible Explanations

1. **Model info not persisted**: Cursor may not persist model configuration per message, only using it at request time
2. **Server-side only**: Model information may be stored server-side and not synced to local database
3. **Different schema version**: The research document may describe a different version of Cursor's schema
4. **Settings-based**: Model configuration may be stored in user settings/preferences, not in composer data
5. **Derived from usageData**: Model information might be derivable from `usageData` at composer level (shows which models were used)

## Next Steps

1. ✅ Check `aiService.generations` structure for model fields - **No model fields found**
2. ✅ Check `cursorai/serverConfig` for global model settings - **Found `modelMigrations` key**
3. ✅ Check `cursorai/featureConfigCache` for feature-specific config - **Not yet examined**
4. ✅ Examine `usageData` at composer level - **Field does not exist in current schema**
5. ⏳ Check `modelMigrations` structure in serverConfig
6. ⏳ Check `chatConfig` in serverConfig for model settings
7. ⏳ Check if model info is in request/response metadata (not persisted)
8. ⏳ Check Cursor settings files (outside SQLite databases)

## Findings

Based on investigation:
- Model information is **not stored at bubble level** in the current schema
- Model information may be:
  - Stored server-side only
  - Available in `aiService.generations` (needs verification)
  - Derivable from `usageData` at composer level
  - Stored in settings/preferences files (not in SQLite)

