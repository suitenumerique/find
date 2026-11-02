"""Endpoints of find's core app."""

import functools
import logging
from typing import List, Union

from django.core.handlers.asgi import ASGIRequest

from ninja import Body, Router, Status
from pydantic import ValidationError as PydanticValidationError

from . import schemas
from .authentication import MenshenBearer, ServiceTokenBearer
from .services.deletion import delete_documents
from .services.indexing import bulk_index_documents, index_document
from .services.opensearch import close_async_opensearch_client
from .services.scopes import get_delete_index, get_search_indices
from .services.search import format_hit, search

logger = logging.getLogger(__name__)


def close_opensearch_client_after_wsgi_request(func):
    """
    Under WSGI, Django runs each async view in its own event loop, which ends with
    the request: close the AsyncOpenSearch client of this loop before it does. Under
    ASGI, the event loop and its client live as long as the process.
    """

    @functools.wraps(func)
    async def wrapper(request, *args, **kwargs):
        try:
            return await func(request, *args, **kwargs)
        finally:
            if not isinstance(request, ASGIRequest):
                await close_async_opensearch_client()

    return wrapper


router = Router()
router.add_decorator(close_opensearch_client_after_wsgi_request)

USER_ERRORS = {
    400: Union[List[schemas.ValidationErrorSchema], schemas.ErrorSchema],
    401: schemas.ErrorSchema,
    403: schemas.ErrorSchema,
    503: schemas.ErrorSchema,
}


@router.post(
    "index/",
    operation_id="index_documents",
    auth=ServiceTokenBearer(),
    response={
        201: Union[schemas.IndexedDocumentSchema, List[schemas.BulkIndexResultSchema]],
        207: List[schemas.BulkIndexResultSchema],
        400: Union[
            List[schemas.BulkIndexResultSchema],
            List[schemas.ValidationErrorSchema],
            schemas.ErrorSchema,
        ],
        403: schemas.ErrorSchema,
    },
    by_alias=True,
    exclude_unset=True,
)
async def index_documents(request, payload: Body[schemas.IndexPayload]):
    """
    Index a document, or a list of documents, into the index of the authenticated
    service. A document that already exists is updated.

    - A single document is answered with a 201, or a 400 listing its validation
      errors.
    - A list of documents is answered with the status of each document: a 201 if
      all were indexed, a 207 if some failed to be indexed, or a 400 if any failed
      validation, in which case none is indexed.
    """
    index_name = request.auth.index_name

    if isinstance(payload, list):
        results, has_errors = await bulk_index_documents(index_name, payload)
        if has_errors:
            return Status(400, results)
        if any(result["status"] == "error" for result in results):
            return Status(207, results)
        return Status(201, results)

    try:
        document = schemas.DocumentSchema.model_validate(payload)
    except PydanticValidationError as error:
        return Status(400, schemas.format_validation_errors(error.errors()))
    _id = await index_document(index_name, document)
    return Status(201, {"status": "created", "_id": _id})


@router.post(
    "delete/",
    operation_id="delete_documents",
    auth=MenshenBearer(),
    response={200: schemas.DeleteDocumentsResponseSchema, **USER_ERRORS},
    by_alias=True,
)
async def delete(request, params: schemas.DeleteDocumentsSchema):
    """
    Delete documents of a service, if the token grants `find:<service>:delete`.

    Only the documents listing the authenticated user in their `users` are
    deleted. The ids and the tags, if both are given, must both match. The
    response does not reveal whether the documents that were not deleted exist.
    """
    index_name = await get_delete_index(request.auth.scopes, params.service)

    nb_deleted, undeleted_ids = await delete_documents(
        index_name,
        request.auth.sub,
        document_ids=params.document_ids,
        tags=params.tags,
    )
    return {
        "nb-deleted-documents": nb_deleted,
        "undeleted-document-ids": undeleted_ids,
    }


@router.post(
    "search/",
    operation_id="search_documents",
    auth=MenshenBearer(),
    response={200: schemas.SearchResponseSchema, **USER_ERRORS},
)
async def search_documents(request, params: schemas.SearchQueryParametersSchema):
    """
    Search the documents the authenticated user may access, in the services granted
    by `find:<service>:search` scopes: all of them, or the requested `services`.

    `q="*"` matches all documents. A document is returned if the user is listed in
    its `users`, or if it is not restricted and listed in `visited`.
    """
    search_indices = await get_search_indices(request.auth.scopes, params.services)

    logger.info("Search '%s' on indices %s", params.q, search_indices)
    hits = (
        await search(
            q=params.q,
            nb_results=params.nb_results,
            order_by=params.order_by,
            order_direction=params.order_direction,
            search_indices=search_indices,
            reach=params.reach,
            visited=params.visited,
            user_sub=request.auth.sub,
            # Groups are not retrieved yet
            groups=[],
            tags=params.tags,
            path=params.path,
        )
    )["hits"]["hits"]
    logger.info("found %d results", len(hits))
    logger.debug("results %s", hits)

    return {"results": [format_hit(hit) for hit in hits]}
