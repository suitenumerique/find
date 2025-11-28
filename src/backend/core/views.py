"""Views for find's core app."""

import logging

from django.core.exceptions import BadRequest, SuspiciousOperation

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response

from . import schemas
from .authentication import ServiceTokenAuthentication
from .models import IndexDocument, Service, get_opensearch_index_name
from .permissions import IsAuthAuthenticated
from .services.indexer_services import IndexerTaskService
from .services.opensearch import (
    opensearch_client,
    search,
)
from .tasks.indexer import dispatch_indexing_tasks

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

    def clean_document(self, data):
        """
        Returns a IndexDocument from request data.
        """
        try:
            document = schemas.DocumentSchema(**data)
        except PydanticValidationError as err:
            raise BadRequest(
                [
                    {key: error[key] for key in ("msg", "type", "loc")}
                    for error in err.errors()
                ]
            ) from err

        return IndexDocument(**document.model_dump())

    # pylint: disable=too-many-locals
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
        service = request.auth
        opensearch_client_ = opensearch_client()
        indexer = IndexerTaskService(service, client=opensearch_client_)

        # Bulk indexing several documents
        if isinstance(request.data, list):
            is_valid = True
            results = []
            documents = []

            # Parse request data and raise on any validation error
            for i, document_data in enumerate(request.data):
                try:
                    doc = self.clean_document(document_data)
                    documents.append(doc)
                    results.append({"index": i, "status": "valid", "_id": str(doc.id)})
                except BadRequest as e:
                    results.append({"index": i, "status": "error", "errors": e.args[0]})
                    is_valid = False

            if not is_valid:
                return Response(results, status=status.HTTP_400_BAD_REQUEST)

            # Indexing all documents
            errors = indexer.index(documents)

            # Dispatch deferred indexation tasks for the documents
            dispatch_indexing_tasks(service, documents)

            # Update error status of documents
            errors = {e.id: e for e in errors}

            for result in results:
                error = errors.get(result["_id"])

                if error is None:
                    result["status"] = "success"
                else:
                    result["status"] = "error"
                    result["message"] = error.message

            return Response(results, status=status.HTTP_201_CREATED)

        try:
            document = self.clean_document(request.data)
        except BadRequest as e:
            return Response(e.args[0], status=status.HTTP_400_BAD_REQUEST)

        # Indexing a single document
        errors = indexer.index((document,))

        if errors:
            return Response(
                {"status": "error", **errors[0]}, status=status.HTTP_400_BAD_REQUEST
            )

        # Dispatch deferred indexation tasks for the document
        dispatch_indexing_tasks(service, (document,))

        return Response(
            {"status": "created", "_id": document.id}, status=status.HTTP_201_CREATED
        )


class SearchDocumentView(ResourceServerMixin, views.APIView):
    """
    API view for searching documents in OpenSearch.
        - Enables searching through indexed documents with support for various filters
          and sorting options.
        - The search results can be sorted or filtered via querystring parameters.
    """

    authentication_classes = [ResourceServerAuthentication]
    permission_classes = [IsAuthAuthenticated]

    @staticmethod
    def _get_opensearch_indices(audience, services):
        # Get request user service
        try:
            user_service = Service.objects.get(client_id=audience, is_active=True)
        except Service.DoesNotExist as e:
            logger.warning("Login failed: No service %s found", audience)
            raise SuspiciousOperation("Service is not available") from e

        # Find allowed sub-services for this service
        allowed_services = set(user_service.services.values_list("name", flat=True))
        allowed_services.add(user_service.name)

        if services:
            available = set(services).intersection(allowed_services)

            if len(available) < len(services):
                raise SuspiciousOperation("Some requested services are not available")

        return [get_opensearch_index_name(name) for name in allowed_services]

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
        # //////////////////////////////////////////////////

        # Extract and validate query parameters using Pydantic schema
        params = schemas.SearchQueryParametersSchema(**request.data)

        # Get index list for search query
        try:
            search_indices = self._get_opensearch_indices(
                audience, services=params.services
            )
        except SuspiciousOperation as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response = search(
            q=params.q,
            nb_results=params.nb_results,
            order_by=params.order_by,
            order_direction=params.order_direction,
            search_indices=search_indices,
            reach=params.reach,
            visited=params.visited,
            user_sub=user_sub,
            groups=groups,
        )

        return Response(response["hits"]["hits"], status=status.HTTP_200_OK)
