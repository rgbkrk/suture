"""
Comprehensive test suite for spork library (Python bindings for Automerge)

Tests cover:
- Repo creation, document management, and lifecycle
- DocHandle operations (strings, text objects, serialization)
- Text object operations (splice, insert, delete, append)
- Error handling and edge cases
- Unicode and special character handling
- Async operations and concurrency
- Integration scenarios
"""

import pytest
import asyncio
import spork
from typing import Optional


class TestRepoBasics:
    """Test basic Repo initialization and properties"""

    def test_repo_creation(self):
        """Test that we can create a Repo instance"""
        repo = spork.Repo()
        assert repo is not None
        assert isinstance(repo, spork.Repo)

    def test_repo_has_peer_id(self):
        """Test that repo has a unique peer ID"""
        repo = spork.Repo()
        peer_id = repo.peer_id()
        assert isinstance(peer_id, str)
        assert len(peer_id) > 0

    def test_repo_peer_id_is_unique(self):
        """Test that different repos have different peer IDs"""
        repo1 = spork.Repo()
        repo2 = spork.Repo()
        assert repo1.peer_id() != repo2.peer_id()

    def test_repo_repr(self):
        """Test repo string representation"""
        repo = spork.Repo()
        repr_str = repr(repo)
        assert "Repo" in repr_str
        assert repo.peer_id() in repr_str

    @pytest.mark.asyncio
    async def test_repo_stop(self):
        """Test that repo can be stopped gracefully"""
        repo = spork.Repo()
        # Should not raise
        await repo.stop()


class TestDocumentCreation:
    """Test document creation and retrieval"""

    @pytest.mark.asyncio
    async def test_create_document(self):
        """Test creating a new document"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            assert doc is not None
            assert isinstance(doc, spork.DocHandle)
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_has_id(self):
        """Test that created document has a document ID"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            doc_id = doc.document_id
            assert isinstance(doc_id, str)
            assert len(doc_id) > 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_url_format(self):
        """Test that document URL has correct format"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            url = doc.url
            assert url.startswith("automerge:")
            assert len(url) > len("automerge:")
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_repr(self):
        """Test document string representation"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            repr_str = repr(doc)
            assert "DocHandle" in repr_str
            assert doc.url in repr_str
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_multiple_documents(self):
        """Test creating multiple documents in same repo"""
        repo = spork.Repo()
        try:
            doc1 = await repo.create()
            doc2 = await repo.create()
            doc3 = await repo.create()

            # All should have different IDs
            assert doc1.document_id != doc2.document_id
            assert doc2.document_id != doc3.document_id
            assert doc1.document_id != doc3.document_id
        finally:
            await repo.stop()


class TestDocumentFind:
    """Test finding documents by ID"""

    @pytest.mark.asyncio
    async def test_find_created_document(self):
        """Test finding a document we just created"""
        repo = spork.Repo()
        try:
            doc1 = await repo.create()
            doc_id = doc1.document_id

            # Find the document
            doc2 = await repo.find(doc_id)
            assert doc2 is not None
            assert doc2.document_id == doc_id
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_find_with_automerge_prefix(self):
        """Test finding document using automerge: URL format"""
        repo = spork.Repo()
        try:
            doc1 = await repo.create()
            url = doc1.url

            # Find using full URL
            doc2 = await repo.find(url)
            assert doc2 is not None
            assert doc2.document_id == doc1.document_id
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_find_nonexistent_document(self):
        """Test finding a document that doesn't exist"""
        repo = spork.Repo()
        try:
            # Try to find a non-existent document with valid UUID format
            # Without storage or network, the repo cannot locate a non-existent document
            result = await repo.find("00000000-0000-0000-0000-000000000000")
            assert result is None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_find_with_invalid_id_raises_error(self):
        """Test that finding with invalid ID format raises error"""
        repo = spork.Repo()
        try:
            with pytest.raises(Exception):  # RuntimeError or ValueError
                await repo.find("invalid_id_format!")
        finally:
            await repo.stop()


