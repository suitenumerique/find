"""
Test suite for searching documents in OpenSearch over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import operator
import random

from django.test import Client

import pytest

from core import enums, factories
from core.services.opensearch import opensearch_client
from core.utils import prepare_index

from .utils import (
    MENSHEN_INTROSPECTION_URL,
    build_authorization_bearer,
    bulk_create_documents,
    setup_menshen,
    setup_menshen_introspection,
)

pytestmark = pytest.mark.django_db


def test_api_documents_search_inactive_token(settings, httpx2_mock):
    """A token that Menshen reports as inactive should be rejected."""
    setup_menshen_introspection(httpx2_mock, settings, active=False)
    factories.ServiceFactory(name="docs")

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_search_menshen_unavailable(settings, httpx2_mock):
    """A 503 should be returned when Menshen cannot introspect the token."""
    setup_menshen(settings)
    httpx2_mock.add_response(
        method="POST", url=MENSHEN_INTROSPECTION_URL, status_code=500
    )
    factories.ServiceFactory(name="docs")

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "The authentication service is unavailable."}


def test_api_documents_search_without_search_scope(settings, httpx2_mock):
    """A token granting no find search scope should get a 403."""
    setup_menshen_introspection(httpx2_mock, settings, scope="openid find:docs:delete")
    factories.ServiceFactory(name="docs")

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to perform this action."
    }


def test_api_documents_search_unknown_service_scope(settings, httpx2_mock):
    """A search scope naming no registered service should result in a 403."""
    setup_menshen_introspection(httpx2_mock, settings, scope="find:unknown:search")
    factories.ServiceFactory(name="docs")

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have permission to perform this action."
    }


def test_api_documents_search_query_missing(settings, httpx2_mock):
    """The "q" parameter is required."""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_services_invalid_parameters(settings, httpx2_mock):
    """Invalid services parameter should result in a 400 error"""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_visited_invalid_parameters(settings, httpx2_mock):
    """Invalid visited parameters should result in a 400 error"""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_match_all(settings, httpx2_mock):
    """Searching a document with q='*' should match all docs"""
    setup_menshen_introspection(httpx2_mock, settings)
    nb_documents = 12
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_full_text_query_title(settings, httpx2_mock):
    """Searching a document by its title should work as expected"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")

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


def test_api_documents_search_full_text_query_content(settings, httpx2_mock):
    """Searching a document by its content should work as expected"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")

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


def test_api_documents_search_full_text_query_trigrams(settings, httpx2_mock):
    """A partial word should match documents through trigrams"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")

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


def test_api_documents_search_ordering_by_fields(settings, httpx2_mock):
    """It should be possible to order by several fields"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_ordering_by_title(settings, httpx2_mock):
    """It should be possible to order by title"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_api_documents_search_ordering_by_title_across_languages(
    settings, httpx2_mock, direction
):
    """Titles should be sorted together whatever their language, ignoring accents."""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_ordering_by_title_ignores_case(settings, httpx2_mock):
    """Titles should be sorted case-insensitively, and returned with their case."""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
    titles = ["alpha", "Beta", "gamma", "Delta"]
    documents = bulk_create_documents(
        [{"title": title, "content": "content"} for title in titles]
    )
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "order_by": "title", "order_direction": "asc"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["title"] for r in response.json()["results"]] == [
        "alpha",
        "Beta",
        "Delta",
        "gamma",
    ]


def test_api_documents_search_title_case_kept_from_indexing(settings, httpx2_mock):
    """
    A title indexed through the API should be returned by the search as received,
    and found whatever the case of the query.
    """
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
    document = factories.DocumentSchemaFactory.build(
        title="  Rapport Annuel 2025  ",
        content="Bilan des activités de l'année",
        users=["user_sub"],
    )
    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )
    assert response.status_code == 201
    opensearch_client().indices.refresh(index=service.index_name)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "RAPPORT annuel"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert [r["title"] for r in response.json()["results"]] == ["Rapport Annuel 2025"]


def test_api_documents_search_ordering_by_relevance(settings, httpx2_mock):
    """It should be possible to order by relevance (score)"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_ordering_by_unknown_field(settings, httpx2_mock):
    """Trying to sort by an unknown field should return a 400 error"""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_ordering_by_unknown_direction(settings, httpx2_mock):
    """Trying to sort with an unknown direction should return a 400 error"""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_filtering_by_reach(settings, httpx2_mock):
    """It should be possible to filter results by their reach"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_with_nb_results(settings, httpx2_mock):
    """nb_size should correctly return results of given size"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_nb_results_default(settings, httpx2_mock):
    """At most 50 results should be returned by default"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_nb_results_invalid_parameters(settings, httpx2_mock):
    """Invalid nb_results parameters should result in a 400 error"""
    setup_menshen_introspection(httpx2_mock, settings)
    factories.ServiceFactory(name="docs")

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


def test_api_documents_search_nb_results_with_filtering(settings, httpx2_mock):
    """nb_results should work correctly when combined with filtering by reach"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")
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


def test_api_documents_search_filtering_by_tags(settings, httpx2_mock):
    """Documents matching any of the given tags should be returned"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")

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


def test_api_documents_search_filtering_by_path(settings, httpx2_mock):
    """Test filtering documents by path prefix via API"""
    setup_menshen_introspection(httpx2_mock, settings)
    service = factories.ServiceFactory(name="docs")

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
