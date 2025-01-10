"""Models for find's core app"""

import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Length
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

models.CharField.register_lookup(Length)
TOKEN_LENGTH = 50


class User(AbstractUser):
    """User for the find application"""


class Service(models.Model):
    """Service registered to index its documents to our find"""

    name = models.SlugField(max_length=20, unique=True)
    token = models.CharField(max_length=TOKEN_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "find_service"
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["-is_active", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(token__length=TOKEN_LENGTH), name="token_length_exact_50"
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
        characters = string.ascii_letters + string.digits + string.punctuation
        token = "".join(secrets.choice(characters) for _ in range(TOKEN_LENGTH))
        return token

    @property
    def index_name(self):
        """Compute index name from service name"""
        return f"find-{self.name:s}"
