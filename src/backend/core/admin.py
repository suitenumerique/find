"""Admin config for drive's core app"""
from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Register the serivce model for the admin site"""

    list_display = ("name", "created_at", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "token")
