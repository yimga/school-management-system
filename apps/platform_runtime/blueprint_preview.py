"""Preview engine for blueprint marketplace installs."""

from __future__ import annotations

from typing import Any

from django.db.models import Count

from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.blueprint_contract import BlueprintContract, get_blueprint_or_raise
from apps.platform_runtime.pack_preview import preview_pack


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
    changes.append(
        {
            "section": "local_first_manifest",
            "operation": "activate_manifest",
            "target": blueprint.local_first_manifest_payload.get("server_proof_status", "unproven"),
            "destructive": False,
            "rollback": "invalidate_offline_manifest_and_restore_previous_school_settings",
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


def _offline_readiness(
    blueprint: BlueprintContract,
    manifest: dict[str, Any],
    *,
    external_required: list[str],
) -> dict[str, Any]:
    """Offline proof posture — scored on offline evidence ALONE.

    A go-live payment/settlement requirement says nothing about whether the
    client survives a restart, so it is reported alongside (``external_blockers``)
    and never folded into ``status``. It used to be: a non-empty
    ``external_required`` overwrote the verdict with a composite
    ``READY_WITH_EXTERNAL_BLOCKERS`` that downstream readiness scoring counted as
    *ready*, so a blueprint carrying a payment blocker scored HIGHER than a clean
    one. Two independent dimensions, two independent fields.
    """
    browser_partial = str(manifest.get("browser_proof_status", "")).startswith("PARTIAL")
    proof_status = "PARTIAL" if browser_partial else "READY"
    target_days = int(manifest.get("offline_survival_target_days") or 0)
    cached_surfaces = list(manifest.get("cached_surfaces") or [])
    offline_actions = list(manifest.get("offline_actions") or [])
    proof_detail = str(manifest.get("browser_proof_detail") or "")
    return {
        "status": proof_status,
        "mode": blueprint.offline_defaults.get("mode", "standard"),
        "coverage": blueprint.offline_defaults.get("coverage", ""),
        "survival_target_days": target_days,
        "cached_surface_count": len(cached_surfaces),
        "offline_action_count": len(offline_actions),
        "browser_proof_status": manifest.get("browser_proof_status"),
        "browser_proof_reason": manifest.get("browser_proof_reason", ""),
        "server_proof_status": manifest.get("server_proof_status"),
        # Reported, not scored: these gate live collection, not offline survival.
        "external_blockers": list(external_required),
        "external_blocked": bool(external_required),
        "honesty_note": (
            f"Server rails are represented; client proof is pending. {proof_detail}".strip()
            if browser_partial
            else f"Server and browser proof are both recorded. {proof_detail}".strip()
        ),
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
    if blueprint.status != "installable":
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
    local_first_manifest = blueprint.local_first_manifest_payload
    offline_readiness = _offline_readiness(
        blueprint,
        local_first_manifest,
        external_required=external_required,
    )
    # Status is gated via conflicts (same shape as pack_preview): preview_ready
    # must surface a blocker, not a silent disabled Apply with empty conflicts.
    can_apply = (
        blueprint.apply_available
        and not conflicts
        and school is not None
    )
    rollback_plan = {
        "available": blueprint.rollback_available,
        "strategy": "deactivate blueprint marker, restore previous school settings snapshot, and invalidate offline manifest",
        "non_reversible": list(external_required),
        "destructive_delete": False,
        "offline_manifest_invalidation": local_first_manifest.get(
            "rollback_invalidation",
            {},
        ),
    }
    composition_guidance = {
        "role": blueprint.composition_role,
        "compatible_blueprints": list(blueprint.compatible_blueprints),
        "regional_overlays": list(blueprint.regional_overlays),
        "education_tracks": list(blueprint.education_tracks),
        "local_constraints": list(blueprint.local_constraints),
        "note": (
            "Use this as an overlay with a base school blueprint."
            if blueprint.composition_role.endswith("overlay")
            else "Use this as a base operating model; add overlays for region, language, boarding, or offline needs."
        ),
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
        "local_first_manifest": local_first_manifest,
        "offline_readiness": offline_readiness,
        "outage_survival_matrix": {
            "target_days": local_first_manifest.get("offline_survival_target_days"),
            "works_offline": list(local_first_manifest.get("cached_surfaces") or []),
            "queued_actions": list(local_first_manifest.get("offline_actions") or []),
            "manual_fallbacks": list(local_first_manifest.get("manual_fallbacks") or []),
            "proof_status": offline_readiness["status"],
        },
        "device_role_impacts": [
            {
                "role": role,
                "offline_access": role in set(local_first_manifest.get("device_roles") or []),
                "sync_cadence": local_first_manifest.get("sync_cadence", {}),
            }
            for role in blueprint.roles
        ],
        "conflict_policy_by_domain": local_first_manifest.get("conflict_policies", {}),
        "composition_guidance": composition_guidance,
        "app_catalog_recommendations": list(blueprint.app_catalog_recommendations),
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
    pack_sections = (
        ("workflow_pack", blueprint.workflow_packs, "workflow_pack"),
        ("dashboard_pack", blueprint.dashboard_packs, "dashboard_pack"),
        ("policy_bundle", blueprint.policy_bundles, "policy_bundle"),
    )
    pack_previews: list[dict[str, Any]] = []
    pack_install_blockers: list[dict[str, str]] = []
    for section, refs, pack_type in pack_sections:
        for ref in refs:
            try:
                pack_preview = preview_pack(
                    ref,
                    pack_type=pack_type,
                    school=school,
                    actor=actor,
                    platform_operator=platform_operator,
                )
                pack_previews.append(
                    {
                        "section": section,
                        "reference": ref,
                        "pack_key": pack_preview["pack_key"],
                        "pack_type": pack_preview["pack_type"],
                        "can_apply": pack_preview["can_apply"],
                        "simulation_ready": not pack_preview.get("requires_simulation")
                        or bool(pack_preview.get("can_apply")),
                        "impact_targets": len(pack_preview.get("included_changes", [])),
                        "external_required": pack_preview.get("external_required", []),
                        "rollback_posture": pack_preview.get("rollback_posture", {}),
                    }
                )
                if not pack_preview["can_apply"]:
                    pack_install_blockers.extend(pack_preview.get("conflicts", []))
            except (KeyError, ValueError) as exc:
                pack_install_blockers.append(
                    {"code": "pack_not_found", "message": f"{ref}: {exc}"}
                )
    result["pack_previews"] = pack_previews
    result["pack_simulation_readiness"] = [
        {"pack_key": row["pack_key"], "ready": row["simulation_ready"]}
        for row in pack_previews
    ]
    result["pack_impact_results"] = [
        {
            "pack_key": row["pack_key"],
            "impact_targets": row["impact_targets"],
            "external_required": row["external_required"],
        }
        for row in pack_previews
    ]
    result["pack_install_blockers"] = pack_install_blockers
    result["pack_rollback_posture"] = [
        {"pack_key": row["pack_key"], "rollback": row["rollback_posture"]}
        for row in pack_previews
    ]
    if pack_install_blockers:
        result["can_apply"] = False
        result["conflicts"].extend(pack_install_blockers)
    if emit_audit:
        event = audit_blueprint_event(
            "blueprint_previewed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked" if result["conflicts"] else "ok",
            payload={"can_apply": result["can_apply"]},
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