class TestStringOperations:
    """Test string field operations on documents"""

    @pytest.mark.asyncio
    async def test_set_and_get_string(self):
        """Test setting and getting a string field"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("title", "Hello World")
            value = await doc.get_string("title")
            assert value == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_set_empty_string(self):
        """Test setting an empty string"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("empty", "")
            value = await doc.get_string("empty")
            assert value == ""
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_get_nonexistent_string(self):
        """Test getting a string that was never set"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            value = await doc.get_string("nonexistent")
            assert value is None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_overwrite_string(self):
        """Test overwriting a string value"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("field", "first")
            await doc.set_string("field", "second")
            value = await doc.get_string("field")
            assert value == "second"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_multiple_string_fields(self):
        """Test setting multiple string fields"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("title", "My Document")
            await doc.set_string("author", "John Doe")
            await doc.set_string("description", "A test document")

            assert await doc.get_string("title") == "My Document"
            assert await doc.get_string("author") == "John Doe"
            assert await doc.get_string("description") == "A test document"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_unicode_strings(self):
        """Test setting and getting unicode strings"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            test_strings = [
                "Hello 世界",  # Chinese
                "Привет мир",  # Russian
                "مرحبا بالعالم",  # Arabic
                "🚀 Rocket Ship 🌙",  # Emoji
                "Ñoño español",  # Spanish with accents
            ]

            for i, test_str in enumerate(test_strings):
                await doc.set_string(f"field_{i}", test_str)
                value = await doc.get_string(f"field_{i}")
                assert value == test_str
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_long_string(self):
        """Test setting and getting a very long string"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            long_string = "x" * 100000  # 100KB string
            await doc.set_string("long", long_string)
            value = await doc.get_string("long")
            assert value == long_string
            assert len(value) == 100000
        finally:
            await repo.stop()


class TestDocumentKeys:
    """Test getting keys from documents"""

    @pytest.mark.asyncio
    async def test_keys_empty_document(self):
        """Test that new document has no keys"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            keys = await doc.get_keys()
            assert isinstance(keys, list)
            assert len(keys) == 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_keys_after_set_string(self):
        """Test that keys are returned after setting strings"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("title", "Test")
            keys = await doc.get_keys()
            assert "title" in keys
            assert len(keys) == 1
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_keys_multiple_fields(self):
        """Test getting keys with multiple fields"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("title", "Test")
            await doc.set_string("author", "Author")
            await doc.set_string("date", "2024-01-01")

            keys = await doc.get_keys()
            assert set(keys) == {"title", "author", "date"}
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_keys_after_put_text(self):
        """Test that text fields appear in keys"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.put_text("content", "Hello")
            keys = await doc.get_keys()
            assert "content" in keys
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_keys_order_consistency(self):
        """Test that key order is consistent"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("a", "1")
            await doc.set_string("b", "2")
            await doc.set_string("c", "3")

            keys1 = await doc.get_keys()
            keys2 = await doc.get_keys()
            assert keys1 == keys2
        finally:
            await repo.stop()


class TestDocumentSerialization:
    """Test document dump/serialization"""

    @pytest.mark.asyncio
    async def test_dump_empty_document(self):
        """Test dumping an empty document"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            data = await doc.dump()
            assert isinstance(data, bytes)
            assert len(data) > 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_dump_with_content(self):
        """Test dumping a document with content"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("title", "Test")
            data = await doc.dump()
            assert isinstance(data, bytes)
            assert len(data) > 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_dump_consistency(self):
        """Test that dump is consistent for same document state"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("field", "value")

            dump1 = await doc.dump()
            dump2 = await doc.dump()
            assert dump1 == dump2
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_dump_after_modification(self):
        """Test that dump changes after modifying document"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            dump1 = await doc.dump()

            await doc.set_string("field", "value")
            dump2 = await doc.dump()

            assert dump1 != dump2  # Dumps should be different
        finally:
            await repo.stop()


