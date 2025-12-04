#!/usr/bin/env python3
# Run as:
# ```
# uv run --with ./target/wheels/spork-*.whl demo/bot.py
# ```
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "openai>=1.0.0",
#   "cbor2>=5.0.0",
#   "partial-json-parser>=0.2.0",
# ]
# ///
"""
AI bot that participates in collaborative Automerge editing using Ollama.

This bot uses Ollama's OpenAI-compatible API with configurable models.
Make sure Ollama is running before starting the bot.

Usage from demo directory:
    uv run bot.py <doc_id> [--once] [--model MODEL] [--debug] [--wait SECONDS]

Usage from project root:
    uv run demo/bot.py <doc_id> [--once] [--model MODEL] [--debug] [--wait SECONDS]

Example:
    uv run bot.py automerge:4xKg...
    uv run bot.py automerge:4xKg... --once
    uv run bot.py automerge:4xKg... --model llama3.3
    uv run bot.py automerge:4xKg... --model llama3.3 --wait 2
    uv run bot.py automerge:4xKg... --once --model llama3.3 --debug
"""

import asyncio
import os
import sys
import time
from typing import Optional

import cbor2
import spork
from openai import AsyncOpenAI

from cursor_controller import StreamingEditController, CursorPosition, CursorType


class CollaborativeBot:
    def __init__(
        self,
        doc_id: str,
        model: str = "gpt-oss",
        once: bool = False,
        debug: bool = False,
        wait_time: float = 1.0,
    ):
        self.doc_id = doc_id
        self.model = model
        self.peer_id = f"ai-bot-{int(time.time())}"
        self.color = "#9333EA"  # Purple for AI
        self.repo: Optional[spork.Repo] = None
        self.doc_handle: Optional[spork.DocHandle] = None
        # Use Ollama's OpenAI-compatible endpoint
        self.client = AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Ollama doesn't need a real API key
        )
        self.running = False
        self.once = once
        self.debug = debug
        self.wait_time = wait_time

    async def connect(self):
        """Connect to Automerge document."""
        print(f"🤖 {self.model} connecting to document...")

        # Create repo and connect to sync server
        self.repo = spork.Repo()
        await self.repo.connect_websocket("wss://sync.automerge.org")

        # Find document
        self.doc_handle = await self.repo.find(self.doc_id)

        # Wait for initial sync
        await asyncio.sleep(2)

        print(f"✓ Connected to {self.doc_id}")
        print(f"  Peer ID: {self.peer_id}")

    async def broadcast_cursor(self, position: int, cursor_type: str = "ai", anchor: Optional[int] = None):
        """Broadcast cursor position via ephemeral message.

        Args:
            position: Main cursor position (head of selection)
            cursor_type: Type of cursor ("user" | "ai" | "streaming_edit")
            anchor: Selection start position (if different from position)
        """
        if not self.doc_handle:
            return

        message = {
            "type": "cursor",
            "peerId": self.peer_id,
            "name": self.model,
            "cursorType": cursor_type,
            "position": position,
            "color": self.color if cursor_type == "ai" else "#F59E0B",
            "timestamp": int(time.time() * 1000),
        }

        # Add anchor for selections
        if anchor is not None:
            message["anchor"] = anchor

        # Encode message as CBOR and broadcast
        encoded = cbor2.dumps(message)
        await self.doc_handle.broadcast(encoded)

    async def get_text(self) -> str:
        """Get current document text."""
        if not self.doc_handle:
            return ""

        text_obj = await self.doc_handle.get_text("text")
        return await text_obj.get() if text_obj else ""

    async def _handle_cursor_move(self, cursor_pos: CursorPosition) -> None:
        """Handle cursor movement from the streaming edit controller."""
        # Map internal CursorType to frontend protocol cursor types
        # Frontend expects: "user" | "ai" | "streaming_edit"
        # We use "streaming_edit" for lookahead/preview cursors
        # We use "ai" with anchor for selections
        # We use "ai" for active typing

        if cursor_pos.cursor_type == CursorType.LOOKAHEAD:
            # Lookahead = streaming edit preview
            cursor_type = "streaming_edit"
            anchor = None
            print(f"  👁️  Lookahead cursor at position {cursor_pos.position}")

        elif cursor_pos.cursor_type == CursorType.SELECTION:
            # Selection = ai cursor with anchor
            cursor_type = "ai"
            # anchor is start of selection, position is end
            anchor = cursor_pos.position
            position = cursor_pos.position + cursor_pos.selection_length
            print(f"  📍 Selection from {anchor} to {position} (length: {cursor_pos.selection_length})")
            await self.broadcast_cursor(position, cursor_type, anchor)
            return

        elif cursor_pos.cursor_type == CursorType.AI:
            # AI actively typing
            cursor_type = "ai"
            anchor = None
            print(f"  ✍️  AI cursor at position {cursor_pos.position}")
        else:
            cursor_type = "ai"
            anchor = None

        await self.broadcast_cursor(cursor_pos.position, cursor_type, anchor)

    async def stream_edit(self, current_text: str) -> bool:
        """Use OpenAI streaming to suggest and apply an edit with real-time cursor movement."""
        if not current_text.strip():
            return False

        try:
            print(f"  🤔 Asking {self.model} (Ollama) for improvement...")

            # Create cursor controller for this edit with current document text
            controller = StreamingEditController(
                document_text=current_text,
                on_cursor_move=self._handle_cursor_move
            )

            # Define the edit tool using regex pattern matching
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "apply_text_edit",
                        "description": "Apply an edit by finding text with a regex pattern and replacing it. Use lookahead/lookbehind for context anchoring.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "Regex pattern to find the text to edit. Use capturing groups or lookahead/lookbehind like '(?<=some context)text to replace' for precision.",
                                },
                                "replacement": {
                                    "type": "string",
                                    "description": "Text to replace the matched pattern with",
                                },
                            },
                            "required": ["pattern", "replacement"],
                        },
                    },
                }
            ]

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful writing assistant. "
                            "Improve the given text by fixing typos, improving clarity, "
                            "or adding helpful content. Make ONE edit at a time. "
                            "Use regex patterns with the apply_text_edit tool. "
                            "Use lookahead/lookbehind for context: '(?<=word )typo' matches 'typo' after 'word '. "
                            "Keep changes minimal and natural."
                        ),
                    },
                    {"role": "user", "content": f"Current text:\n\n{current_text}"},
                ],
                tools=tools,
                tool_choice="required",
                temperature=0.7,
                stream=True,
            )

            # Track tool call metadata
            tool_call_id = None
            tool_name = None

            if self.debug:
                print("\n  🔍 Debug: Streaming tokens:")

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Check for tool calls in the delta
                if delta.tool_calls:
                    for tool_call_chunk in delta.tool_calls:
                        # Track tool call metadata
                        if tool_call_chunk.id:
                            tool_call_id = tool_call_chunk.id
                        if tool_call_chunk.function and tool_call_chunk.function.name:
                            tool_name = tool_call_chunk.function.name

                        # Feed streaming tokens to cursor controller
                        if (
                            tool_call_chunk.function
                            and tool_call_chunk.function.arguments
                        ):
                            token = tool_call_chunk.function.arguments
                            if self.debug:
                                print(f"    {repr(token)}")
                            await controller.feed_token(token)

            # Get final parsed edit from controller
            if tool_name == "apply_text_edit":
                final_edit = controller.get_final_edit()
                if final_edit:
                    try:
                        import re as regex_module

                        pattern = final_edit["pattern"]
                        replacement = final_edit["replacement"]

                        print("\n  📋 Tool call:")
                        print(f"     Pattern: {repr(pattern)}")
                        print(f"     Replacement: {repr(replacement)}")

                        # Find the pattern in the current text
                        try:
                            match = regex_module.search(pattern, current_text)
                            if not match:
                                print(f"  ⚠️  Pattern not found in document")
                                return False

                            # Get match position and text
                            position = match.start()
                            matched_text = match.group(0)
                            delete_count = len(matched_text)

                            print(f"\n  🔍 Match found:")
                            print(f"     Position: {position}")
                            print(f"     Matched: {repr(matched_text)}")

                            print(f"\n  🔄 Change preview:")
                            print(f"     Old: {repr(matched_text)}")
                            print(f"     New: {repr(replacement)}")

                            # Show cursor at match position
                            await self.broadcast_cursor(position, "ai")

                            # Apply the edit
                            text_obj = await self.doc_handle.get_text("text")
                            await text_obj.splice(position, delete_count, replacement)

                            print(f"\n  ✏️  Edit applied at position {position}")
                            return True

                        except regex_module.error as e:
                            print(f"  ⚠️  Invalid regex pattern: {e}")
                            return False

                    except (KeyError, TypeError) as e:
                        print(f"  ⚠️  Error extracting edit parameters: {e}")
                        print(f"  📄 Final edit: {final_edit}")
                        return False
                else:
                    print(f"  ⚠️  Could not parse final edit")
                    return False

        except Exception as e:
            print(f"  ⚠️  Error getting suggestion: {e}")
            import traceback

            traceback.print_exc()

        return False

    async def work_loop(self):
        """Main loop: read text, suggest edit, apply, wait, repeat."""
        self.running = True
        iteration = 0

        while self.running:
            iteration += 1
            print(f"\n[Iteration {iteration}]")

            # Get current text
            current_text = await self.get_text()
            print(f"  📄 Current text length: {len(current_text)} chars")

            if not current_text.strip():
                print("  ⏳ Document is empty, waiting...")
                if self.once:
                    print("  🛑 Once mode: exiting without edit")
                    break
                await asyncio.sleep(5)
                continue

            # Stream edit with real-time cursor movement
            applied = await self.stream_edit(current_text)

            if applied:
                print("  ✓ Edit applied!")
            else:
                print("  ℹ️  No edit suggested")

            # Exit if in once mode
            if self.once:
                print("  🛑 Once mode: exiting after single edit")
                break

            # Wait before next iteration
            print(f"  ⏱  Waiting {self.wait_time}s before next check...")
            await asyncio.sleep(self.wait_time)

    async def run(self):
        """Connect and start working."""
        try:
            await self.connect()
            await self.work_loop()
        except KeyboardInterrupt:
            print("\n\n👋 Bot shutting down...")
        finally:
            if self.repo:
                await self.repo.stop()


