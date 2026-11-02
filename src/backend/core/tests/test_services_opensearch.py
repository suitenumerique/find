"""
Test suite for the OpenSearch clients
"""

# pylint: disable=protected-access

import asyncio
import threading

from core.services import opensearch


def test_services_opensearch_async_client_one_per_event_loop():
    """The async client should be shared within an event loop, not between loops."""
    # Both loops hold their client open at the same time, each in its own thread
    both_open = threading.Barrier(2, timeout=10)
    clients = {}

    async def get_clients(name):
        try:
            clients[name] = (
                opensearch.async_opensearch_client(),
                opensearch.async_opensearch_client(),
            )
            both_open.wait()
        finally:
            await opensearch.close_async_opensearch_client()

    threads = [
        threading.Thread(target=asyncio.run, args=(get_clients(name),))
        for name in ("first", "other")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    first_client, same_loop_client = clients["first"]
    other_loop_client, other_same_loop_client = clients["other"]
    assert first_client is same_loop_client
    assert other_loop_client is other_same_loop_client
    assert other_loop_client is not first_client
    assert len(opensearch._async_clients) == 0
