"""Models for find's core app"""

import secrets
import string
from dataclasses import dataclass
from dataclasses import field as datafield
from typing import List, Optional
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Length
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.timezone import datetime
from django.utils.translation import gettext_lazy as _

from . import enums

models.CharField.register_lookup(Length)
TOKEN_LENGTH = 50


def get_opensearch_index_name(name: str):
    """Returns the opensearch index for a service name"""
    return f"{settings.OPENSEARCH_INDEX_PREFIX}-{name}"


class User(AbstractUser):
    """User for the find application"""


class Service(models.Model):
    """Service registered to index its documents to our find"""

    name = models.SlugField(max_length=20, unique=True)
    token = models.CharField(max_length=TOKEN_LENGTH)
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(token__length=TOKEN_LENGTH),
                name="token_length_exact_50",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Automatically slugify the service name and generate a token on creation"""
        self.name = slugify(self.name)
        if not self.token:
            self.token = self.generate_secure_token()
        super().save(*args, **kwargs)

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


# pylint: disable=too-many-instance-attributes
@dataclass
class IndexDocument:
    """Represents the _source data of opensearch entry"""

    id: UUID
    title: str = ""
    depth: int = 0
    path: str = ""
    numchild: int = 0
    content: str = ""
    content_uri: str = ""
    content_status: enums.ContentStatusEnum = enums.ContentStatusEnum.READY
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    size: int = 0
    users: List[str] = datafield(default_factory=list)
    groups: List[str] = datafield(default_factory=list)
    reach: enums.ReachEnum = enums.ReachEnum.RESTRICTED
    is_active: bool = True
    mimetype: str = "text/plain"
    language: str = "en"
    embedding: Optional[str] = None
    embedding_model: Optional[str] = None

    @property
    def is_waiting(self):
        """Retuns true if in waiting status"""
        return self.content_status == enums.ContentStatusEnum.WAIT

    @property
    def is_ready(self):
        """Retuns true if in ready status"""
        return self.content_status == enums.ContentStatusEnum.READY

    @property
    def is_loaded(self):
        """Retuns true if in loaded status"""
        return self.content_status == enums.ContentStatusEnum.LOADED

    @staticmethod
    def from_dict(data):
        """Create an instance from dict data"""
        document = IndexDocument(**data)
        document.reach = enums.ReachEnum(document.reach)
        document.content_status = enums.ContentStatusEnum(document.content_status)

        if isinstance(document.created_at, str):
            document.created_at = datetime.fromisoformat(document.created_at)

        if isinstance(document.updated_at, str):
            document.updated_at = datetime.fromisoformat(document.updated_at)

        return document
