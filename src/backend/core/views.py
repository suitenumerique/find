"""Views for find's core app."""

import logging

from django.core.exceptions import SuspiciousOperation

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response

from . import schemas
from .authentication import ServiceTokenAuthentication
from .models import Service
from .permissions import IsAuthAuthenticated
from .query.builder import combine_with_system_scope
from .query.dsl import SearchQuerySchema
from .services.indexing import (
    ensure_index_exists,
    get_opensearch_indices,
    prepare_document_for_indexing,
)
from .services.opensearch import opensearch_client
from .services.search import search
from .utils import get_language_value

logger = logging.getLogger(__name__)


class IndexDocumentView(views.APIView):
    """
    API view for indexing documents in OpenSearch.
        - Handles both single document and bulk document indexing.
        - The index is dynamically determined based on the service authentication token,
          ensuring that each service has its own isolated index.
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        API view for indexing documents into OpenSearch index of the authenticated service.

        This view supports both single document indexing and bulk indexing. It handles
        the following scenarios based on the type of request data:

        1. **Single Document Indexing**: If the request contains a single document (as a
            dictionary), it will be indexed into an OpenSearch index named `find-{auth_token}`.
            On success, the indexed document is returned with a `201 Created` status. If an
            error occurs, a `400 Bad Request` response with an error message is returned.

        2. **Bulk Indexing**: If the request contains a list of documents, each document is
            validated and indexed in bulk. The response includes a detailed status of each
            document, indicating whether it was successfully indexed or if an error occurred.
            The HTTP status code for the bulk indexing operation is `207 Multi-Status`, and the
            response body contains information about the success or failure of each individual
            document.

        Methods:
        -------
        post(request, *args, **kwargs):
            Handles POST requests to index either a single document or a list of documents.
            - **Single Document**: Expects a dictionary representing a document.
            - **Bulk Indexing**: Expects a list of dictionaries, each representing a document.

        Request Data:
        -------------
        For single document indexing:
        - Content-Type: application/json
        - Body: JSON object representing a document.

        For bulk indexing:
        - Content-Type: application/json
        - Body: JSON array of JSON objects, each representing a document.

        Responses:
        -----------
        - **Single Document Indexing**:
            - 201 Created: Returns the indexed document.
            - 400 Bad Request: Returns an error message if the document is invalid or if
              indexing fails.

        - **Bulk Indexing**:
            - 207 Multi-Status if all documents formatting is correct, 400 Bad Request otherwise:
            - Returns a list of results for all documents, with details of success and indexing
              errors.
        """
        index_name = request.auth.index_name
        opensearch_client_ = opensearch_client()

        if isinstance(request.data, list):
            return self.bulk_index(request, index_name, opensearch_client_)

        return self.single_index(request, index_name, opensearch_client_)

    def single_index(self, request, index_name, opensearch_client_):
        """
        Index a single document into OpenSearch.

        Args:
            request: The HTTP request containing document data.
            index_name: The name of the OpenSearch index.
            opensearch_client_: The OpenSearch client instance.

        Returns:
            Response: HTTP response with status and document ID.
                - 201 Created: Returns the indexed document ID.
                - 400 Bad Request: Returns an error message if the document is invalid.
        """
        document_dict = prepare_document_for_indexing(
            schemas.DocumentSchema(**request.data).model_dump()
        )
        _id = document_dict.pop("id")
        logger.info(
            "Indexing single document %s on index %s",
            get_language_value(document_dict, "title"),
            index_name,
        )

        ensure_index_exists(index_name)
        opensearch_client_.index(
            index=index_name,
            body=document_dict,
            id=_id,
        )

        return Response(
            {"status": "created", "_id": _id}, status=status.HTTP_201_CREATED
        )

    # pylint: disable=too-many-locals
    def bulk_index(self, request, index_name, opensearch_client_):
        """
        Index multiple documents into OpenSearch in bulk.

        Args:
            request: The HTTP request containing a list of documents.
            index_name: The name of the OpenSearch index.
            opensearch_client_: The OpenSearch client instance.

        Returns:
            Response: HTTP response with detailed status for each document.
                - 201 Created: Returns status for all documents.
                - 400 Bad Request: Returns errors if document validation fails.
        """
        results = []
        actions = []
        has_errors = False

        for i, document_data in enumerate(request.data):
            try:
                document = schemas.DocumentSchema(**document_data)
            except PydanticValidationError as excpt:
                errors = [
                    {key: error[key] for key in ("msg", "type", "loc")}
                    for error in excpt.errors()
                ]
                results.append({"index": i, "status": "error", "errors": errors})
                has_errors = True
            else:
                document_dict = prepare_document_for_indexing(document.model_dump())
                logger.info(
                    "Indexing document %s on index %s",
                    get_language_value(document_dict, "title"),
                    index_name,
                )
                _id = document_dict.pop("id")
                actions.append({"index": {"_id": _id}})
                actions.append(document_dict)
                results.append({"index": i, "_id": _id, "status": "valid"})

        if has_errors:
            return Response(results, status=status.HTTP_400_BAD_REQUEST)

        ensure_index_exists(index_name)
        response = opensearch_client_.bulk(index=index_name, body=actions)
        for i, item in enumerate(response["items"]):
            if item["index"]["status"] != 201:
                results[i]["status"] = "error"
                results[i]["message"] = (
                    item["index"].get("error", {}).get("reason", "Unknown error")
                )
            else:
                results[i]["status"] = "success"

        return Response(results, status=status.HTTP_201_CREATED)


