"""Find Core application"""

import sys

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    """Configuration class for the Find core app."""

    name = "core"
    app_label = "core"
    verbose_name = _("Find core application")

    def ready(self):
        if "pytest" in sys.modules:
            return

        from .services.indexing import ensure_index_exists

        ensure_index_exists(settings.OPENSEARCH_INDEX)
