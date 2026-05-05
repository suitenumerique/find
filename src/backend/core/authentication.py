"""Token authentication."""

import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist

from lasuite.oidc_resource_server.backend import ResourceServerBackend
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """A custom authentication looking for valid tokens among registered services"""

    def authenticate(self, request):
        """Authenticate token from the "Authorization" header."""
        token = request.headers.get("Authorization")
        if not token:
            raise exceptions.NotAuthenticated()

        token = token.split(" ")[-1]  # Extract token if prefixed with "Token"

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token):
        """Check that the token is registered and valid."""
        service_config = settings.SERVICES.get_by_token(token)
        if service_config is None:
            raise exceptions.AuthenticationFailed("Invalid token.")

        # We don't associate tokens with a user
        return AnonymousUser(), service_config


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
