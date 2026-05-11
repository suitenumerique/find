"""Views for find's core app."""

import logging
from uuid import UUID

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from opensearchpy import NotFoundError
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.request import Request
from rest_framework.response import Response

from . import schemas
from .authentication import ServiceTokenAuthentication
from .permissions import IsAuthAuthenticated
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
    """API view for indexing a single document in OpenSearch."""

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        API view for indexing a single document into OpenSearch index of the authenticated service.

        Request Data:
        -------------
        - Content-Type: application/json
        - Body: JSON object representing a document.

        Responses:
        -----------
        - 201 Created: Returns {"status": "created", "_id": <uuid>}.
        - 400 Bad Request: Returns an error message if the document is invalid,
          if indexing fails, or if bulk indexing is attempted (array input).
        """
        index_name = request.auth.index_name
        opensearch_client_ = opensearch_client()

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


class DeleteDocumentView(ResourceServerMixin, views.APIView):
    """API view for deleting a single document from OpenSearch."""

    authentication_classes = [ResourceServerAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def delete(self, request: Request, document_id: UUID, *args, **kwargs) -> Response:
        """
        Delete a single document by ID.

        Path Parameters:
        ----------------
        document_id : UUID
            The ID of the document to delete.

        Returns:
        --------
        Response : rest_framework.response.Response
            - 204 No Content: Document deleted successfully.
            - 403 Forbidden: User not authorized to delete this document.
            - 404 Not Found: Document doesn't exist.
        """
        index_names = get_opensearch_indices(
            self._get_service_provider_audience(), services=[]
        )

        client = opensearch_client()
        document_id_str = str(document_id)

        for index_name in index_names:
            try:
                doc = client.get(index=index_name, id=document_id_str)
            except NotFoundError:
                continue

            users = doc.get("_source", {}).get("users", [])
            if self.request.user.sub not in users:
                return Response(
                    {"detail": "Not authorized to delete this document."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            logger.info(
                "Deleting document %s from index %s", document_id_str, index_name
            )
            client.delete(index=index_name, id=document_id_str)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"detail": "Document not found."},
            status=status.HTTP_404_NOT_FOUND,
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
            - 200 OK: Returns a list of search results matching the query.
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
        search_indices = get_opensearch_indices(audience, services=params.services)

        logger.info("Search '%s' on indices %s", params.q, search_indices)
        result = search(
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
        logger.info("found %d results", len(result))
        logger.debug("results %s", result)

        return Response(result, status=status.HTTP_200_OK)
