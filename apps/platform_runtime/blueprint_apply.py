"""Safe blueprint apply engine."""

from __future__ import annotations

from typing import Any

from django.conf import settings as dj_settings
from django.db import transaction
from django.utils import timezone

from apps.packages.engine import apply_package
from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.blueprint_composition import composition_conflicts
from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_modules import enable_blueprint_modules
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_dependency_graph import explain_dependency_blockers


def _snapshot_school(school) -> dict[str, Any]:
    return {
        "settings": dict(getattr(school, "settings", {}) or {}),
        "features": dict(getattr(school, "features", {}) or {}),
    }


def apply_blueprint(
    blueprint_key: str,
    *,
    school,
    actor=None,
    preview_snapshot: dict[str, Any] | None = None,
    confirmed: bool = False,
    platform_operator: bool = False,
    idempotency_key: str = "",
) -> dict[str, Any]:
    blueprint = get_blueprint_or_raise(blueprint_key)
    preview = preview_snapshot or preview_blueprint(
        blueprint.key,
        school=school,
        actor=actor,
        platform_operator=platform_operator,
        emit_audit=False,
    )
    audit_blueprint_event(
        "blueprint_apply_requested",
        blueprint_key=blueprint.key,
        school=school,
        actor=actor,
        result="requested",
        payload={"confirmed": confirmed},
    )
    # Resolved against LIVE installations, not against the preview: a caller may
    # pass a preview_snapshot captured before another blueprint landed (the
    # approved-change-request path replays a stored snapshot), and a stale payload
    # must not be able to carry a second operating model past the guard.
    live_conflicts = composition_conflicts(blueprint, school=school)
    if live_conflicts:
        event = audit_blueprint_event(
            "blueprint_apply_failed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked",
            reason="composition_conflict",
            payload={"conflicts": live_conflicts},
        )
        return {
            "ok": False,
            "errors": explain_dependency_blockers(live_conflicts),
            "conflicts": live_conflicts,
            "warnings": preview.get("warnings", []),
            "audit_id": getattr(event, "pk", None),
        }
    impact = analyze_blueprint_impact(
        blueprint.key,
        school=school,
        actor=actor,
        platform_operator=platform_operator,
        emit_audit=False,
    )
    if not idempotency_key and (
        blueprint.platform_only
        or blueprint.requires_platform_operator
        or any(category in {"destructive"} for category in impact.get("impact_categories", []))
    ):
        event = audit_blueprint_event(
            "blueprint_apply_failed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked",
            reason="approval_required",
        )
        return {
            "ok": False,
            "errors": ["High-risk or platform-only blueprint apply requires an approved change request."],
            "warnings": preview.get("warnings", []),
            "audit_id": getattr(event, "pk", None),
        }
    if not preview.get("can_apply"):
        event = audit_blueprint_event(
            "blueprint_apply_failed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked",
            reason="preview_not_applyable",
            payload={"conflicts": preview.get("conflicts", [])},
        )
        return {
            "ok": False,
            "errors": ["Blueprint apply requires a successful preview."],
            "warnings": preview.get("warnings", []),
            "audit_id": getattr(event, "pk", None),
        }
    if impact["requires_confirmation"] and not confirmed:
        event = audit_blueprint_event(
            "blueprint_apply_failed",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="blocked",
            reason="confirmation_required",
        )
        return {
            "ok": False,
            "errors": ["Confirmation is required for this blueprint impact level."],
            "warnings": preview.get("warnings", []),
            "audit_id": getattr(event, "pk", None),
        }

    # Stable per (blueprint, version, school). Deliberately NOT a hash of the
    # preview: the preview embeds a live installation COUNT, so it changed the
    # instant the first apply landed — a second click then hashed differently,
    # missed this duplicate guard, and wrote another installation row.
    idem = idempotency_key or f"{blueprint.key}:{blueprint.version}:{school.pk}"
    existing = BlueprintInstallation.objects.filter(
        school=school,
        blueprint_key=blueprint.key,
        idempotency_key=idem,
        status=BlueprintInstallation.Status.APPLIED,
    ).first()
    if existing:
        return {
            "ok": True,
            "installation_id": existing.pk,
            "applied_changes": existing.applied_changes,
            "skipped_changes": ["duplicate_idempotency_key"],
            "warnings": preview.get("warnings", []),
            "external_blockers": existing.external_blockers,
            "rollback_available": bool(existing.rollback_snapshot),
            "audit_id": existing.audit_ref,
            "idempotent": True,
            "local_first_manifest": (existing.preview_snapshot or {}).get(
                "local_first_manifest",
                {},
            ),
        }

    rollback_snapshot = _snapshot_school(school)
    applied_changes = preview.get("changes", [])
    package_result: dict[str, Any] = {}
    with transaction.atomic():
        settings = dict(school.settings or {})
        settings.setdefault("blueprint_marketplace", {})
        settings.setdefault("local_first_blueprints", {})
        local_first_manifest = dict(preview.get("local_first_manifest") or {})
        settings["blueprint_marketplace"][blueprint.key] = {
            "version": blueprint.version,
            "applied_at": timezone.now().isoformat(),
            "external_required": list(preview.get("external_required") or []),
            "offline_readiness": dict(preview.get("offline_readiness") or {}),
            "local_first_manifest": local_first_manifest,
        }
        settings["local_first_blueprints"][blueprint.key] = {
            "version": blueprint.version,
            "manifest": local_first_manifest,
            "activated_at": timezone.now().isoformat(),
            "status": "active",
        }
        school.settings = settings
        school.save(update_fields=["settings"])
        package_result = apply_package(
            school.pk,
            f"blueprint:{blueprint.key}",
            blueprint.version,
            preview.get("package_payload", {}),
            actor_id=getattr(actor, "pk", None),
            scope="tenant",
            compatibility={"allowed_scopes": ["tenant"]},
        )
        # Bridge: switch on the opt-in modules this blueprint's archetype implies
        # (e.g. boarding-school → dormitory, low-connectivity-school → offline_mode)
        # in School.features, so applying a blueprint no longer leaves its modules
        # off until an admin toggles each one by hand. Only codes the blueprint
        # explicitly names AND the registry exposes are enabled; nothing is fabricated.
        # Gated by RMC_BLUEPRINT_SYNCS_MODULES (default on) so it stays reversible.
        module_sync: dict[str, Any] = {}
        if getattr(dj_settings, "RMC_BLUEPRINT_SYNCS_MODULES", True):
            module_sync = enable_blueprint_modules(school, blueprint, persist=True)
        # Rollback needs to know which feature codes THIS apply switched on, so it
        # can reverse exactly those and leave every other feature alone. Without
        # it, rollback restored school.settings and left the modules enabled
        # forever — a state that is neither pre-apply nor post-apply.
        rollback_snapshot["modules_enabled"] = list(module_sync.get("enabled", []))
        installation = BlueprintInstallation.objects.create(
            school=school,
            blueprint_key=blueprint.key,
            blueprint_version=blueprint.version,
            installed_version=blueprint.version,
            available_version=blueprint.version,
            status=BlueprintInstallation.Status.APPLIED,
            applied_by=actor if getattr(actor, "pk", None) else None,
            applied_at=timezone.now(),
            preview_snapshot=preview,
            applied_changes=applied_changes,
            external_blockers=list(preview.get("external_required") or []),
            rollback_snapshot=rollback_snapshot,
            idempotency_key=idem,
        )
        event = audit_blueprint_event(
            "blueprint_applied",
            blueprint_key=blueprint.key,
            school=school,
            actor=actor,
            result="applied",
            installation_id=installation.pk,
            payload={
                "external_blockers": installation.external_blockers,
                "local_first_manifest": local_first_manifest,
                "modules_enabled": module_sync.get("enabled", []),
                "modules_skipped_unentitled": module_sync.get("skipped_unentitled", []),
            },
        )
        if event:
            installation.audit_ref = str(event.pk)
            installation.save(update_fields=["audit_ref"])
    pack_install_results: list[dict[str, Any]] = []
    for pack_preview in preview.get("pack_previews", []):
        pack_result = apply_pack(
            pack_preview["pack_key"],
            pack_type=pack_preview["pack_type"],
            school=school,
            actor=actor,
            confirmed=True,
            platform_operator=platform_operator,
            blueprint_installation=installation,
            idempotency_key=f"{idem}:{pack_preview['pack_type']}:{pack_preview['pack_key']}",
            skip_dependency_checks=True,
        )
        pack_install_results.append(pack_result)
        if not pack_result.get("ok"):
            installation.status = BlueprintInstallation.Status.PARTIALLY_APPLIED
            installation.save(update_fields=["status", "updated_at"])
            audit_blueprint_event(
                "blueprint_apply_failed",
                blueprint_key=blueprint.key,
                school=school,
                actor=actor,
                result="partial",
                reason="pack_install_failed",
                installation_id=installation.pk,
                payload={"pack_result": pack_result},
            )
            return {
                "ok": False,
                "errors": ["A referenced pack failed to install."],
                "installation_id": installation.pk,
                "pack_installations": pack_install_results,
                "warnings": preview.get("warnings", []),
                "external_blockers": list(preview.get("external_required") or []),
                "rollback_available": True,
                "audit_id": installation.audit_ref,
                "local_first_manifest": local_first_manifest,
            }

    return {
        "ok": True,
        "installation_id": installation.pk,
        "applied_changes": applied_changes,
        "skipped_changes": [],
        "warnings": preview.get("warnings", []),
        "external_blockers": list(preview.get("external_required") or []),
        "rollback_available": blueprint.rollback_available,
        "audit_id": installation.audit_ref,
        "package_result": package_result,
        "pack_installations": pack_install_results,
        "idempotent": False,
        "local_first_manifest": preview.get("local_first_manifest", {}),
        "modules_enabled": module_sync.get("enabled", []),
        "modules_already_on": module_sync.get("already_on", []),
        "modules_skipped_unentitled": module_sync.get("skipped_unentitled", []),
    }
