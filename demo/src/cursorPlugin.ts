/**
 * CodeMirror plugin for displaying collaborative cursors and selections.
 */

import { EditorView, ViewPlugin, ViewUpdate, Decoration, WidgetType } from "@codemirror/view";
import type { DecorationSet } from "@codemirror/view";
import { StateField, StateEffect } from "@codemirror/state";
import { DocHandle } from "@automerge/automerge-repo";
import type { Cursor, CursorType } from "./cursorProtocol";
import { parseCursorMessage, isCursorStale, getCursorDisplayName } from "./cursorProtocol";

// State effect to update peer cursors
export const updatePeerCursors = StateEffect.define<Cursor[]>();

/**
 * Cursor widget that appears at a position in the editor.
 */
class CursorWidget extends WidgetType {
  constructor(readonly cursor: Cursor) {
    super();
  }

  eq(other: CursorWidget) {
    return (
      this.cursor.peerId === other.cursor.peerId &&
      this.cursor.position === other.cursor.position &&
      this.cursor.partialPattern === other.cursor.partialPattern
    );
  }

  toDOM() {
    const dom = document.createElement("span");
    dom.className = `cm-remote-cursor cm-cursor-${this.cursor.cursorType}`;
    dom.style.cssText = `
      position: absolute;
      border-left: 2px solid ${this.cursor.color};
      height: 1.2em;
      pointer-events: none;
      z-index: 10;
      margin-left: -1px;
      ${this.cursor.cursorType === "streaming_edit" ? "animation: pulse 1.5s ease-in-out infinite;" : ""}
    `;

    // Add cursor label with peer name
    const label = document.createElement("span");
    label.className = "cm-cursor-label";
    label.textContent = getCursorDisplayName(this.cursor);
    label.style.cssText = `
      position: absolute;
      top: -1.8em;
      left: 0;
      background-color: ${this.cursor.color};
      color: white;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.75em;
      white-space: nowrap;
      pointer-events: none;
      font-family: sans-serif;
      box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    `;
    dom.appendChild(label);

    return dom;
  }

  ignoreEvent() {
    return true;
  }
}

/**
 * Create cursor widget decoration.
 */
function cursorWidget(cursor: Cursor): Decoration {
  return Decoration.widget({
    widget: new CursorWidget(cursor),
    side: -1,
  });
}

/**
 * Create selection mark decoration.
 */
function selectionMark(cursor: Cursor, from: number, to: number) {
  const opacity = cursor.cursorType === "ai" ? "20" : "33";
  return Decoration.mark({
    attributes: {
      style: `background-color: ${cursor.color}${opacity}; border-radius: 2px;`,
    },
  }).range(from, to);
}

/**
 * State field to track and display peer cursors.
 */
export const peerCursorField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none;
  },

  update(decorations, tr) {
    // Map existing decorations through document changes
    decorations = decorations.map(tr.changes);

    // Rebuild decorations when we receive a cursor update
    for (const effect of tr.effects) {
      if (effect.is(updatePeerCursors)) {
        const cursors = effect.value;
        const newDecorations: any[] = [];

        for (const cursor of cursors) {
          // Validate cursor position
          if (cursor.position >= 0 && cursor.position <= tr.newDoc.length) {
            // Check if cursor is at or near a newline - hide it if ambiguous
            const charAtPos = cursor.position < tr.newDoc.length
              ? tr.newDoc.sliceString(cursor.position, cursor.position + 1)
              : "";

            // Don't show cursor if it's exactly at a newline - position is ambiguous
            if (charAtPos !== "\n" && charAtPos !== "\r") {
              newDecorations.push(cursorWidget(cursor).range(cursor.position));
            }
          }

          // Add selection mark if present
          if (cursor.anchor !== undefined && cursor.anchor !== cursor.position) {
            const from = Math.min(cursor.anchor, cursor.position);
            const to = Math.max(cursor.anchor, cursor.position);

            if (from >= 0 && to <= tr.newDoc.length) {
              newDecorations.push(selectionMark(cursor, from, to));
            }
          }
        }

        decorations = Decoration.set(newDecorations, true);
      }
    }

    return decorations;
  },

  provide: (field) => EditorView.decorations.from(field),
});

