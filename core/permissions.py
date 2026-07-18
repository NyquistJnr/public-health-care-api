# core/permissions.py
from rest_framework import permissions

class HasRequiredPermission(permissions.BasePermission):
    """
    Checks if the user has the specific permissions required by the view.
    The view must define a 'required_permissions' list.
    """
    
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True

        required_perms = getattr(view, 'required_permissions', [])

        if not required_perms:
            return True

        for perm in required_perms:
            if not request.user.has_perm(perm):
                return False

        return True


class IsStateAdmin(permissions.BasePermission):
    """Restricts access to State Admins (role='ADMIN') or Django superusers."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role == 'ADMIN'))


class IsFacilityITAdmin(permissions.BasePermission):
    """Restricts access to Facility IT Admins (role='FACILITY_IT_ADMIN') or Django superusers."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role == 'FACILITY_IT_ADMIN'))
