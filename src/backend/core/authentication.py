"""Authentication utilities for Bolt."""

import logging

from django.core.exceptions import ObjectDoesNotExist

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
    a user model from the database
    """

    def __init__(self):
        try:
            super().__init__()
        except Exception as e:
            logger.error(e)
            raise

        self.UserModel = ResourceUser
