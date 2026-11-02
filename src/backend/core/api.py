"""Find API, with the error responses of its endpoints."""

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation

from ninja import NinjaAPI
from ninja.errors import ValidationError as NinjaValidationError
from ninja.renderers import BaseRenderer
from pydantic_core import to_json

from .schemas import format_validation_errors
from .services.menshen import MenshenUnavailable
from .views import router

logger = logging.getLogger(__name__)


class PydanticJSONRenderer(BaseRenderer):
    """
    Render responses as Pydantic serializes them to JSON. Unlike ninja's default
    renderer, datetimes keep their microseconds.
    """

    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return to_json(data)


api = NinjaAPI(
    title="Find API",
    version=settings.API_VERSION,
    description="Index documents of La Suite services and search them.",
    docs_url=settings.API_DOCS_URL if settings.API_DOCS_ENABLED else None,
    openapi_url=settings.API_OPENAPI_URL if settings.API_OPENAPI_ENABLED else None,
    renderer=PydanticJSONRenderer(),
)
api.add_router("documents/", router, tags=["documents"])


@api.exception_handler(NinjaValidationError)
def validation_error(request, exc):
    """
    Answer the request parameters that failed validation with a 400, as validation
    errors of the request body itself: ninja locates them as ("body", <parameter>, ...).
    """
    return api.create_response(
        request, format_validation_errors(exc.errors, loc_start=2), status=400
    )


@api.exception_handler(SuspiciousOperation)
def suspicious_operation(request, exc):
    """Answer requests for services the caller may not use with a 400."""
    logger.error(exc)
    return api.create_response(request, {"detail": "Invalid request."}, status=400)


@api.exception_handler(PermissionDenied)
def permission_denied(request, exc):
    """Answer requests whose token grants no applicable scope with a 403."""
    logger.warning(exc)
    return api.create_response(
        request,
        {"detail": "You do not have permission to perform this action."},
        status=403,
    )


@api.exception_handler(MenshenUnavailable)
def menshen_unavailable(request, _exc):
    """Answer with a 503 when Menshen cannot tell whether a token is valid."""
    return api.create_response(
        request,
        {"detail": "The authentication service is unavailable."},
        status=503,
    )
