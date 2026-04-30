"""Unit tests for core.utils module"""

import pytest

from core.utils import extract_language_code, get_language_value


def test_extract_language_code_english():
    """Test extract_language_code with English document"""
    document = {
        "title.en": "English Title",
        "content.en": "English Content",
        "other_field": "value",
    }

    language_code = extract_language_code(document)

    assert language_code == "en"


def test_extract_language_code_no_title():
    """Test extract_language_code when no title field exists"""
    document = {
        "id": "123",
        "other_field": "value",
    }

    with pytest.raises(ValueError) as exc:
        extract_language_code(document)

    assert str(exc.value) == "No supported language code in source"


def test_get_language_value_english():
    """Test get_language_value with English field"""
    source = {
        "title.en": "English Title",
        "content.en": "English Content",
        "other_field": "value",
    }

    assert get_language_value(source, "title") == "English Title"
    assert get_language_value(source, "content") == "English Content"


def test_get_language_value_french():
    """Test get_language_value with French field"""
    source = {
        "title.fr": "Titre français",
        "content.fr": "Contenu français",
    }

    assert get_language_value(source, "title") == "Titre français"
    assert get_language_value(source, "content") == "Contenu français"


def test_get_language_value_no_field():
    """Test get_language_value when field doesn't exist"""
    source = {
        "id": "123",
        "other_field": "value",
    }

    with pytest.raises(ValueError) as exc_info:
        get_language_value(source, "title")

    assert "No 'title' field with any supported language code" in str(exc_info.value)
