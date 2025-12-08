"""
Test suite for opensearch indexing service
"""

import pytest
import responses

from core.services.indexing import detect_language_code, ensure_index_exists
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client

from .mock import albert_embedding_response
from .utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
)
from .utils import (
    enable_hybrid_search,
)

pytestmark = pytest.mark.django_db


SERVICE_NAME = "test-service"


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches before each test"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear caches used in opensearch service and factories"""
    check_hybrid_search_enabled.cache_clear()
    # the instance of check_hybrid_search_enabled used in utils.py
    # is different and must be cleared separately
    check_hybrid_search_enabled_utils.cache_clear()
    opensearch_client().indices.delete(index="*")


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
@responses.activate
def test_opensearch_analyzers(
    settings,
    text,
    analyzer_name,
    expected_language_analyzer_tokens,
    expected_trigram_analyzer_tokens,
):
    """Test the analyzers are correctly configured in OpenSearch"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    ensure_index_exists(SERVICE_NAME)

    language_analyzer_response = opensearch_client().indices.analyze(
        index=SERVICE_NAME,
        body={
            "analyzer": analyzer_name,
            "text": text,
        },
    )
    language_analyzer_tokens = [
        token_info["token"] for token_info in language_analyzer_response["tokens"]
    ]
    response_trigram_analyzer = opensearch_client().indices.analyze(
        index=SERVICE_NAME,
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
