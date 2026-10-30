"""
Test suite for opensearch indexing service
"""

import threading
from unittest import mock
from uuid import UUID

import pytest
from opensearchpy import NotFoundError

from core import factories, schemas
from core.models import get_opensearch_index_name
from core.services import indexing
from core.services.indexing import (
    aensure_index_exists,
    bulk_index_documents,
    detect_language_code,
    ensure_index_exists,
    index_document,
)
from core.services.opensearch import opensearch_client, run_async

SERVICE_NAME = "test-service"


@pytest.mark.parametrize(
    "text, analyzer_name, expected_language_analyzer_tokens, expected_trigram_analyzer_tokens",
    [
        (
            "l'éléphant a couru avec les Gens",
            "french_analyzer",
            # lowercase is applied ("Gens" -> "gens")
            # asciifolding is applied ("éléphant" -> "elephant")
            # stop words are removed ('avec', 'les')
            # elisions are removed ("l'")
            # stemming is applied ("gens" -> "gen")
            ["elephant", "a", "couru", "gen"],
            # lowercase is applied ("Gens" -> "gens")
            # asciifolding is applied ("éléphant" -> "elephant")
            # words smaller than 3 characters are removed ("a")
            # trigrams are generated
            [
                "l'e",
                "'el",
                "ele",
                "lep",
                "eph",
                "pha",
                "han",
                "ant",
                "cou",
                "our",
                "uru",
                "ave",
                "vec",
                "les",
                "gen",
                "ens",
            ],
        ),
        (
            "The Elephant is running into a café",
            "english_analyzer",
            # lowercase is applied ("Elephant" -> "elephant")
            # asciifolding is applied ("café" -> "cafe")
            # stop words are removed ("The", "into", "a")
            # stemming is applied ("running" -> "run", "elephant" -> "eleph")
            ["eleph", "run", "cafe"],
            # lowercase is applied ("Gens" -> "gens")
            # asciifolding is applied ("café" -> "cafe")
            # trigrams are generated
            # words smaller than 3 characters are removed ("a")
            [
                "the",
                "ele",
                "lep",
                "eph",
                "pha",
                "han",
                "ant",
                "run",
                "unn",
                "nni",
                "nin",
                "ing",
                "int",
                "nto",
                "caf",
                "afe",
            ],
        ),
        (
            "Der Käfer läuft über die Straße",
            "german_analyzer",
            # lowercase is applied ("Der" -> "der", "Käfer" -> "käfer", "Straße" -> "straße")
            # asciifolding is applied ("käfer" -> "kafer", "straße" -> "strass")
            # stop words are removed ("Der", "die")
            # stemming is applied ("kafer" -> "kaf")
            ["kaf", "lauft", "uber", "strass"],
            # lowercase is applied
            # asciifolding is applied ("käfer" -> "kafer", "straße" -> "strasse")
            # trigrams are generated
            [
                "der",
                "kaf",
                "afe",
                "fer",
                "lau",
                "auf",
                "uft",
                "ube",
                "ber",
                "die",
                "str",
                "tra",
                "ras",
                "ass",
                "sse",
            ],
        ),
        (
            "De Kinderen lopen naar de bakkerij",
            "dutch_analyzer",
            # lowercase is applied ("De" -> "de", "Kinderen" -> "kinderen")
            # stop words are removed ("De", "naar", "de")
            # stemming is applied ("kinderen" -> "kinder", "lopen" -> "lop")
            ["kinder", "lop", "bakkerij"],
            # lowercase is applied
            # words smaller than 3 characters are removed ("de")
            # trigrams are generated
            [
                "kin",
                "ind",
                "nde",
                "der",
                "ere",
                "ren",
                "lop",
                "ope",
                "pen",
                "naa",
                "aar",
                "bak",
                "akk",
                "kke",
                "ker",
                "eri",
                "rij",
            ],
        ),
    ],
)
def test_opensearch_analyzers(
    text,
    analyzer_name,
    expected_language_analyzer_tokens,
    expected_trigram_analyzer_tokens,
):
    """Test the analyzers are correctly configured in OpenSearch"""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    ensure_index_exists(index_name)

    language_analyzer_response = opensearch_client().indices.analyze(
        index=index_name,
        body={
            "analyzer": analyzer_name,
            "text": text,
        },
    )
    language_analyzer_tokens = [
        token_info["token"] for token_info in language_analyzer_response["tokens"]
    ]
    response_trigram_analyzer = opensearch_client().indices.analyze(
        index=index_name,
        body={
            "analyzer": "trigram_analyzer",
            "text": text,
        },
    )
    trigram_analyzer_tokens = [
        token_info["token"] for token_info in response_trigram_analyzer["tokens"]
    ]

    assert expected_language_analyzer_tokens == language_analyzer_tokens
    assert expected_trigram_analyzer_tokens == trigram_analyzer_tokens


