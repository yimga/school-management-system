"""Role → Django-permission bridge backend.

The backend management views in ``apps/people/views_backend.py`` (teacher /
student / classroom / applicant / guardian lists + create/edit) gate access with
Django's BUILT-IN permission system::

    @permission_required("people.view_teacherprofile", raise_exception=True)

But the platform's actual access model is a CUSTOM role system (``AccessRole`` +
``has_feature_permission`` + direct ``role == ADMIN`` checks used everywhere else).
Nothing grants those built-in ``auth.Permission`` rows to role-based users, so a
non-superuser ADMIN has ``has_perm("people.view_teacherprofile") == False`` and
every one of those pages returns 403 ("permission denied").

This backend bridges the gap the way Django intends — by contributing
permissions through ``get_all_permissions`` — granting the ``people`` and
``academics`` management permissions (view / add / change, NOT delete) to
admin-like roles and Django staff. It is additive: Django unions every backend's
permissions, so this only ever GRANTS, never revokes, and non-admin roles get an
empty set from here (their perms are unchanged). Mirrors the ``role == ADMIN``
full-access pattern already used across the platform.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import BaseBackend

# Roles that manage people + academics (mirrors the admin-like set used by the
# copilot RBAC and the role == ADMIN checks in apps/accounts/views.py).
ADMIN_LIKE_ROLES = frozenset(
    {
        "ADMIN",  # role-string-allow: admin-like role-permission set; bridges built-in Django perms (mirrors role_registry / role==ADMIN checks)
        "SUPERADMIN",
        "PROPRIETOR",  # role-string-allow: admin-like role-permission set; extended role not in User.Role TextChoices (mirrors role_registry)
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "LEADERSHIP",
        "DEAN",
        "IT_ADMIN",
    }
)

# Apps whose management views are gated on built-in Django perms.
BRIDGED_APP_LABELS = ("people", "academics")

_USER_PERM_CACHE_ATTR = "_role_perm_bridge_cache"


def bridge_eligible(user_obj: Any) -> bool:
    """Pure, DB-free predicate: should this user receive the bridged perms?

    Superusers already hold every permission, so they are excluded (no point
    running the query). Anonymous / inactive users get nothing. Otherwise the
    user must be Django staff or carry an admin-like role.
    """
    if user_obj is None:
        return False
    if not getattr(user_obj, "is_active", False):
        return False
    if not getattr(user_obj, "is_authenticated", False):
        return False
    if getattr(user_obj, "is_superuser", False):
        return False
    if getattr(user_obj, "is_staff", False):
        return True
    role = (getattr(user_obj, "role", "") or "").upper()
    return role in ADMIN_LIKE_ROLES


class RolePermissionBackend(BaseBackend):
    """Grants ``people`` / ``academics`` management perms to admin-like roles."""

    def authenticate(self, request, **kwargs):  # noqa: D401 — auth handled elsewhere
        # This backend only contributes permissions; it never authenticates.
        return None

    def get_all_permissions(self, user_obj, obj=None) -> set[str]:
        # Object-level perms are out of scope for this app-level bridge.
        if obj is not None or not bridge_eligible(user_obj):
            return set()
        cached = getattr(user_obj, _USER_PERM_CACHE_ATTR, None)
        if cached is not None:
            return cached
        from django.contrib.auth.models import Permission

        perms = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in (
                Permission.objects.filter(
                    content_type__app_label__in=BRIDGED_APP_LABELS
                )
                .exclude(codename__startswith="delete_")
                .select_related("content_type")
            )
        }
        try:
            setattr(user_obj, _USER_PERM_CACHE_ATTR, perms)
        except (AttributeError, TypeError):
            pass
        return perms

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        return perm in self.get_all_permissions(user_obj, obj=obj)

    def has_module_perms(self, user_obj, app_label: str) -> bool:
        prefix = f"{app_label}."
        return any(perm.startswith(prefix) for perm in self.get_all_permissions(user_obj))
