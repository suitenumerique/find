"""
Authorization of user requests from the OAuth scopes granted by Menshen.

Scopes follow Menshen's `service:resource:action` convention, with the indexed
service name as the resource: `find:<service>:search` allows searching the documents
indexed by `<service>`, `find:<service>:delete` allows deleting them. Scopes only
select which indices a request may touch: the per-document access filter still
applies inside them.
"""

from django.core.exceptions import PermissionDenied, SuspiciousOperation

from ..models import Service, get_opensearch_index_name

SCOPE_PREFIX = "find"
SEARCH = "search"
DELETE = "delete"


def get_scoped_services(scopes, action):
    """Return the names of the services covered by `find:<service>:<action>` scopes."""
    services = set()
    for scope in scopes:
        parts = scope.split(":")
        if len(parts) == 3 and parts[0] == SCOPE_PREFIX and parts[2] == action:
            services.add(parts[1])
    services.discard("")
    return services


async def get_granted_services(scopes, action):
    """
    Return the names of the active services covered by `find:<service>:<action>` scopes.
    Scopes naming an unknown or inactive service are ignored.
    Raise PermissionDenied if no service is granted.
    """
    names = get_scoped_services(scopes, action)
    granted = {
        name
        async for name in Service.objects.filter(
            name__in=names, is_active=True
        ).values_list("name", flat=True)
    }
    if not granted:
        raise PermissionDenied(f"No {SCOPE_PREFIX} {action} scope granted")
    return granted


async def get_search_indices(scopes, services):
    """
    Return the OpenSearch indices to search, sorted by name.

    All the granted services are searched if `services` is empty. Otherwise, the
    search is restricted to `services`, which must all be granted, or
    SuspiciousOperation is raised.
    """
    granted = await get_granted_services(scopes, SEARCH)
    if services:
        requested = set(services)
        if not requested <= granted:
            raise SuspiciousOperation("Some requested services are not available")
        granted = requested
    return sorted(get_opensearch_index_name(name) for name in granted)


async def get_delete_index(scopes, service):
    """
    Return the OpenSearch index to delete documents from.
    Raise SuspiciousOperation if `service` is not granted.
    """
    granted = await get_granted_services(scopes, DELETE)
    if service not in granted:
        raise SuspiciousOperation("The requested service is not available")
    return get_opensearch_index_name(service)
