"""Tests for the settings of the API documentation"""

import importlib

import pytest

from core import api as api_module
from core.api import api


def test_api_docs_urls_disabled_by_default():
    """The API documentation urls should be disabled by default."""
    assert api.docs_url is None
    assert api.openapi_url is None


@pytest.mark.parametrize(
    ("docs_enabled", "openapi_enabled", "expected_docs_url", "expected_openapi_url"),
    [
        (False, False, None, None),
        (True, True, "/docs", "/openapi.json"),
        (False, True, None, "/openapi.json"),
        (True, False, "/docs", None),
    ],
)
def test_api_docs_urls_settings(
    settings, docs_enabled, openapi_enabled, expected_docs_url, expected_openapi_url
):
    """The API documentation urls should depend on the docs settings."""
    settings.API_DOCS_ENABLED = docs_enabled
    settings.API_OPENAPI_ENABLED = openapi_enabled

    api_instance = importlib.reload(api_module).api

    assert api_instance.docs_url == expected_docs_url
    assert api_instance.openapi_url == expected_openapi_url


@pytest.mark.parametrize(
    ("docs_url", "openapi_url"),
    [
        ("/api-docs", "/schema.json"),
        (None, "/openapi.json"),
        ("/docs", None),
        (None, None),
    ],
)
def test_api_docs_urls_custom(settings, docs_url, openapi_url):
    """The API documentation urls should depend on the urls settings."""
    settings.API_DOCS_ENABLED = docs_url is not None
    settings.API_OPENAPI_ENABLED = openapi_url is not None
    settings.API_DOCS_URL = docs_url or "/docs"
    settings.API_OPENAPI_URL = openapi_url or "/openapi.json"

    api_instance = importlib.reload(api_module).api

    assert api_instance.docs_url == docs_url
    assert api_instance.openapi_url == openapi_url


def test_api_docs_urls_should_differ(settings):
    """The docs url should be different from the openapi url."""
    settings.API_DOCS_ENABLED = True
    settings.API_OPENAPI_ENABLED = True
    settings.API_DOCS_URL = "/docs"
    settings.API_OPENAPI_URL = "/docs"

    with pytest.raises(
        AssertionError, match="Please use different urls for openapi_url and docs_url"
    ):
        _ = importlib.reload(api_module).api.urls
