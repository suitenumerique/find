"""
Test suite for searching documents in OpenSearch over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import operator
import random

from django.test import Client

import pytest
import responses

from core import enums, factories
from core.services.opensearch import opensearch_client
from core.utils import prepare_index

from .utils import (
    build_authorization_bearer,
    bulk_create_documents,
    setup_oicd_resource_server,
)

pytestmark = pytest.mark.django_db


@responses.activate
def test_api_documents_search_inactive_token(settings):
    """A token that the identity provider reports as inactive should be rejected."""
    setup_oicd_resource_server(
        responses,
        settings,
        sub="user_sub",
        introspect=lambda request, user_info: (
            200,
            {},
            '{"active": false}',
        ),
    )
    factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    # The resource server raises a SuspiciousOperation, that Django turns into a 400
    assert response.status_code == 400


@responses.activate
def test_api_documents_search_unknown_calling_service(settings):
    """A token whose audience matches no registered service should result in a 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="unknown")
    factories.ServiceFactory(client_id="some_client_id")

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


@responses.activate
def test_api_documents_search_query_missing(settings):
    """The "q" parameter is required."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/search/",
        {},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {"loc": ["q"], "msg": "Field required", "type": "missing"}
    ]


@responses.activate
def test_api_documents_search_services_invalid_parameters(settings):
    """Invalid services parameter should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/search/",
        # services should be a list
        {"q": "a quick fox", "services": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "loc": ["services"],
            "msg": "Value error, ",
            "type": "value_error",
        }
    ]


@responses.activate
def test_api_documents_search_visited_invalid_parameters(settings):
    """Invalid visited parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/search/",
        # visited should be a list
        {"q": "a quick fox", "visited": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "loc": ["visited"],
            "msg": "Value error, ",
            "type": "value_error",
        }
    ]


@responses.activate
def test_api_documents_search_match_all(settings):
    """Searching a document with q='*' should match all docs"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    nb_documents = 12
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        nb_documents, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [doc["id"] for doc in documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == nb_documents

    assert [r["id"] for r in response.json()["results"]] == [
        str(doc["id"]) for doc in documents
    ]


@responses.activate
def test_api_documents_search_full_text_query_title(settings):
    """Searching a document by its title should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {"title": "The quick brown fox", "content": "the wolf"},
            {"title": "The blue fox", "content": "the wolf"},
            {"title": "The brown goat", "content": "the wolf"},
        ]
    )

    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 2

    fox_response, other_fox_response = response.json()["results"]
    fox_document, other_fox_document = documents[:2]
    assert fox_response["score"] > 0
    assert fox_response == {
        "id": str(fox_document["id"]),
        "service": service.name,
        "title": fox_document["title"],
        "score": fox_response["score"],
        "path": fox_document["path"],
        "depth": 1,
        "numchild": 0,
        "size": fox_document["size"],
        # Pydantic serializes UTC datetimes with a "Z" suffix
        "created_at": fox_document["created_at"].isoformat().replace("+00:00", "Z"),
        "updated_at": fox_document["updated_at"].isoformat().replace("+00:00", "Z"),
        "reach": fox_document["reach"],
        "tags": [],
    }

    assert other_fox_response["id"] == str(other_fox_document["id"])
    assert 0 < other_fox_response["score"] < fox_response["score"]


@responses.activate
def test_api_documents_search_full_text_query_content(settings):
    """Searching a document by its content should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {"title": "Animals", "content": "The quick brown fox"},
            {"title": "Animals", "content": "The blue fox"},
            {"title": "Animals", "content": "The brown goat"},
        ]
    )

    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [
        str(documents[0]["id"]),
        str(documents[1]["id"]),
    ]


