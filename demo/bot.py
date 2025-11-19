#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "openai>=1.0.0",
#   "cbor2>=5.0.0",
# ]
# ///
"""
AI bot that participates in collaborative Automerge editing.

Usage from demo directory:
    uv run bot.py <doc_id>

Usage from project root:
    uv run demo/bot.py <doc_id>

Example:
    uv run bot.py automerge:4xKg...
"""

import asyncio
import os
import re
import sys
import time
from typing import Optional

import cbor2
import spork
from openai import AsyncOpenAI


def compute_splice(old_text: str, new_text: str) -> tuple[int, int, str]:
    """
    Compute a single splice operation to transform old_text into new_text.

    Returns:
        Tuple of (position, delete_count, insert_text)
    """
    # Find longest common prefix
    prefix_len = 0
    min_len = min(len(old_text), len(new_text))
    while prefix_len < min_len and old_text[prefix_len] == new_text[prefix_len]:
        prefix_len += 1

    # Find longest common suffix
    suffix_len = 0
    old_remaining = len(old_text) - prefix_len
    new_remaining = len(new_text) - prefix_len
    min_remaining = min(old_remaining, new_remaining)

    while (
        suffix_len < min_remaining
        and old_text[-(suffix_len + 1)] == new_text[-(suffix_len + 1)]
    ):
        suffix_len += 1

    # Calculate splice
    position = prefix_len
    delete_count = old_remaining - suffix_len
    insert_text = (
        new_text[prefix_len : len(new_text) - suffix_len]
        if suffix_len > 0
        else new_text[prefix_len:]
    )

    return position, delete_count, insert_text


class CollaborativeBot:
    def __init__(self, doc_id: str, name: str = "GPT-4o"):
        self.doc_id = doc_id
        self.name = name
        self.peer_id = f"ai-bot-{int(time.time())}"
        self.color = "#9333EA"  # Purple for AI
        self.repo: Optional[spork.Repo] = None
        self.doc_handle: Optional[spork.DocHandle] = None
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.running = False

    async def connect(self):
        """Connect to Automerge document."""
        print(f"🤖 {self.name} connecting to document...")

        # Create repo and connect to sync server
        self.repo = spork.Repo()
        await self.repo.connect_websocket("wss://sync.automerge.org")

        # Find document
        self.doc_handle = await self.repo.find(self.doc_id)

        # Wait for initial sync
        await asyncio.sleep(2)

        print(f"✓ Connected to {self.doc_id}")
        print(f"  Peer ID: {self.peer_id}")

    async def broadcast_cursor(self, position: int, cursor_type: str = "ai"):
        """Broadcast cursor position via ephemeral message."""
        if not self.doc_handle:
            return

        message = {
            "type": "cursor",
            "peerId": self.peer_id,
            "name": self.name,
            "cursorType": cursor_type,
            "position": position,
            "color": self.color if cursor_type == "ai" else "#F59E0B",
            "timestamp": int(time.time() * 1000),
        }

        # Encode message as CBOR and broadcast
        encoded = cbor2.dumps(message)
        await self.doc_handle.broadcast(encoded)

    async def get_text(self) -> str:
        """Get current document text."""
        if not self.doc_handle:
            return ""

        text_obj = await self.doc_handle.get_text("text")
        return await text_obj.get() if text_obj else ""

    async def apply_edit(self, old_text: str, new_text: str) -> bool:
        """Apply edit using minimal splice operation."""
        if not self.doc_handle or old_text == new_text:
            return False

        # Compute splice
        position, delete_count, insert_text = compute_splice(old_text, new_text)

        if delete_count == 0 and not insert_text:
            return False

        # Show cursor at edit position
        await self.broadcast_cursor(position, "ai")

        # Apply splice
        text_obj = await self.doc_handle.get_text("text")
        await text_obj.splice(position, delete_count, insert_text)

        print(
            f"  ✏️  Edit at position {position}: "
            f"del={delete_count}, ins={len(insert_text)} chars"
        )

        return True

    async def suggest_edit(self, current_text: str) -> Optional[str]:
        """Use OpenAI to suggest an improvement to the text."""
        if not current_text.strip():
            return None

        try:
            print("  🤔 Asking GPT-4o for improvement...")

            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful writing assistant. "
                            "Improve the given text by fixing typos, improving clarity, "
                            "or adding helpful content. Keep changes minimal and natural. "
                            "Return ONLY the improved text, nothing else."
                        ),
                    },
                    {"role": "user", "content": current_text},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            suggested_text = response.choices[0].message.content
            if suggested_text and suggested_text != current_text:
                return suggested_text.strip()

        except Exception as e:
            print(f"  ⚠️  Error getting suggestion: {e}")

        return None

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
                await asyncio.sleep(5)
                continue

            # Get suggestion from OpenAI
            suggested_text = await self.suggest_edit(current_text)

            if suggested_text:
                print(f"  💡 Got suggestion (length: {len(suggested_text)} chars)")
                applied = await self.apply_edit(current_text, suggested_text)

                if applied:
                    print("  ✓ Edit applied!")
                else:
                    print("  ℹ️  No changes needed")
            else:
                print("  ℹ️  No improvement suggested")

            # Wait before next iteration
            wait_time = 15
            print(f"  ⏱  Waiting {wait_time}s before next check...")
            await asyncio.sleep(wait_time)

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
        print("Usage: uv run bot.py <doc_id>")
        print("\nExample:")
        print("  uv run bot.py automerge:4xKg...")
        sys.exit(1)

    doc_id = sys.argv[1]

    if not doc_id.startswith("automerge:"):
        print("Error: doc_id must start with 'automerge:'")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    bot = CollaborativeBot(doc_id)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
