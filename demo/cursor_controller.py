"""
Cursor controller for streaming edits.

This module handles cursor positioning and movement during streaming edits,
separated from LLM logic for deterministic testing.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Awaitable


class CursorType(Enum):
    """Types of cursors that can be shown."""
    LOOKAHEAD = "lookahead"  # Shows where edit will happen
    AI = "ai"  # Shows active AI cursor
    SELECTION = "selection"  # Shows text being selected/deleted


@dataclass
class CursorPosition:
    """Represents a cursor position with optional selection."""
    position: int
    cursor_type: CursorType
    selection_length: int = 0  # If > 0, shows selection from position to position+length


class StreamingEditController:
    """
    Controls cursor movement during streaming edits.

    This class is designed to be deterministic and testable - it takes
    streaming JSON tokens as input and emits cursor positions based on
    the partially-parsed edit operation.

    For regex-based edits, it incrementally searches for pattern matches
    as the pattern streams in, showing cursor movement in real-time.
    """

    def __init__(
        self,
        document_text: str,
        on_cursor_move: Optional[Callable[[CursorPosition], Awaitable[None]]] = None
    ):
        """
        Initialize the streaming edit controller.

        Args:
            document_text: The current document text to search in
            on_cursor_move: Async callback invoked when cursor should move.
                           Takes a CursorPosition as argument.
        """
        self.document_text = document_text
        self.on_cursor_move = on_cursor_move
        self.accumulated_json = ""
        self.last_match_position: Optional[int] = None
        self.last_matched_length: int = 0
        self.last_pattern: str = ""
        self.replacement_chars_shown = 0
        self.shown_selection = False

    async def feed_token(self, token: str) -> None:
        """
        Feed a streaming token of JSON to the controller.

        This incrementally builds up the edit operation and emits cursor
        movements as it understands what will happen.

        For regex-based edits: as the pattern streams in, we progressively
        try to match it against the document and show the cursor at match positions.

        Args:
            token: A piece of the streaming JSON tool call arguments
        """
        from partial_json_parser import loads
        import re

        self.accumulated_json += token

        # Try to parse what we have so far
        try:
            partial_data = loads(self.accumulated_json)
            if partial_data is None:
                return

            # Check if we have a pattern (regex-based edit)
            if "pattern" in partial_data:
                pattern = partial_data["pattern"]

                # Only try to match if pattern has changed (more tokens arrived)
                if pattern != self.last_pattern:
                    self.last_pattern = pattern

                    # Try to find a match with the partial pattern
                    try:
                        match = re.search(pattern, self.document_text)
                        if match:
                            position = match.start()
                            matched_text = match.group(0)

                            # Show lookahead cursor at match position
                            if self.last_match_position != position:
                                self.last_match_position = position
                                self.last_matched_length = len(matched_text)
                                await self._move_cursor(CursorPosition(
                                    position=position,
                                    cursor_type=CursorType.LOOKAHEAD
                                ))
                    except re.error:
                        # Invalid regex pattern (still streaming), ignore
                        pass

            # If we have replacement text streaming, show selection first, then insertions
            if (
                "replacement" in partial_data
                and self.last_match_position is not None
            ):
                # Show selection before we start inserting (only once)
                if not self.shown_selection and self.last_matched_length > 0:
                    self.shown_selection = True
                    await self._move_cursor(CursorPosition(
                        position=self.last_match_position,
                        cursor_type=CursorType.SELECTION,
                        selection_length=self.last_matched_length
                    ))

                # Show character-by-character insertion
                replacement = partial_data["replacement"]
                new_chars = len(replacement) - self.replacement_chars_shown

                if new_chars > 0:
                    # Move cursor forward for EACH new character
                    for i in range(self.replacement_chars_shown, len(replacement)):
                        await self._move_cursor(CursorPosition(
                            position=self.last_match_position + i + 1,
                            cursor_type=CursorType.AI
                        ))
                    self.replacement_chars_shown = len(replacement)

        except Exception:
            # If partial parser fails, try regex extraction for pattern
            if self.last_match_position is None:
                pattern_match = re.search(r'"pattern"\s*:\s*"([^"]*)"', self.accumulated_json)
                if pattern_match:
                    try:
                        pattern = pattern_match.group(1)
                        match = re.search(pattern, self.document_text)
                        if match:
                            position = match.start()
                            self.last_match_position = position
                            self.last_pattern = pattern
                            await self._move_cursor(CursorPosition(
                                position=position,
                                cursor_type=CursorType.LOOKAHEAD
                            ))
                    except re.error:
                        pass

    async def _move_cursor(self, cursor_pos: CursorPosition) -> None:
        """Internal method to emit cursor movement."""
        if self.on_cursor_move:
            await self.on_cursor_move(cursor_pos)

    def reset(self) -> None:
        """Reset the controller for a new edit."""
        self.accumulated_json = ""
        self.last_match_position = None
        self.last_matched_length = 0
        self.last_pattern = ""
        self.replacement_chars_shown = 0
        self.shown_selection = False

    def get_final_edit(self) -> Optional[dict]:
        """
        Get the final parsed edit operation.

        Returns:
            Dict with 'position', 'delete_count', 'insert_text' keys,
            or None if parsing failed.
        """
        import json
        try:
            return json.loads(self.accumulated_json)
        except json.JSONDecodeError:
            return None
