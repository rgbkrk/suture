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
                "timestamp": 1234567890
            }
            message = cbor2.dumps(data)

            # Should successfully broadcast
            await doc.broadcast(message)
        finally:
            await repo.stop()


class TestEphemeraReceive:
    """Test receiving ephemeral messages"""

    @pytest.mark.asyncio
    async def test_recv_ephemera_timeout(self):
        """Test that recv_ephemera times out when no messages"""
        repo = spork.Repo()
        try:
            doc = await repo.create()

            # Should timeout since no peers are sending messages
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(doc.recv_ephemera(), timeout=0.5)
        finally:
            await repo.stop()


class TestReactiveMessagePattern:
    """Test reactive message handling patterns"""

    @pytest.mark.asyncio
    async def test_background_listener_pattern(self):
        """Test spawning a background task to listen for messages"""
        repo = spork.Repo()
        received_messages = []

        async def listen_for_messages(doc, duration=0.5):
            """Background task that listens for messages"""
            try:
                start = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start < duration:
                    try:
                        message = await asyncio.wait_for(
                            doc.recv_ephemera(),
                            timeout=0.1
                        )
                        if message is not None:
                            received_messages.append(message)
                    except asyncio.TimeoutError:
                        continue
            except Exception:
                pass

        try:
            doc = await repo.create()

            # Spawn background listener
            listener_task = asyncio.create_task(listen_for_messages(doc))

            # Do other work while listening
            await asyncio.sleep(0.1)
            await doc.set_string("field", "value")

            # Wait for listener to complete
            await listener_task

            # No messages expected (no peers), but task should complete cleanly
            assert len(received_messages) == 0
        finally:
            await repo.stop()


# Demonstration code (not a test, but useful for documentation)
async def _demo_reactive_message_handler():
    """
    Example of how to build a reactive application that handles
    ephemeral messages while doing other work.

    This is NOT a test - it's example code showing the recommended pattern.
    """
    repo = spork.Repo()

    try:
        doc = await repo.create()

        # Pattern 1: Background listener with callback
        async def message_listener(doc, callback):
            """Continuously listen for messages and invoke callback"""
            while True:
                try:
                    message = await asyncio.wait_for(
                        doc.recv_ephemera(),
                        timeout=1.0
                    )
                    if message is None:
                        break
                    await callback(message)
                except asyncio.TimeoutError:
                    # No message yet, continue listening
                    continue
                except Exception as e:
                    print(f"Error in listener: {e}")
                    break

        async def handle_message(message):
            """Process received message"""
            try:
                import cbor2
                data = cbor2.loads(message)
                print(f"Received: {data}")
            except Exception:
                print(f"Received raw: {message}")

        # Start background listener
        listener = asyncio.create_task(message_listener(doc, handle_message))

        # Do other work in your application
        await doc.set_string("title", "My Document")
        await asyncio.sleep(1)

        # Send a broadcast
        try:
            import cbor2
            await doc.broadcast(cbor2.dumps({"type": "cursor", "pos": 10}))
        except ImportError:
            await doc.broadcast(b"test message")

        # Clean up
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

    finally:
        await repo.stop()
