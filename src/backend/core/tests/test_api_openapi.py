"""Tests for the OpenAPI schema of the API"""

from core.api import api


def test_api_openapi_schema():
    """The OpenAPI schema should document the request and response bodies."""
    schema = api.get_openapi_schema(path_prefix="/api/v1.0/")
    operations = {
        path: operations["post"] for path, operations in schema["paths"].items()
    }
    assert {
        path: operation["operationId"] for path, operation in operations.items()
    } == {
        "/api/v1.0/documents/index/": "index_documents",
        "/api/v1.0/documents/delete/": "delete_documents",
        "/api/v1.0/documents/search/": "search_documents",
    }
    assert operations["/api/v1.0/documents/search/"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/SearchQueryParametersSchema"}
    assert operations["/api/v1.0/documents/search/"]["responses"][200]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/SearchResponseSchema"}
    assert operations["/api/v1.0/documents/index/"]["security"] == [
        {"ServiceTokenBearer": []}
    ]
    assert operations["/api/v1.0/documents/search/"]["security"] == [
        {"MenshenBearer": []}
    ]
