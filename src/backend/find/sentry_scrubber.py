"""Sentry event scrubbing — strips Authorization headers, request bodies, and
token-bearing query params before events are sent.

Imported by find.settings.Base.post_setup at module load. MUST NOT import any
Django module at top-level — only stdlib.
"""

import re
from typing import Optional

_TOKEN_PARAM_RE = re.compile(
    r"(?i)(token|api_?key|access_token|id_token|refresh_token)=[^&]*"
)


def before_send(
    event: Optional[dict],
    hint: dict,  # pylint: disable=unused-argument
) -> Optional[dict]:
    """Sentry before_send hook. Removes secrets from outgoing events."""
    if event is None:
        return None
    request = event.get("request")
    if not isinstance(request, dict):
        return event
    # Strip Authorization header
    headers = request.get("headers")
    if isinstance(headers, dict) and "Authorization" in headers:
        headers.pop("Authorization", None)
    # Always replace request.data — multipart-safe
    if "data" in request:
        request["data"] = "[Filtered]"
    # Redact known token-bearing query params (preserves other params)
    qs = request.get("query_string")
    if isinstance(qs, str):
        request["query_string"] = _TOKEN_PARAM_RE.sub(r"\1=[Filtered]", qs)
    return event