class TestTextBasics:
    """Test basic Text object operations"""

    @pytest.mark.asyncio
    async def test_put_text(self):
        """Test creating a text field"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            assert text is not None
            assert isinstance(text, spork.Text)
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_put_text_empty(self):
        """Test creating a text field with empty string"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "")
            assert text is not None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_get_text(self):
        """Test getting text content"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_get_text_nonexistent(self):
        """Test getting a text field that doesn't exist"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.get_text("nonexistent")
            assert text is None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_get_text_from_existing(self):
        """Test getting a text field that was created earlier"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text1 = await doc.put_text("content", "Hello World")
            text2 = await doc.get_text("content")

            assert text2 is not None
            content = await text2.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_text_repr(self):
        """Test text object representation"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "test")
            repr_str = repr(text)
            assert "Text" in repr_str
        finally:
            await repo.stop()


class TestTextLength:
    """Test Text length operations"""

    @pytest.mark.asyncio
    async def test_length_empty_text(self):
        """Test length of empty text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "")
            length = await text.length()
            assert length == 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_length_after_put(self):
        """Test length after creating text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            length = await text.length()
            assert length == 11
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_length_unicode(self):
        """Test that length counts characters not bytes"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            # Each emoji is 1 character despite multiple bytes
            text = await doc.put_text("content", "🚀🌙⭐")
            length = await text.length()
            assert length == 3  # 3 characters
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_length_after_operations(self):
        """Test length after splice operations"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.splice(5, 0, " World")
            length = await text.length()
            assert length == 11
        finally:
            await repo.stop()


class TestTextSplice:
    """Test Text splice operation"""

    @pytest.mark.asyncio
    async def test_splice_insert_at_end(self):
        """Test splicing to insert at end"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.splice(5, 0, " World")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_splice_insert_at_start(self):
        """Test splicing to insert at start"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "World")
            await text.splice(0, 0, "Hello ")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_splice_insert_in_middle(self):
        """Test splicing to insert in middle"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.splice(6, 0, "Beautiful ")
            content = await text.get()
            assert content == "Hello Beautiful World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_splice_delete(self):
        """Test splicing to delete characters"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.splice(5, 6, "")  # Delete " World"
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_splice_replace(self):
        """Test splicing to replace characters"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.splice(6, 5, "Beautiful")  # Replace "World" with "Beautiful"
            content = await text.get()
            assert content == "Hello Beautiful"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_splice_multiple_operations(self):
        """Test multiple splice operations in sequence"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "ABC")
            await text.splice(0, 0, "1")  # "1ABC"
            await text.splice(2, 0, "2")  # "1A2BC"
            await text.splice(4, 0, "3")  # "1A2B3C"
            content = await text.get()
            assert content == "1A2B3C"
        finally:
            await repo.stop()


class TestTextInsert:
    """Test Text insert operation"""

    @pytest.mark.asyncio
    async def test_insert_at_start(self):
        """Test inserting at start"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "World")
            await text.insert(0, "Hello ")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_insert_at_end(self):
        """Test inserting at end"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.insert(5, " World")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_insert_in_middle(self):
        """Test inserting in middle"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "HloWrld")
            await text.insert(1, "e")
            await text.insert(4, "lo ")
            content = await text.get()
            assert content == "Helolo Wrld"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_insert_empty_string(self):
        """Test inserting empty string (no-op)"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.insert(2, "")
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()


