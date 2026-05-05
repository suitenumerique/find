"""Models for find's core app"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Length

# Register Length lookup for CharField - required by historical migrations
models.CharField.register_lookup(Length)


def get_opensearch_index_name(name: str):
    """Returns the opensearch index for a service name"""
    return f"{settings.OPENSEARCH_INDEX_PREFIX}-{name}"


class User(AbstractUser):
    """User for the find application"""