/**
 * Plugin to sync local cursor via ephemeral messages and display remote cursors.
 */
export function createCursorSyncPlugin(
  docHandle: DocHandle<any>,
  localPeerId: string,
  localPeerName: string,
  localCursorType: CursorType = "user",
  localColor: string
) {
  return ViewPlugin.fromClass(
    class {
      view: EditorView;
      throttleTimeout: number | null = null;
      peerCursors: Map<string, Cursor> = new Map();
      cleanupInterval: number | null = null;

      constructor(view: EditorView) {
        this.view = view;

        // Listen for ephemeral messages (cursor updates from peers)
        docHandle.on("ephemeral-message", this.onEphemeralMessage);

        // Periodic cleanup of stale cursors
        this.cleanupInterval = window.setInterval(() => {
          this.cleanupStaleCursors();
        }, 2000);

        // Send initial cursor position
        this.syncLocalCursor();
      }

      update(update: ViewUpdate) {
        // Only sync cursor on selection changes or when focused
        if (update.selectionSet || update.focusChanged) {
          this.syncLocalCursor();
        }
      }

      syncLocalCursor = () => {
        // Throttle cursor updates
        if (this.throttleTimeout) return;

        this.throttleTimeout = window.setTimeout(() => {
          this.throttleTimeout = null;

          const selection = this.view.state.selection.main;

          // Broadcast cursor position via ephemeral message
          const message = {
            type: "cursor",
            peerId: localPeerId,
            name: localPeerName,
            cursorType: localCursorType,
            position: selection.head,
            anchor: selection.anchor !== selection.head ? selection.anchor : undefined,
            color: localColor,
            timestamp: Date.now(),
          };

          docHandle.broadcast(message);
        }, 100); // 100ms throttle
      };

      onEphemeralMessage = (payload: any) => {
        const cursor = parseCursorMessage(payload);
        if (!cursor) return;

        // Ignore own cursor
        if (cursor.peerId === localPeerId) return;

        // Update peer cursor data
        this.peerCursors.set(cursor.peerId, cursor);

        // Schedule decoration update
        this.scheduleUpdate();
      };

      cleanupStaleCursors() {
        let needsUpdate = false;

        for (const [peerId, cursor] of this.peerCursors.entries()) {
          if (isCursorStale(cursor)) {
            this.peerCursors.delete(peerId);
            needsUpdate = true;
          }
        }

        if (needsUpdate) {
          this.scheduleUpdate();
        }
      }

      scheduleUpdate() {
        // Defer update to next event loop
        setTimeout(() => {
          this.updatePeerCursors();
        }, 0);
      }

      updatePeerCursors() {
        const cursors: Cursor[] = Array.from(this.peerCursors.values());

        try {
          this.view.dispatch({
            effects: updatePeerCursors.of(cursors),
          });
        } catch (e) {
          console.error("Error updating peer cursors:", e);
        }
      }

      destroy() {
        if (this.throttleTimeout) {
          clearTimeout(this.throttleTimeout);
        }
        if (this.cleanupInterval) {
          clearInterval(this.cleanupInterval);
        }
        docHandle.off("ephemeral-message", this.onEphemeralMessage);
      }
    }
  );
}

/**
 * Theme styles for cursors with animation support.
 */
export const cursorTheme = EditorView.theme({
  ".cm-remote-cursor": {
    position: "absolute",
  },
  ".cm-cursor-label": {
    zIndex: "20",
  },
  // Pulse animation for streaming cursors
  "@keyframes pulse": {
    "0%, 100%": {
      opacity: "1",
    },
    "50%": {
      opacity: "0.5",
    },
  },
});