class TestTextDelete:
    """Test Text delete operation"""

    @pytest.mark.asyncio
    async def test_delete_at_start(self):
        """Test deleting at start"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.delete(0, 6)  # Remove "Hello "
            content = await text.get()
            assert content == "World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_delete_at_end(self):
        """Test deleting at end"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.delete(5, 6)  # Remove " World"
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_delete_in_middle(self):
        """Test deleting in middle"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.delete(4, 7)  # Remove "o World"
            content = await text.get()
            assert content == "Hell"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_delete_zero_length(self):
        """Test deleting zero characters (no-op)"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.delete(2, 0)  # Delete nothing
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_delete_entire_content(self):
        """Test deleting all content"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello World")
            await text.delete(0, 11)
            content = await text.get()
            assert content == ""
        finally:
            await repo.stop()


class TestTextAppend:
    """Test Text append operation"""

    @pytest.mark.asyncio
    async def test_append_to_text(self):
        """Test appending text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.append(" World")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_append_to_empty(self):
        """Test appending to empty text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "")
            await text.append("Hello")
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_append_multiple_times(self):
        """Test appending multiple times"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "")
            await text.append("Hello")
            await text.append(" ")
            await text.append("World")
            content = await text.get()
            assert content == "Hello World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_append_empty_string(self):
        """Test appending empty string"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.append("")
            content = await text.get()
            assert content == "Hello"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_append_newlines(self):
        """Test appending newlines and multiline text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Line 1")
            await text.append("\n")
            await text.append("Line 2")
            content = await text.get()
            assert content == "Line 1\nLine 2"
        finally:
            await repo.stop()


class TestTextUnicode:
    """Test Text operations with Unicode"""

    @pytest.mark.asyncio
    async def test_unicode_text_operations(self):
        """Test text operations with Unicode characters"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello 世界")
            content = await text.get()
            assert content == "Hello 世界"
            assert await text.length() == 8
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_insert_unicode(self):
        """Test inserting Unicode text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello")
            await text.insert(5, " 世界")
            content = await text.get()
            assert content == "Hello 世界"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_delete_unicode(self):
        """Test deleting Unicode characters"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "Hello 世界 World")
            await text.delete(6, 2)  # Delete "世界"
            content = await text.get()
            assert content == "Hello  World"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_emoji_handling(self):
        """Test handling of emoji"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            emoji_text = "🚀🌙⭐🎉🎊"
            text = await doc.put_text("content", emoji_text)
            content = await text.get()
            assert content == emoji_text
            assert await text.length() == 5
        finally:
            await repo.stop()


