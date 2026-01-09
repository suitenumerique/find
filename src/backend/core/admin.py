"""Admin config for find's core app"""

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse

from core.management.commands.create_search_pipeline import (
    ensure_search_pipeline_exists,
)

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Register the serivce model for the admin site"""

    list_display = ("name", "created_at", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "token")
    change_list_template = "admin/core/services/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "ensure-search-pipeline/",
                self.admin_site.admin_view(self.ensure_search_pipeline_view),
                name="core_service_ensure_search_pipeline",
            ),
        ]
        return custom_urls + urls

    def ensure_search_pipeline_view(self, request):
        """Run the management command function to assert the pipeline exists."""
        changelist_url = reverse("admin:core_service_changelist")

        try:
            ensure_search_pipeline_exists()
        except Exception as exc:  # noqa: BLE001# pylint: disable=broad-exception-caught
            self.message_user(
                request, f"Failed to ensure search pipeline: {exc}", messages.ERROR
            )
        else:
            self.message_user(
                request, "Search pipeline presence insured", messages.SUCCESS
            )

        return redirect(changelist_url)
