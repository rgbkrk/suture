# Automerge CodeMirror + MCP Demo

A collaborative text editor demo showcasing real-time CRDT synchronization between a CodeMirror frontend and a Python Model Context Protocol (MCP) server.

## Architecture

```
┌─────────────────────┐
│  Browser Client 1   │
│  (CodeMirror)       │◄─┐
└─────────────────────┘  │
                         │
┌─────────────────────┐  │    wss://sync.automerge.org
│  Browser Client 2   │◄─┼────────────────────────────
│  (CodeMirror)       │  │    (WebSocket Sync Server)
└─────────────────────┘  │
                         │
┌─────────────────────┐  │
│  Python MCP Server  │◄─┘
│  (LLM-driven edits) │
└─────────────────────┘
```

## Features

### Frontend (CodeMirror)
- Real-time collaborative text editing
- Live cursor tracking showing each client's position
- Color-coded cursors for each user
- Automatic synchronization via Automerge CRDT
- Persistent storage in IndexedDB

### Backend (Python MCP Server)
- Language-first editing using regex patterns
- Multiple editing modes:
  - Regex-based find and replace
  - Position-based insertion
  - Range-based deletion
  - Full text replacement
- LLM-friendly interface for AI-driven text editing

## Quick Start

### 1. Install Dependencies

#### Frontend
```bash
cd demo
npm install
```

#### Python MCP Server
```bash
cd mcp-server
pip install -e .
```

Note: The MCP server requires the `spork` library (Automerge Python bindings) which is built from the Rust code in the parent directory.

### 2. Build Spork Library

```bash
cd ..  # Return to project root
pip install maturin
maturin develop
```

### 3. Run the Frontend

```bash
cd demo
npm run dev
```

This will open your browser at http://localhost:5173. The URL will contain a document ID like:
```
http://localhost:5173/#automerge:4xKg...
```

### 4. Connect the MCP Server

```bash
cd mcp-server
python server.py
```

Then use the MCP client to connect to the document:

```json
{
  "tool": "connect",
  "arguments": {
    "doc_id": "automerge:4xKg...",
    "sync_url": "wss://sync.automerge.org"
  }
}
```

## MCP Server Tools

### connect
Connect to an Automerge document via WebSocket sync server.

```json
{
  "tool": "connect",
  "arguments": {
    "doc_id": "automerge:YOUR_DOC_ID",
    "sync_url": "wss://sync.automerge.org"
  }
}
```

### get_text
Get the current text content of the document.

```json
{
  "tool": "get_text",
  "arguments": {}
}
```

### regex_edit
Edit text using regex pattern matching. This is the primary LLM-friendly editing method.

**Example: Replace a word**
```json
{
  "tool": "regex_edit",
  "arguments": {
    "pattern": "world",
    "replacement": "universe",
    "global": false
  }
}
```

**Example: Insert after specific text (using lookbehind)**
```json
{
  "tool": "regex_edit",
  "arguments": {
    "pattern": "(?<=Rice crispy )treats",
    "replacement": "sprinkle-treats",
    "global": true
  }
}
```

**Example: Insert before specific text (using lookahead)**
```json
{
  "tool": "regex_edit",
  "arguments": {
    "pattern": "(?=\\n\\nConclusion)",
    "replacement": "## Summary\nThis section summarizes...\n",
    "global": false
  }
}
```

### insert_at_position
Insert text at a specific character position.

```json
{
  "tool": "insert_at_position",
  "arguments": {
    "position": 42,
    "text": "Hello, "
  }
}
```

### delete_range
Delete a range of characters from the document.

```json
{
  "tool": "delete_range",
  "arguments": {
    "start": 10,
    "end": 25
  }
}
```

### set_text
Replace the entire document text.

```json
{
  "tool": "set_text",
  "arguments": {
    "text": "New document content..."
  }
}
```

## Language-First Syntax

The MCP server uses a language-first approach to editing, making it easier for LLMs to modify text without dealing with fine-grained character operations.

### Regex Pattern Examples

**Insert at the end of a line:**
```json
{
  "pattern": "$",
  "replacement": " (edited)",
  "global": false
}
```

**Replace within specific context:**
```json
{
  "pattern": "(?<=# Chapter 1\\n\\n).*?(?=\\n\\n# Chapter 2)",
  "replacement": "New content for Chapter 1",
  "global": false
}
```

**Add line numbers:**
```json
{
  "pattern": "^",
  "replacement": "1. ",
  "global": false
}
```

**Remove extra whitespace:**
```json
{
  "pattern": "\\s+",
  "replacement": " ",
  "global": true
}
```

## How It Works

### Automerge CRDT
- Conflict-free data structure that automatically merges concurrent edits
- Each client maintains a local copy of the document
- Changes are synced through a WebSocket server
- No central authority - true peer-to-peer collaboration

### Cursor Tracking
- Each client reports their cursor position in the Automerge document
- Positions are stored in a `cursors` object with client IDs as keys
- Frontend renders remote cursors with color-coded indicators
- Updates happen in real-time as users type and move their cursor

### Sync Flow
1. User makes a change in CodeMirror
2. Change is applied to local Automerge document
3. Automerge generates a change message
4. Message is sent to WebSocket sync server
5. Server broadcasts to all connected peers
6. Peers apply the change to their local documents
7. CodeMirror updates to reflect the new state

### MCP Integration
1. LLM client connects to MCP server
2. Server connects to same Automerge document
3. LLM uses regex patterns to describe edits
4. Server translates patterns to text operations
5. Operations are applied to Automerge document
6. Changes sync to all connected clients (including browsers)

## Development

### Frontend Development
```bash
cd demo
npm run dev     # Start dev server
npm run build   # Production build
```

### MCP Server Development
```bash
cd mcp-server
pip install -e ".[dev]"    # Install with dev dependencies
pytest                      # Run tests
black .                     # Format code
ruff check .                # Lint code
```

### Rebuild Spork Library
If you modify the Rust bindings:
```bash
cd ..  # Project root
maturin develop --release
```

## Troubleshooting

### Frontend won't connect
- Ensure you're using `wss://sync.automerge.org` (not `ws://`)
- Check browser console for WebSocket errors
- Verify the document ID is correct

### MCP server can't connect
- Ensure the `spork` library is installed: `pip list | grep spork`
- If missing, run `maturin develop` from project root
- Check that the document ID matches the frontend URL

### Changes not syncing
- Verify all clients are connected to the same sync server
- Check that the document ID is identical across clients
- Look for errors in browser console and server output

## References

- [Automerge Documentation](https://automerge.org/docs/)
- [Automerge Repo](https://github.com/automerge/automerge-repo)
- [CodeMirror 6](https://codemirror.net/)
- [Model Context Protocol](https://github.com/modelcontextprotocol)
- [Samod (Automerge Rust)](https://github.com/alexjg/samod)

## License

MIT
