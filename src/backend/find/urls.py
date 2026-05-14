"""URL configuration for the find project.

Note: Bolt API endpoints (/api/v1.0/*) are served directly by Bolt
via core.handlers.api. This file only contains Django-native URLs
(admin, OIDC) which are mounted via Bolt's mount_django() in asgi.py.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("lasuite.oidc_resource_server.urls")),
]
