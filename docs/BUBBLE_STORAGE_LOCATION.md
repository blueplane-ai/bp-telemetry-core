# Bubble Storage Location

## Answer: Bubbles Do NOT Live in ItemTable

Bubbles are **not stored in ItemTable**. They are stored in **cursorDiskKV** in the global storage database.

## Storage Structure

### ItemTable (Workspace Storage)
**Location**: `~/Library/Application Support/Cursor/User/workspaceStorage/{hash}/state.vscdb`

**Contains**:
- `composer.composerData` - **Metadata only** (composer IDs, names, timestamps)
  - Structure: `{allComposers: [{composerId, name, createdAt, ...}], ...}`
  - **NO bubbles** - just references/composer metadata

**Example**:
```json
{
  "allComposers": [
    {
      "composerId": "uuid",
      "name": "Conversation Title",
      "createdAt": 1234567890,
      "lastUpdatedAt": 1234567890,
      // ... metadata only, NO bubbles
    }
  ]
}
```

### cursorDiskKV (Global Storage)
**Location**: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

**Contains**:
1. **`composerData:<composerId>`** - Full composer data with **embedded bubbles**
   - Structure: `{composerId, conversation: [bubble1, bubble2, ...], ...}`
   - Bubbles are stored **inline** in the `conversation` array
   - This is where bubbles actually live

2. **`bubbleData:<bubbleId>`** - Separate bubble entries (if they exist)
   - **Note**: In our investigation, we found **0** `bubbleData:<id>` keys
   - Research document suggests this format, but current schema embeds bubbles

## Actual Bubble Storage

### Current Schema (What We Found)
```json
// cursorDiskKV: composerData:<composerId>
{
  "composerId": "uuid",
  "name": "Conversation Title",
  "conversation": [
    {
      "bubbleId": "uuid-1",
      "type": 1,  // user
      "text": "User message",
      // ... full bubble data
    },
    {
      "bubbleId": "uuid-2",
      "type": 2,  // ai
      "text": "AI response",
      // ... full bubble data
    }
  ]
}
```

**Key Finding**: Bubbles are **embedded** in the `conversation` array, not stored as separate `bubbleData:<id>` entries.

### Research Document Schema (May Be Outdated)
The research document suggests bubbles should be stored as:
- `bubbleData:<bubbleId>` keys in cursorDiskKV
- Referenced from `composerData.fullConversationHeadersOnly`

**Reality**: This format doesn't exist in the current database. Bubbles are embedded directly in `composerData.conversation`.

## Query Patterns

### To Get Bubbles from ItemTable
**❌ Not Possible** - Bubbles are not in ItemTable

### To Get Bubbles from cursorDiskKV
```sql
-- Get composer with embedded bubbles
SELECT value FROM cursorDiskKV WHERE key = 'composerData:<composerId>';

-- Parse JSON and extract conversation array
-- conversation array contains all bubbles
```

### To Get Bubble References from ItemTable
```sql
-- Get composer metadata (includes composer IDs)
SELECT value FROM ItemTable WHERE key = 'composer.composerData';

-- Parse to get composer IDs, then query cursorDiskKV for full data
```

## Summary

| Location | Contains | Bubbles? |
|----------|----------|----------|
| **ItemTable** (workspace) | `composer.composerData` | ❌ No - metadata only |
| **cursorDiskKV** (global) | `composerData:<id>` | ✅ Yes - embedded in `conversation` array |
| **cursorDiskKV** (global) | `bubbleData:<id>` | ❌ No - 0 found (may be deprecated format) |

## Conclusion

**Bubbles do NOT live in ItemTable**. They live in:
- **cursorDiskKV** table in **global storage** database
- Embedded in `composerData:<composerId>` entries
- Stored in the `conversation` array (not as separate `bubbleData:<id>` keys)

To access bubbles:
1. Query `composer.composerData` from ItemTable to get composer IDs
2. Query `composerData:<id>` from cursorDiskKV to get full composer data
3. Extract `conversation` array which contains all bubbles