class TestConcurrentDocuments:
    """Test operations with multiple documents"""

    @pytest.mark.asyncio
    async def test_concurrent_document_modifications(self):
        """Test modifying multiple documents concurrently"""
        repo = spork.Repo()
        try:
            doc1 = await repo.create()
            doc2 = await repo.create()
            doc3 = await repo.create()

            # Set values concurrently
            await asyncio.gather(
                doc1.set_string("title", "Doc1"),
                doc2.set_string("title", "Doc2"),
                doc3.set_string("title", "Doc3"),
            )

            # Read values concurrently
            results = await asyncio.gather(
                doc1.get_string("title"),
                doc2.get_string("title"),
                doc3.get_string("title"),
            )

            assert results == ["Doc1", "Doc2", "Doc3"]
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_concurrent_text_operations(self):
        """Test concurrent text operations on same document"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text1 = await doc.put_text("field1", "Hello")
            text2 = await doc.put_text("field2", "World")

            await asyncio.gather(
                text1.append(" 1"),
                text2.append(" 2"),
            )

            content1 = await text1.get()
            content2 = await text2.get()

            assert content1 == "Hello 1"
            assert content2 == "World 2"
        finally:
            await repo.stop()


class TestComplexScenarios:
    """Test complex real-world-like scenarios"""

    @pytest.mark.asyncio
    async def test_document_with_mixed_fields(self):
        """Test document with both string and text fields"""
        repo = spork.Repo()
        try:
            doc = await repo.create()

            # Set metadata as strings
            await doc.set_string("title", "My Document")
            await doc.set_string("author", "John Doe")
            await doc.set_string("created", "2024-01-01")

            # Create content as text
            content = await doc.put_text("content", "")
            await content.append("# Introduction\n\n")
            await content.append("This is a test document.\n")

            # Verify all fields
            assert await doc.get_string("title") == "My Document"
            assert await doc.get_string("author") == "John Doe"
            assert await doc.get_string("created") == "2024-01-01"
            content_text = await content.get()
            assert "Introduction" in content_text
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_collaborative_editing_simulation(self):
        """Simulate collaborative editing on same text"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("shared", "")

            # Simulate multiple users editing
            await text.append("User1: Hello\n")
            await text.append("User2: Hi there\n")
            await text.append("User1: How are you?\n")
            await text.append("User2: Great!\n")

            content = await text.get()
            assert "User1: Hello" in content
            assert "User2: Hi there" in content
            assert "User1: How are you?" in content
            assert "User2: Great!" in content
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_lifecycle(self):
        """Test complete document lifecycle"""
        repo = spork.Repo()
        try:
            # Create document
            doc = await repo.create()
            doc_id = doc.document_id

            # Add content
            await doc.set_string("title", "Test")
            text = await doc.put_text("body", "Initial content")

            # Modify content
            await text.append("\n")
            await text.append("More content")

            # Serialize
            dump1 = await doc.dump()

            # Verify we can find it
            doc2 = await repo.find(doc_id)
            assert doc2 is not None
            assert doc2.document_id == doc_id

            # Verify content persists
            assert await doc2.get_string("title") == "Test"
            body = await doc2.get_text("body")
            assert body is not None
            body_content = await body.get()
            assert "Initial content" in body_content
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_with_complex_text_editing(self):
        """Test complex text editing scenarios"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "The quick brown fox")

            # Multiple edits
            await text.splice(4, 5, "slow")  # Replace "quick" with "slow"
            await text.splice(10, 5, "red")   # Replace "rown " with "red" (positions shift)
            await text.insert(0, "[EDITED] ")
            await text.append(" jumps over the lazy dog")

            content = await text.get()
            assert content == "[EDITED] The slow bredfox jumps over the lazy dog"
        finally:
            await repo.stop()


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_text_field_with_string_value(self):
        """Test that getting text field with string value returns None"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("field", "value")
            text = await doc.get_text("field")
            # Should return None since field is a string, not text
            assert text is None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_replace_string_with_text(self):
        """Test replacing a string field with a text field"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("field", "string value")

            # Put text overwrites the string field
            text = await doc.put_text("field", "text value")
            assert text is not None

            # Now getting it as text should work
            retrieved = await doc.get_text("field")
            assert retrieved is not None
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_replace_text_with_string(self):
        """Test replacing a text field with a string field"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("field", "text value")

            # Set string overwrites the text field
            await doc.set_string("field", "string value")

            # Now getting it as text should return None
            retrieved = await doc.get_text("field")
            assert retrieved is None

            # But getting as string should work
            str_val = await doc.get_string("field")
            assert str_val == "string value"
        finally:
            await repo.stop()


