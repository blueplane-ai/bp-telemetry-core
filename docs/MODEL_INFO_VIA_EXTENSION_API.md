# Model Information via Extension API

## Key Discovery

The `extension.js` file (SpecStory extension) successfully accesses model information through **Cursor's internal extension API**, not directly from SQLite databases.

## How It Works

### 1. Accessing Cursor's Internal Extension

The extension accesses Cursor's internal services through VSCode's extension API:

```typescript
// Extension gets access to Cursor's internal extension
const cursorExtension = vscode.extensions.getExtension('cursor.cursor');
const editorStorageService = cursorExtension?.exports?.editorStorageService;

// Then calls:
const composers = await editorStorageService.getAllWorkspaceComposers();
```

### 2. Model Information Structure

Based on the `extension.js` code analysis, model information is accessed as:

**At Composer Level:**
```javascript
// From composer object returned by getAllWorkspaceComposers()
const modelName = composer.modelConfig?.modelName;
```

**At Bubble Level:**
```javascript
// From bubble/conversation item
const modelName = bubble.modelInfo?.modelName ?? composerModelName ?? "";
```

### 3. Code Evidence

From `extension.js` (minified):

```javascript
// Line 404: Composer-level model config extraction
function oz(e) {
    // ...
    let r = e.modelConfig && typeof e.modelConfig == "object" && "modelName" in e.modelConfig 
        ? e.modelConfig.modelName 
        : void 0;
    return {
        id: e.composerId,
        name: e.name ?? "Untitled",
        conversation: e.conversation?.map(n => az(n, t, e._v, r)) ?? [],
        // ...
    }
}

// Line 405: Bubble-level model info extraction
function az(e, t, r, n) {
    // ...
    return {
        // ...
        modelName: e?.modelInfo?.modelName ?? n ?? "",
        // ...
    }
}
```

## Why SQLite Doesn't Have It

1. **API vs Database**: The `editorStorageService.getAllWorkspaceComposers()` API returns **enriched data** that includes model information, but this may not be persisted in SQLite in the same format.

2. **Runtime Data**: Model information may be:
   - Added at runtime when composers are loaded
   - Stored server-side and injected via API
   - Derived from other data sources (settings, server config)

3. **Schema Difference**: The SQLite database stores the **raw data structure**, while the extension API returns a **processed/enriched structure** with additional metadata.

## Implications

### ✅ What Works
- **Extension API**: Can access model information via `editorStorageService.getAllWorkspaceComposers()`
- **Real-time Access**: Model info is available when composers are loaded through the API

### ❌ What Doesn't Work
- **Direct SQLite Access**: Model information is not stored in SQLite in accessible format
- **Offline Access**: Without the extension API, model info cannot be retrieved

## Solution: Use Extension API

To access model information, we need to:

1. **Access Cursor's Extension**:
   ```typescript
   const cursorExtension = vscode.extensions.getExtension('cursor.cursor');
   ```

2. **Get Editor Storage Service**:
   ```typescript
   const editorStorageService = cursorExtension?.exports?.editorStorageService;
   ```

3. **Call getAllWorkspaceComposers**:
   ```typescript
   const composers = await editorStorageService.getAllWorkspaceComposers();
   ```

4. **Extract Model Info**:
   ```typescript
   for (const composer of composers) {
       const composerModelName = composer.modelConfig?.modelName;
       
       for (const bubble of composer.conversation || []) {
           const bubbleModelName = bubble.modelInfo?.modelName ?? composerModelName;
           // Use model name
       }
   }
   ```

## Next Steps

1. **Update composerLoader.ts**: Use `editorStorageService.getAllWorkspaceComposers()` instead of direct SQLite access
2. **Extract Model Info**: Parse `modelConfig` and `modelInfo` from the API response
3. **Fallback Strategy**: If extension API unavailable, document that model info is not accessible

## Files to Update

- `src/capture/cursor/extension/src/composerLoader.ts` - Use extension API instead of SQLite
- `docs/MODEL_INFO_SEARCH_SUMMARY.md` - Document extension API as solution
- `docs/SQLITE_COMPOSER_QUERIES.md` - Add note about model info via API






