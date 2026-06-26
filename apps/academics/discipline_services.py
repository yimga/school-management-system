"""Incident routing FSM + behavior points (metric 11)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import Sum

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