class DeleteDocumentsView(ResourceServerMixin, views.APIView):
    """
    API view for deleting documents from OpenSearch.
        - Allows authenticated users to delete documents from a specified index.
        - Users can only delete documents where they are listed in the 'users' field.
        - Returns the count of deleted documents without revealing document existence.
    """

    authentication_classes = [ResourceServerAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests to delete documents from the specified index.

        Only documents where the authenticated user is in the 'users' field will be deleted.

        Body Parameters:
        ---------------
        service: str
            service name to determine the index from which to delete documents.
        document_ids : List[str], optional
            A list of document IDs to delete from the index.
        tags : List[str], optional
            A list of tags to filter documents for deletion.

        At least one of document_ids or tags must be provided.
        The list of ids and the list of tags are combined with AND logic.

        Returns:
        --------
        Response : rest_framework.response.Response
            - 200 OK: returns a JSON object with the following keys:
                - nb-deleted-documents: Number of documents deleted.
                - undeleted-document-ids: sublist of param.document_ids that were not deleted.
                Deletion may be prevented because the document does not exist,
                because the user is not authorized to delete it or because a tag filter was used.
            - 400 Bad Request: If parameters are invalid or missing.
        """
        params = schemas.DeleteDocumentsSchema(**request.data)
        try:
            index_name = get_opensearch_indices(
                self._get_service_provider_audience(), services=[params.service]
            )[0]
        except SuspiciousOperation as e:
            logger.error(e)
            return Response(
                {"detail": "Invalid request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Deleting documents from index %s with filters: document_ids=%s, tags=%s",
            index_name,
            params.document_ids,
            params.tags,
        )

        client = opensearch_client()
        deletable_matches = client.search(
            index=index_name,
            body={
                "query": self._build_query(
                    self.request.user.sub,
                    document_ids=params.document_ids,
                    tags=params.tags,
                )
            },
        )
        deletable_ids = [hit["_id"] for hit in deletable_matches["hits"]["hits"]]

        if deletable_ids:
            response = client.delete_by_query(
                index=index_name,
                body={"query": {"ids": {"values": deletable_ids}}},
            )
            nb_deleted = response.get("deleted", 0)
        else:
            nb_deleted = 0

        return Response(
            {
                "nb-deleted-documents": nb_deleted,
                "undeleted-document-ids": [
                    document_id
                    for document_id in params.document_ids or []
                    if document_id not in deletable_ids
                ],
            },
            status=status.HTTP_200_OK,
        )

    def _build_query(self, user_sub, document_ids=None, tags=None):
        """
        Build OpenSearch query for document deletion.

        Args:
            user_sub: User subject identifier for authorization.
            document_ids: Optional list of document IDs to filter.
            tags: Optional list of tags to filter.

        Returns:
            Deletion OpenSearch query.
        """
        filters = [{"term": {"users": user_sub}}]
        if document_ids:
            filters.append({"ids": {"values": document_ids}})
        if tags:
            filters.append({"terms": {"tags": tags}})
        return {"bool": {"must": filters}}


class SearchDocumentView(ResourceServerMixin, views.APIView):
    """
    API view for searching documents in OpenSearch.
        - Enables searching through indexed documents with support for various filters
          and sorting options.
        - The search results can be sorted or filtered via querystring parameters.
    """

    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests to search documents using structured query DSL.

        Body Parameters:
        ----------------
        query : str
            The search query string. Use "*" for match_all.
        where : WhereClause, optional
            Structured filter conditions. Supports:
            - Field conditions: {"field": "reach", "op": "eq", "value": "public"}
            - Boolean combinators: {"and": [...]}, {"or": [...]}, {"not": {...}}
            - Operators: eq, in, all, prefix, gt, gte, lt, lte, exists
        sort : List[SortClause], optional
            Sort specifications: [{"field": "created_at", "direction": "desc"}]
            Available fields: relevance, title, created_at, updated_at, size
            Defaults to relevance descending.
        limit : int, optional
            Number of results (1-100). Defaults to 50.

        Allowed Filter Fields:
        ---------------------
        id, reach, tags, path, created_at, updated_at, size, depth, numchild, title, content

        Blocked Fields (return 400):
        ---------------------------
        users, groups, is_active

        Visited Replacement:
        -------------------
        The old 'visited' parameter filtered non-restricted docs to those the user had seen.
        To replicate this behavior, use a where clause:

        {
            "query": "search term",
            "where": {
                "or": [
                    {"field": "reach", "op": "eq", "value": "restricted"},
                    {"and": [
                        {"field": "id", "op": "in", "value": ["doc-id-1", "doc-id-2"]},
                        {"not": {"field": "reach", "op": "eq", "value": "restricted"}}
                    ]}
                ]
            }
        }

        This returns: all restricted docs the user can access + non-restricted docs in the ID list.

        Returns:
        --------
        Response : rest_framework.response.Response
            - 200 OK: List of search results.
            - 400 Bad Request: If validation fails or blocked fields are used.
        """
        user_sub = None
        # Service tokens have request.auth = Service instance; user tokens don't
        if not isinstance(getattr(request, "auth", None), Service):
            user_sub = getattr(request.user, "sub", None)

        audience = self._get_service_provider_audience()

        params = SearchQuerySchema(**request.data)
        combined_where = combine_with_system_scope(params.where, user_sub)

        search_params = params.model_copy(update={"where": combined_where})
        search_indices = get_opensearch_indices(audience, services=None)

        logger.info("Search '%s' on indices %s", params.query, search_indices)
        result = search(search_params, search_indices)["hits"]["hits"]
        logger.info("found %d results", len(result))
        logger.debug("results %s", result)

        return Response(result, status=status.HTTP_200_OK)
