"""Dependency graph helpers for blueprint and pack governed installs."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.blueprint_composition import (
    composition_conflicts,
    effective_installed_blueprint_keys,
)
from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_contract import get_pack_or_raise


def _installed_pack_keys(school) -> set[str]:
    if school is None:
        return set()
    return set(
        PackInstallation.objects.filter(
            school=school,
            status=PackInstallation.Status.APPLIED,
        ).values_list("pack_key", flat=True)
    )


def _installed_blueprint_keys(school) -> set[str]:
    return set(effective_installed_blueprint_keys(school))


def resolve_pack_dependencies(pack_key: str, *, pack_type: str | None = None, school=None) -> dict[str, Any]:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    installed = _installed_pack_keys(school)
    missing_packs = [key for key in pack.requires_packs if key not in installed]
    recommended_missing = [key for key in pack.recommends_packs if key not in installed]
    return {
        "target_type": pack.pack_type,
        "target_key": pack.key,
        "requires_packs": list(pack.requires_packs),
        "requires_modules": list(pack.requires_modules),
        "requires_roles": list(pack.requires_roles),
        "requires_features": list(pack.requires_features),
        "recommended_with": list(pack.recommends_packs),
        "missing_required_packs": missing_packs,
        "recommended_missing": recommended_missing,
        "blocked_by_external": list(pack.blocked_by_external or pack.external_dependencies),
        "blocked_by_plan": list(pack.blocked_by_plan),
        "blocked_by_missing_setup": list(pack.blocked_by_missing_setup),
    }


def resolve_blueprint_dependencies(blueprint_key: str, *, school=None) -> dict[str, Any]:
    blueprint = get_blueprint_or_raise(blueprint_key)
    pack_keys = set(blueprint.dashboard_packs + blueprint.workflow_packs + blueprint.policy_bundles)
    installed = _installed_pack_keys(school)
    missing = sorted(key for key in blueprint.requires_packs if key not in installed)
    return {
        "target_type": "blueprint",
        "target_key": blueprint.key,
        "requires_packs": list(blueprint.requires_packs),
        "included_pack_aliases": sorted(pack_keys),
        "requires_modules": list(blueprint.requires_modules or blueprint.modules),
        "requires_roles": list(blueprint.requires_roles or blueprint.roles),
        "requires_features": list(blueprint.requires_features),
        "recommended_with": list(blueprint.recommends_packs),
        "missing_required_packs": missing,
        "blocked_by_external": list(blueprint.blocked_by_external or blueprint.external_dependencies),
        "blocked_by_plan": list(blueprint.blocked_by_plan),
        "blocked_by_missing_setup": list(blueprint.blocked_by_missing_setup),
    }


def detect_dependency_conflicts(
    target_key: str,
    *,
    target_type: str,
    pack_type: str | None = None,
    school=None,
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    if target_type == "blueprint":
        target = get_blueprint_or_raise(target_key)
        # The declared composition model is the real source of blueprint-level
        # conflicts. Reading only conflicts_with_blueprints made this a dead
        # guard: no contract in the catalog populates that tuple, so it returned
        # [] unconditionally and always had.
        conflicts.extend(composition_conflicts(target, school=school))
        installed_blueprints = _installed_blueprint_keys(school)
        for key in target.conflicts_with_blueprints:
            if key in installed_blueprints:
                conflicts.append({"code": "blueprint_conflict", "target": key})
        installed_packs = _installed_pack_keys(school)
        for key in target.conflicts_with_packs:
            if key in installed_packs:
                conflicts.append({"code": "pack_conflict", "target": key})
    else:
        target = get_pack_or_raise(target_key, pack_type=pack_type)
        installed_packs = _installed_pack_keys(school)
        for key in target.conflicts_with_packs:
            if key in installed_packs:
                conflicts.append({"code": "pack_conflict", "target": key})
        installed_blueprints = _installed_blueprint_keys(school)
        for key in target.conflicts_with_blueprints:
            if key in installed_blueprints:
                conflicts.append({"code": "blueprint_conflict", "target": key})
    return conflicts


def detect_missing_prerequisites(
    target_key: str,
    *,
    target_type: str,
    pack_type: str | None = None,
    school=None,
) -> list[dict[str, str]]:
    dependencies = (
        resolve_blueprint_dependencies(target_key, school=school)
        if target_type == "blueprint"
        else resolve_pack_dependencies(target_key, pack_type=pack_type, school=school)
    )
    blockers = [{"code": "missing_required_pack", "target": key} for key in dependencies["missing_required_packs"]]
    blockers.extend({"code": "external_required", "target": key} for key in dependencies["blocked_by_external"])
    blockers.extend({"code": "plan_blocked", "target": key} for key in dependencies["blocked_by_plan"])
    blockers.extend({"code": "missing_setup", "target": key} for key in dependencies["blocked_by_missing_setup"])
    return blockers


def order_installation_plan(pack_keys: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        try:
            pack = get_pack_or_raise(key)
        except KeyError:
            ordered.append(key)
            return
        for dependency in sorted(pack.requires_packs):
            visit(dependency)
        ordered.append(pack.key)

    for key in sorted(pack_keys):
        visit(key)
    return ordered


def explain_dependency_blockers(blockers: list[dict[str, str]]) -> list[str]:
    messages = []
    for blocker in blockers:
        code = blocker.get("code")
        target = blocker.get("target", "")
        if code == "missing_required_pack":
            messages.append(f"Required pack is not installed: {target}.")
        elif code == "incompatible_base_blueprint":
            messages.append(
                f"A different school operating model is already applied: {target}. "
                f"Roll it back before applying another base blueprint."
            )
        elif code == "external_required":
            messages.append(f"External proof remains required: {target}.")
        elif code == "pack_conflict":
            messages.append(f"Conflicting pack is already installed: {target}.")
        elif code == "blueprint_conflict":
            messages.append(f"Conflicting blueprint is already installed: {target}.")
        else:
            messages.append(f"Dependency blocker: {target}.")
    return messages
