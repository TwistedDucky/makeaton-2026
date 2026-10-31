from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminOrReadOnly(BasePermission):
    """
    Any authenticated user may read; only users with role ADMIN may write.
    """

    message = "Only administrators can perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == "ADMIN"

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsAdminWriteStaffRead(BasePermission):
    """
    ADMIN has full access; STAFF has read-only access; CUSTOMER has no access.
    """

    message = "Staff or administrators only."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == "ADMIN":
            return True
        if request.user.role == "STAFF" and request.method in SAFE_METHODS:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)

