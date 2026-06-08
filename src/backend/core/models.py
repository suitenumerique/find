"""Models for find's core app"""

import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Length
from django.utils.translation import gettext_lazy as _

models.CharField.register_lookup(Length)
TOKEN_LENGTH = 50
SLUG_REGEX = r"^[a-z0-9]+$"
SLUG_VALIDATOR = RegexValidator(
    regex=SLUG_REGEX,
    message=_("Slug must contain only lowercase letters and digits."),
)


class User(AbstractUser):
    """User for the find application"""


class Service(models.Model):
    """Service registered to index its documents to our find"""

    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=20,
        unique=True,
        validators=[SLUG_VALIDATOR],
        help_text=_(
            "Stable identifier used in the OpenSearch index name. "
            "Lowercase alphanumeric only. Set on creation, immutable thereafter."
        ),
    )
    token = models.CharField(max_length=TOKEN_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    client_id = models.CharField(blank=True, null=True)
    services = models.ManyToManyField(
        "self", blank=True, verbose_name=_("Allowed services for search")
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
            models.CheckConstraint(
                condition=models.Q(slug__regex=SLUG_REGEX),
                name="slug_alphanumeric_only",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Generate token and enforce slug immutability.

        - ``slug`` must be provided explicitly on creation and is immutable
          thereafter. The DB check constraint enforces the allowed character
          set; no auto-derivation is performed.
        - ``name`` is a free-form display field and can be edited.
        - ``token`` is generated once on creation if missing.
        """
        if not self._state.adding:
            stored_slug = (
                Service.objects.filter(pk=self.pk)
                .values_list("slug", flat=True)
                .first()
            )
            if self.slug != stored_slug:
                raise ValidationError(
                    {"slug": _("Service.slug is immutable after creation.")}
                )
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
