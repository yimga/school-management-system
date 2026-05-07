"""Impact analysis for installable packs."""

from __future__ import annotations

from apps.platform_runtime.pack_audit import audit_pack_event
from apps.platform_runtime.pack_contract import get_pack_or_raise
from apps.platform_runtime.pack_preview import preview_pack


def analyze_pack_impact(
    pack_key: str,
    *,
    pack_type: str | None = None,
    school=None,
    actor=None,
    platform_operator: bool = False,
    emit_audit: bool = False,
) -> dict:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    preview = preview_pack(pack.key, school=school, actor=actor, platform_operator=platform_operator)
    categories = ["low"]
    if pack.safety_level in {"medium", "high"}:
        categories.append(pack.safety_level)
    if pack.safety_level == "destructive":
        categories.append("destructive")
    if pack.external_dependencies:
        categories.append("external_required")
    if pack.approval_flows:
        categories.append("approval_required")
    if pack.platform_only and not platform_operator:
        categories.append("tenant_blocked")
        categories.append("platform_only")
    result = {
        "pack_key": pack.key,
        "pack_type": pack.pack_type,
        "impact_categories": list(dict.fromkeys(categories)),
        "requires_confirmation": pack.safety_level in {"medium", "high", "destructive"},
        "requires_simulation": pack.safety_level in {"high", "destructive"},
        "can_apply": preview["can_apply"],
        "conflicts": preview["conflicts"],
        "warnings": preview["warnings"],
        "affected_users": list(pack.target_roles),
        "affected_roles": list(pack.target_roles),
        "affected_routes": [f"/configuration/{pack.pack_type.replace('_', '-')}/{pack.key}/"],
        "affected_dashboards": list(pack.widgets),
        "affected_workflows": list(pack.triggers),
        "affected_policies": list(pack.rules),
        "billing_effects": {"live_psp_enabled": False, "package_metadata_only": True},
        "external_dependencies": list(pack.external_dependencies),
        "rollback_coverage": preview["rollback_posture"],
        "audit_coverage": ["pack_previewed", "pack_simulated", "pack_applied", "pack_rolled_back"],
    }
    if emit_audit:
        event = audit_pack_event(
            "pack_impact_viewed",
            pack_key=pack.key,
            pack_type=pack.pack_type,
            school=school,
            actor=actor,
            result="blocked" if result["conflicts"] else "ok",
            payload={"impact_categories": result["impact_categories"]},
        )
        if event:
            result["audit_id"] = event.pk
    return result
