"""Keep the SUPERADMIN role ROW agreeing with the superadmin RESOLVER.

``has_feature_permission`` already grants a superadmin every code structurally
(see ``apps.accounts.superadmin``), so enforcement cannot drift. But the stored
``AccessRole.permissions`` rows are what the RBAC console renders, what the
profile lists, what ``check_roles`` audits and what an offline IAM snapshot
ships. If the row says 36 codes while the resolver enforces 40, the product
lies to the operator about their own access.

This module is the reconciliation: every ``Permission`` in the catalog belongs
to the global SUPERADMIN role. It runs on ``post_migrate`` — so a migration that
adds a code grants it in the same command, with nothing to remember — and is
exposed as ``manage.py sync_superadmin_permissions`` for repair on a box whose
migrations were applied out of order.

Additive by construction: it only ever calls ``.add()``. It never removes a
grant, so a deliberately widened role is never narrowed behind an operator's
back.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SUPERADMIN_ROLE_DEFAULTS = {
    "name": "Super Administrator",
    "description": (
        "Platform top role — holds every permission in the catalog, including "
        "codes added in the future. Granted structurally, not by seeding."
    ),
}


def sync_superadmin_role_permissions(*, access_role_model=None, permission_model=None) -> int:
    """Grant every catalog ``Permission`` to the global SUPERADMIN role.

    Returns the number of grants ADDED (0 when already reconciled). Accepts the
    models explicitly so a migration can pass its historical versions.
    """
    if access_role_model is None or permission_model is None:
        from apps.accounts.models import AccessRole, Permission

        access_role_model = access_role_model or AccessRole
        permission_model = permission_model or Permission

    from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE

    role, _created = access_role_model.objects.get_or_create(
        code=SUPERADMIN_ROLE_CODE,
        school=None,
        defaults=dict(SUPERADMIN_ROLE_DEFAULTS),
    )
    held = set(role.permissions.values_list("pk", flat=True))
    missing = [p for p in permission_model.objects.all() if p.pk not in held]
    if not missing:
        return 0
    role.permissions.add(*missing)
    logger.info(
        "sync_superadmin_permissions: granted %s code(s) to the global SUPERADMIN role: %s",
        len(missing),
        ", ".join(sorted(str(getattr(p, "code", p)) for p in missing)),
    )
    return len(missing)


def on_post_migrate(sender, **kwargs) -> None:
    """``post_migrate`` receiver — never let a failure break a deploy."""
    if getattr(sender, "label", None) != "accounts":
        return
    from django.db import DatabaseError, ProgrammingError

    try:
        sync_superadmin_role_permissions()
    except (DatabaseError, ProgrammingError, LookupError) as exc:
        # A partially-migrated or unmigrated database is an expected state here
        # (e.g. the first `migrate` on an empty box). The next run reconciles.
        logger.warning("sync_superadmin_permissions skipped: %s", exc)


__all__ = ["on_post_migrate", "sync_superadmin_role_permissions"]
