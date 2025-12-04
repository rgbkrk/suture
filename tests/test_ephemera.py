#!/usr/bin/env python3
"""Test script for the new EphemeraStream async iterator implementation."""

import asyncio

import spork

try:
    import cbor2

    HAS_CBOR2 = True
except ImportError:
    HAS_CBOR2 = False
    print("Warning: cbor2 not installed, skipping CBOR tests")


async def test_ephemera_stream():
    """Test the ephemera() method with async iteration."""
    print("Creating two repos...")
    repo1 = spork.Repo()
    repo2 = spork.Repo()

    print(f"Repo 1 peer ID: {repo1.peer_id()}")
    print(f"Repo 2 peer ID: {repo2.peer_id()}")

    # Create a document in repo1
    print("\nCreating document in repo1...")
    doc1 = await repo1.create()
    print(f"Document URL: {doc1.url}")

    # Connect repos via WebSocket (you'll need a server running)
    # For this test, we'll simulate by directly creating the same doc in repo2
    # In a real scenario, you'd connect to a sync server

    # For now, let's test the stream API locally
    print("\nTesting ephemera() method...")
    stream = doc1.ephemera()
    print(f"Created stream: {stream}")
    print(f"Stream type: {type(stream)}")

    # Test that it's iterable
    print("\nChecking if stream has __aiter__...")
    assert hasattr(stream, "__aiter__"), "Stream should have __aiter__"
    assert hasattr(stream, "__anext__"), "Stream should have __anext__"
    assert hasattr(stream, "__iter__"), "Stream should have __iter__"
    assert hasattr(stream, "__next__"), "Stream should have __next__"

    print("✓ Stream has all required iterator methods")

    # Test broadcasting (we need another repo/doc connection for this to work properly)
    # For now, let's just verify the API doesn't crash
    print("\nTesting broadcast...")
    if HAS_CBOR2:
        message = cbor2.dumps({"type": "test", "data": "Hello, World!"})
    else:
        message = b"Hello, World!"
    await doc1.broadcast(message)
    print("✓ Broadcast succeeded")

    # Note: To fully test receiving, we'd need two connected repos
    # The stream will work when there are actual messages to receive
    #
    # TODO: Test calling doc.ephemera() like:
    # ```
    # async for message in doc.ephemera():
    #     data = cbor2.loads(message)
    #     assert data["type"] == "test"
    #     assert data["data"] == "Hello, World!"
    # ```
    # Note that we'll want to just get the first message then finish

    # Cleanup
    await repo1.stop()
    await repo2.stop()


if __name__ == "__main__":
    print("Testing EphemeraStream Implementation")
    print("=" * 60)

    asyncio.run(test_ephemera_stream())

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
