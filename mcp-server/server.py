#!/usr/bin/env python3
"""
Model Context Protocol server for Automerge CRDT text editing.

This MCP server provides language-first editing capabilities for Automerge documents,
allowing LLMs to edit text using regex-based transformations instead of character-by-character
edits.
"""

import asyncio
import re
from typing import Any, Dict, Optional

import spork
from mcp.server import Server
from mcp.types import TextContent, Tool

# Global repo instance
repo: Optional[spork.Repo] = None
doc_handle: Optional[spork.DocHandle] = None
doc_id: Optional[str] = None


def apply_regex_edit(
    text: str, pattern: str, replacement: str, global_replace: bool = False
) -> tuple[str, int]:
    """
    Apply a regex-based edit to text.

    Args:
        text: The current text content
        pattern: Regex pattern to match
        replacement: Text to replace matches with
        global_replace: If True, replace all matches; if False, replace only first match

    Returns:
        Tuple of (new_text, number_of_replacements)
    """
    flags = re.MULTILINE
    if global_replace:
        new_text, count = re.subn(pattern, replacement, text, flags=flags)
    else:
        new_text, count = re.subn(pattern, replacement, text, count=1, flags=flags)

    return new_text, count


def compute_splice(old_text: str, new_text: str) -> tuple[int, int, str]:
    """
    Compute a single splice operation to transform old_text into new_text.

    Uses a simple diff algorithm:
    1. Find longest common prefix
    2. Find longest common suffix
    3. Return (position, delete_count, insert_text) for the middle section

    Args:
        old_text: The current text
        new_text: The desired text

    Returns:
        Tuple of (position, delete_count, insert_text)
    """
    # Find longest common prefix
    prefix_len = 0
    min_len = min(len(old_text), len(new_text))
    while prefix_len < min_len and old_text[prefix_len] == new_text[prefix_len]:
        prefix_len += 1

    # Find longest common suffix (after the prefix)
    suffix_len = 0
    old_remaining = len(old_text) - prefix_len
    new_remaining = len(new_text) - prefix_len
    min_remaining = min(old_remaining, new_remaining)

    while suffix_len < min_remaining and old_text[-(suffix_len + 1)] == new_text[-(suffix_len + 1)]:
        suffix_len += 1

    # Calculate the splice operation
    position = prefix_len
    delete_count = old_remaining - suffix_len
    insert_text = new_text[prefix_len:len(new_text) - suffix_len] if suffix_len > 0 else new_text[prefix_len:]

    return position, delete_count, insert_text


