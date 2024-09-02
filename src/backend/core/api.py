"""Impress core API endpoints"""

from django.core.exceptions import ValidationError

from pydantic import ValidationError as PydanticValidationError
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework import views as drf_views
from rest_framework.response import Response


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
