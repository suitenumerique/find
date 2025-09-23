"""Test pydantic models & helpers"""

import pytest

from core.schemas import cleanlist


def test_cleanlist_empty():
    """Empty data should return an empty list"""
    assert cleanlist(None) == []
    assert cleanlist([]) == []
    assert cleanlist("") == []


def test_cleanlist_error():
    """Invalid data should raise"""
    with pytest.raises(ValueError):
        cleanlist(123)


def test_cleanlist():
    """Should return a list of stripped strings and remove the empty items"""
    assert cleanlist([1, 2, 3]) == ["1", "2", "3"]
    assert cleanlist("  1,  2,3   ") == ["1", "2", "3"]
    assert cleanlist(["1 ", "  2", "3 "]) == ["1", "2", "3"]
    assert cleanlist([None, 2, 3, ""]) == ["2", "3"]
