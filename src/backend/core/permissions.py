"""Permission classes for find's core app"""

from rest_framework import permissions


class IsAuthAuthenticated(permissions.BasePermission):
    """
    Allows access only to auth authenticated users.
    """

    def has_permission(self, request, view):
        return bool(request.auth)
