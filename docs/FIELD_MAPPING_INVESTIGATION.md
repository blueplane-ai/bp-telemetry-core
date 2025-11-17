# Field Mapping Investigation Results

## Summary

After running Phase 4 validation and investigating missing fields, we discovered that the actual bubble schema in Cursor's database differs from the research document expectations.

## Actual vs Expected Fields

### ✅ Fields That Exist (with different names)

| Expected Field | Actual Field | Notes |
|----------------|--------------|-------|
| `tokenCount.inputTokens` | `tokenCountUpUntilHere` (not always present) | Different structure |
| `tokenCount.outputTokens` | `tokenCountUpUntilHere` (not always present) | Different structure |
| `createdAt`, `lastUpdatedAt`, `completedAt` | `timingInfo.clientStartTime`, `timingInfo.clientEndTime`, etc. | Nested in timingInfo dict |
| `capabilities[]` (array) | `capabilitiesRan` (dict) | Different structure - dict with capability names as keys |
| `capabilities[].bubbleDataMap` | `capabilityStatuses` (dict) | Different structure |

### ❌ Fields That Don't Exist

| Expected Field | Status | Notes |
|----------------|--------|-------|
| `modelType` | ❌ Not found | Model information may be stored elsewhere or not persisted |
| `aiStreamingSettings` | ❌ Not found | Model settings may not be persisted per bubble |
| `thinking` | ❌ Not found | Thinking content may be in `intermediateChunks` or not persisted |
| `toolFormerdata` | ❌ Not found | Tool calls may be represented differently |
| `toolFormerdata.toolCalls[]` | ❌ Not found | Tool execution may be in `capabilitiesRan` or `codeBlocks` |

### 🔍 Fields That Exist But Need Investigation

| Field | Type | Notes |
|-------|------|-------|
| `intermediateChunks` | array | May contain thinking/tool execution data |
| `codeBlocks` | array | May contain tool execution results |
| `capabilitiesRan` | dict | Contains capability execution metadata |
| `capabilityStatuses` | dict | Contains capability status information |
| `timingInfo` | dict | Contains timing metadata: `clientStartTime`, `clientRpcSendTime`, `clientSettleTime`, `clientEndTime` |
| `isThought` | boolean | Flag indicating if bubble contains thinking content (not always present) |
| `tokenCountUpUntilHere` | number | Cumulative token count (not always present) |
| `tokenDetailsUpUntilHere` | object | Detailed token information (not always present) |

## Actual Bubble Structure

Based on analysis of real bubbles from the database:

```json
{
  "bubbleId": "uuid",
  "serverBubbleId": "uuid",
  "type": 1,  // 1=user, 2=ai
  "text": "Message content",
  "richText": {...},  // Lexical editor state
  "timingInfo": {
    "clientStartTime": 1234567890123,
    "clientRpcSendTime": 1234567890124,
    "clientSettleTime": 1234567890456,
    "clientEndTime": 1234567890456
  },
  "capabilitiesRan": {
    "mutate-request": {...},
    "start-submit-chat": {...},
    "before-submit-chat": {...},
    "after-submit-chat": {...},
    "after-apply": {...}
  },
  "capabilityStatuses": {
    "mutate-request": {...},
    "start-submit-chat": {...},
    // ... same keys as capabilitiesRan
  },
  "intermediateChunks": [...],  // May contain thinking/tool data
  "codeBlocks": [...],  // May contain tool execution results
  "relevantFiles": [...],
  "context": {...},
  "isAgentic": boolean,
  "isThought": boolean,  // Not always present
  "tokenCountUpUntilHere": number,  // Not always present
  "tokenDetailsUpUntilHere": {...}  // Not always present
}
```

## Recommendations

1. **Update extraction script** to look for:
   - `timingInfo` instead of individual timing fields
   - `capabilitiesRan` and `capabilityStatuses` instead of `capabilities` array
   - `intermediateChunks` for thinking/tool data
   - `codeBlocks` for tool execution results

2. **Investigate further**:
   - Check if `intermediateChunks` contains thinking content
   - Check if `codeBlocks` contains tool execution results
   - Check if model information is stored at composer level or elsewhere
   - Check if tool calls are embedded in `capabilitiesRan` or `codeBlocks`

3. **Schema version differences**:
   - The research document may describe a different version of the schema
   - Cursor may have changed how data is stored
   - Some fields may only be present in certain contexts (e.g., agentic mode)

## Next Steps

1. Update `extract_bubble_fields()` to handle actual field names
2. Investigate `intermediateChunks` structure
3. Investigate `codeBlocks` structure  
4. Check composer-level metadata for model information
5. Update validation script to check for actual fields






