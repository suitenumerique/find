"""Find Core application"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    """Configuration class for the Find core app."""

    name = "core"
    app_label = "core"
    verbose_name = _("Find core application")

    def ready(self):
        pass
