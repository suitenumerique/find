"""Bolt authentication backends for OIDC."""

from __future__ import annotations

from functools import cache
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from asgiref.sync import sync_to_async
from django_bolt.auth.backends import BaseAuthentication

from .authentication import ResourceUser


@cache
def _get_resource_server_backend():
    """Return the resource server backend instance based on settings."""
    backend_class = import_string(settings.OIDC_RS_BACKEND_CLASS)
    return backend_class()


class OIDCAuthentication(BaseAuthentication):
    """
    OIDC authentication backend for Bolt.

    Validates JWT tokens from the Authorization header using django-lasuite's
    ResourceServerBackend for token introspection. Returns a context dict with
    user claims on success, None on failure (does not raise exceptions).

    This backend wraps lasuite's OIDC resource server to integrate with Bolt's
    authentication system while reusing all existing JWT validation logic.
    """

    @property
    def scheme_name(self) -> str:
        """Return the authentication scheme name."""
        return "oidc"

    def to_metadata(self) -> dict[str, Any]:
        """
        Compile this authentication backend into metadata for Rust.

        Note: OIDC token validation happens in Python (get_user) since it
        requires HTTP introspection to the OIDC provider. The metadata just
        describes the auth type and header configuration.
        """
        return {
            "type": "oidc",
            "header": "authorization",
            "algorithms": [getattr(settings, "OIDC_RS_SIGNING_ALGO", "ES256")],
            "audience": getattr(settings, "OIDC_RS_CLIENT_ID", None),
        }

    async def get_user(
        self, user_id: str | None, auth_context: dict[str, Any]
    ) -> ResourceUser | None:
        auth_header = auth_context.get("authorization") or auth_context.get(
            "auth_header"
        )
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        access_token = parts[1]
        if not access_token:
            return None

        backend = _get_resource_server_backend()
        try:
            user_info = await sync_to_async(backend.get_user_info_with_introspection)(
                access_token
            )
            user = await sync_to_async(backend.get_or_create_user)(
                access_token, None, user_info
            )
        except Exception:
            return None

        if not user:
            return None

        user.token_audience = backend.token_origin_audience
        return user
