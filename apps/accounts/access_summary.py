"""What this account actually holds — the one answer both profiles render.

Before this module the profile told a user almost nothing true about their own
access:

* it printed ``user.role`` (the single CharField) and nothing else, so every
  role granted through the RBAC console, a RoleGroup bundle, SCIM or a temporary
  grant was invisible — the platform supports several roles per user and then
  showed one;
* the flattened permission list existed only inside ``_admin_context``, so it
  rendered ONLY for staff / ADMIN / IT_ADMIN / LEADERSHIP. A bursar or a teacher
  granted an extra capability could not see it anywhere;
* that list was sliced ``[:20]`` with no indication, so an account with more
  codes than that was shown a silent truncation as if it were the whole set;
* and it listed only EXPLICIT grant rows, which meant a superuser — who holds
  everything — was shown an EMPTY permission list.

Everything here is read-only and degrades to an empty summary rather than
raising: a profile page must not 500 because a permission table is mid-migration.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError, connection, transaction
from django.db.models import Q
from django.db.transaction import TransactionManagementError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Where a role came from. Ordered by how strongly it should read on the page.
SOURCE_SUPERADMIN = "superadmin"
SOURCE_PRIMARY = "primary"
SOURCE_ASSIGNED = "assigned"
SOURCE_TEMPORARY = "temporary"
SOURCE_DIRECT = "direct"

SOURCE_LABELS = {
    SOURCE_SUPERADMIN: _("Platform superadmin"),
    SOURCE_PRIMARY: _("Primary role"),
    SOURCE_ASSIGNED: _("Assigned role"),
    SOURCE_TEMPORARY: _("Temporary grant"),
    SOURCE_DIRECT: _("Granted directly"),
}

SUPERADMIN_REASON_LABELS = {
    "django-superuser": _("Django superuser — every permission, present and future."),
    "primary-role": _("Primary role is Super Administrator — every permission, present and future."),
    "assigned-role": _("Holds the Super Administrator role — every permission, present and future."),
}


def _reset_db_state() -> None:
    """Mirror the recovery the profile templatetags already perform."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except (DatabaseError, TransactionManagementError):
        pass


def _empty_summary() -> dict[str, Any]:
    return {
        "available": False,
        "is_superadmin": False,
        "superadmin_reason": "",
        "superadmin_label": "",
        "primary_role_code": "",
        "primary_role_label": "",
        "roles": [],
        "groups": [],
        "permissions": [],
        "permission_count": 0,
        "role_count": 0,
    }


def _role_entry(role: Any, source: str, *, expires_at=None) -> dict[str, Any]:
    return {
        "code": getattr(role, "code", ""),
        "name": getattr(role, "name", "") or getattr(role, "code", ""),
        "description": getattr(role, "description", "") or "",
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "is_global": getattr(role, "school_id", None) is None,
        "expires_at": expires_at,
    }


def effective_access_summary(user: Any, *, school: Any = None) -> dict[str, Any]:
    """Every role, bundle and permission code ``user`` effectively holds.

    ``school`` scopes the answer the way ``has_feature_permission`` does: global
    template roles always count, school catalog roles count only for their own
    school. Passing ``None`` (the operator host, where there is no tenant in
    context) reports every role the account holds.
    """
    summary = _empty_summary()
    if user is None or not getattr(user, "is_authenticated", False):
        return summary

    from apps.accounts.superadmin import superadmin_reason

    summary["primary_role_code"] = str(getattr(user, "role", "") or "")
    try:
        summary["primary_role_label"] = user.get_role_display()
    except (AttributeError, TypeError, ValueError):
        summary["primary_role_label"] = summary["primary_role_code"]

    if connection.needs_rollback:
        # A broken transaction upstream: answer with the DB-free signals only
        # rather than compounding the failure with more queries.
        _reset_db_state()
        reason = superadmin_reason(user, allow_queries=False)
        summary["is_superadmin"] = bool(reason)
        summary["superadmin_reason"] = reason
        summary["superadmin_label"] = SUPERADMIN_REASON_LABELS.get(reason, "")
        return summary

    try:
        return _build_summary(user, school, summary)
    except (DatabaseError, TransactionManagementError) as exc:
        _reset_db_state()
        logger.warning(
            "effective_access_summary unavailable for user_id=%s: %s",
            getattr(user, "pk", None),
            exc,
        )
        return summary
    except (AttributeError, ImportError, TypeError, ValueError):
        logger.exception(
            "effective_access_summary failed for user_id=%s",
            getattr(user, "pk", None),
        )
        return summary


