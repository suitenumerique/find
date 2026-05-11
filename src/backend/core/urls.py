"""URL configuration for find's core app."""

from django.http import JsonResponse
from django.urls import include, path, re_path

from .views import DeleteDocumentView, IndexDocumentView, SearchDocumentView


def api_404(request, *args, **kwargs):
    return JsonResponse({"detail": "Not found."}, status=404)


urlpatterns = [
    path("resources/index/", IndexDocumentView.as_view(), name="document"),
    path("resources/search/", SearchDocumentView.as_view(), name="document"),
    path(
        "resources/<uuid:document_id>/",
        DeleteDocumentView.as_view(),
        name="document-delete",
    ),
    re_path(r"^resources/.*$", api_404),
    path("", include("lasuite.oidc_resource_server.urls")),
]
