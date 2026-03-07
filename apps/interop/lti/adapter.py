"""
LTI 1.3 / AGS / NRPS: canonical model ⇄ LTI payloads (read-only helpers).

Used by apps.schools.section8_views for line items, scores, and memberships.
"""

from __future__ import annotations

from typing import Any


def build_ags_lineitem_from_canonical(
    resource_id: str,
    resource_link_id: str,
    label: str,
    score_max: float | None = None,
) -> dict[str, Any]:
    """Build LTI AGS line item dict from canonical assignment/eval identifiers."""
    out = {
        "id": resource_id,
        "resourceLinkId": resource_link_id,
        "label": label,
    }
    if score_max is not None:
        out["scoreMaximum"] = score_max
    return out


def build_nrps_member_from_user(
    user: Any,
    *,
    role: str = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student",
    sourced_id: str | None = None,
) -> dict[str, Any]:
    """Build LTI NRPS member dict from User/StudentProfile."""
    sid = sourced_id or str(getattr(user, "pk", id(user)))
    return {
        "user_id": sid,
        "status": "Active",
        "given_name": getattr(user, "first_name", "") or "",
        "family_name": getattr(user, "last_name", "") or "",
        "roles": [role],
    }
