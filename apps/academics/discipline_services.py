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


class InvalidIncidentTransition(ValueError):
    """Raised when a discipline incident is pushed along an illegal FSM edge."""


def _incident_transitions() -> dict[str, frozenset[str]]:
    """Legal edges of the incident lifecycle, keyed by CURRENT status.

    Mirrors the shape ``apps.academics.lesson_homework_kernel`` already uses for
    the lesson lifecycle, so discipline stops being the one domain whose "FSM"
    was a pair of scattered inline ``!=`` guards.

    ``RESOLVED`` is terminal. That is the edge that mattered: the escalation
    guard below used to read ``status != REFERRED``, which is TRUE for a
    RESOLVED incident -- so a closed case could be silently reopened to
    REFERRED by any later routing call, putting the student back on the
    counselor caseload with no audit trail and no error.
    """
    from apps.academics.models import Incident

    return {
        Incident.Status.OPEN: frozenset(
            {Incident.Status.REFERRED, Incident.Status.RESOLVED}
        ),
        Incident.Status.REFERRED: frozenset({Incident.Status.RESOLVED}),
        Incident.Status.RESOLVED: frozenset(),
    }


def can_transition_incident(current: str, target: str) -> bool:
    """True when ``current -> target`` is a legal incident lifecycle edge."""
    return target in _incident_transitions().get(current, frozenset())


def assert_incident_transition(current: str, target: str) -> None:
    """Refuse an illegal incident lifecycle edge.

    Raises rather than returning a flag: an illegal transition is a bug in the
    caller, and silently swallowing it is exactly how a resolved case came back
    to life.
    """
    if not can_transition_incident(current, target):
        raise InvalidIncidentTransition(
            f"illegal discipline incident transition {current!r} -> {target!r}"
        )


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
    # One accrual per incident. The ledger carries no unique constraint, and
    # this producer is reachable more than once for the same row (a direct
    # service call, an offline replay, a re-save that re-fires routing), so an
    # unconditional create silently double-counts a student towards the
    # escalation threshold. get_or_create keyed on the incident is the same
    # shape RestorativeAction below already uses.
    _ledger_row, points_accrued = BehaviorPointLedger.objects.get_or_create(
        school=school,
        student=student,
        incident=incident,
        defaults={
            "points": delta,
            "reason": f"Incident {incident.incident_type} ({severity})",
            "recorded_by": recorded_by,
        },
    )
    if not points_accrued:
        delta = 0
    total = student_behavior_point_total(school=school, student=student)
    escalated = False
    escalation_refused = False
    if total >= _ESCALATION_THRESHOLD:
        try:
            assert_incident_transition(
                incident.status, Incident.Status.REFERRED
            )
        except InvalidIncidentTransition:
            # Already REFERRED (nothing to do) or terminal RESOLVED (must not
            # be reopened). Routing runs from a post_save signal, so it reports
            # the refusal instead of raising through an unrelated save.
            escalation_refused = incident.status == Incident.Status.RESOLVED
        else:
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

    safeguarding_concern_id = None
    if severity == Incident.Severity.HIGH:
        try:
            from apps.safeguarding.services import maybe_open_concern_from_discipline_incident

            sg = maybe_open_concern_from_discipline_incident(
                school=school,
                incident=incident,
                recorded_by=recorded_by,
            )
            safeguarding_concern_id = getattr(sg, "concern_id", None)
        except Exception:  # noqa: BLE001 — discipline path must stay load-bearing
            logger.warning(
                "discipline_safeguarding_bridge_failed incident_id=%s",
                getattr(incident, "pk", None),
                exc_info=True,
            )

    return {
        "points_added": delta,
        "total_points": total,
        "escalated": escalated,
        "escalation_refused": escalation_refused,
        "points_accrued": points_accrued,
        "restorative_action_id": getattr(restorative, "pk", None),
        "safeguarding_concern_id": safeguarding_concern_id,
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

