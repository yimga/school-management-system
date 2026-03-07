"""
Phase 6: Blueprint pack apply service.
Applying a BlueprintPack to a school creates a PolicyBundle and sets TenantBlueprint.active_bundle.
24.15: preview_blueprint_pack for preview/validation without apply; apply validates pack active.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.policies.models import BlueprintPack
    from apps.schools.models import School


def preview_blueprint_pack(school, pack) -> dict[str, Any]:
    """
    24.15: Preview what would be applied (policy keys, pack summary). No DB write.
    Returns dict with pack slug/name, policy_keys, current_bundle_id (if any).
    """
    from apps.policies.models import BlueprintPack, TenantBlueprint

    if not isinstance(pack, BlueprintPack):
        pack = BlueprintPack.objects.get(slug=pack) if isinstance(pack, str) else BlueprintPack.objects.get(pk=pack)
    snapshot = getattr(pack, "policy_snapshot", None) or {}
    policy_keys = list(snapshot.keys()) if isinstance(snapshot, dict) else []
    current_bundle_id = None
    if school:
        tb = TenantBlueprint.objects.filter(school=school).select_related("active_bundle").first()
        if tb and tb.active_bundle_id:
            current_bundle_id = tb.active_bundle_id
    return {
        "pack_slug": getattr(pack, "slug", ""),
        "pack_name": getattr(pack, "name", ""),
        "pack_version": getattr(pack, "version", ""),
        "policy_keys": policy_keys,
        "current_bundle_id": current_bundle_id,
    }


def apply_blueprint_pack(school, pack, *, applied_by=None):
    """
    Apply a BlueprintPack to a school: create a PolicyBundle from pack.policy_snapshot,
    set TenantBlueprint.active_bundle to it, invalidate policy cache.
    Returns the created/updated PolicyBundle.
    """
    from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
    from apps.policies.policy_registry import invalidate_policy_cache

    if not isinstance(pack, BlueprintPack):
        pack = BlueprintPack.objects.get(slug=pack) if isinstance(pack, str) else BlueprintPack.objects.get(pk=pack)
    if not pack.is_active:
        raise ValueError(f"Blueprint pack {pack.slug} is not active.")

    bundle = PolicyBundle.objects.create(
        school=school,
        name=f"{pack.name} (applied)",
        policy_snapshot=dict(pack.policy_snapshot),
        version=1,
        applied_pack_version=getattr(pack, "version", "") or "",
        is_active=True,
        created_by=applied_by,
    )
    tb, _ = TenantBlueprint.objects.get_or_create(
        school=school,
        defaults={"active_bundle": bundle, "applied_pack": pack},
    )
    if tb.active_bundle_id != bundle.pk or tb.applied_pack_id != pack.pk:
        tb.active_bundle = bundle
        tb.applied_pack = pack
        tb.save(update_fields=["active_bundle", "applied_pack", "updated_at"])
    invalidate_policy_cache(school)
    return bundle


def update_bundle_for_schools(pack, *, school_ids=None, applied_by=None):
    """
    Re-apply a BlueprintPack to schools that use it (e.g. when pack version increased).
    If school_ids is None, applies to all schools that have this pack applied and need update
    (active_bundle.applied_pack_version != pack.version).
    Returns list of (school, bundle) for each updated school.
    """
    from apps.policies.models import BlueprintPack
    if not isinstance(pack, BlueprintPack):
        pack = BlueprintPack.objects.get(slug=pack) if isinstance(pack, str) else BlueprintPack.objects.get(pk=pack)
    if school_ids is not None:
        schools = pack.get_schools_using_this_pack().filter(pk__in=school_ids)
    else:
        schools = pack.get_schools_needing_update()
    result = []
    for school in schools:
        try:
            bundle = apply_blueprint_pack(school, pack, applied_by=applied_by)
            result.append((school, bundle))
        except Exception:
            continue
    return result
