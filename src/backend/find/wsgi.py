"""
WSGI config for the find project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/wsgi/
"""

import os

from configurations.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "find.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Development")

application = get_wsgi_application()
