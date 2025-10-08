"""Token authentication."""

import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist

from lasuite.oidc_resource_server.backend import ResourceServerBackend
from rest_framework import authentication, exceptions

from .models import Service

logger = logging.getLogger(__name__)


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
            service = self.model.objects.only("name").get(token=token, is_active=True)
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

    def _verify_claims(self, token):
        """
        Verify the claims of the token to ensure authentication security.

        By verifying these claims, we ensure that the token was issued by a
        trusted authorization server and is intended for this specific
        resource server. This prevents various types of attacks, such as
        token substitution or misuse of tokens issued for different clients.
        """

        # To run Find in development mode along other projects like docs/impress
        # we have to use OIDC endpoints on a common keycloak realm. e.g :
        # OIDC_OP_URL = http://nginx:8083/realms/impress
        #
        # This will cause a conflict with the 'iss' claim validation rule because the docs realm
        # gives {'iss': 'http://localhost:8083/realms/impress'} and it must be OIDC_OP_URL
        #
        # In order to make it work anyway, this flag allows to disable the claims validation.
        if settings.OIDC_RS_VERIFY_CLAIMS:
            return super()._verify_claims(token)

        return token.claims