@pytest.mark.parametrize(
    "text, expected_language_code",
    [
        ("This is a test sentence.", "en"),
        ("Ceci est une phrase de test.", "fr"),
        ("Dies ist ein Testsatz.", "de"),
        ("Dit is een testzin.", "nl"),
        ("Esta es una oración de prueba.", "und"),  # Spanish, unsupported
        ("", "und"),
        ("zefk,l", "und"),
    ],
)
def test_detect_language_code(text, expected_language_code):
    """Test detect_language_code function"""

    assert detect_language_code(text) == expected_language_code


def test_aensure_index_exists():
    """The index should be created with Find's mappings, only if it does not exist."""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    with pytest.raises(NotFoundError):
        opensearch_client().indices.get(index=index_name)

    run_async(aensure_index_exists, index_name)
    run_async(aensure_index_exists, index_name)

    properties = opensearch_client().indices.get_mapping(index=index_name)[index_name][
        "mappings"
    ]["properties"]
    assert properties["content"]["properties"]["fr"]["analyzer"] == "french_analyzer"
    assert properties["users"] == {"type": "keyword"}


def test_index_document():
    """A validated document should be indexed with language-suffixed fields."""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    document = schemas.DocumentSchema(
        **factories.DocumentSchemaFactory.build(
            title="The quick brown fox", content="jumps over the lazy dog"
        )
    )

    _id = run_async(index_document, index_name, document)

    assert _id == document.id
    source = opensearch_client().get(index=index_name, id=str(_id))["_source"]
    assert source["title.en"] == "the quick brown fox"
    assert source["content.en"] == "jumps over the lazy dog"
    assert "id" not in source


def test_bulk_index_documents():
    """All the documents should be indexed and reported as successful."""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    documents = factories.DocumentSchemaFactory.build_batch(2)

    results, has_errors = run_async(bulk_index_documents, index_name, documents)

    assert has_errors is False
    assert results == [
        {"index": 0, "_id": UUID(documents[0]["id"]), "status": "success"},
        {"index": 1, "_id": UUID(documents[1]["id"]), "status": "success"},
    ]
    opensearch_client().indices.refresh(index=index_name)
    assert opensearch_client().count(index=index_name)["count"] == 2


def test_bulk_index_documents_validation_error():
    """Nothing should be indexed, nor the index created, if a document is invalid."""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    valid, invalid = factories.DocumentSchemaFactory.build_batch(2)
    invalid["size"] = -1

    results, has_errors = run_async(bulk_index_documents, index_name, [valid, invalid])

    assert has_errors is True
    assert results[0] == {"index": 0, "_id": UUID(valid["id"]), "status": "valid"}
    assert results[1]["status"] == "error"
    assert [error["loc"] for error in results[1]["errors"]] == [("size",)]
    with pytest.raises(NotFoundError):
        opensearch_client().indices.get(index=index_name)


def test_bulk_index_documents_language_detection_off_event_loop():
    """Validation and language detection should not run in the event loop thread."""
    index_name = get_opensearch_index_name(SERVICE_NAME)
    threads = []
    prepare = indexing.prepare_document_for_indexing

    def recording_prepare(document):
        threads.append(threading.get_ident())
        return prepare(document)

    async def bulk_index():
        loop_threads.append(threading.get_ident())
        return await bulk_index_documents(
            index_name, factories.DocumentSchemaFactory.build_batch(2)
        )

    loop_threads = []
    with mock.patch.object(
        indexing, "prepare_document_for_indexing", side_effect=recording_prepare
    ):
        run_async(bulk_index)

    assert len(threads) == 2
    assert loop_threads[0] not in threads
