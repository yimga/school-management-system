"""Permission classes for the Migration Cloud public REST API.

Two-shell access model:
  - **Operator shell** — staff users (``request.user.is_staff``) see every
    bundle regardless of tenant. Mirrors the wizard's ``shell="super"``
    behavior.
  - **Tenant shell** — non-staff authenticated users must have a school
    binding that matches the bundle's school. Mirrors the wizard's
    ``shell="portal"`` behavior. Pre-tenant bundles (school is NULL)
    are operator-only; tenant callers see them as "not found" so an
    ID-enumeration attacker can't distinguish "exists pre-tenant" from
    "doesn't exist".
"""

from __future__ import annotations

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


def _is_operator_shell_request(request) -> bool:
    """Migration Cloud operator API — manager host + platform operator only."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    from apps.schools.control_plane import user_has_control_plane_access

    if not user_has_control_plane_access(user):
        return False
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()
    return host_kind in {"manager", "local"}


class MigrationCloudAPIPermission(BasePermission):
    """Authenticated + (staff OR tenant-match) gate for Migration Cloud API.

    The ``has_permission`` check covers list / create endpoints; the
    ``has_object_permission`` check enforces tenant scoping for retrieve /
    update / action endpoints. The two together replicate the wizard's
    ``_tenant_scoped_bundle`` discipline at the API layer.
    """

    message = "Migration Cloud API access requires staff or matching tenant binding."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if _is_operator_shell_request(request):
            return True
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        if school is None:
            return False
        from apps.schools.models import SchoolMembership

        return SchoolMembership.objects.filter(user=user, school=school).exists()

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if _is_operator_shell_request(request):
            return True
        bundle_school_id = getattr(obj, "school_id", None)
        if bundle_school_id is None:
            # Pre-tenant bundle — operator-only. Non-staff see this as
            # "no permission" which the viewset translates to 404 via
            # the queryset filter; this branch is defense-in-depth.
            return False
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        return getattr(school, "pk", None) == bundle_school_id


class ScopedAPIPermission(MigrationCloudAPIPermission):
    """Tenant gate + per-action scope gate for ``MigrationCloudAPIToken`` callers.

    If the request was authenticated via a scoped token, ``request.auth``
    is the :class:`apps.migration_cloud.models.MigrationCloudAPIToken`
    row. We map ``(view.basename, action_name)`` to a required scope via
    :data:`apps.migration_cloud.api.scoped_tokens.ACTION_SCOPE_REQUIREMENTS`
    and reject the call if the token's ``scopes`` list doesn't include
    it.

    For callers using session / DRF authtoken auth (where
    ``request.auth`` is not one of our scoped rows), the parent class's
    staff-or-tenant-match check applies — scopes are not enforced.
    """

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return self._scope_ok(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        if not super().has_object_permission(request, view, obj):
            return False
        # Object-level scope check is the same as view-level — we don't
        # vary scope per object; tenant_scope on the token row handles
        # cross-tenant denial separately below.
        return self._scope_ok(request, view, obj=obj)

    def _scope_ok(self, request, view, *, obj=None) -> bool:
        # Lazy import — keeps module load order safe.
        from .scoped_tokens import ACTION_SCOPE_REQUIREMENTS
        from apps.migration_cloud.models import MigrationCloudAPIToken

        token = getattr(request, "auth", None)
        if not isinstance(token, MigrationCloudAPIToken):
            # Not a scoped-token request — fall through (parent already OK'd).
            return True

        # Enforce token's tenant_scope if set.
        if token.tenant_scope_id is not None:
            target_school_id = None
            if obj is not None:
                target_school_id = getattr(obj, "school_id", None) or getattr(
                    obj, "tenant_id", None,
                )
            if target_school_id is None:
                school = getattr(request, "school", None) or getattr(
                    request, "tenant", None,
                )
                target_school_id = getattr(school, "pk", None)
            if (
                target_school_id is not None
                and target_school_id != token.tenant_scope_id
            ):
                self.message = "scoped token bound to a different tenant"
                return False

        basename = getattr(view, "basename", None) or getattr(view, "_basename", None)
        action_name = getattr(view, "action", None)
        if not basename or not action_name:
            # Unknown view shape — fail closed.
            return False
        required = ACTION_SCOPE_REQUIREMENTS.get((basename, action_name))
        if required is None:
            # No scope mapping — fail closed; every action must be cataloged.
            self.message = (
                f"action {basename}.{action_name} has no scope mapping; refused"
            )
            return False
        scopes = list(token.scopes or [])
        if required not in scopes:
            self.message = f"missing required scope '{required}'"
            return False
        return True
