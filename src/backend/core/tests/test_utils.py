"""Unit tests for core.utils module"""

import pytest

from core.utils import extract_language_code


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
