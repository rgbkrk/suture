# Cursor Protocol

This document describes the cursor protocol for collaborative editing with AI assistance.

## Overview

Cursors are shared using **Automerge ephemeral messages** (`docHandle.broadcast()`), not stored in the CRDT document. This ensures:
- Real-time updates without document history bloat
- No conflicts with document edits
- Automatic cleanup when peers disconnect

## Message Format

All cursor messages follow this structure:

```typescript
{
  type: "cursor",
  peerId: string,      // Unique peer identifier
  name: string,        // Display name
  cursorType: "user" | "ai" | "streaming_edit",
  position: number,    // Character position (0-indexed)
  anchor?: number,     // Optional: selection anchor for ranges
  color: string,       // Hex color code
  partialPattern?: string,     // For streaming_edit: partial regex pattern
  operationType?: string,      // For AI: type of operation being performed
  timestamp: number    // Unix timestamp in milliseconds
}
```

## Cursor Types

### `user`
Standard human user cursor with optional selection.

```typescript
{
  type: "cursor",
  peerId: "peer-a3f2",
  name: "Alice",
  cursorType: "user",
  position: 42,
  anchor: 35,          // Selection from 35 to 42
  color: "#4ECDC4",
  timestamp: Date.now()
}
```

### `ai`
AI assistant cursor during/after making edits.

```typescript
{
  type: "cursor",
  peerId: "ai-gpt4",
  name: "GPT-4",
  cursorType: "ai",
  position: 100,
  color: "#9333EA",    // Purple
  timestamp: Date.now()
}
```

### `streaming_edit`
Streaming cursor showing partial regex pattern as it's constructed.

```typescript
{
  type: "cursor",
  peerId: "ai-gpt4",
  name: "GPT-4",
  cursorType: "streaming_edit",
  position: 50,
  partialPattern: "(?<=Hello ",  // Incomplete regex pattern
  color: "#F59E0B",              // Amber
  timestamp: Date.now()
}
```

## Visual Rendering

- **User cursors**: Colored vertical line with name label
- **AI cursors**: Purple vertical line with 🤖 icon and name
- **Streaming cursors**: Amber pulsing line with 🔄 icon, name, and partial pattern

## Python Implementation

Broadcasting cursor updates from Python:

```python
import time

# Connect to document
doc_handle = await repo.find(doc_id)

# Broadcast cursor position
message = {
    "type": "cursor",
    "peerId": "ai-bot-001",
    "name": "Bot",
    "cursorType": "ai",
    "position": 50,
    "color": "#9333EA",
    "timestamp": int(time.time() * 1000)
}

doc_handle.broadcast(message)
```

## Stale Cursor Cleanup

Cursors are automatically removed after 10 seconds of no updates:

```typescript
if (Date.now() - cursor.timestamp > 10000) {
  removeCursor(cursor.peerId);
}
```

This handles:
- Browser tabs closing
- Network disconnections
- AI sessions ending

## Implementation Notes

- Cursor updates should be throttled to ~100ms to avoid excessive messages
- The `position` field is always required
- The `anchor` field creates a selection range when different from `position`
- Colors are generated consistently per peerId for human users
- AI cursors use fixed colors: purple (#9333EA) for `ai`, amber (#F59E0B) for `streaming_edit`
- Cursors at newline characters are hidden to avoid ambiguous positioning
