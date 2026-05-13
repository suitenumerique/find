"""Impress core API endpoints"""

import logging
from http import HTTPStatus

from django.core.exceptions import ValidationError

from opensearchpy.exceptions import NotFoundError as OpenSearchNotFoundError
from pydantic import ValidationError as PydanticValidationError
from rest_framework import views as drf_views
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def problem_details_response(status_code: int, detail: str) -> Response:
    """Create an RFC 9457 Problem Details response.

    Args:
        status_code: HTTP status code (e.g., 400, 401, 503)
        detail: Human-readable explanation of the error

    Returns:
        Response with application/problem+json content type and RFC 9457 body
    """
    return Response(
        {
            "type": "about:blank",
            "title": HTTPStatus(status_code).phrase,
            "status": status_code,
            "detail": detail,
        },
        status=status_code,
        content_type="application/problem+json",
    )


def exception_handler(exc, context):
    """Handle exceptions and return RFC 9457 Problem Details responses.

    Converts all exceptions to RFC 9457 format with exactly 4 fields:
    type, title, status, detail.
    """
    if isinstance(exc, ValidationError):
        return problem_details_response(400, "Validation failed")

    if isinstance(exc, PydanticValidationError):
        return problem_details_response(400, "Validation failed")

    if isinstance(exc, OpenSearchNotFoundError):
        logger.exception("OpenSearch index not found")
        return problem_details_response(503, "Service temporarily unavailable")

    # Let DRF handle known HTTP exceptions (401, 403, 404, etc.)
    response = drf_views.exception_handler(exc, context)
    if response is not None:
        detail = (
            response.data.get("detail", "An error occurred")
            if isinstance(response.data, dict)
            else "An error occurred"
        )
        return problem_details_response(response.status_code, detail)

    # Unhandled exception - log and return generic 500
    logger.exception("Unhandled exception")
    return problem_details_response(500, "Internal server error")