async def main():
    if len(sys.argv) < 2:
        print("Usage: uv run bot.py <doc_id> [--once] [--model MODEL] [--debug] [--wait SECONDS]")
        print("\nExample:")
        print("  uv run bot.py automerge:4xKg...")
        print("  uv run bot.py automerge:4xKg... --once")
        print("  uv run bot.py automerge:4xKg... --model llama3.3")
        print("  uv run bot.py automerge:4xKg... --model llama3.3 --wait 2")
        print("  uv run bot.py automerge:4xKg... --once --model llama3.3 --debug")
        sys.exit(1)

    doc_id = sys.argv[1]
    once = "--once" in sys.argv
    debug = "--debug" in sys.argv

    # Parse --model flag
    model = "gpt-oss"  # default
    if "--model" in sys.argv:
        try:
            model_index = sys.argv.index("--model")
            model = sys.argv[model_index + 1]
        except (IndexError, ValueError):
            print("Error: --model flag requires a model name")
            sys.exit(1)

    # Parse --wait flag
    wait_time = 1.0  # default 1 second
    if "--wait" in sys.argv:
        try:
            wait_index = sys.argv.index("--wait")
            wait_time = float(sys.argv[wait_index + 1])
        except (IndexError, ValueError):
            print("Error: --wait flag requires a number (seconds)")
            sys.exit(1)

    if not doc_id.startswith("automerge:"):
        print("Error: doc_id must start with 'automerge:'")
        sys.exit(1)

    print(f"Configuration:")
    print(f"  Model: {model}")
    print(f"  Once mode: {once}")
    print(f"  Debug mode: {debug}")
    print(f"  Wait time: {wait_time}s")
    print()

    bot = CollaborativeBot(doc_id, model=model, once=once, debug=debug, wait_time=wait_time)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
