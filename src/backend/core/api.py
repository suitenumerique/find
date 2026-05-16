"""BoltAPI autodiscovery entry point for django-bolt's runbolt command."""

from .handlers import api

__all__ = ["api"]