def _build_summary(user: Any, school: Any, summary: dict[str, Any]) -> dict[str, Any]:
    from apps.accounts.models import Permission, TemporaryRoleGrant
    from apps.accounts.superadmin import superadmin_reason

    summary["available"] = True
    reason = superadmin_reason(user)
    summary["is_superadmin"] = bool(reason)
    summary["superadmin_reason"] = reason
    summary["superadmin_label"] = SUPERADMIN_REASON_LABELS.get(reason, "")

    scope_q = Q()
    if school is not None:
        scope_q = Q(school__isnull=True) | Q(school_id=getattr(school, "pk", None))

    # --- roles ------------------------------------------------------------
    roles: list[dict[str, Any]] = []
    seen_role_keys: set[tuple[str, Any]] = set()
    primary_code = (summary["primary_role_code"] or "").upper()

    assigned = list(user.roles.filter(scope_q).prefetch_related("permissions"))
    for role in assigned:
        key = (role.code, role.school_id)
        if key in seen_role_keys:
            continue
        seen_role_keys.add(key)
        source = SOURCE_PRIMARY if role.code.upper() == primary_code else SOURCE_ASSIGNED
        roles.append(_role_entry(role, source))

    now = timezone.now()
    grants = (
        TemporaryRoleGrant.objects.filter(user=user, expires_at__gt=now)
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now))
        .select_related("role")
        .prefetch_related("role__permissions")
    )
    if school is not None:
        grants = grants.filter(
            Q(role__school__isnull=True) | Q(role__school_id=getattr(school, "pk", None))
        )
    active_grants = list(grants)
    for grant in active_grants:
        if grant.role is None:
            continue
        key = (grant.role.code, grant.role.school_id)
        if key in seen_role_keys:
            continue
        seen_role_keys.add(key)
        roles.append(_role_entry(grant.role, SOURCE_TEMPORARY, expires_at=grant.expires_at))

    roles.sort(key=lambda r: (r["source"] != SOURCE_PRIMARY, r["code"]))
    summary["roles"] = roles
    summary["role_count"] = len(roles)

    # --- permissions ------------------------------------------------------
    # code -> the role codes (or grant kinds) that confer it, so the page can
    # answer why an account holds something and not merely that it does.
    sources: dict[str, set[str]] = {}
    names: dict[str, str] = {}

    if summary["is_superadmin"]:
        # A superadmin holds the catalog, not a set of grant rows. Listing only
        # explicit rows is what made a superuser profile look empty.
        for perm in Permission.objects.all():
            sources.setdefault(perm.code, set()).add(SOURCE_SUPERADMIN)
            names[perm.code] = perm.name or perm.code
    else:
        for perm in user.feature_permissions.all():
            sources.setdefault(perm.code, set()).add(SOURCE_DIRECT)
            names[perm.code] = perm.name or perm.code
        for role in assigned:
            for perm in role.permissions.all():
                sources.setdefault(perm.code, set()).add(role.code)
                names[perm.code] = perm.name or perm.code
        for grant in active_grants:
            if grant.role is None:
                continue
            for perm in grant.role.permissions.all():
                sources.setdefault(perm.code, set()).add(grant.role.code)
                names[perm.code] = perm.name or perm.code

    summary["permissions"] = [
        {
            "code": code,
            "name": names.get(code, code),
            "sources": sorted(sources[code]),
            "via_superadmin": SOURCE_SUPERADMIN in sources[code],
        }
        for code in sorted(sources)
    ]
    summary["permission_count"] = len(summary["permissions"])

    # --- role bundles -----------------------------------------------------
    # RoleGroup stores no user link: applying a bundle does roles.add(*roles).
    # A bundle therefore applies when the account holds all of its members — a
    # derivation, and labelled as one rather than implying stored membership.
    summary["groups"] = _matching_groups(user, school, {r["code"] for r in roles})
    return summary


def _matching_groups(user: Any, school: Any, held_codes: set[str]) -> list[dict[str, Any]]:
    from apps.accounts.models import RoleGroup

    groups = RoleGroup.objects.prefetch_related("roles")
    if school is not None:
        groups = groups.filter(school_id=getattr(school, "pk", None))
    else:
        from apps.schools.models import SchoolMembership

        school_ids = list(
            # tenant-isolation-allow: reads the acting user's own memberships to BUILD the school_id__in scope applied just below; bounding this by school would be circular (both tenancy modes, reviewed 2026-09-01)
            SchoolMembership.objects.filter(user_id=getattr(user, "pk", None))
            .values_list("school_id", flat=True)
        )
        if not school_ids:
            return []
        groups = groups.filter(school_id__in=school_ids)

    matched = []
    for group in groups:
        codes = {r.code for r in group.roles.all()}
        if codes and codes.issubset(held_codes):
            matched.append(
                {
                    "code": group.code,
                    "name": group.name,
                    "role_codes": sorted(codes),
                }
            )
    matched.sort(key=lambda g: g["name"])
    return matched


__all__ = ["SOURCE_LABELS", "effective_access_summary"]
