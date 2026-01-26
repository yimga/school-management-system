# apps/api/permissions.py
"""
Custom permission classes for API endpoints
Location: apps/api/permissions.py
"""

from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """Only admin users can access"""
    def has_permission(self, request, view):
        return bool(request.user and (request.user.is_staff or request.user.role == 'ADMIN'))


class IsTeacherOrAdmin(permissions.BasePermission):
    """Only teachers and admins can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role in ['TEACHER', 'ADMIN', 'HOD', 'LEADERSHIP'])


class IsTeacher(permissions.BasePermission):
    """Only teachers can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role == 'TEACHER')


class IsParent(permissions.BasePermission):
    """Only parents can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role == 'PARENT')


class IsStudent(permissions.BasePermission):
    """Only students can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role == 'STUDENT')


class IsStudentOrParent(permissions.BasePermission):
    """Only students and parents can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role in ['STUDENT', 'PARENT'])


class IsBursar(permissions.BasePermission):
    """Only bursars can access"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.role in ['BURSAR', 'ADMIN', 'LEADERSHIP'])


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Object-level permission to only allow owners of an object to edit it"""
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Only owner can edit
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False


class CanViewChild(permissions.BasePermission):
    """Parent can only view their own children's data"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'PARENT':
            # Check if this child belongs to this parent
            from apps.people.models import StudentGuardian
            return StudentGuardian.objects.filter(
                guardian_user=request.user,
                student=obj,
                can_view_results=True,
            ).exists()
        
        return True


class RoleBasedPermission(permissions.BasePermission):
    """Base permission for role-based access"""
    
    # Define which roles can access which resources
    ROLE_PERMISSIONS = {
        'ADMIN': ['list', 'retrieve', 'create', 'update', 'delete'],
        'LEADERSHIP': ['list', 'retrieve', 'create', 'update'],
        'TEACHER': ['list', 'retrieve', 'create', 'update'],
        'PARENT': ['list', 'retrieve'],
        'STUDENT': ['list', 'retrieve'],
        'BURSAR': ['list', 'retrieve', 'create', 'update'],
    }
    
    def has_permission(self, request, view):
        user_role = request.user.role
        action = view.action if hasattr(view, 'action') else 'retrieve'
        
        allowed_actions = self.ROLE_PERMISSIONS.get(user_role, [])
        return action in allowed_actions


class IsAdminLike(permissions.BasePermission):
    """Staff/superuser or admin-like role gate for sensitive endpoints."""

    ADMIN_ROLES = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "IT_ADMIN",
        "CENSOR",
        "BURSAR",
    }

    def has_permission(self, request, view):
        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        return bool(user and (user.is_staff or user.is_superuser or role in self.ADMIN_ROLES))
