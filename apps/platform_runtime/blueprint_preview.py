"""Preview engine for blueprint marketplace installs."""

from __future__ import annotations

from typing import Any

from django.db.models import Count

from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.blueprint_contract import BlueprintContract, get_blueprint_or_raise


def _change_rows(blueprint: BlueprintContract) -> list[dict[str, Any]]:
    sections = (
        ("module", blueprint.modules),
        ("role", blueprint.roles),
        ("permission", blueprint.permissions),
        ("dashboard_pack", blueprint.dashboard_packs),
        ("workflow_pack", blueprint.workflow_packs),
        ("policy_bundle", blueprint.policy_bundles),
        ("metadata_template", blueprint.metadata_templates),
        ("report_template", blueprint.report_templates),
    )
    changes: list[dict[str, Any]] = []
    for section, values in sections:
        for value in values:
            changes.append(
                {
                    "section": section,
                    "operation": "enable_or_update",
                    "target": value,
                    "destructive": False,
                    "rollback": "deactivate_marker",
                }
            )
    changes.append(
        {
            "section": "billing_defaults",
            "operation": "metadata_ready_update",
            "target": blueprint.billing_defaults.get("plan", ""),
            "destructive": False,
            "rollback": "restore_previous_school_settings",
        }
    )
    changes.append(
        {
            "section": "offline_defaults",
            "operation": "metadata_ready_update",
            "target": blueprint.offline_defaults.get("mode", ""),
            "destructive": False,
            "rollback": "restore_previous_school_settings",
        }
    )
    return changes


def _tenant_counts(school) -> dict[str, int]:
    if school is None:
        return {}
    from apps.platform_runtime.models import BlueprintInstallation

    return {
        "blueprint_installations": BlueprintInstallation.objects.filter(
            school=school
        ).count(),
        "active_same_blueprint": 0,
    }


def preview_blueprint(
    blueprint_key: str,
    *,
    school=None,
    actor=None,
    platform_operator: bool = False,
    emit_audit: bool = False,
) -> dict[str, Any]:
    blueprint = get_blueprint_or_raise(blueprint_key)
    conflicts: list[dict[str, str]] = []
    warnings: list[str] = []
    safety_notes: list[str] = []

    if school is None and blueprint.tenant_scoped:
        conflicts.append(
            {
                "code": "tenant_required",
                "message": "Tenant school is required before applying this blueprint.",
            }
        )
    if blueprint.requires_platform_operator and not platform_operator:
        conflicts.append(
            {
                "code": "platform_operator_required",
                "message": "This blueprint requires a platform operator.",
            }
        )
    if not blueprint.tenant_safe and not platform_operator:
        conflicts.append(
            {
                "code": "tenant_blocked",
                "message": "Tenant users cannot apply this blueprint directly.",
            }
        )
    if blueprint.status not in {"preview_ready", "installable"}:
        conflicts.append(
            {
                "code": "not_installable",
                "message": f"Blueprint status is {blueprint.status}.",
            }
        )
    if blueprint.external_required:
        warnings.append("External dependencies remain required and are not marked complete.")
        safety_notes.append("Live PSP, settlement, and external certification readiness are not enabled by this blueprint.")

    changes = _change_rows(blueprint)
    external_required = list(blueprint.external_required_items or blueprint.external_dependencies)
    can_apply = (
        blueprint.apply_available
        and blueprint.status == "installable"
        and not conflicts
        and school is not None
    )
    rollback_plan = {
        "available": blueprint.rollback_available,
        "strategy": "deactivate blueprint marker and restore previous school settings snapshot",
        "non_reversible": list(external_required),
        "destructive_delete": False,
    }
    result = {
        "blueprint_key": blueprint.key,
        "blueprint_name": blueprint.name,
        "blueprint_version": blueprint.version,
        "tenant": str(getattr(school, "pk", "") or ""),
        "tenant_name": getattr(school, "name", "") or "",
        "can_apply": can_apply,
        "requires_confirmation": blueprint.requires_confirmation,
        "changes": changes,
        "conflicts": conflicts,
        "warnings": warnings,
        "external_required": external_required,
        "tenant_safety_notes": safety_notes,
        "rollback_plan": rollback_plan,
        "audit_summary": {
            "audit_required": blueprint.audit_required,
            "events": [
                "blueprint_previewed",
                "blueprint_apply_requested",
                "blueprint_applied",
                "blueprint_rollback_requested",
                "blueprint_rolled_back",
            ],
            "tenant_counts": _tenant_counts(school),
        },
        "implementation_checklist": list(blueprint.implementation_checklist),
        "package_payload": {
            "blueprint": {
                "key": blueprint.key,
                "modules": list(blueprint.modules),
                "roles": list(blueprint.roles),
                "dashboard_packs": list(blueprint.dashboard_packs),
                "workflow_packs": list(blueprint.workflow_packs),
                "policy_bundles": list(blueprint.policy_bundles),
                "metadata_templates": list(blueprint.metadata_templates),
            }
        },
    }
    if emit_audit:
        event = audit_blueprint_event(
            "blueprint_previewed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked" if conflicts else "ok",
            payload={"can_apply": can_apply},
        )
        if event:
            result["audit_summary"]["last_audit_id"] = event.pk
    return result


def preview_mutation_fingerprint(school) -> dict[str, Any]:
    """Small helper used by tests to prove preview is read-only."""
    from apps.platform_runtime.models import BlueprintInstallation, PlatformEventLog

    return {
        "installations": BlueprintInstallation.objects.filter(school=school).count()
        if school
        else BlueprintInstallation.objects.count(),
        "events": PlatformEventLog.objects.values("event_type").annotate(n=Count("id")).count(),
        "settings": dict(getattr(school, "settings", {}) or {}) if school else {},
    }
