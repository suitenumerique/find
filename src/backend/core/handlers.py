from django.conf import settings

from django_bolt.api import BoltAPI
from django_bolt.exceptions import HTTPException
from django_bolt.middleware import middleware
from django_bolt.request import Request
from opensearchpy.exceptions import NotFoundError

from .middleware import SearchAuthMiddleware, ServiceAuthMiddleware
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


@api.post("/documents/search")
@middleware(SearchAuthMiddleware)
async def search_documents(
    request: Request, search_query: SearchQuerySchema
) -> SearchResponse:
    service = request.state.get("service_name")
    user = request.state.get("user")
    user_sub = user.sub if user else None

    where = parse_where_clause(search_query.where)
    combined_where = combine_with_system_scope(where, user_sub, service)

    sort_clauses = None
    if search_query.sort:
        sort_clauses = [
            SortClause(field=s.field, direction=s.direction) for s in search_query.sort
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

    def extract_localized_field(source: dict, field_prefix: str) -> str:
        """Extract first matching localized field (e.g., title.en from title.*)."""
        for key, value in source.items():
            if key.startswith(f"{field_prefix}."):
                return value
        return source.get(field_prefix, "")

    data = [
        SearchResultDocument(
            id=hit["_id"],
            title=extract_localized_field(hit["_source"], "title"),
            content=extract_localized_field(hit["_source"], "content"),
            size=hit["_source"].get("size", 0),
            depth=hit["_source"].get("depth", 0),
            path=hit["_source"].get("path", ""),
            numchild=hit["_source"].get("numchild", 0),
            created_at=hit["_source"].get("created_at", ""),
            updated_at=hit["_source"].get("updated_at", ""),
            reach=hit["_source"].get("reach"),
            tags=hit["_source"].get("tags", []),
            number_of_users=hit.get("fields", {}).get("number_of_users", [0])[0],
            number_of_groups=hit.get("fields", {}).get("number_of_groups", [0])[0],
        )
        for hit in hits
    ]

    return SearchResponse(data=data, total=total, limit=search_query.limit or 50)


@api.delete("/documents/{document_id}", status_code=204)
@middleware(ServiceAuthMiddleware)
async def delete_document(request: Request, document_id: str) -> None:
    client = opensearch.opensearch_client()

    try:
        client.delete(
            index=settings.OPENSEARCH_INDEX,
            id=document_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Document not found") from e


@api.post("/documents/index", status_code=201)
@middleware(ServiceAuthMiddleware)
async def index_document(request: Request, document: Document) -> IndexResponse:
    service_name = request.state["service_name"]
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
        service_name=service_name,
    )
    doc_id = document_dict.pop("id")

    opensearch_client_.index(
        index=index_name,
        body=document_dict,
        id=doc_id,
    )

    return IndexResponse(id=str(doc_id))
