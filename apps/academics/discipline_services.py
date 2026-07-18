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
