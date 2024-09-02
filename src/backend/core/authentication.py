"""Token authentication."""
from django.contrib.auth.models import AnonymousUser

from rest_framework import authentication, exceptions

from .models import Service


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
            service_name = (
                self.model.objects.only("name").get(token=token, is_active=True).name
            )
        except self.model.DoesNotExist as excpt:
            raise exceptions.AuthenticationFailed("Invalid token.") from excpt

        # We don't associate tokens with a user
        return AnonymousUser(), service_name
