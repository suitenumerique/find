"""URL configuration for find's core app."""

from django.urls import include, path

from .views import IndexDocumentView, SearchDocumentView

urlpatterns = [
    path("documents/index/", IndexDocumentView.as_view(), name="document"),
    path("documents/search/", SearchDocumentView.as_view(), name="document"),
    path("", include("lasuite.oidc_resource_server.urls")),
]
