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
        # Staff always pass (operator shell). Non-staff need a school binding
        # on the request so the object-level check can match.
        if user.is_staff:
            return True
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        return school is not None

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        bundle_school_id = getattr(obj, "school_id", None)
        if bundle_school_id is None:
            # Pre-tenant bundle — operator-only. Non-staff see this as
            # "no permission" which the viewset translates to 404 via
            # the queryset filter; this branch is defense-in-depth.
            return False
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        return getattr(school, "pk", None) == bundle_school_id
