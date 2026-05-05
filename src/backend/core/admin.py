"""Admin config for find's core app"""

from django.contrib import admin
from django.shortcuts import render
from django.urls import path

from . import selftests_builtin  # pylint: disable=unused-import
from .models import Service
from .selftests import registry


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Register the serivce model for the admin site"""

    list_display = ("name", "created_at", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "token")


def selftest_view(request):
    """Display the self-test page and run tests if requested."""
    # selftests_builtin and registry are imported at module level to ensure tests are registered
    run_tests = request.GET.get("run", "false").lower() == "true"

    if run_tests:
        results = registry.run_all()
        all_passed = all(result.success for result in results)
    else:
        results = []
        all_passed = None

    context = {
        **admin.site.each_context(request),
        "title": "System Self-Tests",
        "results": results,
        "all_passed": all_passed,
        "run_tests": run_tests,
        "available_tests": registry.get_all_tests(),
    }

    return render(request, "admin/selftest.html", context)


# Add custom URL to the default admin site
def get_admin_urls():
    """Get URLs with selftest added."""

    def get_urls():
        urls = get_admin_urls.original_get_urls()
        custom_urls = [
            path(
                "selftest/",
                admin.site.admin_view(selftest_view),
                name="selftest",
            ),
        ]
        return custom_urls + urls

    return get_urls


# Store original get_urls and override it
get_admin_urls.original_get_urls = admin.site.get_urls
admin.site.get_urls = get_admin_urls()
