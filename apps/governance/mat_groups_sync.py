"""
Derive operator MAT group registry entries from Organization membership.

Phase 6 (post global-governance P5): when schools opt into group mode and bind
to an Organization, the MAT hub registry is built from live School rows instead
of requiring manual ``cockpit_payload["mat_groups"]`` JSON. Legacy JSON entries
are preserved for groups not yet backed by Organization rows.
"""

from __future__ import annotations

from typing import Any

from apps.governance.operating_modes import GovernanceOperatingMode

GROUP_MEMBER_MODES: frozenset[str] = frozenset(
    {
        GovernanceOperatingMode.GROUP_MEMBER,
        GovernanceOperatingMode.GROUP_MEMBER_SOVEREIGN,
    }
)


def build_mat_groups_payload_from_organizations() -> dict[str, Any]:
    """Build ``mat_groups`` JSON shape from Organization + group-member schools."""
    from apps.schools.models import School

    schools = (
        School.objects.filter(
            organization_id__isnull=False,
            governance_operating_mode__in=GROUP_MEMBER_MODES,
            is_active=True,
        )
        .select_related("organization")
        .order_by("organization__name", "name")
    )

    buckets: dict[str, dict[str, Any]] = {}
    for school in schools:
        org = school.organization
        if org is None or not org.is_active:
            continue
        group_id = org.slug
        bucket = buckets.setdefault(
            group_id,
            {
                "display_name": org.name,
                "operator_email": "",
                "region": "",
                "members": [],
                "_seen_slugs": set(),
            },
        )
        tenant_slug = (school.slug or "").strip()
        if not tenant_slug or tenant_slug in bucket["_seen_slugs"]:
            continue
        bucket["_seen_slugs"].add(tenant_slug)
        member: dict[str, str] = {
            "tenant_slug": tenant_slug,
            "display_name": (school.name or tenant_slug).strip(),
        }
        region = (getattr(school, "data_region", None) or "").strip()
        if region:
            member["region"] = region
        bucket["members"].append(member)

    out: dict[str, Any] = {}
    for group_id, bucket in buckets.items():
        if not bucket["members"]:
            continue
        out[group_id] = {
            "display_name": bucket["display_name"],
            "operator_email": bucket["operator_email"],
            "region": bucket["region"],
            "members": bucket["members"],
        }
    return out


def load_legacy_mat_groups_payload() -> dict[str, Any]:
    """Operator SiteSettings ``cockpit_payload["mat_groups"]`` (legacy JSON path)."""
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        ss = get_platform_site_settings_record(create=False)
    except Exception:  # noqa: BLE001
        return {}
    if ss is None:
        return {}
    payload = getattr(ss, "cockpit_payload", None) or {}
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("mat_groups")
    return raw if isinstance(raw, dict) else {}


def merge_mat_groups_payloads(
    derived: dict[str, Any] | None,
    legacy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Organization-derived groups win on ``group_id``; legacy fills remaining keys."""
    merged: dict[str, Any] = dict(legacy or {})
    for group_id, payload in (derived or {}).items():
        if isinstance(group_id, str) and isinstance(payload, dict) and payload.get("members"):
            merged[group_id] = payload
    return merged


def resolve_mat_groups_payload() -> dict[str, Any]:
    """Effective operator MAT registry: Organization-derived + legacy JSON fallback."""
    legacy = load_legacy_mat_groups_payload()
    try:
        derived = build_mat_groups_payload_from_organizations()
    except Exception:  # noqa: BLE001
        return legacy
    return merge_mat_groups_payloads(derived, legacy)
