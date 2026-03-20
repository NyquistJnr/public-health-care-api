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
