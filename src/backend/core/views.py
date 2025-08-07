"""Views for find's core app."""

from pydantic import ValidationError as PydanticValidationError
from rest_framework import status, views
from rest_framework.response import Response
from urllib3.exceptions import ReadTimeoutError

from . import enums, schemas
from .authentication import ServiceTokenAuthentication
from .opensearch import client, ensure_index_exists
from .permissions import IsAuthAuthenticated


class DocumentView(views.APIView):
    """
    API view for managing documents in an OpenSearch index.

    This view provides functionality for both indexing and searching documents
    within an OpenSearch index dedicated to the authenticated service. The class
    supports the following operations:

    1. **Document Indexing (POST)**:
        - Handles both single document and bulk document indexing.
        - The index is dynamically determined based on the service authentication token,
        ensuring that each service has its own isolated index.

    2. **Document Search (GET)**:
        - Enables searching through indexed documents with support for various filters
        and sorting options.
        - The search results can be sorted or filtered via querystring parameters.
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsAuthAuthenticated]

    @property
    def index_name(self):
        """Compute index name from the service name extracted during authentication"""
        return f"find-{self.request.auth}"

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

            return Response(results, status=status.HTTP_207_MULTI_STATUS)

        # Indexing a single document
        document = schemas.DocumentSchema(**request.data)
        document_dict = document.model_dump()
        _id = document_dict.pop("id")
        try:
            client.index(index=index_name, body=document_dict, id=_id)
        except ReadTimeoutError:
            ensure_index_exists(index_name)
            client.index(index=index_name, body=document_dict, id=_id)

        return Response(
            {"status": "created", "_id": _id}, status=status.HTTP_201_CREATED
        )

    def get(self, request, *args, **kwargs):
        """
        Handle GET requests to perform a search on indexed documents with optional filtering
        and ordering.

        The search query should be provided as a query parameter 'q'. The method constructs a
        search request to OpenSearch using the specified query, with the option to filter by
        'is_public' and order by 'relevance', 'created_at', 'updated_at', or 'size'.
        The results are further filtered by 'users' and 'groups' based on the authentication
        header.

        Query Parameters:
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

        Returns:
        --------
        Response : rest_framework.response.Response
            - 200 OK: Returns a list of search results matching the query.
            - 400 Bad Request: If the query parameter 'q' is not provided or invalid.
        """
        # Extract and validate query parameters using Pydantic schema
        params = schemas.SearchQueryParametersSchema(**request.GET)

        # Compute pagination parameters
        from_value = (params.page_number - 1) * params.page_size
        size_value = params.page_size

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

        # Filter by reach if provided
        if params.reach is not None:
            search_body["query"]["bool"]["filter"].append(
                {"term": {enums.REACH: params.reach}}
            )

        # Always filter out inactive documents
        search_body["query"]["bool"]["filter"].append({"term": {"is_active": True}})

        response = client.search(index=",".join(params.services), body=search_body)
        return Response(response["hits"]["hits"], status=status.HTTP_200_OK)
