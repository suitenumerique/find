"""Tests for compute_content_hash function."""

from core.services.indexing import compute_content_hash


def test_compute_content_hash_deterministic():
    """Same input should always produce the same hash."""
    title = "Test Document"
    content = "This is test content"

    hash1 = compute_content_hash(title, content)
    hash2 = compute_content_hash(title, content)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest is 64 characters


def test_compute_content_hash_different_inputs():
    """Different inputs should produce different hashes."""
    hash1 = compute_content_hash("Title 1", "Content 1")
    hash2 = compute_content_hash("Title 2", "Content 2")
    hash3 = compute_content_hash("Title 1", "Content 2")

    assert hash1 != hash2
    assert hash1 != hash3
    assert hash2 != hash3


def test_compute_content_hash_empty_title():
    """Empty title with content should produce a valid hash."""
    title = ""
    content = "This is test content"

    hash_result = compute_content_hash(title, content)

    assert len(hash_result) == 64
    assert hash_result == compute_content_hash("", content)


def test_compute_content_hash_empty_content():
    """Title with empty content should produce a valid hash."""
    title = "Test Document"
    content = ""

    hash_result = compute_content_hash(title, content)

    assert len(hash_result) == 64
    assert hash_result == compute_content_hash(title, "")


def test_compute_content_hash_no_collision():
    """Null separator should prevent collisions between different title/content combinations."""
    hash1 = compute_content_hash("hello", "world")
    hash2 = compute_content_hash("hellow", "orld")

    assert hash1 != hash2