@responses.activate
def test_api_documents_search_full_text_query_trigrams(settings):
    """A partial word should match documents through trigrams"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {"title": "Organisation of the meeting", "content": "the agenda"},
            {"title": "The brown goat", "content": "the wolf"},
        ]
    )

    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "organ", "visited": [doc["id"] for doc in documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [str(documents[0]["id"])]


@responses.activate
def test_api_documents_search_ordering_by_fields(settings):
    """It should be possible to order by several fields"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    parameters = [
        (enums.CREATED_AT, "asc"),
        (enums.CREATED_AT, "desc"),
        (enums.UPDATED_AT, "asc"),
        (enums.UPDATED_AT, "desc"),
        (enums.SIZE, "asc"),
        (enums.SIZE, "desc"),
        (enums.REACH, "asc"),
        (enums.REACH, "desc"),
    ]

    for field, direction in parameters:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "order_by": field,
                "order_direction": direction,
                "visited": [doc["id"] for doc in documents],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        data = response.json()["results"]
        assert len(data) == 4

        assert all(result["score"] is None for result in data)

        # Check that results are sorted by the field as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(data) - 1):
            assert compare(data[i][field], data[i + 1][field])


@responses.activate
def test_api_documents_search_ordering_by_title(settings):
    """It should be possible to order by title"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = bulk_create_documents(
        [
            {"title": "Beta", "content": "content"},
            {"title": "Alpha", "content": "content"},
        ]
    )
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "order_by": "title", "order_direction": "asc"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [
        str(documents[1]["id"]),
        str(documents[0]["id"]),
    ]


@responses.activate
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_api_documents_search_ordering_by_title_across_languages(settings, direction):
    """Titles should be sorted together whatever their language, ignoring accents."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    titles = [
        "Apfelbäume blühen im Frühling auf der Wiese",
        "Écureuils roux dans la forêt de Fontainebleau",
        "Elephants are walking slowly in the dry grassland",
        "Zèbres et girafes de la savane africaine",
    ]
    documents = bulk_create_documents(
        [{"title": title, "content": title} for title in reversed(titles)]
    )
    prepare_index(service.index_name, documents)

    # The titles are indexed under different languages
    hits = opensearch_client().search(index=service.index_name)["hits"]["hits"]
    assert {
        key for hit in hits for key in hit["_source"] if key.startswith("title.")
    } == {
        "title.de",
        "title.en",
        "title.fr",
    }

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "order_by": "title", "order_direction": direction},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    expected = titles if direction == "asc" else list(reversed(titles))
    assert [r["title"] for r in response.json()["results"]] == expected


@responses.activate
def test_api_documents_search_ordering_by_relevance(settings):
    """It should be possible to order by relevance (score)"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "wolf dog", "content": "wolfdogs are wolves crossed with dogs"},
        ]
    )
    prepare_index(service.index_name, documents)

    for direction in ["asc", "desc"]:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {
                "q": "wolves dogs",
                "order_by": "relevance",
                "order_direction": direction,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        data = response.json()["results"]
        assert len(data) == 3

        # Check that results are sorted by score as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(data) - 1):
            assert compare(data[i]["score"], data[i + 1]["score"])


@responses.activate
def test_api_documents_search_ordering_by_unknown_field(settings):
    """Trying to sort by an unknown field should return a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    for direction in ["asc", "desc"]:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "order_by": "unknown", "order_direction": direction},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {
                "loc": ["order_by"],
                "msg": (
                    "Input should be 'relevance', 'title', 'created_at', "
                    "'updated_at', 'size' or 'reach'"
                ),
                "type": "literal_error",
            }
        ]


@responses.activate
def test_api_documents_search_ordering_by_unknown_direction(settings):
    """Trying to sort with an unknown direction should return a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    for field in enums.ORDER_BY_OPTIONS:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "order_by": field, "order_direction": "unknown"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {
                "loc": ["order_direction"],
                "msg": "Input should be 'asc' or 'desc'",
                "type": "literal_error",
            }
        ]


@responses.activate
def test_api_documents_search_filtering_by_reach(settings):
    """It should be possible to filter results by their reach"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = {
        reach: factories.DocumentSchemaFactory.build_batch(
            2, reach=reach, users=["user_sub"]
        )
        for reach in enums.ReachEnum
    }
    prepare_index(service.index_name, sum(documents.values(), []))

    for reach, reach_documents in documents.items():
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "reach": reach.value},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        assert sorted(r["id"] for r in response.json()["results"]) == sorted(
            doc["id"] for doc in reach_documents
        )