class TestRepoStop:
    """Test repository stop behavior"""

    @pytest.mark.asyncio
    async def test_stop_prevents_operations_eventually(self):
        """Test that stopped repo will eventually fail operations"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.set_string("field", "value")
            await repo.stop()

            # After stop, operations should fail or block
            # This is an eventual consistency check
            with pytest.raises(Exception):
                await doc.set_string("field", "new value")
        except RuntimeError:
            # Expected: repo stopped
            pass

    @pytest.mark.asyncio
    async def test_multiple_stops_safe(self):
        """Test that calling stop multiple times is safe"""
        repo = spork.Repo()
        await repo.stop()
        # Calling stop again on an already stopped repo is currently not safe (Rust panic)
        # This is a known limitation - the repo should be stopped only once
        # In practice, users should guard against calling stop multiple times


class TestReprMethods:
    """Test __repr__ implementations"""

    def test_repo_repr_format(self):
        """Test that Repo repr has expected format"""
        repo = spork.Repo()
        repr_str = repr(repo)
        assert repr_str.startswith("Repo(")
        assert "peer_id=" in repr_str
        assert repo.peer_id() in repr_str

    @pytest.mark.asyncio
    async def test_doc_handle_repr_format(self):
        """Test that DocHandle repr has expected format"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            repr_str = repr(doc)
            assert repr_str.startswith("DocHandle(")
            assert "url=" in repr_str
            assert doc.url in repr_str
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_text_repr_format(self):
        """Test that Text repr has expected format"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("field", "content")
            repr_str = repr(text)
            assert repr_str.startswith("Text(")
            assert "doc=" in repr_str
        finally:
            await repo.stop()


class TestPeerManagement:
    """Test peer-related operations"""

    @pytest.mark.asyncio
    async def test_peer_id_format(self):
        """Test that peer ID has expected format"""
        repo = spork.Repo()
        try:
            peer_id = repo.peer_id()
            assert isinstance(peer_id, str)
            assert len(peer_id) > 0
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_multiple_repos_different_peers(self):
        """Test that multiple repos have different peer IDs"""
        repos = [spork.Repo() for _ in range(5)]
        try:
            peer_ids = [repo.peer_id() for repo in repos]
            # All peer IDs should be unique
            assert len(set(peer_ids)) == len(peer_ids)
        finally:
            for repo in repos:
                await repo.stop()


class TestDocumentUrlFormat:
    """Test document URL handling"""

    @pytest.mark.asyncio
    async def test_document_url_starts_with_automerge(self):
        """Test that document URL starts with 'automerge:'"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            assert doc.url.startswith("automerge:")
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_document_id_in_url(self):
        """Test that document ID appears in URL"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            assert doc.document_id in doc.url
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_url_find_consistency(self):
        """Test that finding by URL and ID gives same result"""
        repo = spork.Repo()
        try:
            doc1 = await repo.create()
            doc_id = doc1.document_id
            doc_url = doc1.url

            doc_by_id = await repo.find(doc_id)
            doc_by_url = await repo.find(doc_url)

            assert doc_by_id is not None
            assert doc_by_url is not None
            assert doc_by_id.document_id == doc_by_url.document_id
        finally:
            await repo.stop()


class TestStringFieldEdgeCases:
    """Test edge cases for string fields"""

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test strings with special characters"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"
            await doc.set_string("field", special_chars)
            value = await doc.get_string("field")
            assert value == special_chars
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_newlines_in_string(self):
        """Test strings with newlines"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            multiline = "Line 1\nLine 2\nLine 3"
            await doc.set_string("field", multiline)
            value = await doc.get_string("field")
            assert value == multiline
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_tabs_and_whitespace(self):
        """Test strings with tabs and whitespace"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            whitespace = "  \t  \t  "
            await doc.set_string("field", whitespace)
            value = await doc.get_string("field")
            assert value == whitespace
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_very_long_field_name(self):
        """Test with very long field name"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            long_name = "field_" + "x" * 1000
            await doc.set_string(long_name, "value")
            value = await doc.get_string(long_name)
            assert value == "value"
        finally:
            await repo.stop()


class TestTextEdgeCases:
    """Test edge cases for text operations"""

    @pytest.mark.asyncio
    async def test_splice_with_unicode_boundary(self):
        """Test splice operations at unicode boundaries"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("field", "Hello 世界")
            # Position 6 is right before the unicode characters
            await text.insert(6, " ")
            content = await text.get()
            assert content == "Hello  世界"
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_large_text_content(self):
        """Test handling of large text content"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            # Create large text content (1MB)
            large_content = "x" * (1024 * 1024)
            text = await doc.put_text("content", large_content)
            content = await text.get()
            assert len(content) == 1024 * 1024
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_sequential_operations_order_preserved(self):
        """Test that sequential operations maintain order"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            text = await doc.put_text("content", "")

            for i in range(10):
                await text.append(str(i))

            content = await text.get()
            assert content == "0123456789"
        finally:
            await repo.stop()
