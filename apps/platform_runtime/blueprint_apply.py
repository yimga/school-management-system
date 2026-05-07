"""Safe blueprint apply engine."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.packages.engine import apply_package
from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation


def _snapshot_school(school) -> dict[str, Any]:
    return {
        "settings": dict(getattr(school, "settings", {}) or {}),
        "features": dict(getattr(school, "features", {}) or {}),
    }


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


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
    impact = analyze_blueprint_impact(
        blueprint.key,
        school=school,
        actor=actor,
        platform_operator=platform_operator,
        emit_audit=False,
    )
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

    idem = idempotency_key or f"{blueprint.key}:{school.pk}:{_stable_hash(preview)}"
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
        }

    rollback_snapshot = _snapshot_school(school)
    applied_changes = preview.get("changes", [])
    package_result: dict[str, Any] = {}
    with transaction.atomic():
        settings = dict(school.settings or {})
        settings.setdefault("blueprint_marketplace", {})
        settings["blueprint_marketplace"][blueprint.key] = {
            "version": blueprint.version,
            "applied_at": timezone.now().isoformat(),
            "external_required": list(preview.get("external_required") or []),
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
        installation = BlueprintInstallation.objects.create(
            school=school,
            blueprint_key=blueprint.key,
            blueprint_version=blueprint.version,
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
            payload={"external_blockers": installation.external_blockers},
        )
        if event:
            installation.audit_ref = str(event.pk)
            installation.save(update_fields=["audit_ref"])

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
        "idempotent": False,
    }
