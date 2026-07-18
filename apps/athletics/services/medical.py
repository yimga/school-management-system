"""Athlete medical-clearance (fitness-to-play) recording — the CLEARED producer.

The eligibility resolver ships a CONSUMER of ``MedicalClearance.Status.CLEARED``
(``services.eligibility._medical_ok``) but the module had no product path that
ever SET a clearance to CLEARED, so ``_medical_ok`` failed closed and no athlete
could ever be ELIGIBLE. This service is that producer: an authorized athletics
staffer (coach assigned to the team, or the athletics-admin tier) records a
fitness-to-play clearance for an athlete, and the acting user is captured as
``cleared_by`` — the sign-off of record.

Health data hygiene: the free-text ``notes`` is NEVER logged (mirrors the
consent service's discipline of never logging guardian emails / tokens).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.athletics.constants import MEDICAL_CLEARANCE_VALIDITY_DAYS
from apps.athletics.models import MedicalClearance

logger = logging.getLogger(__name__)


def _audit_clearance(*, clearance, actor) -> None:
    """Best-effort append-only audit of a clearance sign-off.

    Mirrors ``ParticipationConsent._audit`` — a medical clearance is a meaningful
    (HIGH-sensitivity, health-adjacent) record, so who signed it off is journaled.
    Never blocks the clearance and never logs the notes/PII.
    """
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.CREATE,
            user=actor if getattr(actor, "pk", None) else None,
            model_name="MedicalClearance",
            object_id=str(clearance.pk)[:200],
            object_repr=(
                f"medical clearance CLEARED (student {clearance.student_id}, "
                f"sport {clearance.sport_id})"
            )[:500],
            app_label="athletics",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={
                "status": clearance.status,
                "valid_from": clearance.valid_from.isoformat()
                if clearance.valid_from
                else None,
                "valid_until": clearance.valid_until.isoformat()
                if clearance.valid_until
                else None,
            },
        )
    except Exception:  # noqa: BLE001 — audit must never block the clearance
        logger.warning(
            "athletics_medical_clearance_audit_failed clearance=%s", clearance.pk
        )


def record_medical_clearance(
    *,
    membership,
    actor,
    sport=None,
    valid_from: date | None = None,
    valid_until: date | None = None,
    notes: str = "",
) -> MedicalClearance:
    """Record a CLEARED fitness-to-play clearance for a membership's student.

    This is the producer the eligibility resolver's ``_medical_ok`` predicate has
    been waiting on. Defaults the validity window to
    ``[today, today + MEDICAL_CLEARANCE_VALIDITY_DAYS]`` so a clearance is
    time-boxed. ``actor`` is captured as ``cleared_by``. Sport defaults to the
    membership's team sport (the clearance stays student-scoped for eligibility —
    the resolver does not filter by sport — but recording the sport is meaningful
    provenance).

    Returns the created :class:`MedicalClearance`.
    """
    today = timezone.now().date()
    if valid_from is None:
        valid_from = today
    if valid_until is None:
        valid_until = valid_from + timedelta(days=MEDICAL_CLEARANCE_VALIDITY_DAYS)
    resolved_sport = sport if sport is not None else getattr(
        membership.team, "sport", None
    )

    with transaction.atomic():
        clearance = MedicalClearance.objects.create(
            school_id=membership.school_id,
            student_id=membership.student_id,
            sport=resolved_sport,
            status=MedicalClearance.Status.CLEARED,
            cleared_by=actor if getattr(actor, "pk", None) else None,
            valid_from=valid_from,
            valid_until=valid_until,
            notes=notes or "",
        )

    _audit_clearance(clearance=clearance, actor=actor)
    # School/student ids only — never the notes (health PII).
    logger.info(
        "athletics_medical_clearance_recorded clearance=%s membership=%s",
        clearance.pk,
        membership.pk,
    )
    return clearance


__all__ = ["record_medical_clearance"]
