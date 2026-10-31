"""
Permission classes for the billing app.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated
from common.permissions import IsAdmin, IsStaffOrAdmin


class IsCustomer(BasePermission):
    """Allows access only to authenticated users with role CUSTOMER."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "CUSTOMER"
        )
