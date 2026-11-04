"""
Custom Permission Classes for Users App
Provides role-based and object-level permissions for user management.
"""

from rest_framework import permissions


class IsSelfOrAdmin(permissions.BasePermission):
    """
    Permission that allows users to access their own data,
    or admins to access any user's data.
    """
    
    def has_object_permission(self, request, view, obj):
        # Allow if user is accessing their own data
        if obj.id == request.user.id:
            return True
        
        # Allow if user is staff or admin
        return request.user.is_staff or request.user.is_admin()


class CanImpersonate(permissions.BasePermission):
    """
    Permission that allows only admins to impersonate other users.
    """
    
    def has_permission(self, request, view):
        # Only staff/admin users can impersonate
        if not request.user.is_authenticated:
            return False
        return request.user.is_staff or request.user.is_admin()
    
    def has_object_permission(self, request, view, obj):
        # Cannot impersonate superusers unless you're a superuser
        if obj.is_superuser and not request.user.is_superuser:
            return False
        
        # Cannot impersonate staff unless you're staff
        if obj.is_staff and not request.user.is_staff:
            return False
        
        return True


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission that allows read access to anyone authenticated,
    but write access only to admins.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.method in permissions.SAFE_METHODS:
            return True
        
        return request.user.is_staff or request.user.is_admin()


class CanManageRoles(permissions.BasePermission):
    """
    Permission that allows only admins to manage roles.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.is_staff or request.user.is_admin()


class CanRevokeSession(permissions.BasePermission):
    """
    Permission that allows users to revoke their own sessions,
    or admins to revoke any session.
    """
    
    def has_object_permission(self, request, view, obj):
        # Allow if user owns the session
        if obj.user.id == request.user.id:
            return True
        
        # Allow if user is staff or admin
        return request.user.is_staff or request.user.is_admin()
