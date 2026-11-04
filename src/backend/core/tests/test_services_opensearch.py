"""
Test suite for the OpenSearch clients
"""

# pylint: disable=protected-access

import asyncio
import threading

import pytest

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


def test_services_opensearch_client_options_verify_certs_by_default(settings):
    """TLS certificates should be verified against the default trust store by default."""
    assert settings.OPENSEARCH_VERIFY_CERTS is True
    assert settings.OPENSEARCH_CA_CERTS is None
    settings.OPENSEARCH_USE_SSL = True

    options = opensearch.get_client_options()

    assert options["use_ssl"] is True
    assert options["verify_certs"] is True
    assert "ca_certs" not in options


def test_services_opensearch_client_options_ca_certs(settings):
    """A CA bundle should be passed to the clients when configured."""
    settings.OPENSEARCH_CA_CERTS = "/etc/ssl/opensearch-ca.pem"

    options = opensearch.get_client_options()

    assert options["verify_certs"] is True
    assert options["ca_certs"] == "/etc/ssl/opensearch-ca.pem"


@pytest.mark.parametrize("value", [None, ""])
def test_services_opensearch_client_options_ca_certs_unset(settings, value):
    """An unset or empty CA bundle should fall back to the default trust store."""
    settings.OPENSEARCH_CA_CERTS = value

    assert "ca_certs" not in opensearch.get_client_options()


def test_services_opensearch_client_options_verify_certs_disabled(settings):
    """Certificate verification can be disabled explicitly."""
    settings.OPENSEARCH_VERIFY_CERTS = False

    assert opensearch.get_client_options()["verify_certs"] is False
