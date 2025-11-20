"""
Test suite for broadcast functionality.

Tests ephemeral message broadcasting between peers, including
CBOR encoding and reactive message reception patterns.
"""

import asyncio

import pytest
import spork


class TestBroadcastBasics:
    """Test basic broadcast functionality"""

    @pytest.mark.asyncio
    async def test_broadcast_raw_bytes(self):
        """Test broadcasting raw bytes"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            message = b"Hello from broadcast!"

            # Should not raise, even with no peers
            await doc.broadcast(message)
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_broadcast_empty_message(self):
        """Test broadcasting empty message"""
        repo = spork.Repo()
        try:
            doc = await repo.create()
            await doc.broadcast(b"")
        finally:
            await repo.stop()

    @pytest.mark.asyncio
    async def test_broadcast_multiple_messages(self):
        """Test broadcasting multiple messages in sequence"""
        repo = spork.Repo()
        try:
            doc = await repo.create()

            for i in range(5):
                message = f"Message {i}".encode()
                await doc.broadcast(message)
        finally:
            await repo.stop()


class TestBroadcastCBOR:
    """Test CBOR encoding with broadcasts"""

    @pytest.mark.asyncio
    async def test_broadcast_cbor_message(self):
        """Test broadcasting CBOR-encoded data"""
        try:
            import cbor2
        except ImportError:
            pytest.skip("cbor2 not installed")

        repo = spork.Repo()
        try:
            doc = await repo.create()

            # Encode a CBOR message
            data = {
                "type": "cursor",
                "user": "alice",
                "position": 42,
                "timestamp": 1234567890,
            }
            message = cbor2.dumps(data)

            # Should successfully broadcast
            await doc.broadcast(message)
        finally:
            await repo.stop()
