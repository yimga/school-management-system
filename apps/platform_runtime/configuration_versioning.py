"""Version and upgrade helpers for blueprint and pack installations."""

from __future__ import annotations

from django.utils import timezone

from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation, PackInstallation
from apps.platform_runtime.pack_contract import get_pack_or_raise
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack


def detect_blueprint_upgrade(installation: BlueprintInstallation) -> dict:
    blueprint = get_blueprint_or_raise(installation.blueprint_key)
    installed = installation.installed_version or installation.blueprint_version
    available = blueprint.version
    return {
        "upgrade_available": installed != available,
        "installed_version": installed,
        "available_version": available,
    }


def preview_blueprint_upgrade(installation: BlueprintInstallation, *, actor=None) -> dict:
    upgrade = detect_blueprint_upgrade(installation)
    preview = preview_blueprint(installation.blueprint_key, school=installation.school, actor=actor, platform_operator=True)
    impact = analyze_blueprint_impact(installation.blueprint_key, school=installation.school, actor=actor, platform_operator=True)
    installation.available_version = upgrade["available_version"]
    installation.upgrade_available = upgrade["upgrade_available"]
    installation.upgrade_status = "previewed" if upgrade["upgrade_available"] else "current"
    installation.upgrade_preview_snapshot = preview
    installation.upgrade_impact_snapshot = impact
    installation.save(update_fields=["available_version", "upgrade_available", "upgrade_status", "upgrade_preview_snapshot", "upgrade_impact_snapshot", "updated_at"])
    return {"upgrade": upgrade, "preview": preview, "impact": impact}


def apply_blueprint_upgrade(installation: BlueprintInstallation, *, actor=None, approved: bool = False) -> dict:
    if not installation.upgrade_preview_snapshot:
        return {"ok": False, "errors": ["Upgrade must be previewed first."]}
    risk = set(installation.upgrade_impact_snapshot.get("impact_categories") or [])
    if risk & {"medium", "high", "destructive", "external_required"} and not approved:
        return {"ok": False, "errors": ["Upgrade requires approval."]}
    upgrade = detect_blueprint_upgrade(installation)
    installation.previous_version = installation.installed_version or installation.blueprint_version
    installation.installed_version = upgrade["available_version"]
    installation.blueprint_version = upgrade["available_version"]
    installation.available_version = upgrade["available_version"]
    installation.upgrade_available = False
    installation.upgrade_status = "applied"
    installation.applied_at = installation.applied_at or timezone.now()
    installation.save()
    return {"ok": True, "previous_version": installation.previous_version, "installed_version": installation.installed_version}


def detect_pack_upgrade(installation: PackInstallation) -> dict:
    pack = get_pack_or_raise(installation.pack_key, pack_type=installation.pack_type)
    installed = installation.installed_version or installation.version
    available = pack.version
    return {
        "upgrade_available": installed != available,
        "installed_version": installed,
        "available_version": available,
    }


def preview_pack_upgrade(installation: PackInstallation, *, actor=None) -> dict:
    upgrade = detect_pack_upgrade(installation)
    preview = preview_pack(installation.pack_key, pack_type=installation.pack_type, school=installation.school, actor=actor, platform_operator=True)
    impact = analyze_pack_impact(installation.pack_key, pack_type=installation.pack_type, school=installation.school, actor=actor, platform_operator=True)
    installation.available_version = upgrade["available_version"]
    installation.upgrade_available = upgrade["upgrade_available"]
    installation.upgrade_status = "previewed" if upgrade["upgrade_available"] else "current"
    installation.upgrade_preview_snapshot = preview
    installation.upgrade_impact_snapshot = impact
    installation.save(update_fields=["available_version", "upgrade_available", "upgrade_status", "upgrade_preview_snapshot", "upgrade_impact_snapshot", "updated_at"])
    return {"upgrade": upgrade, "preview": preview, "impact": impact}


def apply_pack_upgrade(installation: PackInstallation, *, actor=None, approved: bool = False) -> dict:
    if not installation.upgrade_preview_snapshot:
        return {"ok": False, "errors": ["Upgrade must be previewed first."]}
    risk = set(installation.upgrade_impact_snapshot.get("impact_categories") or [])
    if risk & {"medium", "high", "destructive", "external_required"} and not approved:
        return {"ok": False, "errors": ["Upgrade requires approval."]}
    if installation.external_blockers:
        return {"ok": False, "errors": ["External readiness cannot be upgraded to live without proof."]}
    upgrade = detect_pack_upgrade(installation)
    installation.previous_version = installation.installed_version or installation.version
    installation.installed_version = upgrade["available_version"]
    installation.version = upgrade["available_version"]
    installation.available_version = upgrade["available_version"]
    installation.upgrade_available = False
    installation.upgrade_status = "applied"
    installation.applied_at = installation.applied_at or timezone.now()
    installation.save()
    return {"ok": True, "previous_version": installation.previous_version, "installed_version": installation.installed_version}
