"""Non-mutating preview engine for installable packs."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.pack_audit import audit_pack_event
from apps.platform_runtime.pack_contract import PackContract, get_pack_or_raise


def _changes(pack: PackContract) -> list[dict[str, Any]]:
    rows = []
    for item in pack.included_items:
        rows.append(
            {
                "section": pack.pack_type,
                "operation": "install_or_update",
                "target": item,
                "destructive": False,
                "rollback": "deactivate_pack_marker",
            }
        )
    return rows


def preview_pack(
    pack_key: str,
    *,
    pack_type: str | None = None,
    school=None,
    actor=None,
    platform_operator: bool = False,
    emit_audit: bool = False,
) -> dict[str, Any]:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    conflicts: list[dict[str, str]] = []
    warnings: list[str] = []
    if school is None and pack.tenant_scope == "tenant":
        conflicts.append({"code": "tenant_required", "message": "Tenant school is required."})
    if pack.platform_only and not platform_operator:
        conflicts.append({"code": "platform_only", "message": "This pack requires a platform operator."})
    if not pack.tenant_safe and not platform_operator:
        conflicts.append({"code": "tenant_blocked", "message": "Tenant users cannot apply this pack directly."})
    if pack.status != "installable":
        conflicts.append({"code": "not_installable", "message": f"Pack status is {pack.status}."})
    if pack.external_dependencies:
        warnings.append("External dependencies remain required and are not marked complete.")
    can_apply = pack.apply_available and not conflicts and school is not None
    result = {
        "pack_key": pack.key,
        "pack_name": pack.name,
        "pack_type": pack.pack_type,
        "version": pack.version,
        "tenant": str(getattr(school, "pk", "") or ""),
        "tenant_name": getattr(school, "name", "") or "",
        "included_changes": _changes(pack),
        "prerequisites": list(pack.prerequisites),
        "conflicts": conflicts,
        "warnings": warnings,
        "external_required": list(pack.external_dependencies),
        "affected_roles": list(pack.target_roles),
        "affected_dashboards": list(pack.widgets if pack.pack_type == "dashboard_pack" else ()),
        "affected_workflows": list(pack.triggers if pack.pack_type == "workflow_pack" else ()),
        "affected_policies": list(pack.rules if pack.pack_type == "policy_bundle" else ()),
        "rollback_posture": {
            "available": pack.rollback_available,
            "strategy": "deactivate installation marker and restore captured school settings",
            "destructive_delete": False,
            "manual_review": pack.safety_level in {"high", "destructive"},
        },
        "can_apply": can_apply,
        "requires_confirmation": pack.safety_level in {"medium", "high", "destructive"},
        "requires_simulation": pack.safety_level in {"high", "destructive"},
        "package_payload": pack.package_payload(),
    }
    if emit_audit:
        event = audit_pack_event(
            "pack_previewed",
            pack_key=pack.key,
            pack_type=pack.pack_type,
            school=school,
            actor=actor,
            result="blocked" if conflicts else "ok",
            payload={"can_apply": can_apply},
        )
        if event:
            result["audit_id"] = event.pk
    return result
