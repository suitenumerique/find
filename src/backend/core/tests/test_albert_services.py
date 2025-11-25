"""Tests albert AI service"""

from io import BytesIO
from json import dumps as json_dumps
from unittest import mock

import pytest
import responses

from core.services import albert
from core.tests.mock import albert_embedding_response
from core.tests.utils import (
    enable_hybrid_search,
)

pytestmark = pytest.mark.django_db


@responses.activate
def test_albert_service_embedding(settings):
    """Should return the embedding vector from Albert API"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    assert (
        albert.AlbertAI().embedding("any text")
        == (albert_embedding_response.response["data"][0]["embedding"])
    )

    responses.assert_call_count(settings.EMBEDDING_API_PATH, 1)

    assert (
        responses.calls[0].request.body
        == json_dumps(
            {
                "input": "any text",
                "model": settings.EMBEDDING_API_MODEL_NAME,
                "dimensions": settings.EMBEDDING_DIMENSION,
                "encoding_format": "float",
            }
        ).encode()
    )


@responses.activate
def test_albert_service_embedding__arguments(settings):
    """Should return the embedding vector from Albert API with custom arguments"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    assert (
        albert.AlbertAI().embedding("any text", dimensions=123, model="mymodel")
        == (albert_embedding_response.response["data"][0]["embedding"])
    )

    responses.assert_call_count(settings.EMBEDDING_API_PATH, 1)

    assert (
        responses.calls[0].request.body
        == json_dumps(
            {
                "input": "any text",
                "model": "mymodel",
                "dimensions": 123,
                "encoding_format": "float",
            }
        ).encode()
    )


def test_albert_service_embedding__not_configured(settings):
    """Should raise if not configured"""
    settings.EMBEDDING_API_PATH = ""

    with pytest.raises(albert.AlbertAIError):
        albert.AlbertAI().embedding("any text")


@responses.activate
def test_albert_service_embedding__unexpected_content(settings):
    """Should raise if the API response is invalid"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        body="invalid !!",
        status=200,
    )

    with pytest.raises(albert.AlbertAIError) as err:
        albert.AlbertAI().embedding("any text")

    assert err.value.message == "Unexpected content : invalid !!"


@responses.activate
def test_albert_service_embedding__invalid_response(settings):
    """Should raise if the API returned error"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json={"detail": "Invalid request"},
        status=400,
    )

    with pytest.raises(albert.AlbertAIError) as err:
        albert.AlbertAI().embedding("any text")

    assert err.value.message == "Invalid request"


@pytest.mark.parametrize(
    "content",
    [
        "PDF content",
        b"PDF content",
        BytesIO(b"PDF content"),
    ],
)
@responses.activate
def test_albert_service_convert(settings, content):
    """Should return a converted PDF from Albert API"""
    settings.ALBERT_PARSE_ENDPOINT = "https://test.albert.api/v1/parse"

    responses.add(
        responses.POST,
        settings.ALBERT_PARSE_ENDPOINT,
        json={
            "data": [
                {"content": "Markdown line 1"},
                {"content": "Markdown line 2"},
            ]
        },
        status=200,
    )

    assert albert.AlbertAI().convert(content) == ("Markdown line 1\nMarkdown line 2")

    responses.assert_call_count(settings.ALBERT_PARSE_ENDPOINT, 1)


def test_albert_service_convert__arguments(settings):
    """Should return a converted PDF from Albert API"""
    settings.ALBERT_PARSE_ENDPOINT = "https://test.albert.api/v1/parse"

    with mock.patch("core.services.albert.AlbertAI._request_api") as mock_api:
        content = BytesIO(b"PDF content")

        assert albert.AlbertAI().convert(content, pages=5, output="json") == ""

    mock_api.assert_called_once()
    assert mock_api.call_args == mock.call(
        "https://test.albert.api/v1/parse",
        files={
            "file": ("input", content, "application/pdf"),
        },
        data={
            "output_format": "json",
            "page_range": "0-5",
        },
    )


def test_albert_service_convert__not_configured(settings):
    """Should raise if not configured"""
    settings.ALBERT_PARSE_ENDPOINT = ""

    with pytest.raises(albert.AlbertAIError):
        albert.AlbertAI().convert(BytesIO(b"PDF content"))


@responses.activate
def test_albert_service_convert__unexpected_content(settings):
    """Should raise if the API response is invalid"""
    settings.ALBERT_PARSE_ENDPOINT = "https://test.albert.api/v1/parse"

    responses.add(
        responses.POST,
        settings.ALBERT_PARSE_ENDPOINT,
        body="invalid !!",
        status=200,
    )

    with pytest.raises(albert.AlbertAIError) as err:
        albert.AlbertAI().convert(BytesIO(b"PDF content"))

    assert err.value.message == "Unexpected content : invalid !!"


@responses.activate
def test_albert_service_convert__invalid_response(settings):
    """Should raise if the API returned error"""
    settings.ALBERT_PARSE_ENDPOINT = "https://test.albert.api/v1/parse"

    responses.add(
        responses.POST,
        settings.ALBERT_PARSE_ENDPOINT,
        json={"detail": "Invalid request"},
        status=400,
    )

    with pytest.raises(albert.AlbertAIError) as err:
        albert.AlbertAI().convert(BytesIO(b"PDF content"))

    assert err.value.message == "Invalid request"
