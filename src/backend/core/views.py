"""Views for find's core app."""

import logging

from django.conf import settings

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from opensearchpy import Q
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response

from . import schemas
from .api import problem_details_response
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
    API view for indexing a single document in OpenSearch.
        - Handles single document indexing only.
        - Documents are indexed into a single shared index with a `service` field
          for scoping, derived from the service authentication token.
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsAuthAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Index a single document into OpenSearch for the authenticated service.

        Documents are stored in a shared index with a `service` field set to the
        authenticated service's name.

        Request Data:
        -------------
        - Content-Type: application/json
        - Body: JSON object representing a single document.

        Responses:
        -----------
        - **201 Created**: Returns the indexed document ID.
        - **400 Bad Request**: Returns an error if the document is invalid, if bulk
          indexing is attempted, or if indexing fails.
        """
        index_name = settings.OPENSEARCH_INDEX
        opensearch_client_ = opensearch_client()

        if isinstance(request.data, list):
            return problem_details_response(
                400, "Bulk indexing not supported. Send a single document."
            )

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

    def _build_query(
        self,
        user_sub: str,
        document_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """
        Build OpenSearch query for document deletion.

        Args:
            user_sub: User subject identifier for authorization.
            document_ids: Optional list of document IDs to filter.
            tags: Optional list of tags to filter.

        Returns:
            Deletion OpenSearch query.
        """
        filters = [Q("term", users=user_sub)]
        if document_ids:
            filters.append(Q("ids", values=document_ids))
        if tags:
            filters.append(Q("terms", tags=tags))
        return Q("bool", must=filters).to_dict()


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

        params = schemas.SearchQueryParameters(**request.data)

        logger.info("Search '%s' on index %s", params.q, settings.OPENSEARCH_INDEX)
        result = search(
            query=params.q,
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
