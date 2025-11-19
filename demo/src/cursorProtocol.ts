/**
 * Cursor Protocol for collaborative editing with AI assistance.
 *
 * Uses Automerge ephemeral messages for real-time cursor updates.
 * Designed to support both human cursors and AI streaming edits.
 */

export type CursorType = "user" | "ai" | "streaming_edit";

/**
 * Cursor message sent via ephemeral broadcast.
 */
export interface CursorMessage {
  type: "cursor";
  peerId: string;
  name: string;
  cursorType: CursorType;

  // Cursor position
  position: number; // Main cursor position (head)
  anchor?: number; // Selection start (if different from position)

  // Visual metadata
  color: string;

  // For streaming edits: partial pattern being typed
  partialPattern?: string;

  // For AI edits: what operation is being performed
  operationType?: "regex_edit" | "insert" | "delete" | "replace";

  // Timestamp for stale cursor cleanup
  timestamp: number;
}

/**
 * Internal cursor state for display.
 */
export interface Cursor {
  peerId: string;
  name: string;
  cursorType: CursorType;
  position: number;
  anchor?: number;
  color: string;
  partialPattern?: string;
  operationType?: string;
  timestamp: number;
}

/**
 * Generate a consistent color for a peer ID.
 */
export function generatePeerColor(peerId: string): string {
  const colors = [
    "#FF6B6B", // Red
    "#4ECDC4", // Teal
    "#45B7D1", // Blue
    "#FFA07A", // Orange
    "#98D8C8", // Mint
    "#F7DC6F", // Yellow
    "#BB8FCE", // Purple
    "#85C1E2", // Sky blue
    "#F8B739", // Gold
    "#52B788", // Green
  ];

  let hash = 0;
  for (let i = 0; i < peerId.length; i++) {
    hash = peerId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

/**
 * Generate a distinct color for AI cursors.
 */
export function generateAIColor(): string {
  return "#9333EA"; // Purple for AI
}

/**
 * Generate a color for streaming edit cursors.
 */
export function generateStreamingColor(): string {
  return "#F59E0B"; // Amber for streaming
}

/**
 * Get display name for cursor based on type.
 */
export function getCursorDisplayName(cursor: Cursor): string {
  if (cursor.cursorType === "ai") {
    return `🤖 ${cursor.name}`;
  }
  if (cursor.cursorType === "streaming_edit") {
    if (cursor.partialPattern) {
      return `🔄 ${cursor.name}: ${cursor.partialPattern}`;
    }
    return `🔄 ${cursor.name}`;
  }
  return cursor.name;
}

/**
 * Check if cursor is stale and should be removed.
 */
export function isCursorStale(cursor: Cursor, staleTimeoutMs: number = 10000): boolean {
  return Date.now() - cursor.timestamp > staleTimeoutMs;
}

/**
 * Create a cursor message for broadcast.
 */
export function createCursorMessage(
  peerId: string,
  name: string,
  cursorType: CursorType,
  position: number,
  anchor?: number,
  options?: {
    color?: string;
    partialPattern?: string;
    operationType?: string;
  }
): CursorMessage {
  return {
    type: "cursor",
    peerId,
    name,
    cursorType,
    position,
    anchor,
    color: options?.color || generatePeerColor(peerId),
    partialPattern: options?.partialPattern,
    operationType: options?.operationType,
    timestamp: Date.now(),
  };
}

/**
 * Parse cursor message from ephemeral broadcast.
 */
export function parseCursorMessage(payload: any): Cursor | null {
  const message = payload.message;

  if (!message || message.type !== "cursor") {
    return null;
  }

  return {
    peerId: message.peerId,
    name: message.name || "Anonymous",
    cursorType: message.cursorType || "user",
    position: message.position,
    anchor: message.anchor,
    color: message.color || generatePeerColor(message.peerId),
    partialPattern: message.partialPattern,
    operationType: message.operationType,
    timestamp: message.timestamp || Date.now(),
  };
}