# Create MCP server
app = Server("automerge-mcp-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for the MCP server."""
    return [
        Tool(
            name="connect",
            description="Connect to an Automerge document via WebSocket sync server",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "The Automerge document ID (e.g., 'automerge:...')",
                    },
                    "sync_url": {
                        "type": "string",
                        "description": "WebSocket sync server URL (default: wss://sync.automerge.org)",
                        "default": "wss://sync.automerge.org",
                    },
                },
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="get_text",
            description="Get the current text content of the document",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="regex_edit",
            description=(
                "Edit text using regex pattern matching. This is more LLM-friendly than "
                "character-by-character edits. Use lookbehind/lookahead for precise positioning."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Regex pattern to match. Use (?<=...) for lookbehind and (?=...) "
                            "for lookahead to match positions. Example: '(?<=Hello )world' matches "
                            "'world' that comes after 'Hello '."
                        ),
                    },
                    "replacement": {
                        "type": "string",
                        "description": "Text to replace the matched pattern with",
                    },
                    "global": {
                        "type": "boolean",
                        "description": "If true, replace all matches; if false, replace only first match",
                        "default": False,
                    },
                },
                "required": ["pattern", "replacement"],
            },
        ),
        Tool(
            name="insert_at_position",
            description="Insert text at a specific character position in the document",
            inputSchema={
                "type": "object",
                "properties": {
                    "position": {
                        "type": "integer",
                        "description": "Character position to insert at (0-indexed)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to insert",
                    },
                },
                "required": ["position", "text"],
            },
        ),
        Tool(
            name="delete_range",
            description="Delete a range of characters from the document",
            inputSchema={
                "type": "object",
                "properties": {
                    "start": {
                        "type": "integer",
                        "description": "Start position (0-indexed, inclusive)",
                    },
                    "end": {
                        "type": "integer",
                        "description": "End position (0-indexed, exclusive)",
                    },
                },
                "required": ["start", "end"],
            },
        ),
        Tool(
            name="set_text",
            description="Replace the entire document text with new content",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "New text content",
                    },
                },
                "required": ["text"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from the MCP client."""
    global repo, doc_handle, doc_id

    if name == "connect":
        # Initialize repo if needed
        if repo is None:
            repo = spork.Repo()

        doc_id = arguments["doc_id"]
        sync_url = arguments.get("sync_url", "wss://sync.automerge.org")

        # Connect to WebSocket server
        await repo.connect_websocket(sync_url)

        # Find or create document
        doc_handle = await repo.find(doc_id)

        # Wait for initial sync
        await asyncio.sleep(2)

        return [
            TextContent(
                type="text",
                text=f"Connected to document {doc_id} via {sync_url}",
            )
        ]

    # All other commands require an active connection
    if doc_handle is None:
        return [
            TextContent(
                type="text",
                text="Error: Not connected to a document. Use 'connect' tool first.",
            )
        ]

    if name == "get_text":
        text_obj = await doc_handle.get_text("text")
        text = await text_obj.get() if text_obj else ""
        return [
            TextContent(
                type="text",
                text=text,
            )
        ]

    elif name == "regex_edit":
        pattern = arguments["pattern"]
        replacement = arguments["replacement"]
        global_replace = arguments.get("global", False)

        # Get current text
        text_obj = await doc_handle.get_text("text")
        current_text = await text_obj.get() if text_obj else ""

        # Apply regex edit
        try:
            new_text, count = apply_regex_edit(
                current_text, pattern, replacement, global_replace
            )

            if count == 0:
                return [
                    TextContent(
                        type="text",
                        text=f"No matches found for pattern: {pattern}",
                    )
                ]

            # Compute minimal splice operation
            position, delete_count, insert_text = compute_splice(current_text, new_text)

            # Apply splice to CRDT
            await text_obj.splice(position, delete_count, insert_text)

            return [
                TextContent(
                    type="text",
                    text=f"Applied {count} replacement(s). Pattern: {pattern} → {replacement} (splice: pos={position}, del={delete_count}, ins={len(insert_text)} chars)",
                )
            ]
        except re.error as e:
            return [
                TextContent(
                    type="text",
                    text=f"Invalid regex pattern: {e}",
                )
            ]

    elif name == "insert_at_position":
        position = arguments["position"]
        text_to_insert = arguments["text"]

        # Get current text
        text_obj = await doc_handle.get_text("text")
        current_text = await text_obj.get() if text_obj else ""

        # Validate position
        if position < 0 or position > len(current_text):
            return [
                TextContent(
                    type="text",
                    text=f"Invalid position: {position}. Text length is {len(current_text)}",
                )
            ]

        # Insert text using splice (delete 0, insert text)
        await text_obj.splice(position, 0, text_to_insert)

        return [
            TextContent(
                type="text",
                text=f"Inserted {len(text_to_insert)} characters at position {position}",
            )
        ]

    elif name == "delete_range":
        start = arguments["start"]
        end = arguments["end"]

        # Get current text
        text_obj = await doc_handle.get_text("text")
        current_text = await text_obj.get() if text_obj else ""

        # Validate range
        if start < 0 or end > len(current_text) or start >= end:
            return [
                TextContent(
                    type="text",
                    text=f"Invalid range: [{start}, {end}). Text length is {len(current_text)}",
                )
            ]

        # Delete range using splice (delete count, insert nothing)
        delete_count = end - start
        await text_obj.splice(start, delete_count, "")

        return [
            TextContent(
                type="text",
                text=f"Deleted {delete_count} characters from position {start} to {end}",
            )
        ]

    elif name == "set_text":
        new_text = arguments["text"]

        # Get current text
        text_obj = await doc_handle.get_text("text")
        current_text = await text_obj.get() if text_obj else ""

        # Compute minimal splice to replace everything
        position, delete_count, insert_text = compute_splice(current_text, new_text)

        # Apply splice to CRDT
        await text_obj.splice(position, delete_count, insert_text)

        return [
            TextContent(
                type="text",
                text=f"Set document text ({len(new_text)} characters) using splice (pos={position}, del={delete_count}, ins={len(insert_text)} chars)",
            )
        ]

    else:
        return [
            TextContent(
                type="text",
                text=f"Unknown tool: {name}",
            )
        ]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
