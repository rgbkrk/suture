import { EditorView, basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { Repo, DocHandle, type AutomergeUrl } from "@automerge/automerge-repo";
import { IndexedDBStorageAdapter } from "@automerge/automerge-repo-storage-indexeddb";
import { BrowserWebSocketClientAdapter } from "@automerge/automerge-repo-network-websocket";
import { automergeSyncPlugin } from "@automerge/automerge-codemirror";
import { peerCursorField, createCursorSyncPlugin, cursorTheme } from "./cursorPlugin";
import { generatePeerColor } from "./cursorProtocol";

// Document schema
interface Doc {
  text: string;
}

// Get or generate client name
function getClientName(): string {
  let name = localStorage.getItem("clientName");
  if (!name) {
    name = `User-${Math.random().toString(36).substring(2, 6)}`;
    localStorage.setItem("clientName", name);
  }
  return name;
}

// Setup Automerge Repo
const repo = new Repo({
  storage: new IndexedDBStorageAdapter(),
  network: [new BrowserWebSocketClientAdapter("wss://sync.automerge.org")],
});

// Get or create document
const existingDocId = window.location.hash.slice(1);

let handle: DocHandle<Doc>;

async function initEditor() {
  if (existingDocId && existingDocId.startsWith("automerge:")) {
    // Load existing document
    handle = await repo.find<Doc>(existingDocId as AutomergeUrl);
    document.getElementById("doc-id")!.textContent =
      `Document ID: ${existingDocId}`;
  } else {
    // Create new document
    handle = repo.create<Doc>();
    handle.change((doc: Doc) => {
      doc.text = "";
    });
    window.location.hash = handle.url;
    document.getElementById("doc-id")!.textContent =
      `Document ID: ${handle.url}`;
  }

  // Wait for handle to be ready
  await handle.whenReady();

  // Verify handle is ready before creating editor
  if (!handle.isReady()) {
    throw new Error("Handle not ready after whenReady() completed");
  }

  const doc = handle.doc();
  const initialText = doc?.text || "";

  // Get client info for cursor
  const clientName = getClientName();
  const peerId = repo.networkSubsystem.peerId;
  const clientColor = generatePeerColor(peerId);

  // Create editor state with plugins
  const startState = EditorState.create({
    doc: initialText,
    extensions: [
      basicSetup,
      automergeSyncPlugin({
        handle,
        path: ["text"],
      }),
      // Cursor support
      peerCursorField,
      createCursorSyncPlugin(handle, peerId, clientName, "user", clientColor),
      cursorTheme,
      EditorView.theme({
        "&": {
          height: "100%",
        },
        ".cm-scroller": {
          fontFamily: "ui-monospace, monospace",
        },
        ".cm-content": {
          caretColor: "#fff",
          color: "#fff",
        },
        "&.cm-focused .cm-cursor": {
          borderLeftColor: "#fff",
        },
        ".cm-gutters": {
          backgroundColor: "#2a2a2a",
          color: "#888",
          border: "none",
        },
      }),
      EditorView.lineWrapping,
    ],
  });

  // Create editor view
  const view = new EditorView({
    state: startState,
    parent: document.getElementById("editor-container")!,
  });

  document.getElementById("status")!.textContent =
    "Connected - Ready to collaborate!";
  document.getElementById("cursor-list")!.innerHTML =
    `<span style="color: #888;">You are <strong style="color: ${clientColor}">${clientName}</strong> • Remote cursors will appear when others connect</span>`;
}

// Initialize the editor
initEditor().catch((err) => {
  console.error("Failed to initialize editor:", err);
  document.getElementById("status")!.textContent = `Error: ${err.message}`;
});
