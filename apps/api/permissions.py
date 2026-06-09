# apps/api/permissions.py
"""
Custom permission classes for API endpoints.
Uses shared RBAC from apps.accounts.permissions (AccessRole + user.role) and
guards against unauthenticated users to avoid AttributeError.
"""

from rest_framework import permissions

from apps.accounts.permissions import api_user_has_any_role


def _user(request):
    return getattr(request, "user", None)


class IsAdminUser(permissions.BasePermission):
    """Only admin users can access."""

    def has_permission(self, request, view):
        user = _user(request)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(
            user.is_staff or (getattr(user, "role", None) or "").upper() == "ADMIN"
        )


class IsTeacherOrAdmin(permissions.BasePermission):
    """Only teachers and admins can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(
            _user(request), {"TEACHER", "ADMIN", "HOD", "LEADERSHIP"}
        )


class IsTeacher(permissions.BasePermission):
    """Only teachers can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(_user(request), {"TEACHER"})


class IsParent(permissions.BasePermission):
    """Only parents can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(_user(request), {"PARENT"})


class IsStudent(permissions.BasePermission):
    """Only students can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(_user(request), {"STUDENT"})


class IsStudentOrParent(permissions.BasePermission):
    """Only students and parents can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(_user(request), {"STUDENT", "PARENT"})


class IsBursar(permissions.BasePermission):
    """Only bursars can access."""

    def has_permission(self, request, view):
        return api_user_has_any_role(_user(request), {"BURSAR", "ADMIN", "LEADERSHIP"})


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Object-level permission to only allow owners of an object to edit it."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = _user(request)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if hasattr(obj, "user"):
            return obj.user == request.user
        return False


class CanViewChild(permissions.BasePermission):
    """Parent can only view their own children's data."""

    def has_object_permission(self, request, view, obj):
        user = _user(request)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if not api_user_has_any_role(user, {"PARENT"}):
            return True
        from apps.people.models import StudentGuardian

        return StudentGuardian.objects.filter(
            guardian_user=user,
            student=obj,
            can_view_results=True,
        ).exists()


class RoleBasedPermission(permissions.BasePermission):
    """Base permission for role-based access (uses shared RBAC: user.role + AccessRole)."""

    ROLE_PERMISSIONS = {
        "ADMIN": ["list", "retrieve", "create", "update", "delete"],
        "LEADERSHIP": ["list", "retrieve", "create", "update"],
        "TEACHER": ["list", "retrieve", "create", "update"],
        "PARENT": ["list", "retrieve"],
        "STUDENT": ["list", "retrieve"],
        "BURSAR": ["list", "retrieve", "create", "update"],
    }

    def has_permission(self, request, view):
        user = _user(request)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        role = (getattr(user, "role", "") or "").strip().upper()
        allowed = self.ROLE_PERMISSIONS.get(role, [])
        if not allowed:
            role_manager = getattr(user, "roles", None)
            role_rows = role_manager.all() if hasattr(role_manager, "all") else []
            for ac in role_rows:
                code = (getattr(ac, "code", None) or "").strip().upper()
                if code in self.ROLE_PERMISSIONS:
                    allowed = self.ROLE_PERMISSIONS[code]
                    break
        action = getattr(view, "action", None) or "retrieve"
        return action in allowed


V1_TENANT_CRUD_SCOPE_MAP: dict[tuple[str, str], str] = {
    ("students", "list"): "students:read",
    ("students", "retrieve"): "students:read",
    ("students", "create"): "students:write",
    ("students", "update"): "students:write",
    ("students", "partial_update"): "students:write",
    ("students", "destroy"): "students:write",
    ("teachers", "list"): "users:read",
    ("teachers", "retrieve"): "users:read",
    ("teachers", "create"): "users:write",
    ("teachers", "update"): "users:write",
    ("teachers", "partial_update"): "users:write",
    ("teachers", "destroy"): "users:write",
    ("guardians", "list"): "guardians:read",
    ("guardians", "retrieve"): "guardians:read",
    ("guardians", "create"): "guardians:write",
    ("guardians", "update"): "guardians:write",
    ("guardians", "partial_update"): "guardians:write",
    ("guardians", "destroy"): "guardians:write",
    ("evaluations", "list"): "grades:read",
    ("evaluations", "retrieve"): "grades:read",
    ("evaluations", "create"): "grades:write",
    ("evaluations", "update"): "grades:write",
    ("evaluations", "partial_update"): "grades:write",
    ("evaluations", "destroy"): "grades:write",
    ("invoices", "list"): "finance:read",
    ("invoices", "retrieve"): "finance:read",
    ("invoices", "create"): "finance:write",
    ("invoices", "update"): "finance:write",
    ("invoices", "partial_update"): "finance:write",
    ("invoices", "destroy"): "finance:write",
    ("payments", "list"): "finance:read",
    ("payments", "retrieve"): "finance:read",
    ("payments", "create"): "finance:write",
    ("payments", "update"): "finance:write",
    ("payments", "partial_update"): "finance:write",
    ("payments", "destroy"): "finance:write",
}


class MarketplaceAppScopedPermission(permissions.BasePermission):
    """Enforce marketplace OAuth/API-key scopes when app context is present."""

    message = "Insufficient marketplace app scope for this action."

    def has_permission(self, request, view) -> bool:
        if getattr(request, "app_installation", None) is None:
            return True
        scopes = getattr(request, "app_scope", None) or frozenset()
        basename = getattr(view, "basename", "") or ""
        action = getattr(view, "action", "") or ""
        required = V1_TENANT_CRUD_SCOPE_MAP.get((basename, action))
        if not required:
            return False
        return required in scopes


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
        user = _user(request)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(
            user.is_staff
            or user.is_superuser
            or api_user_has_any_role(user, self.ADMIN_ROLES)
        )
