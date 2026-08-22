"""Approval workflow for governed blueprint and pack changes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_composition import _installation_sort_key
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.configuration_change_set import (
    assert_change_set_fresh,
    generate_blueprint_change_set,
    generate_pack_change_set,
)
from apps.platform_runtime.events import emit_platform_event
from apps.platform_runtime.models import BlueprintInstallation, ConfigurationChangeRequest, PackInstallation
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_rollback import (
    deactivate_pack_installation,
    rollback_pack_installation,
)


TERMINAL_STATUSES = {
    ConfigurationChangeRequest.Status.REJECTED,
    ConfigurationChangeRequest.Status.CANCELLED,
    ConfigurationChangeRequest.Status.APPLIED,
    ConfigurationChangeRequest.Status.ROLLED_BACK,
}

_ROLLBACK_REQUEST_TYPES = frozenset(
    {
        ConfigurationChangeRequest.RequestType.BLUEPRINT_ROLLBACK,
        ConfigurationChangeRequest.RequestType.PACK_ROLLBACK,
        ConfigurationChangeRequest.RequestType.PACK_DEACTIVATE,
    }
)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def _is_platform_operator(actor) -> bool:
    return bool(getattr(actor, "is_superuser", False) or getattr(actor, "is_staff", False) and getattr(actor, "role", "") in {"superadmin", "platform_operator"})


def _event(event_type: str, change_request: ConfigurationChangeRequest, *, actor=None, payload: dict[str, Any] | None = None):
    return emit_platform_event(
        event_type,
        {
            "change_request_id": change_request.pk,
            "request_type": change_request.request_type,
            "target_type": change_request.target_type,
            "target_key": change_request.target_key,
            "actor_id": getattr(actor, "pk", None),
            **(payload or {}),
        },
        tenant_id=str(getattr(change_request.school, "pk", "") or "") or None,
        school_id=str(getattr(change_request.school, "pk", "") or "") or None,
        idempotency_key=change_request.idempotency_key,
    )


def create_change_request(
    request_type: str,
    *,
    target_key: str,
    target_type: str,
    school=None,
    actor=None,
    reason: str = "",
    platform_operator: bool = False,
    idempotency_key: str = "",
) -> ConfigurationChangeRequest:
    change_set = (
        generate_blueprint_change_set(target_key, school=school, actor=actor, platform_operator=platform_operator)
        if target_type == "blueprint"
        else generate_pack_change_set(target_key, pack_type=target_type, school=school, actor=actor, platform_operator=platform_operator)
    )
    status = (
        ConfigurationChangeRequest.Status.PENDING_APPROVAL
        if change_set["requires_approval"]
        else ConfigurationChangeRequest.Status.APPROVED
    )
    idem = idempotency_key or f"{request_type}:{target_type}:{target_key}:{getattr(school, 'pk', '')}:{_hash(change_set)}"
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    existing = ConfigurationChangeRequest.objects.filter(idempotency_key=idem).first()
    if existing:
        return existing
    change_request = ConfigurationChangeRequest.objects.create(
        school=school,
        request_type=request_type,
        target_key=target_key,
        target_type=target_type,
        target_version=change_set["target_version"],
        requested_by=actor if getattr(actor, "pk", None) else None,
        status=status,
        risk_level=change_set["risk_level"],
        reason=reason,
        preview_snapshot=change_set["preview_summary"],
        simulation_snapshot=change_set["simulation_summary"],
        impact_snapshot=change_set["impact_summary"],
        rollback_plan=change_set["rollback_coverage"],
        external_blockers=change_set["external_blockers"],
        idempotency_key=idem,
    )
    event = _event("configuration_change_requested", change_request, actor=actor, payload={"status": status})
    if event:
        change_request.audit_ref = str(event.pk)
        change_request.save(update_fields=["audit_ref"])
    return change_request


def approve_change_request(change_request: ConfigurationChangeRequest, *, actor=None, notes: str = "") -> ConfigurationChangeRequest:
    if change_request.status in TERMINAL_STATUSES:
        raise ValueError("Terminal change requests cannot be approved.")
    if not _is_platform_operator(actor):
        raise PermissionError("Platform operator approval is required.")
    change_request.status = ConfigurationChangeRequest.Status.APPROVED
    change_request.approval_notes = notes
    change_request.approved_by = actor if getattr(actor, "pk", None) else None
    change_request.approved_at = timezone.now()
    change_request.save(update_fields=["status", "approval_notes", "approved_by", "approved_at", "updated_at"])
    _event("configuration_change_approved", change_request, actor=actor)
    return change_request


def reject_change_request(change_request: ConfigurationChangeRequest, *, actor=None, notes: str = "") -> ConfigurationChangeRequest:
    if change_request.status in TERMINAL_STATUSES:
        raise ValueError("Terminal change requests cannot be rejected.")
    change_request.status = ConfigurationChangeRequest.Status.REJECTED
    change_request.approval_notes = notes
    change_request.rejected_by = actor if getattr(actor, "pk", None) else None
    change_request.rejected_at = timezone.now()
    change_request.save(update_fields=["status", "approval_notes", "rejected_by", "rejected_at", "updated_at"])
    _event("configuration_change_rejected", change_request, actor=actor)
    return change_request


def cancel_change_request(change_request: ConfigurationChangeRequest, *, actor=None, reason: str = "") -> ConfigurationChangeRequest:
    if change_request.status in TERMINAL_STATUSES:
        raise ValueError("Terminal change requests cannot be cancelled.")
    change_request.status = ConfigurationChangeRequest.Status.CANCELLED
    change_request.approval_notes = reason
    change_request.save(update_fields=["status", "approval_notes", "updated_at"])
    _event("configuration_change_cancelled", change_request, actor=actor)
    return change_request


def schedule_change_request(
    change_request: ConfigurationChangeRequest,
    *,
    actor=None,
    scheduled_at,
    execution_window: str = "",
) -> ConfigurationChangeRequest:
    if change_request.status != ConfigurationChangeRequest.Status.APPROVED:
        raise ValueError("Only approved change requests can be scheduled.")
    change_request.status = ConfigurationChangeRequest.Status.SCHEDULED
    change_request.scheduled_at = scheduled_at
    change_request.scheduled_by = actor if getattr(actor, "pk", None) else None
    change_request.schedule_status = "scheduled"
    change_request.execution_window = execution_window
    change_request.save(update_fields=["status", "scheduled_at", "scheduled_by", "schedule_status", "execution_window", "updated_at"])
    _event("configuration_change_scheduled", change_request, actor=actor, payload={"scheduled_at": scheduled_at.isoformat()})
    return change_request


def _stored_change_set(change_request: ConfigurationChangeRequest) -> dict[str, Any]:
    return {
        "target_type": change_request.target_type,
        "target_key": change_request.target_key,
        "target_version": change_request.target_version,
    }


def _latest_blueprint_installation_for_mutation(school, blueprint_key):
    if school is None:
        return None
    candidates = list(
        BlueprintInstallation.objects.filter(
            school=school,
            blueprint_key=blueprint_key,
            status__in=(
                BlueprintInstallation.Status.APPLIED,
                BlueprintInstallation.Status.PARTIALLY_APPLIED,
            ),
        )
    )
    if not candidates:
        return None
    return max(candidates, key=_installation_sort_key)


def _latest_pack_installation_for_mutation(school, pack_key, pack_type):
    if school is None:
        return None
    candidates = list(
        PackInstallation.objects.filter(
            school=school,
            pack_key=pack_key,
            pack_type=pack_type,
            status__in=(
                PackInstallation.Status.APPLIED,
                PackInstallation.Status.PARTIALLY_APPLIED,
            ),
        )
    )
    if not candidates:
        return None
    return max(candidates, key=_installation_sort_key)


def apply_approved_change_request(change_request: ConfigurationChangeRequest, *, actor=None, force_scheduled: bool = False) -> dict[str, Any]:
    if change_request.status not in {ConfigurationChangeRequest.Status.APPROVED, ConfigurationChangeRequest.Status.SCHEDULED}:
        return {"ok": False, "errors": ["Only approved or due scheduled change requests can apply."]}
    if change_request.status == ConfigurationChangeRequest.Status.SCHEDULED:
        if not force_scheduled and change_request.scheduled_at and change_request.scheduled_at > timezone.now():
            return {"ok": False, "errors": ["Scheduled change request is not due yet."], "scheduled": True}
    assert_change_set_fresh(_stored_change_set(change_request))
    result: dict[str, Any]
    with transaction.atomic():
        if change_request.request_type == ConfigurationChangeRequest.RequestType.BLUEPRINT_APPLY:
            result = apply_blueprint(
                change_request.target_key,
                school=change_request.school,
                actor=actor,
                preview_snapshot=change_request.preview_snapshot,
                confirmed=True,
                platform_operator=True,
                idempotency_key=change_request.idempotency_key,
            )
        elif change_request.request_type == ConfigurationChangeRequest.RequestType.PACK_APPLY:
            result = apply_pack(
                change_request.target_key,
                pack_type=change_request.target_type,
                school=change_request.school,
                actor=actor,
                preview_snapshot=change_request.preview_snapshot,
                simulation_snapshot=change_request.simulation_snapshot,
                impact_snapshot=change_request.impact_snapshot,
                confirmed=True,
                platform_operator=True,
                idempotency_key=change_request.idempotency_key,
            )
        elif change_request.request_type == ConfigurationChangeRequest.RequestType.BLUEPRINT_ROLLBACK:
            installation = _latest_blueprint_installation_for_mutation(
                change_request.school, change_request.target_key
            )
            if installation is None:
                result = {
                    "ok": False,
                    "errors": ["No applied blueprint installation found to roll back."],
                }
            else:
                result = rollback_blueprint_installation(
                    installation, actor=actor, confirmed=True
                )
        elif change_request.request_type == ConfigurationChangeRequest.RequestType.PACK_ROLLBACK:
            installation = _latest_pack_installation_for_mutation(
                change_request.school,
                change_request.target_key,
                change_request.target_type,
            )
            if installation is None:
                result = {
                    "ok": False,
                    "errors": ["No applied pack installation found to roll back."],
                }
            else:
                result = rollback_pack_installation(
                    installation, actor=actor, confirmed=True
                )
        elif change_request.request_type == ConfigurationChangeRequest.RequestType.PACK_DEACTIVATE:
            installation = _latest_pack_installation_for_mutation(
                change_request.school,
                change_request.target_key,
                change_request.target_type,
            )
            if installation is None:
                result = {
                    "ok": False,
                    "errors": ["No applied pack installation found to deactivate."],
                }
            else:
                result = deactivate_pack_installation(
                    installation, actor=actor, confirmed=True
                )
        else:
            result = {"ok": False, "errors": ["This request type is not applyable by this helper."]}
        if result.get("ok"):
            if change_request.request_type in _ROLLBACK_REQUEST_TYPES:
                change_request.status = ConfigurationChangeRequest.Status.ROLLED_BACK
            else:
                change_request.status = ConfigurationChangeRequest.Status.APPLIED
            change_request.applied_at = timezone.now()
        else:
            change_request.status = ConfigurationChangeRequest.Status.FAILED
            change_request.applied_at = None
        change_request.audit_ref = str(result.get("audit_id") or change_request.audit_ref)
        change_request.save(update_fields=["status", "applied_at", "audit_ref", "updated_at"])
    _event("configuration_change_applied" if result.get("ok") else "configuration_change_failed", change_request, actor=actor, payload={"result": result})
    return result


def get_change_request_status(change_request: ConfigurationChangeRequest) -> dict[str, Any]:
    return {
        "id": change_request.pk,
        "status": change_request.status,
        "risk_level": change_request.risk_level,
        "target_type": change_request.target_type,
        "target_key": change_request.target_key,
        "scheduled_at": change_request.scheduled_at.isoformat() if change_request.scheduled_at else "",
        "external_blockers": change_request.external_blockers,
    }
