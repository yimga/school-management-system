"""Opt-in Group Console context (global governance Phase 4A).

Visible only when ``school_in_group_mode`` and the school links to an
``Organization``. Standalone schools never see group chrome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.governance.country_matrix_service import matrix_admin_labels
from apps.governance.services import (
    GOVERNANCE_INHERIT_SETTINGS_KEY,
    KNOWN_INHERIT_DOMAINS,
    inherit_domain,
    school_in_group_mode,
)

if TYPE_CHECKING:
    from apps.governance.models import Organization
    from apps.schools.models import School


def group_console_visible(school: "School | None") -> bool:
    """True when the tenant opted into organization group membership."""
    if school is None:
        return False
    if not school_in_group_mode(school):
        return False
    return getattr(school, "organization_id", None) is not None


def _organization_for_school(school: "School") -> "Organization | None":
    org = getattr(school, "organization", None)
    if org is not None:
        return org
    org_id = getattr(school, "organization_id", None)
    if not org_id:
        return None
    from apps.governance.models import Organization

    return Organization.objects.filter(pk=org_id, is_active=True).first()


def member_schools_for_organization(organization: "Organization"):
    from apps.schools.models import School

    # tenant-isolation-allow: group-console-explicit-organization-fk-scope
    return School.objects.filter(organization=organization, is_active=True).order_by("name")


def build_group_console_context(school: "School", user) -> dict[str, Any]:
    """Assemble read-only Group Console payload for templates/API."""
    organization = _organization_for_school(school)
    members: list[dict[str, Any]] = []
    if organization is not None:
        for member in member_schools_for_organization(organization):
            members.append(
                {
                    "id": str(member.pk),
                    "name": member.name,
                    "slug": member.slug,
                    "operating_mode": getattr(member, "governance_operating_mode", ""),
                    "is_current": member.pk == school.pk,
                }
            )

    settings_blob = getattr(school, "settings", None) or {}
    inherit_map = (
        settings_blob.get(GOVERNANCE_INHERIT_SETTINGS_KEY)
        if isinstance(settings_blob, dict)
        else {}
    )
    if not isinstance(inherit_map, dict):
        inherit_map = {}

    inherit_domains = {
        domain: inherit_domain(school, domain) for domain in sorted(KNOWN_INHERIT_DOMAINS)
    }

    country_code = getattr(school, "country_code", None) or ""
    return {
        "organization": organization,
        "member_schools": members,
        "member_count": len(members),
        "admin_level_labels": matrix_admin_labels(country_code),
        "inherit_domains": inherit_domains,
        "inherit_map": inherit_map,
        "can_manage_org": _user_can_manage_group(user, organization),
    }


def _user_can_manage_group(user, organization: "Organization | None") -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if organization is None:
        return False
    from apps.governance.models import OrgMembership

    return OrgMembership.objects.filter(
        user=user,
        organization=organization,
        role__in={
            OrgMembership.Role.OWNER,
            OrgMembership.Role.GROUP_ADMIN,
        },
    ).exists()


def apply_group_upgrade(
    school: "School",
    *,
    organization_id: str,
    inherit_map: dict[str, str] | None = None,
) -> None:
    """
    Upgrade a standalone school into group membership (wizard completion).

    Does not run at signup — explicit operator action only.
    """
    from apps.governance.models import Organization
    from apps.governance.operating_modes import GovernanceOperatingMode

    org = Organization.objects.filter(pk=organization_id, is_active=True).first()
    if org is None:
        raise ValueError("organization_not_found")

    school.organization = org
    school.governance_operating_mode = GovernanceOperatingMode.GROUP_MEMBER
    settings_blob = dict(getattr(school, "settings", None) or {})
    merged = dict(inherit_map or {})
    for domain in KNOWN_INHERIT_DOMAINS:
        merged.setdefault(domain, "local")
    settings_blob[GOVERNANCE_INHERIT_SETTINGS_KEY] = merged
    school.settings = settings_blob
    school.save(
        update_fields=[
            "organization",
            "governance_operating_mode",
            "settings",
        ]
    )
