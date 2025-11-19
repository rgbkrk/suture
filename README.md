# Spork 🍴

Python bindings for [Automerge](https://automerge.org) - a CRDT library for building collaborative applications.

## What is Spork?

Spork provides Pythonic bindings to Automerge, enabling you to interact with real-time collaborative applications in Python. It supports:

- **Text CRDTs** for collaborative text editing
- **WebSocket sync** for real-time collaboration
- **Offline-first** architecture with automatic conflict resolution

## Installation

Note: these instructions are aspirational until published.

```bash
pip install spork --pre
```

For development:

```bash
git clone <repository-url>
cd spork
pip install -e .
```

## Quick Start

### Basic Document Operations

```python
import spork

repo = spork.Repo()
doc = await repo.create()

# String fields
await doc.set_string("title", "My Document")
print(await doc.get_string("title"))  # "My Document"

# Text fields with collaborative editing
text = await doc.put_text("content", "Hello World")
await text.insert(6, "Beautiful ")
print(await text.get())  # "Hello Beautiful World"

await repo.stop()
```

### Real-Time Collaboration

```python
# Connect to sync server
await repo.connect_websocket("wss://sync.automerge.org")

# Create synced document
doc = await repo.create()
print(f"Share this URL: {doc.url}")

# Changes sync automatically!
text = await doc.put_text("notes", "Hello from Python!")
await repo.stop()
```

### Testing

```bash
# Full test suite
pytest -v
```

## Architecture

Spork uses:
- **Rust**: Core automerge bindings via [PyO3](https://pyo3.rs)
- **Samod**: Automerge-repo for Rust
- **Tokio**: Async runtime for networking

## Requirements

- Python ≥ 3.8
- Rust (for building from source)


## Resources

- **Automerge**: https://automerge.org
- **Automerge Docs**: https://automerge.org/docs/
- **PyO3**: https://pyo3.rs

## Contributing

Contributions welcome! See examples and tests for patterns.

## Demo

Check out the [`demo/`](./demo) directory for an example of a realtime document with an agentic text editor:
- **CodeMirror frontend** with real-time cursor tracking
- **AI Collaborator** edits the document alongside you

Quick start:
```bash
# Start frontend in one terminal
cd demo && npm install && npm run dev

# In another terminal, build spork and start the demo bot with your automerge URL from above
maturin develop
uv run --with ./target/wheels/spork-*.whl demo/bot.py "automerge:j1khGXyZuHf5tgb5EKoAGdUGHuN"
```

## Status

⚠️ **Alpha**: API may change. Suitable for experimentation and prototyping. Come contribute to the design!


## License

MIT
