"""
Backfill Organization rows from existing hierarchy silos (Phase 6B).

Only touches schools already linked via ``parent_school`` or listed in legacy
``mat_groups`` JSON. Standalone schools without hierarchy are never modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.governance.mat_groups_sync import load_legacy_mat_groups_payload
from apps.governance.models import Organization
from apps.governance.operating_modes import GovernanceOperatingMode
from apps.schools.models import School


@dataclass
class BackfillOrganizationsResult:
    organizations_created: int = 0
    schools_linked: int = 0
    schools_skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "organizations_created": self.organizations_created,
            "schools_linked": self.schools_linked,
            "schools_skipped": self.schools_skipped,
            "notes": list(self.notes),
        }


def _ensure_organization(
    *,
    slug: str,
    name: str,
    apply: bool,
    result: BackfillOrganizationsResult,
) -> Organization | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    existing = Organization.objects.filter(slug=slug).first()
    if existing:
        return existing
    if not apply:
        result.organizations_created += 1
        result.notes.append(f"would create Organization slug={slug!r} name={name!r}")
        return None
    org = Organization.objects.create(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        legal_owner_type=Organization.LegalOwnerType.CORPORATION,
    )
    result.organizations_created += 1
    result.notes.append(f"created Organization slug={slug!r}")
    return org


def _link_school_to_org(
    school: School,
    org: Organization | None,
    *,
    org_slug: str,
    apply: bool,
    promote_group_mode: bool,
    result: BackfillOrganizationsResult,
) -> None:
    if school.organization_id is not None:
        result.schools_skipped += 1
        return
    if org is None and not apply:
        result.schools_linked += 1
        result.notes.append(
            f"would link School slug={school.slug!r} → Organization slug={org_slug!r}"
        )
        return
    if org is None:
        result.schools_skipped += 1
        return
    if not apply:
        result.schools_linked += 1
        result.notes.append(
            f"would link School slug={school.slug!r} → Organization {org.slug!r}"
        )
        return
    school.organization = org
    update_fields = ["organization"]
    if promote_group_mode and school.governance_operating_mode == GovernanceOperatingMode.STANDALONE:
        school.governance_operating_mode = GovernanceOperatingMode.GROUP_MEMBER
        update_fields.append("governance_operating_mode")
    school.save(update_fields=update_fields)
    result.schools_linked += 1


def backfill_from_legacy_mat_groups(
    *,
    apply: bool = False,
    promote_group_mode: bool = False,
) -> BackfillOrganizationsResult:
    """Create Organization rows from operator ``mat_groups`` JSON member lists."""
    result = BackfillOrganizationsResult()
    payload = load_legacy_mat_groups_payload()
    if not payload:
        result.notes.append("no legacy mat_groups payload")
        return result

    for group_id, group_data in payload.items():
        if not isinstance(group_id, str) or not isinstance(group_data, dict):
            continue
        members = group_data.get("members")
        if not isinstance(members, list) or not members:
            continue
        display_name = (group_data.get("display_name") or group_id).strip()
        org = _ensure_organization(
            slug=group_id,
            name=display_name,
            apply=apply,
            result=result,
        )
        if apply and org is None:
            org = Organization.objects.filter(slug=group_id).first()
        for raw_member in members:
            if not isinstance(raw_member, dict):
                continue
            tenant_slug = (raw_member.get("tenant_slug") or "").strip()
            if not tenant_slug:
                continue
            school = School.objects.filter(slug=tenant_slug, is_active=True).first()
            if school is None:
                result.notes.append(f"mat_groups member slug={tenant_slug!r} not found")
                continue
            _link_school_to_org(
                school,
                org,
                org_slug=group_id,
                apply=apply,
                promote_group_mode=promote_group_mode,
                result=result,
            )
    return result


def _collect_parent_school_roots() -> dict[int, list[School]]:
    """Map root school pk → all schools in its parent_school subtree (inclusive)."""
    schools = list(School.objects.filter(is_active=True).only("pk", "slug", "name", "parent_school_id", "organization_id"))
    by_pk = {s.pk: s for s in schools}
    components: dict[int, list[School]] = {}

    def root_pk(school: School) -> int:
        current = school
        seen: set[int] = set()
        while current.parent_school_id and current.parent_school_id not in seen:
            seen.add(current.pk)
            parent = by_pk.get(current.parent_school_id)
            if parent is None:
                break
            current = parent
        return current.pk

    for school in schools:
        if school.parent_school_id is None:
            children = [s for s in schools if s.parent_school_id == school.pk]
            if not children:
                continue
        root_id = root_pk(school)
        components.setdefault(root_id, [])
        if school not in components[root_id]:
            components[root_id].append(school)

    for root_id, members in list(components.items()):
        root = by_pk.get(root_id)
        if root is not None and root not in members:
            members.insert(0, root)
        if len(members) < 2:
            del components[root_id]
    return components


def backfill_from_parent_school_trees(
    *,
    apply: bool = False,
    promote_group_mode: bool = False,
) -> BackfillOrganizationsResult:
    """Create Organization per parent_school root that has at least one child."""
    result = BackfillOrganizationsResult()
    components = _collect_parent_school_roots()
    if not components:
        result.notes.append("no parent_school hierarchies")
        return result

    for root_id, members in components.items():
        root = next((s for s in members if s.pk == root_id), members[0])
        org_slug = (root.slug or f"school-{root.pk}").strip()
        org_name = (root.name or org_slug).strip()
        org = _ensure_organization(slug=org_slug, name=org_name, apply=apply, result=result)
        if apply and org is None:
            org = Organization.objects.filter(slug=org_slug).first()
        for school in members:
            _link_school_to_org(
                school,
                org,
                org_slug=org_slug,
                apply=apply,
                promote_group_mode=promote_group_mode,
                result=result,
            )
    return result


def backfill_organizations_from_hierarchy(
    *,
    apply: bool = False,
    promote_group_mode: bool = False,
    include_mat_groups: bool = True,
    include_parent_school: bool = True,
) -> BackfillOrganizationsResult:
    """Run mat_groups + parent_school backfill passes (idempotent)."""
    combined = BackfillOrganizationsResult()
    passes: list[BackfillOrganizationsResult] = []
    if include_mat_groups:
        passes.append(backfill_from_legacy_mat_groups(apply=apply, promote_group_mode=promote_group_mode))
    if include_parent_school:
        passes.append(
            backfill_from_parent_school_trees(apply=apply, promote_group_mode=promote_group_mode)
        )
    for partial in passes:
        combined.organizations_created += partial.organizations_created
        combined.schools_linked += partial.schools_linked
        combined.schools_skipped += partial.schools_skipped
        combined.notes.extend(partial.notes)
    return combined
