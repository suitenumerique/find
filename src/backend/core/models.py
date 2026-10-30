"""Models for find's core app"""

import hashlib
import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Length
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

# Used by the token length constraint of migration 0001
models.CharField.register_lookup(Length)
TOKEN_LENGTH = 50


def get_opensearch_index_name(name: str):
    """Returns the opensearch index for a service name"""
    return f"{settings.OPENSEARCH_INDEX_PREFIX}-{name}"


def get_service_name(index_name: str):
    """Returns the service name for an opensearch index"""
    return index_name.removeprefix(f"{settings.OPENSEARCH_INDEX_PREFIX}-")


def hash_token(token: str):
    """
    Returns the hash under which a service token is stored. Tokens are long random
    strings, so a fast unsalted hash is enough and allows looking them up.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class User(AbstractUser):
    """User for the find application"""


class Service(models.Model):
    """Service registered to index its documents to our find"""

    name = models.SlugField(max_length=20, unique=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    client_id = models.CharField(blank=True, null=True)
    services = models.ManyToManyField(
        "self",
        verbose_name=_("Allowed services for search"),
        blank=True,
    )

    class Meta:
        db_table = "find_service"
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["-is_active", "-created_at"]

    # The plaintext token is never stored: it is only available on the instance
    # that generated it, to be shown once.
    token = None

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Automatically slugify the service name and generate a token on creation"""
        self.name = slugify(self.name)
        if not self.token_hash:
            self.set_token()
        super().save(*args, **kwargs)

    def set_token(self, token=None):
        """Set a new token, generated if not given, and return it. Does not save."""
        self.token = token or self.generate_secure_token()
        self.token_hash = hash_token(self.token)
        return self.token

    @staticmethod
    def generate_secure_token():
        """Generate a secure token with with Python secret module"""
        characters = (
            string.ascii_letters + string.digits + r"""!#%&'()*+,-./:;<=>?@[\]^_`{|}~"""
        )
        token = "".join(secrets.choice(characters) for _ in range(TOKEN_LENGTH))
        return token

    @cached_property
    def index_name(self):
        """Returns the opensearch index for the service"""
        return get_opensearch_index_name(self.name)
