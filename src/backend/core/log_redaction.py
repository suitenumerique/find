"""Helpers for scrubbing sensitive data from log records."""

import hashlib


def redact_search_query(q: str) -> str:
    """Return a length-and-hash summary that is safe to log.

    Uses SHA-256 truncated to 8 hex chars: irreversible for non-trivial inputs,
    deterministic so identical queries correlate across log lines.
    """
    digest = hashlib.sha256(q.encode("utf-8")).hexdigest()[:8]
    return f"len={len(q)} hash={digest}"
