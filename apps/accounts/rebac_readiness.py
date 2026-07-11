"""
Pre-flight readiness for ReBAC sensitive-resource enforcement.

Flipping ``RMC_REBAC_ENFORCE_SENSITIVE`` on makes ``enforce_permission_token``
require BOTH colon RBAC AND a matching ``can`` relationship tuple (see
``rebac.py``). Parity between the two is structural — ``has_feature_permission``
grants a code only via superuser / a direct-permission row / a role-permission
row / a temporary grant, and ``rebuild_user_permission_tuples`` writes a
``can`` tuple for exactly those same sources. So enforcement can only ever
lock out a user through OPERATIONAL DRIFT: an existing tenant whose tuples were
never backfilled, or a signal handler that failed and left a tuple stale.

This module is the pre-flight that proves drift is absent for a tenant BEFORE
an operator enables enforcement. For every active member and every code that
enforcement actually gates, it asks the real ``has_feature_permission`` (would
RBAC allow?) and the real ``check_permission_token`` (does the tuple exist?);
any user where RBAC allows but the tuple is missing WOULD be denied on flip and
is reported. An empty report means enforcement is safe to enable for that
tenant. It reimplements neither check — it calls the production functions.
"""

from __future__ import annotations

import dataclasses
from typing import Iterable

# Colon capability codes that ``enforce_permission_token`` / ``RebacPermission``
# actually gate today. This is the SOT for the enforcement surface; extend it as
# more views adopt enforcement. Wired sites (keep in sync):
#   - apps/finance/api_views.py  RebacPermission("finance.view"/"finance.manage")
#   - apps/api/mobile_api.py     enforce_permission_token(... "grade.submit"
#                                / "attendance.mark" / "finance.manage")
SENSITIVE_ENFORCED_CODES: tuple[str, ...] = (
    "finance.view",
    "finance.manage",
    "grade.submit",
    "attendance.mark",
)


@dataclasses.dataclass(frozen=True)
class ReadinessGap:
    """One (user, code) that RBAC allows but ReBAC would deny on flip."""

    user_id: int
    code: str


@dataclasses.dataclass(frozen=True)
class EnforcementReadinessReport:
    """Result of a per-tenant enforcement pre-flight."""

    school_id: object
    checked_users: int
    checked_codes: tuple[str, ...]
    would_be_denied: tuple[ReadinessGap, ...]

    @property
    def ready(self) -> bool:
        """True when no legitimately-permitted user would be denied on flip."""
        return not self.would_be_denied

    def as_dict(self) -> dict:
        return {
            "school_id": str(self.school_id),
            "checked_users": self.checked_users,
            "checked_codes": list(self.checked_codes),
            "ready": self.ready,
            "would_be_denied": [
                {"user_id": g.user_id, "code": g.code} for g in self.would_be_denied
            ],
        }


def enforcement_readiness(
    school,
    *,
    codes: Iterable[str] | None = None,
    user_limit: int | None = None,
) -> EnforcementReadinessReport:
    """
    Report every (active member, enforced code) that RBAC allows but the ReBAC
    ``can`` tuple is missing — i.e. would be denied if enforcement were enabled.

    Read-only and tenant-scoped. Superusers never appear (both checks pass for
    them). Inactive Django users are skipped — they cannot authenticate, so they
    carry no lockout risk.
    """
    from apps.accounts.rebac import check_permission_token
    from apps.schools.models import SchoolMembership

    check_codes: tuple[str, ...] = tuple(codes) if codes is not None else SENSITIVE_ENFORCED_CODES
    gaps: list[ReadinessGap] = []
    checked_users = 0
    if school is None:
        return EnforcementReadinessReport(
            school_id=None,
            checked_users=0,
            checked_codes=check_codes,
            would_be_denied=(),
        )

    members = (
        SchoolMembership.objects.filter(school=school, user__is_active=True)
        .select_related("user")
        .order_by("user_id")
    )
    if user_limit is not None:
        members = members[:user_limit]

    seen_user_ids: set[int] = set()
    for membership in members:
        user = membership.user
        if user is None or user.pk in seen_user_ids:
            continue
        seen_user_ids.add(user.pk)
        checked_users += 1
        for code in check_codes:
            if not user.has_feature_permission(code, school=school):
                continue  # RBAC already denies — enforcement can't lock out here.
            if check_permission_token(user, code, school=school):
                continue  # Tuple present — parity holds.
            gaps.append(ReadinessGap(user_id=user.pk, code=code))

    return EnforcementReadinessReport(
        school_id=getattr(school, "pk", None),
        checked_users=checked_users,
        checked_codes=check_codes,
        would_be_denied=tuple(gaps),
    )


def is_enforcement_ready(school, *, codes: Iterable[str] | None = None) -> bool:
    """Convenience boolean: True when the tenant has no would-be-denied users."""
    return enforcement_readiness(school, codes=codes).ready
