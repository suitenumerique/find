"""
ASGI config for the find project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

# Set before importing configurations.asgi, which reads them when imported.
# Fail closed: serve the Production configuration unless told otherwise.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "find.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Production")

# pylint: disable=wrong-import-position
from configurations.asgi import (
    get_asgi_application,
)

application = get_asgi_application()
