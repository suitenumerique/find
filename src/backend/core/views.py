"""Views for find's core app."""

import logging

from django.conf import settings

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response

from . import schemas
from .authentication import ServiceTokenAuthentication
from .permissions import IsAuthAuthenticated
from .services.indexing import (
    ensure_index_exists,
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
        - Documents are indexed into a single shared index with a `service` field
          for scoping, derived from the service authentication token.
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Index documents into OpenSearch for the authenticated service.

        Supports single document and bulk indexing. Documents are stored in a shared
        index with a `service` field set to the authenticated service's name.

        1. **Single Document**: Dictionary input returns `201 Created` with document ID.
        2. **Bulk Indexing**: List input returns `207 Multi-Status` with per-document results.

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
        index_name = settings.OPENSEARCH_INDEX
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
            schemas.Document(**request.data).model_dump(),
            service_name=request.auth.name,
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
                document = schemas.Document(**document_data)
            except PydanticValidationError as excpt:
                errors = [
                    {key: error[key] for key in ("msg", "type", "loc")}
                    for error in excpt.errors()
                ]
                results.append({"index": i, "status": "error", "errors": errors})
                has_errors = True
            else:
                document_dict = prepare_document_for_indexing(
                    document.model_dump(),
                    service_name=request.auth.name,
                )
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
        params = schemas.DeleteDocuments(**request.data)

        logger.info(
            "Deleting documents with filters: document_ids=%s, tags=%s",
            params.document_ids,
            params.tags,
        )

        client = opensearch_client()
        deletable_matches = client.search(
            index=settings.OPENSEARCH_INDEX,
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
                index=settings.OPENSEARCH_INDEX,
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
        filters = [
            {"term": {"users": user_sub}},
        ]
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
        Handle POST requests to perform a search on indexed documents with optional filtering
        and ordering.

        The search query should be provided as a "q" parameter. The method constructs a
        search request to OpenSearch using the specified query, with the option to filter by
        'reach' and order by 'relevance', 'created_at', 'updated_at', or 'size'.
        The results are further filtered by 'users' and 'groups' based on the authentication
        header.

        Body Parameters:
        ---------------
        q : str
            The search query string. This is a required parameter.
        reach : str, optional
            Filter results based on the 'reach' field.
        tags : List[str], optional
            Filter results based on the 'tags' field. Documents matching any of the
            provided tags will be returned.
        path : str, optional
            Filter results based on the 'path' field. Only documents whose path
            starts with the provided value will be returned.
        order_by : str, optional
            Order results by 'relevance', 'created_at', 'updated_at', or 'size'.
            Defaults to 'relevance' if not specified.
        order_direction : str, optional
            Order direction, 'asc' for ascending or 'desc' for descending.
            Defaults to 'desc'.
        nb_results : int, optional
            The number of results to return.
            Defaults to 50 if not specified.
        services: List[str], optional
            List of services on which we intend to run the query (current service if left empty)
        visited: List[sub], optional
            List of public/authenticated documents the user has visited to limit
            the document returned to the ones the current user has seen.
            Built from linkreach list of a document in docs app.

        Returns:
        --------
        Response : rest_framework.response.Response
            - 200 OK: Returns a list of search results matching the query.
            - 400 Bad Request: If the query parameter 'q' is not provided or invalid.
        """
        # Get list of groups related to the user from SCIM provider (consider caching result)
        user_sub = self.request.user.sub
        groups = []

        try:
            params = schemas.SearchQueryParameters(**request.data)
        except PydanticValidationError as excpt:
            errors = {error["loc"][0]: error["msg"] for error in excpt.errors()}
            logger.error("Validation error: %s", errors)
            raise excpt

        logger.info("Search '%s' on index %s", params.q, settings.OPENSEARCH_INDEX)
        result = search(
            q=params.q,
            nb_results=params.nb_results,
            order_by=params.order_by,
            order_direction=params.order_direction,
            search_indices=[settings.OPENSEARCH_INDEX],
            reach=params.reach,
            visited=params.visited,
            user_sub=user_sub,
            groups=groups,
            tags=params.tags,
            path=params.path,
        )["hits"]["hits"]
        logger.info("found %d results", len(result))
        logger.debug("results %s", result)

        return Response(result, status=status.HTTP_200_OK)
