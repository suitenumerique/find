"""Authentication of the API requests."""

import logging

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist

from lasuite.oidc_resource_server.backend import ResourceServerBackend
from ninja.errors import AuthenticationError, AuthorizationError
from ninja.security import HttpBearer
from rest_framework import authentication, exceptions

from .models import Service, hash_token
from .services.menshen import authenticate_token
from .services.service_tokens import get_service_by_token

logger = logging.getLogger(__name__)

NOT_PROVIDED = "Authentication credentials were not provided."


class MenshenBearer(HttpBearer):
    """
    Authenticate users with a bearer token exchanged with Menshen for Find (ADR-0001).
    `request.auth` is the MenshenUser of the token.
    """

    def __call__(self, request):
        scheme, _, token = request.headers.get(self.header, "").partition(" ")
        if scheme.lower() != self.openapi_scheme:
            raise AuthenticationError(message=NOT_PROVIDED)
        # RFC 6750 allows several spaces between the scheme and the token
        return self.authenticate(request, token.lstrip(" "))

    # Ninja awaits an async authenticate
    async def authenticate(self, request, token):  # pylint: disable=invalid-overridden-method
        """Introspect the token with Menshen, or use its cached introspection."""
        user = await authenticate_token(token)
        if user is None:
            raise AuthenticationError(message="Invalid token.")
        return user


class ServiceTokenBearer(HttpBearer):
    """
    Authenticate the services indexing their documents with their service token.
    `request.auth` is the Service owning the token.

    Errors are answered with a 403, as the API always did.
    """

    def __call__(self, request):
        header = request.headers.get(self.header)
        if not header:
            raise AuthorizationError(message=NOT_PROVIDED)
        # Extract the token if prefixed with a scheme, e.g. "Bearer"
        return self.authenticate(request, header.split(" ")[-1])

    # Ninja awaits an async authenticate
    async def authenticate(self, request, token):  # pylint: disable=invalid-overridden-method
        """Look up the active service owning the token."""
        service = await get_service_by_token(token)
        if service is None:
            raise AuthorizationError(message="Invalid token.")
        return service


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """A custom authentication looking for valid tokens among registered services"""

    model = Service

    def authenticate(self, request):
        """Authenticate token from the "Authorization" header."""
        token = request.headers.get("Authorization")
        if not token:
            raise exceptions.NotAuthenticated()

        token = token.split(" ")[-1]  # Extract token if prefixed with "Token"

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token):
        """Check that the token is registered and valid."""
        try:
            service = self.model.objects.only("name").get(
                token_hash=hash_token(token), is_active=True
            )
        except self.model.DoesNotExist as excpt:
            raise exceptions.AuthenticationFailed("Invalid token.") from excpt

        # We don't associate tokens with a user
        return AnonymousUser(), service


class ResourceUserManager:
    """Fake manager that simply returns an instance of user object with the right sub"""

    def get(self, sub):
        """Returns a ResourceUser for this sub"""
        return ResourceUser(sub=sub)


class ResourceUser:
    """Fake user model for the ResourceServerBackend.get_object() method"""

    DoesNotExist = ObjectDoesNotExist

    objects = ResourceUserManager()

    def __init__(self, sub: str):
        self.sub = sub
        self.pk = None
        self.is_authenticated = True


class FinderResourceServerBackend(ResourceServerBackend):
    """
    Custom resource server that uses a ResourceUser object instead of
    a user model from the database
    """

    def __init__(self):
        try:
            super().__init__()
        except Exception as e:
            logger.error(e)
            raise

        self.UserModel = ResourceUser
