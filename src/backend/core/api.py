"""Find API, with the error responses of its endpoints."""

import logging

from django.conf import settings
from django.core.exceptions import (
    PermissionDenied,
    SuspiciousOperation,
    ValidationError,
)

from ninja import NinjaAPI
from ninja.errors import ValidationError as NinjaValidationError
from ninja.renderers import BaseRenderer
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import to_json
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework import views as drf_views
from rest_framework.response import Response

from .schemas import format_validation_errors
from .services.menshen import MenshenUnavailable

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


def exception_handler(exc, context):
    """Handle Django ValidationError as an accepted exception.

    For the parameters, see ``exception_handler``
    This code comes from twidi's gist:
    https://gist.github.com/twidi/9d55486c36b6a51bdcb05ce3a763e79f
    """
    if isinstance(exc, ValidationError):
        detail = exc.message_dict

        if hasattr(exc, "message"):
            detail = exc.message
        elif hasattr(exc, "messages"):
            detail = exc.messages
        exc = drf_exceptions.ValidationError(detail=detail)

    elif isinstance(exc, PydanticValidationError):
        return Response(
            [
                {key: error[key] for key in ("msg", "type", "loc")}
                for error in exc.errors()
            ],
            status=status.HTTP_400_BAD_REQUEST,
        )

    return drf_views.exception_handler(exc, context)
