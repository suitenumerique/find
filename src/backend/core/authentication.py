"""Authentication of the API requests."""

from ninja.errors import AuthenticationError, AuthorizationError
from ninja.security import HttpBearer

from .services.menshen import authenticate_token
from .services.service_tokens import get_service_by_token

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
