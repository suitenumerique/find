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
from .permissions import IsAuthAuthenticated
from .services.deletion import delete_documents
from .services.indexing import (
    bulk_index_documents,
    get_opensearch_indices,
    index_document,
)
from .services.opensearch import run_async
from .services.search import format_hit, search

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

        if isinstance(request.data, list):
            return self.bulk_index(request, index_name)

        return self.single_index(request, index_name)

    def single_index(self, request, index_name):
        """
        Index a single document into OpenSearch.

        Args:
            request: The HTTP request containing document data.
            index_name: The name of the OpenSearch index.

        Returns:
            Response: HTTP response with status and document ID.
                - 201 Created: Returns the indexed document ID.
                - 400 Bad Request: Returns an error message if the document is invalid.
        """
        document = schemas.DocumentSchema(**request.data)
        _id = run_async(index_document, index_name, document)

        return Response(
            {"status": "created", "_id": _id}, status=status.HTTP_201_CREATED
        )

    def bulk_index(self, request, index_name):
        """
        Index multiple documents into OpenSearch in bulk.

        Args:
            request: The HTTP request containing a list of documents.
            index_name: The name of the OpenSearch index.

        Returns:
            Response: HTTP response with detailed status for each document.
                - 201 Created: Returns status for all documents.
                - 400 Bad Request: Returns errors if document validation fails.
        """
        results, has_errors = run_async(bulk_index_documents, index_name, request.data)
        if has_errors:
            return Response(results, status=status.HTTP_400_BAD_REQUEST)

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

        nb_deleted, deletable_ids = run_async(
            delete_documents,
            index_name,
            self.request.user.sub,
            document_ids=params.document_ids,
            tags=params.tags,
        )

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
            - 200 OK: Returns {"results": [...]}, the documents matching the query
              (see schemas.SearchResultSchema).
            - 400 Bad Request: If the query parameter 'q' is not provided or invalid.
        """
        # Get list of groups related to the user from SCIM provider (consider caching result)
        audience = self._get_service_provider_audience()
        user_sub = self.request.user.sub
        groups = []

        try:
            params = schemas.SearchQueryParametersSchema(**request.data)
        except PydanticValidationError as excpt:
            errors = {error["loc"][0]: error["msg"] for error in excpt.errors()}
            logger.error("Validation error: %s", errors)
            raise excpt

        # Get index list for search query
        try:
            search_indices = get_opensearch_indices(audience, services=params.services)
        except SuspiciousOperation as e:
            logger.error(e, exc_info=True)
            return Response(
                {"detail": "Invalid request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("Search '%s' on indices %s", params.q, search_indices)
        hits = run_async(
            search,
            q=params.q,
            nb_results=params.nb_results,
            order_by=params.order_by,
            order_direction=params.order_direction,
            search_indices=search_indices,
            reach=params.reach,
            visited=params.visited,
            user_sub=user_sub,
            groups=groups,
            tags=params.tags,
            path=params.path,
        )["hits"]["hits"]
        logger.info("found %d results", len(hits))
        logger.debug("results %s", hits)

        response = schemas.SearchResponseSchema(
            results=[format_hit(hit) for hit in hits]
        )
        return Response(response.model_dump(mode="json"), status=status.HTTP_200_OK)