@responses.activate
def test_api_documents_search_with_nb_results(settings):
    """nb_size should correctly return results of given size"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        9, reach=random.choice(["public", "authenticated"])
    )
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.index_name, documents)

    # nb_results > total number of documents => returns all documents
    for nb_results, expected_ids in [(3, ids[0:3]), (6, ids[0:6]), (10, ids)]:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "nb_results": nb_results, "visited": ids},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        assert [r["id"] for r in response.json()["results"]] == expected_ids


@responses.activate
def test_api_documents_search_nb_results_default(settings):
    """At most 50 results should be returned by default"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(51, users=["user_sub"])
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 50


@responses.activate
def test_api_documents_search_nb_results_invalid_parameters(settings):
    """Invalid nb_results parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    parameters = [
        (
            "invalid",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (-1, "greater_than_equal", "Input should be greater than or equal to 1"),
        (0, "greater_than_equal", "Input should be greater than or equal to 1"),
        (350, "less_than_equal", "Input should be less than or equal to 300"),
    ]

    for nb_results, error_type, error_message in parameters:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "nb_results": nb_results},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {"loc": ["nb_results"], "msg": error_message, "type": error_type}
        ]


@responses.activate
def test_api_documents_search_nb_results_with_filtering(settings):
    """nb_results should work correctly when combined with filtering by reach"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    public_documents = factories.DocumentSchemaFactory.build_batch(3, reach="public")
    public_ids = [str(doc["id"]) for doc in public_documents]
    private_documents = factories.DocumentSchemaFactory.build_batch(
        2, reach="authenticated"
    )
    prepare_index(service.index_name, public_documents + private_documents)

    nb_results = 2
    response = Client().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "reach": "public",
            "nb_results": nb_results,
            "visited": public_ids + [str(doc["id"]) for doc in private_documents],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == public_ids[0:nb_results]


@responses.activate
def test_api_documents_search_filtering_by_tags(settings):
    """Documents matching any of the given tags should be returned"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {
                "title": "Python document",
                "content": "About Python",
                "tags": ["python", "programming"],
            },
            {
                "title": "JavaScript document",
                "content": "About JavaScript",
                "tags": ["javascript", "programming"],
            },
            {
                "title": "Rust document",
                "content": "About Rust",
                "tags": ["rust", "programming"],
            },
            {
                "title": "Untagged document",
                "content": "No tags here",
                "tags": [],
            },
        ]
    )

    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "tags": ["python"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [str(documents[0]["id"])]
    assert response.json()["results"][0]["tags"] == ["python", "programming"]

    # Several tags are combined with OR, also as a comma-separated string
    for tags in [["python", "rust"], "python,rust"]:
        response = Client().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "tags": tags},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        assert sorted(r["id"] for r in response.json()["results"]) == sorted(
            [str(documents[0]["id"]), str(documents[2]["id"])]
        )

    # Without tags filter, all documents are returned
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 4


@responses.activate
def test_api_documents_search_filtering_by_path(settings):
    """Test filtering documents by path prefix via API"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {"title": "Document 1", "content": "Content", "path": "/path/to/doc1"},
            {"title": "Document 2", "content": "Content", "path": "/path/to/doc2"},
            {"title": "Document 3", "content": "Content", "path": "other/path/to/doc3"},
        ]
    )

    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "path": "/path/to/"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert sorted(r["id"] for r in response.json()["results"]) == sorted(
        [str(documents[0]["id"]), str(documents[1]["id"])]
    )
