"""ASGI config for the find project.

Bolt serves API endpoints directly. Django handles admin and OIDC via mount_django().
Run with: uvicorn find.asgi:application or python -m django_bolt runbolt
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "find.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Development")

import django
from configurations import importer

importer.install()
django.setup()

from core.handlers import api

api.mount_django(r"/admin")
api.mount_django(r"/oidc")

application = api
