"""Formal non-mutating change sets for blueprint and pack installs."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.pack_contract import get_pack_or_raise
from apps.platform_runtime.pack_dependency_graph import (
    detect_dependency_conflicts,
    detect_missing_prerequisites,
    explain_dependency_blockers,
    resolve_blueprint_dependencies,
    resolve_pack_dependencies,
)
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_simulation import simulate_pack


APPROVAL_RISK_LEVELS = {"high", "destructive", "external_required", "platform_only"}


def _risk_from_impact(impact: dict[str, Any]) -> str:
    categories = set(impact.get("impact_categories") or [])
    if "destructive" in categories:
        return "destructive"
    if "high" in categories:
        return "high"
    if "external_required" in categories:
        return "high"
    if "medium" in categories:
        return "medium"
    return "low"


def _requires_approval(*, risk_level: str, platform_only: bool, target_type: str) -> bool:
    return platform_only or risk_level in APPROVAL_RISK_LEVELS or target_type == "policy_bundle"


def generate_pack_change_set(
    pack_key: str,
    *,
    pack_type: str | None = None,
    school=None,
    actor=None,
    platform_operator: bool = False,
) -> dict[str, Any]:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    preview = preview_pack(pack.key, pack_type=pack.pack_type, school=school, actor=actor, platform_operator=platform_operator)
    impact = analyze_pack_impact(pack.key, pack_type=pack.pack_type, school=school, actor=actor, platform_operator=platform_operator)
    simulation = simulate_pack(pack.key, pack_type=pack.pack_type, school=school, actor=actor, platform_operator=platform_operator) if impact.get("requires_simulation") else {}
    dependencies = resolve_pack_dependencies(pack.key, pack_type=pack.pack_type, school=school)
    blockers = detect_missing_prerequisites(pack.key, target_type=pack.pack_type, pack_type=pack.pack_type, school=school)
    conflicts = detect_dependency_conflicts(pack.key, target_type=pack.pack_type, pack_type=pack.pack_type, school=school)
    risk_level = _risk_from_impact(impact)
    can_apply = bool(preview.get("can_apply")) and not blockers and not conflicts
    return {
        "target_type": pack.pack_type,
        "target_key": pack.key,
        "target_version": pack.version,
        "tenant": str(getattr(school, "pk", "") or ""),
        "tenant_name": getattr(school, "name", "") or "",
        "preview_summary": preview,
        "simulation_summary": simulation,
        "impact_summary": impact,
        "dependencies": dependencies,
        "conflicts": list(preview.get("conflicts") or []) + conflicts,
        "warnings": list(preview.get("warnings") or []) + explain_dependency_blockers(
            [{"code": "recommended_missing", "target": key} for key in dependencies.get("recommended_missing", [])]
        ),
        "external_blockers": dependencies.get("blocked_by_external", []),
        "rollback_coverage": preview.get("rollback_posture", {}),
        "can_apply": can_apply,
        "requires_approval": _requires_approval(risk_level=risk_level, platform_only=pack.platform_only, target_type=pack.pack_type),
        "requires_confirmation": bool(preview.get("requires_confirmation")),
        "risk_level": risk_level,
        "dependency_blockers": blockers,
        "generated_at": timezone.now().isoformat(),
        "generated_by": str(getattr(actor, "pk", "") or ""),
    }


def generate_blueprint_change_set(
    blueprint_key: str,
    *,
    school=None,
    actor=None,
    platform_operator: bool = False,
) -> dict[str, Any]:
    blueprint = get_blueprint_or_raise(blueprint_key)
    preview = preview_blueprint(blueprint.key, school=school, actor=actor, platform_operator=platform_operator)
    impact = analyze_blueprint_impact(blueprint.key, school=school, actor=actor, platform_operator=platform_operator)
    dependencies = resolve_blueprint_dependencies(blueprint.key, school=school)
    blockers = detect_missing_prerequisites(blueprint.key, target_type="blueprint", school=school)
    conflicts = detect_dependency_conflicts(blueprint.key, target_type="blueprint", school=school)
    risk_level = _risk_from_impact(impact)
    can_apply = bool(preview.get("can_apply")) and not blockers and not conflicts
    return {
        "target_type": "blueprint",
        "target_key": blueprint.key,
        "target_version": blueprint.version,
        "tenant": str(getattr(school, "pk", "") or ""),
        "tenant_name": getattr(school, "name", "") or "",
        "preview_summary": preview,
        "simulation_summary": {},
        "impact_summary": impact,
        "dependencies": dependencies,
        "conflicts": list(preview.get("conflicts") or []) + conflicts,
        "warnings": list(preview.get("warnings") or []),
        "external_blockers": dependencies.get("blocked_by_external", []),
        "rollback_coverage": preview.get("rollback_plan", {}),
        "can_apply": can_apply,
        "requires_approval": blueprint.platform_only or "destructive" in impact.get("impact_categories", []) or bool(dependencies.get("blocked_by_external")),
        "requires_confirmation": bool(preview.get("requires_confirmation")),
        "risk_level": risk_level,
        "dependency_blockers": blockers,
        "generated_at": timezone.now().isoformat(),
        "generated_by": str(getattr(actor, "pk", "") or ""),
    }


def assert_change_set_fresh(change_set: dict[str, Any]) -> None:
    target_type = change_set.get("target_type")
    target_key = change_set.get("target_key")
    expected = change_set.get("target_version")
    if target_type == "blueprint":
        current = get_blueprint_or_raise(target_key).version
    else:
        current = get_pack_or_raise(target_key, pack_type=target_type).version
    if current != expected:
        raise ValueError("Change set is stale because the target version changed.")
