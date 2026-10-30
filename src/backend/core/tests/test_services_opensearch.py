"""
Test suite for the OpenSearch clients
"""

# pylint: disable=protected-access

from asgiref.sync import async_to_sync

from core.services import opensearch


async def get_clients():
    """Get the async client of the running loop twice, then close it"""
    try:
        return (
            opensearch.async_opensearch_client(),
            opensearch.async_opensearch_client(),
        )
    finally:
        await opensearch.close_async_opensearch_client()


def test_services_opensearch_async_client_one_per_event_loop():
    """The async client should be shared within an event loop, not between loops."""
    first_client, same_loop_client = async_to_sync(get_clients)()
    other_loop_client, _ = async_to_sync(get_clients)()

    assert first_client is same_loop_client
    assert other_loop_client is not first_client


def test_services_opensearch_run_async_closes_client():
    """run_async should close the async client of its event loop."""

    async def ping():
        return await opensearch.async_opensearch_client().ping()

    assert opensearch.run_async(ping) is True
    assert len(opensearch._async_clients) == 0

    # A new client is created for the next call
    assert opensearch.run_async(ping) is True
    assert len(opensearch._async_clients) == 0
