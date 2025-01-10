"""URL configuration for find's core app."""

from django.urls import path

from .views import DocumentView

urlpatterns = [
    path("documents/", DocumentView.as_view(), name="document"),
]
