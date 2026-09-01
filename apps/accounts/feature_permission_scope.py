"""Writing direct permission grants from a TENANT surface, scoped to that tenant.

``User.feature_permissions`` is a plain M2M with no tenant column. A console that
writes it directly mints a grant the resolver honours at every school the account
belongs to (see ``FeaturePermissionScope``), so a tenant surface must go through
``set_direct_permissions`` instead of ``user.feature_permissions.set(...)``.
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import FeaturePermissionScope


def set_direct_permissions(user, permissions, *, school) -> None:
    """Replace the direct grants THIS school issued, scoped to this school.

    A pre-existing grant with no scope row is a platform-wide one minted before
    scoping existed; this console did not issue it and does not revoke it — it
    only narrows what it re-grants. Passing ``school=None`` keeps the historical
    platform-wide write for an operator surface.
    """
    permissions = list(permissions)
    if school is None:
        user.feature_permissions.set(permissions)
        return

    keep_ids = {p.pk for p in permissions}
    with transaction.atomic():
        stale_ids = set(
            FeaturePermissionScope.objects.filter(user=user, school=school)
            .exclude(permission_id__in=keep_ids)
            .values_list("permission_id", flat=True)
        )
        if stale_ids:
            FeaturePermissionScope.objects.filter(
                user=user, school=school, permission_id__in=stale_ids
            ).delete()
            # The M2M row is the grant itself; drop it only when no OTHER school
            # still scopes that code to this user, or revoking here would revoke
            # it everywhere.
            still_scoped = set(
                # tenant-isolation-allow: deliberately cross-school: dropping the M2M grant is only safe once no OTHER school still scopes this code to this user (both tenancy modes, reviewed 2026-09-01)
                FeaturePermissionScope.objects.filter(
                    user=user, permission_id__in=stale_ids
                ).values_list("permission_id", flat=True)
            )
            drop = stale_ids - still_scoped
            if drop:
                user.feature_permissions.remove(*drop)
        for perm in permissions:
            FeaturePermissionScope.objects.get_or_create(
                user=user, permission=perm, school=school
            )
        if permissions:
            user.feature_permissions.add(*permissions)


__all__ = ["set_direct_permissions"]
