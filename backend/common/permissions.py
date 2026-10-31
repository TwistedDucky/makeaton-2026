from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "Only administrators can perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "ADMIN"
        )


class IsStaffOrAdmin(BasePermission):
    message = "Staff or administrators only."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ["STAFF", "ADMIN"]
        )