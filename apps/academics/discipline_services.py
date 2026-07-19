"""Incident routing FSM + behavior points (metric 11)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

_SEVERITY_POINTS = {
    "LOW": 1,
    "MEDIUM": 3,
    "HIGH": 5,
}
_ESCALATION_THRESHOLD = 10


def student_behavior_point_total(*, school, student) -> int:
    from apps.academics.models_discipline import BehaviorPointLedger

    agg = BehaviorPointLedger.objects.filter(
        school=school,
        student=student,
    ).aggregate(total=Sum("points"))
    return int(agg["total"] or 0)


@transaction.atomic
def process_incident_routing(*, incident: Any, recorded_by: Any | None = None) -> dict[str, Any]:
    """
    Accrue behavior points from incident severity, escalate when over threshold,
    and create a restorative action for medium+ severity.
    """
    from apps.academics.models import Incident
    from apps.academics.models_discipline import BehaviorPointLedger, RestorativeAction

    school = incident.school
    student = incident.student
    if school is None or student is None:
        return {"skipped": True, "reason": "missing_school_or_student"}

    severity = (incident.severity or Incident.Severity.MEDIUM).upper()
    delta = _SEVERITY_POINTS.get(severity, 3)
    BehaviorPointLedger.objects.create(
        school=school,
        student=student,
        incident=incident,
        points=delta,
        reason=f"Incident {incident.incident_type} ({severity})",
        recorded_by=recorded_by,
    )
    total = student_behavior_point_total(school=school, student=student)
    escalated = False
    if total >= _ESCALATION_THRESHOLD and incident.status != Incident.Status.REFERRED:
        incident.status = Incident.Status.REFERRED
        incident.save(update_fields=["status"])
        escalated = True
        logger.info(
            "discipline_escalated incident_id=%s student_id=%s total_points=%s",
            incident.pk,
            student.pk,
            total,
        )

    restorative = None
    if severity in {Incident.Severity.MEDIUM, Incident.Severity.HIGH}:
        restorative, _ = RestorativeAction.objects.get_or_create(
            school=school,
            incident=incident,
            defaults={
                "title": "Restorative conference",
                "description": incident.description or "",
                "status": RestorativeAction.Status.PLANNED,
            },
        )

    return {
        "points_added": delta,
        "total_points": total,
        "escalated": escalated,
        "restorative_action_id": getattr(restorative, "pk", None),
    }


@transaction.atomic
def resolve_incident(
    *,
    incident: Any,
    resolved_by: Any | None = None,
    complete_restorative: bool = True,
) -> dict[str, Any]:
    """Close out a discipline incident: the RESOLVED-status producer.

    This is the terminal transition of the incident FSM (``REFERRED``/``OPEN`` ->
    ``RESOLVED``). It is the missing counterpart to routing/escalation: without it no
    product path ever writes ``Incident.Status.RESOLVED``, so a student with an open
    incident never leaves the MTSS counselor caseload (the caseload keeps a student
    while ``open_count`` — incidents whose status is not ``RESOLVED`` — is > 0).

    Records the resolver + timestamp for the audit trail and, by default, completes any
    still-open restorative follow-ups tied to the incident (resolving the incident means
    the restorative conference is done). Idempotent: resolving an already-resolved
    incident is a no-op. RBAC is enforced by the caller (the resolve API/view gate on
    ``discipline.manage``); this service is the producer, not the authorization point.
    """
    from apps.academics.models import Incident
    from apps.academics.models_discipline import RestorativeAction

    if incident.status == Incident.Status.RESOLVED:
        return {
            "resolved": False,
            "already_resolved": True,
            "restorative_completed": 0,
        }

    now = timezone.now()
    incident.status = Incident.Status.RESOLVED
    incident.resolved_at = now
    update_fields = ["status", "resolved_at"]
    if resolved_by is not None and getattr(resolved_by, "pk", None):
        incident.resolved_by = resolved_by
        update_fields.append("resolved_by")
    incident.save(update_fields=update_fields)

    completed = 0
    if complete_restorative:
        open_actions = RestorativeAction.objects.filter(
            school_id=incident.school_id,
            incident=incident,
            status__in=[
                RestorativeAction.Status.PLANNED,
                RestorativeAction.Status.IN_PROGRESS,
            ],
        )
        for action in open_actions:
            action.status = RestorativeAction.Status.COMPLETED
            action.completed_at = now
            action.save(update_fields=["status", "completed_at", "updated_at"])
            completed += 1

    logger.info(
        "discipline_resolved incident_id=%s student_id=%s resolved_by=%s "
        "restorative_completed=%s",
        incident.pk,
        incident.student_id,
        getattr(resolved_by, "pk", None),
        completed,
    )
    return {
        "resolved": True,
        "already_resolved": False,
        "restorative_completed": completed,
    }


@transaction.atomic
def set_student_mtss_tier(
    *,
    school: Any,
    student: Any,
    tier: str,
    actor: Any | None = None,
) -> dict[str, Any]:
    """Update MTSS tier on all non-RESOLVED incidents for a student (caseload workflow).

    Caseload aggregates ``Max(mtss_tier)`` across incidents, so mutating open rows
    is what counselors need to escalate/de-escalate without opening a new referral.
    RESOLVED incidents are left unchanged (audit history).
    """
    from apps.academics.models import Incident

    if school is None or student is None:
        return {"updated": 0, "reason": "missing_school_or_student"}
    if getattr(student, "school_id", None) != getattr(school, "pk", None):
        return {"updated": 0, "reason": "student_school_mismatch"}

    valid = {c.value for c in Incident.MtssTier}
    tier_s = str(tier or "").strip()
    if tier_s not in valid:
        return {"updated": 0, "reason": "invalid_tier"}

    qs = Incident.objects.filter(
        school=school,
        student=student,
    ).exclude(status=Incident.Status.RESOLVED)
    updated = qs.update(mtss_tier=tier_s)
    logger.info(
        "mtss_tier_updated school_id=%s student_id=%s tier=%s updated=%s actor=%s",
        getattr(school, "pk", None),
        getattr(student, "pk", None),
        tier_s,
        updated,
        getattr(actor, "pk", None),
    )
    return {"updated": updated, "tier": tier_s}


@transaction.atomic
def log_mtss_contact(
    *,
    school: Any,
    student: Any,
    action_taken: str,
    notes: str = "",
    actor: Any | None = None,
) -> dict[str, Any]:
    """Append an MTSS intervention contact (Meeting/Call/Email) for a student.

    Writes ``analytics.InterventionLog`` so counselor caseload has a real contact
    timeline without inventing a parallel discipline model.
    """
    from apps.analytics.models import InterventionLog

    if school is None or student is None:
        return {"ok": False, "reason": "missing_school_or_student"}
    if getattr(student, "school_id", None) != getattr(school, "pk", None):
        return {"ok": False, "reason": "student_school_mismatch"}

    action = (action_taken or "").strip()[:100] or "Note"
    note = (notes or "").strip()
    trigger = note[:255] if note else f"MTSS contact: {action}"
    log = InterventionLog.objects.create(
        school=school,
        student=student,
        trigger_reason=trigger,
        action_taken=action,
        status=InterventionLog.Status.ONGOING,
    )
    logger.info(
        "mtss_contact_logged school_id=%s student_id=%s action=%s log_id=%s actor=%s",
        getattr(school, "pk", None),
        getattr(student, "pk", None),
        action,
        log.pk,
        getattr(actor, "pk", None),
    )
    return {"ok": True, "log_id": log.pk, "action_taken": action}

