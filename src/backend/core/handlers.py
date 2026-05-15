from typing import Any

from django.conf import settings

from django_bolt.api import BoltAPI
from django_bolt.exceptions import HTTPException
from opensearchpy.exceptions import NotFoundError

from .bolt_auth import OIDCAuthentication, ServiceTokenAuthentication
from .query.builder import combine_with_system_scope
from .schemas import (
    Document,
    IndexResponse,
    SearchParams,
    SearchQuerySchema,
    SearchResponse,
    SearchResultDocument,
    SortClause,
    parse_where_clause,
)
from .services import opensearch
from .services.indexing import prepare_document_for_indexing
from .services.search import search

api = BoltAPI(prefix="/api/v1.0")

_oidc_auth = OIDCAuthentication()
_service_auth = ServiceTokenAuthentication()


async def _require_oidc_user(request: dict[str, Any]):
    headers = request["headers"]
    auth_context = {"authorization": headers.get("authorization", "")}
    user = await _oidc_auth.get_user(None, auth_context)
    if not user or not getattr(user, "sub", None):
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def _require_service_context(request: dict[str, Any]) -> dict[str, Any]:
    headers = request["headers"]
    auth_context = {"authorization": headers.get("authorization", "")}
    context = await _service_auth.get_user(None, auth_context)
    if not context or not context.get("service_name"):
        raise HTTPException(status_code=401, detail="Service authentication required")
    return context


@api.post("/documents/search")
async def search_documents(request: dict[str, Any], search_query: SearchQuerySchema) -> SearchResponse:
    user = await _require_oidc_user(request)
    user_sub = user.sub
    service = getattr(user, "token_audience", None)

    where = parse_where_clause(search_query.where)
    combined_where = combine_with_system_scope(where, user_sub, service)

    sort_clauses = None
    if search_query.sort:
        sort_clauses = [
            SortClause(field=s.field, direction=s.direction)
            for s in search_query.sort
        ]

    search_params = SearchParams(
        query=search_query.query,
        where=combined_where,
        sort=sort_clauses,
        limit=search_query.limit,
    )

    result = search(search_params, [settings.OPENSEARCH_INDEX])
    hits = result["hits"]["hits"]
    total = result["hits"]["total"]["value"]

    data = [
        SearchResultDocument(
            id=hit["_id"],
            **hit["_source"],
            number_of_users=hit.get("fields", {}).get("number_of_users", [0])[0],
            number_of_groups=hit.get("fields", {}).get("number_of_groups", [0])[0],
        )
        for hit in hits
    ]

    return SearchResponse(data=data, total=total, limit=search_query.limit or 50)


@api.delete("/documents/{document_id}", status_code=204)
async def delete_document(request: dict[str, Any], document_id: str) -> None:
    await _require_service_context(request)

    client = opensearch.opensearch_client()

    try:
        client.delete(
            index=settings.OPENSEARCH_INDEX,
            id=document_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Document not found") from e


@api.post("/documents/index", status_code=201)
async def index_document(request: dict[str, Any], document: Document) -> IndexResponse:
    context = await _require_service_context(request)
    index_name = settings.OPENSEARCH_INDEX
    opensearch_client_ = opensearch.opensearch_client()

    document_dict = prepare_document_for_indexing(
        {
            "id": document.id,
            "title": document.title,
            "content": document.content,
            "depth": document.depth,
            "path": document.path,
            "numchild": document.numchild,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "size": document.size,
            "users": document.users,
            "groups": document.groups,
            "reach": document.reach.value if document.reach else None,
            "tags": document.tags,
            "is_active": document.is_active,
        },
        service_name=context.get("service_name"),
    )
    doc_id = document_dict.pop("id")

    opensearch_client_.index(
        index=index_name,
        body=document_dict,
        id=doc_id,
    )

    return IndexResponse(id=str(doc_id))
