"""Find Core application"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from core.management.commands.create_search_pipeline import (
    ensure_search_pipeline_exists,
)
from core.services.opensearch import (
    check_hybrid_search_enabled,
)


class CoreConfig(AppConfig):
    """Configuration class for the Find core app."""

    name = "core"
    app_label = "core"
    verbose_name = _("Find core application")

    def ready(self):
        """
        Ensure search pipeline exists if hybrid search is enabled.
        """
        if check_hybrid_search_enabled():
            ensure_search_pipeline_exists()
