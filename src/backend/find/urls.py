"""URL configuration for the find project.

Note: Bolt API endpoints (/api/v1.0/*) are served directly by Bolt
via core.handlers.api. This file only contains Django-native URLs
(OIDC) which are mounted via Bolt's mount_django() in asgi.py.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("lasuite.oidc_resource_server.urls")),
]
