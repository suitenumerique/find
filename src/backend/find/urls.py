"""URL configuration for the find project"""

from django.conf import settings
from django.contrib import admin
from django.urls import path

from core.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"api/{settings.API_VERSION}/", api.urls),
]
