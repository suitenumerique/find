"""Admin config for find's core app"""

from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

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
    readonly_fields = ("created_at",)
    actions = ("regenerate_tokens",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "services":
            # A service added from the popup would close it without its token
            formfield.widget.can_add_related = False
        return formfield

    def response_add(self, request, obj, post_url_continue=None):
        """Show the token of the new service, the only time it is available"""
        if "_continue" in request.POST:
            next_url = reverse("admin:core_service_change", args=[obj.pk])
            next_label = _("Continue editing")
        elif "_addanother" in request.POST:
            next_url = reverse("admin:core_service_add")
            next_label = _("Add another service")
        else:
            next_url, next_label = None, None
        return self.render_tokens(request, [obj], next_url, next_label)

    @admin.action(description=_("Regenerate the tokens of selected services"))
    def regenerate_tokens(self, request, queryset):
        """Replace the tokens of the selected services and show the new ones"""
        services = list(queryset)
        # All or nothing: tokens that are never shown must not replace the old ones
        try:
            with transaction.atomic():
                for service in services:
                    if not replace_token(service):
                        raise TokenConflict
                return self.render_tokens(request, services)
        except TokenConflict:
            self.message_user(
                request,
                _(
                    "A token was changed meanwhile, no token was regenerated: "
                    "regenerate them again."
                ),
                messages.ERROR,
            )
            return None

    def render_tokens(self, request, services, next_url=None, next_label=None):
        """Render the plaintext tokens, in the response only, never in storage"""
        context = {
            **self.admin_site.each_context(request),
            "title": _("Service tokens"),
            "opts": self.opts,
            "services": services,
            "next_url": next_url,
            "next_label": next_label,
        }
        return render(request, "admin/core/service/tokens.html", context)


class TokenConflict(Exception):
    """The token of a service changed since it was read"""


def replace_token(service):
    """
    Set a new token on a service, saved only if its stored token did not change
    since the service was read: otherwise the token shown by a concurrent
    regeneration would stop working. Return whether the token was saved.
    """
    previous_hash = service.token_hash
    service.set_token()
    return bool(
        Service.objects.filter(pk=service.pk, token_hash=previous_hash).update(
            token_hash=service.token_hash
        )
    )


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
