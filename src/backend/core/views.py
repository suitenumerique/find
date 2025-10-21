"""Views for find's core app."""

import logging

from django.core.exceptions import SuspiciousOperation

from lasuite.oidc_resource_server.authentication import ResourceServerAuthentication
from lasuite.oidc_resource_server.mixins import ResourceServerMixin
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response

from . import enums, schemas
from .authentication import ServiceTokenAuthentication
from .models import Service
from .opensearch import client, ensure_index_exists
from .permissions import IsAuthAuthenticated

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
        index_name = request.auth.name

        if isinstance(request.data, list):
            # Bulk indexing several documents
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
                    document_dict = document.model_dump()
                    _id = document_dict.pop("id")
                    actions.append({"index": {"_id": _id}})
                    actions.append(document_dict)
                    results.append({"index": i, "_id": _id, "status": "valid"})

            if has_errors:
                return Response(results, status=status.HTTP_400_BAD_REQUEST)

            # Build index if needed.
            ensure_index_exists(index_name)

            response = client.bulk(index=index_name, body=actions)
            for i, item in enumerate(response["items"]):
                if item["index"]["status"] != 201:
                    results[i]["status"] = "error"
                    results[i]["message"] = (
                        item["index"].get("error", {}).get("reason", "Unknown error")
                    )
                else:
                    results[i]["status"] = "success"

            return Response(results, status=status.HTTP_201_CREATED)

        # Indexing a single document
        document = schemas.DocumentSchema(**request.data)
        document_dict = document.model_dump()
        _id = document_dict.pop("id")

        # Build index if needed.
        ensure_index_exists(index_name)

        client.index(index=index_name, body=document_dict, id=_id)

        return Response(
            {"status": "created", "_id": _id}, status=status.HTTP_201_CREATED
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

    def _get_opensearch_indices(self, audience, services):
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

        return allowed_services

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
        page_number : int, optional
            The page number to retrieve.
            Defaults to 1 if not specified.
        page_size : int, optional
            The number of results to return per page.
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

        # Compute pagination parameters
        from_value = (params.page_number - 1) * params.page_size
        size_value = params.page_size

        # Get index list for search query
        try:
            search_indices = self._get_opensearch_indices(
                audience, services=params.services
            )
        except SuspiciousOperation as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Prepare the search query
        search_body = {
            "_source": enums.SOURCE_FIELDS,  # limit the fields to return
            "script_fields": {
                "number_of_users": {"script": {"source": "doc['users'].size()"}},
                "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
            },
            "query": {"bool": {"must": [], "filter": []}},
            "sort": [],
            "from": from_value,
            "size": size_value,
        }

        # Adding the text query
        if params.q == "*":
            search_body["query"]["bool"]["must"].append({"match_all": {}})
        else:
            search_body["query"]["bool"]["must"].append(
                {
                    "multi_match": {
                        "query": params.q,
                        # Give title more importance over content by a power of 3
                        "fields": ["title.text^3", "content"],
                    }
                }
            )

        # Add sorting logic based on relevance or specified field
        if params.order_by == enums.RELEVANCE:
            search_body["sort"].append({"_score": {"order": params.order_direction}})
        else:
            search_body["sort"].append(
                {params.order_by: {"order": params.order_direction}}
            )

        # Apply access control based on documents reach
        search_body["query"]["bool"]["must"].append(
            {
                "bool": {
                    "should": [
                        # Access control on public & authenticated reach
                        {
                            "bool": {
                                "must_not": {
                                    "term": {enums.REACH: enums.ReachEnum.RESTRICTED},
                                },
                                # Limit search to already visited documents.
                                "must": {
                                    "terms": {
                                        "_id": sorted(params.visited),
                                    }
                                },
                            },
                        },
                        # Access control on restricted search : either user or group should match
                        {"term": {enums.USERS: user_sub}},
                        {"terms": {enums.GROUPS: groups}},
                    ],
                    # At least one of the 2 optional should clauses must apply
                    "minimum_should_match": 1,
                }
            }
        )

        # Optional filter by reach if explicitly provided in the query
        if params.reach is not None:
            search_body["query"]["bool"]["filter"].append(
                {"term": {enums.REACH: params.reach}}
            )

        # Always filter out inactive documents
        search_body["query"]["bool"]["filter"].append({"term": {"is_active": True}})

        response = client.search(  # pylint: disable=unexpected-keyword-arg
            body={
                "size": 2,
                "query": {
                    "knn": {
                        "embedding":{
                            "vector": [0.0]*384,
                            "k": 2,
                        }
                    },
                },
            },
            # Argument added by the query_params() decorator of opensearch and
            # not in the method declaration.
            ignore_unavailable=True,
        )

        return Response(response["hits"]["hits"], status=status.HTTP_200_OK)
