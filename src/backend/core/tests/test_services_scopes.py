"""
Test suite for the authorization of user requests from Menshen scopes
"""

from django.core.exceptions import PermissionDenied, SuspiciousOperation

import pytest
from asgiref.sync import async_to_sync

from core import factories
from core.models import get_opensearch_index_name
from core.services.scopes import (
    get_delete_index,
    get_scoped_services,
    get_search_indices,
)

pytestmark = pytest.mark.django_db

# Async ORM calls run in the test thread through async_to_sync, so they see the
# data of the test transaction.
search_indices = async_to_sync(get_search_indices)
delete_index = async_to_sync(get_delete_index)


@pytest.mark.parametrize(
    "scopes, action, expected",
    [
        ([], "search", set()),
        (["find:docs:search"], "search", {"docs"}),
        (["find:docs:search", "find:drive:search"], "search", {"docs", "drive"}),
        (["find:docs:search", "find:drive:delete"], "search", {"docs"}),
        (["find:docs:search", "find:drive:delete"], "delete", {"drive"}),
        # Scopes of other resource servers, or not following the convention
        (
            ["openid", "email", "docs:find:search", "menshen:docs:search"],
            "search",
            set(),
        ),
        (
            ["find", "find:docs", "find:docs:search:all", "find::search"],
            "search",
            set(),
        ),
        (["FIND:docs:search", "find:docs:SEARCH"], "search", set()),
    ],
)
def test_services_scopes_get_scoped_services(scopes, action, expected):
    """Only well-formed `find:<service>:<action>` scopes should grant a service."""
    assert get_scoped_services(scopes, action) == expected


def test_services_scopes_search_indices_granted_services():
    """All the granted services should be searched when none is requested."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")
    factories.ServiceFactory(name="other")

    assert search_indices(["find:drive:search", "find:docs:search"], []) == [
        get_opensearch_index_name("docs"),
        get_opensearch_index_name("drive"),
    ]


def test_services_scopes_search_indices_requested_services():
    """The search should be restricted to the requested services (#172)."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")

    assert search_indices(["find:docs:search", "find:drive:search"], ["drive"]) == [
        get_opensearch_index_name("drive")
    ]


def test_services_scopes_search_indices_requested_service_not_granted():
    """Requesting a service that is not granted should raise SuspiciousOperation."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")

    with pytest.raises(SuspiciousOperation):
        search_indices(["find:docs:search"], ["docs", "drive"])


def test_services_scopes_search_indices_requested_service_inactive():
    """Requesting an inactive service should raise SuspiciousOperation."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive", is_active=False)

    with pytest.raises(SuspiciousOperation):
        search_indices(["find:docs:search", "find:drive:search"], ["drive"])


def test_services_scopes_search_indices_unknown_or_inactive_services_ignored():
    """Scopes naming an unknown or inactive service should be ignored."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive", is_active=False)

    assert search_indices(
        ["find:docs:search", "find:drive:search", "find:unknown:search"], []
    ) == [get_opensearch_index_name("docs")]


@pytest.mark.parametrize(
    "scopes",
    [
        [],
        ["openid", "email"],
        ["find:docs:delete"],
        ["find:drive:search"],
        ["find:unknown:search"],
    ],
)
def test_services_scopes_search_indices_no_scope_granted(scopes):
    """A token without any applicable search scope should raise PermissionDenied."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive", is_active=False)

    with pytest.raises(PermissionDenied):
        search_indices(scopes, [])

    with pytest.raises(PermissionDenied):
        search_indices(scopes, ["docs"])


def test_services_scopes_delete_index_granted_service():
    """The index of the requested service should be returned when it is granted."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")

    assert delete_index(
        ["find:docs:delete", "find:drive:delete"], "drive"
    ) == get_opensearch_index_name("drive")


@pytest.mark.parametrize("service", ["drive", "unknown"])
def test_services_scopes_delete_index_service_not_granted(service):
    """Deleting from a service that is not granted should raise SuspiciousOperation."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")

    with pytest.raises(SuspiciousOperation):
        delete_index(["find:docs:delete", "find:drive:search"], service)


def test_services_scopes_delete_index_service_inactive():
    """Deleting from an inactive service should raise SuspiciousOperation."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive", is_active=False)

    with pytest.raises(SuspiciousOperation):
        delete_index(["find:docs:delete", "find:drive:delete"], "drive")


@pytest.mark.parametrize(
    "scopes",
    [[], ["openid"], ["find:docs:search"], ["find:drive:delete"]],
)
def test_services_scopes_delete_index_no_scope_granted(scopes):
    """A token without any applicable delete scope should raise PermissionDenied."""
    factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive", is_active=False)

    with pytest.raises(PermissionDenied):
        delete_index(scopes, "docs")
