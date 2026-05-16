"""Authentication utilities for Bolt."""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist

from joserfc import jwt as jose_jwt
from lasuite.oidc_resource_server.backend import ResourceServerBackend

logger = logging.getLogger(__name__)


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
    a user model from the database.

    We override __init__ completely to avoid calling auth.get_user_model()
    which requires django.contrib.auth to be installed.
    """

    def __init__(self):
        # Set UserModel to our fake ResourceUser instead of using Django's auth model
        self.UserModel = ResourceUser

        # Replicate parent initialization without auth.get_user_model()
        self._client_id = settings.OIDC_RS_CLIENT_ID
        self._client_secret = settings.OIDC_RS_CLIENT_SECRET
        self._encryption_encoding = settings.OIDC_RS_ENCRYPTION_ENCODING
        self._encryption_algorithm = settings.OIDC_RS_ENCRYPTION_ALGO
        self._signing_algorithm = settings.OIDC_RS_SIGNING_ALGO
        self._scopes = settings.OIDC_RS_SCOPES

        self._authorization_server_client = self.authorization_server_client_class()

        if not self._client_id or not self._client_secret:
            raise ImproperlyConfigured(
                f"Could not instantiate {self.__class__.__name__}: some parameters are missing.",
            )

        self._introspection_claims_registry = jose_jwt.JWTClaimsRegistry(
            iss={"essential": False, "value": self._authorization_server_client.url},
            active={"essential": True},
            scope={"essential": False},
            **{settings.OIDC_RS_AUDIENCE_CLAIM: {"essential": False}},
        )

        self.token_origin_audience = None
