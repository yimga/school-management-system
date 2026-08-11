"""Safe pack apply engine."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.brand_experience.template_runtime import ExperienceRuntimeError
from apps.packages.engine import apply_package
from apps.packages.models import InstalledPackage
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_audit import audit_pack_event
from apps.platform_runtime.pack_contract import get_pack_or_raise
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_simulation import simulate_pack
from apps.platform_runtime.pack_dependency_graph import (
    detect_dependency_conflicts,
    detect_missing_prerequisites,
    explain_dependency_blockers,
)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def _snapshot_school(school) -> dict[str, Any]:
    return {"settings": dict(getattr(school, "settings", {}) or {}), "features": dict(getattr(school, "features", {}) or {})}


def apply_pack(
    pack_key: str,
    *,
    pack_type: str | None = None,
    school,
    actor=None,
    preview_snapshot: dict[str, Any] | None = None,
    simulation_snapshot: dict[str, Any] | None = None,
    impact_snapshot: dict[str, Any] | None = None,
    confirmed: bool = False,
    platform_operator: bool = False,
    idempotency_key: str = "",
    blueprint_installation=None,
    skip_dependency_checks: bool = False,
) -> dict[str, Any]:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    preview = preview_snapshot or preview_pack(pack.key, school=school, actor=actor, platform_operator=platform_operator)
    impact = impact_snapshot or analyze_pack_impact(pack.key, school=school, actor=actor, platform_operator=platform_operator)
    simulation = simulation_snapshot or (
        simulate_pack(pack.key, school=school, actor=actor, platform_operator=platform_operator)
        if impact["requires_simulation"]
        else {}
    )
    audit_pack_event("pack_apply_requested", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="requested", payload={"confirmed": confirmed})
    if not idempotency_key and (pack.safety_level in {"high", "destructive"} or pack.platform_only):
        event = audit_pack_event("pack_apply_failed", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="blocked", reason="approval_required")
        return {"ok": False, "errors": ["High-risk or platform-only pack apply requires an approved change request."], "audit_id": getattr(event, "pk", None)}
    if not preview.get("can_apply"):
        event = audit_pack_event("pack_apply_failed", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="blocked", reason="preview_not_applyable", payload={"conflicts": preview.get("conflicts", [])})
        return {"ok": False, "errors": ["Pack apply requires a successful preview."], "audit_id": getattr(event, "pk", None)}
    if not skip_dependency_checks:
        dependency_blockers = [
            row
            for row in detect_missing_prerequisites(pack.key, target_type=pack.pack_type, pack_type=pack.pack_type, school=school)
            if row.get("code") != "external_required"
        ]
        dependency_blockers.extend(detect_dependency_conflicts(pack.key, target_type=pack.pack_type, pack_type=pack.pack_type, school=school))
        if dependency_blockers:
            event = audit_pack_event("pack_apply_failed", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="blocked", reason="dependency_blocked", payload={"dependency_blockers": dependency_blockers})
            return {"ok": False, "errors": explain_dependency_blockers(dependency_blockers), "audit_id": getattr(event, "pk", None)}
    if impact["requires_simulation"] and not simulation:
        event = audit_pack_event("pack_apply_failed", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="blocked", reason="simulation_required")
        return {"ok": False, "errors": ["Simulation is required for this pack."], "audit_id": getattr(event, "pk", None)}
    if impact["requires_confirmation"] and not confirmed:
        event = audit_pack_event("pack_apply_failed", pack_key=pack.key, pack_type=pack.pack_type, school=school, actor=actor, result="blocked", reason="confirmation_required")
        return {"ok": False, "errors": ["Confirmation is required for this pack."], "audit_id": getattr(event, "pk", None)}

    if pack.pack_type == "experience_template":
        from apps.brand_experience.template_runtime import build_experience_runtime_payload

        try:
            build_experience_runtime_payload(
                pack.key,
                platform_operator=platform_operator,
            )
        except ExperienceRuntimeError as exc:
            event = audit_pack_event(
                "pack_apply_failed",
                pack_key=pack.key,
                pack_type=pack.pack_type,
                school=school,
                actor=actor,
                result="blocked",
                reason="experience_runtime_invalid",
                payload={"errors": [str(exc)]},
            )
            return {
                "ok": False,
                "errors": [str(exc)],
                "audit_id": getattr(event, "pk", None),
            }

    idem = idempotency_key or f"{pack.key}:{pack.pack_type}:{getattr(school, 'pk', '')}:{_hash(preview)}"
    existing = PackInstallation.objects.filter(school=school, pack_key=pack.key, pack_type=pack.pack_type, idempotency_key=idem, status=PackInstallation.Status.APPLIED).first()
    if existing:
        runtime_result = None
        if pack.pack_type == "experience_template":
            from apps.brand_experience.template_runtime import activate_experience_template

            try:
                runtime_result = activate_experience_template(
                    school=school,
                    template_key=pack.key,
                    actor=actor,
                    reconciled=True,
                    emit_audit=True,
                    platform_operator=platform_operator,
                ).as_dict()
            except ExperienceRuntimeError as exc:
                event = audit_pack_event(
                    "pack_apply_failed",
                    pack_key=pack.key,
                    pack_type=pack.pack_type,
                    school=school,
                    actor=actor,
                    result="failed",
                    reason="experience_runtime_reconciliation_failed",
                    payload={"errors": [str(exc)]},
                )
                return {
                    "ok": False,
                    "errors": [str(exc)],
                    "audit_id": getattr(event, "pk", None),
                }
        return {"ok": True, "installation_id": existing.pk, "idempotent": True, "applied_changes": existing.applied_changes, "external_blockers": existing.external_blockers, "experience_runtime": runtime_result}

    rollback_snapshot = _snapshot_school(school)
    package_id = f"{pack.pack_type}:{pack.key}"
    installed = InstalledPackage.objects.filter(package_id=package_id, version=pack.version, school=school, is_active=True).first()
    if installed:
        package_result = {"ok": True, "skipped": "already_installed", "installed_id": installed.pk}
    else:
        package_result = apply_package(
            school.pk,
            package_id,
            pack.version,
            preview["package_payload"],
            actor_id=getattr(actor, "pk", None),
            scope="tenant",
            compatibility={"allowed_scopes": ["tenant"]},
        )
    if not package_result.get("ok"):
        event = audit_pack_event(
            "pack_apply_failed",
            pack_key=pack.key,
            pack_type=pack.pack_type,
            school=school,
            actor=actor,
            result="failed",
            reason="package_engine_failed",
            payload={"errors": list(package_result.get("errors") or [])},
        )
        return {
            "ok": False,
            "errors": list(package_result.get("errors") or ["Package installation failed."]),
            "audit_id": getattr(event, "pk", None),
            "package_result": package_result,
        }
    experience_runtime = None
    try:
        with transaction.atomic():
            settings = dict(school.settings or {})
            settings.setdefault("pack_installation_simulation", {})
            settings["pack_installation_simulation"][pack.key] = {
                "pack_type": pack.pack_type,
                "version": pack.version,
                "applied_at": timezone.now().isoformat(),
                "external_required": list(preview.get("external_required") or []),
            }
            school.settings = settings
            school.save(update_fields=["settings"])
            installation = PackInstallation.objects.create(
                school=school,
                blueprint_installation=blueprint_installation,
                pack_key=pack.key,
                pack_type=pack.pack_type,
                version=pack.version,
                installed_version=pack.version,
                available_version=pack.version,
                status=PackInstallation.Status.APPLIED,
                applied_by=actor if getattr(actor, "pk", None) else None,
                applied_at=timezone.now(),
                preview_snapshot=preview,
                simulation_snapshot=simulation,
                impact_snapshot=impact,
                applied_changes=preview.get("included_changes", []),
                rollback_snapshot=rollback_snapshot,
                external_blockers=list(preview.get("external_required") or []),
                idempotency_key=idem,
            )
            event = audit_pack_event(
                "pack_applied",
                pack_key=pack.key,
                pack_type=pack.pack_type,
                school=school,
                actor=actor,
                result="applied",
                installation_id=installation.pk,
                payload={"external_blockers": installation.external_blockers},
            )
            if event:
                installation.audit_ref = str(event.pk)
                installation.save(update_fields=["audit_ref"])
            if pack.pack_type == "experience_template":
                from apps.brand_experience.template_runtime import (
                    activate_experience_template,
                )

                experience_runtime = activate_experience_template(
                    school=school,
                    template_key=pack.key,
                    actor=actor,
                    installed_package_id=package_result.get("installed_id"),
                    platform_operator=platform_operator,
                ).as_dict()
    except ExperienceRuntimeError as exc:
        installed_id = package_result.get("installed_id")
        if installed_id and not package_result.get("skipped"):
            from apps.packages.engine import rollback as rollback_package

            compensating_package = InstalledPackage.objects.filter(pk=installed_id).first()
            if compensating_package is not None and compensating_package.is_active:
                rollback_package(
                    compensating_package,
                    actor_id=getattr(actor, "pk", None),
                )
        event = audit_pack_event(
            "pack_apply_failed",
            pack_key=pack.key,
            pack_type=pack.pack_type,
            school=school,
            actor=actor,
            result="failed",
            reason="experience_runtime_activation_failed",
            payload={"errors": [str(exc)]},
        )
        return {
            "ok": False,
            "errors": [str(exc)],
            "audit_id": getattr(event, "pk", None),
            "package_result": package_result,
        }
    return {
        "ok": True,
        "installation_id": installation.pk,
        "applied_changes": installation.applied_changes,
        "warnings": preview.get("warnings", []),
        "external_blockers": installation.external_blockers,
        "rollback_available": pack.rollback_available,
        "audit_id": installation.audit_ref,
        "package_result": package_result,
        "experience_runtime": experience_runtime,
        "idempotent": False,
    }
