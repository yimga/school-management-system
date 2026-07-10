"""Athlete eligibility resolver.

Computes four school-scoped predicates for a team membership — academic,
attendance, medical, and consent — and materializes an ``EligibilityRecord``
snapshot. When the PDP is in enforce mode a policy DENY forces INELIGIBLE.

No PII is ever logged (no medical notes, guardian emails, or tokens).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.athletics.constants import (
    ELIGIBILITY_ATTENDANCE_WINDOW_DAYS,
    MIN_ELIGIBILITY_ATTENDANCE_PCT,
    MIN_ELIGIBILITY_AVERAGE,
)
from apps.athletics.models import (
    EligibilityRecord,
    MedicalClearance,
    ParticipationConsent,
    ParticipationConsentDecision,
)

logger = logging.getLogger(__name__)

_PERCENT = Decimal("100")


@dataclass
class EligibilityOutcome:
    """Result of an eligibility resolution.

    ``record`` is the persisted :class:`EligibilityRecord` when ``persist`` was
    True, otherwise ``None``.
    """

    eligible: bool
    status: str
    reasons: list[str] = field(default_factory=list)
    record: object | None = None


def _academic_ok(*, school, student_id, reasons: list[str], snapshot: dict) -> bool:
    """True when the student's average is at or above the eligibility floor.

    ``MIN_ELIGIBILITY_AVERAGE`` is a PERCENTAGE (like the attendance floor), so
    the raw ``total_score`` average — which is on the school's operational grade
    scale (/20, /100, /4, …) — is normalized to a 0-100 percentage via
    ``resolve_school_score_scale`` before the comparison. Without this a /20
    school (max raw 20) would mark every graded athlete ineligible against a 50
    floor. No academic data on record is NOT adverse — returns True with a note.
    """
    from apps.evals.grading_provisioning import resolve_school_score_scale
    from apps.evals.models import Evaluation

    evaluations = Evaluation.objects.filter(
        school=school,
        student_id=student_id,
        deleted_at__isnull=True,
    )
    scores: list[float] = []
    for evaluation in evaluations.iterator():
        # Only completed evaluations count. An ungraded row's ``total_score``
        # computes to 0.0 (NOT None), so without this an athlete with real
        # graded work but pending mid-term rows — or a school with no
        # AssessmentWeights (every total_score 0.0) — would be dragged below the
        # floor and wrongly marked INELIGIBLE. Mirrors the ranking path's
        # ``is_complete_for_ranking`` gate.
        if not getattr(evaluation, "is_complete_for_ranking", True):
            continue
        value = getattr(evaluation, "total_score", None)
        if value is None:
            continue
        scores.append(float(value))

    if not scores:
        reasons.append("academic: no academic data on record")
        snapshot["academic_average"] = None
        snapshot["academic_average_pct"] = None
        return True

    raw_average = sum(scores) / len(scores)
    score_scale = float(resolve_school_score_scale(school))
    if score_scale > 0:
        average_pct = Decimal(str(max(0.0, min(100.0, raw_average / score_scale * 100.0))))
    else:  # defensive — resolver never returns <=0, but never divide by zero
        average_pct = Decimal(str(raw_average))
    snapshot["academic_average"] = str(Decimal(str(raw_average)))
    snapshot["academic_average_pct"] = str(average_pct)
    if average_pct >= MIN_ELIGIBILITY_AVERAGE:
        return True
    reasons.append(
        f"academic: average {average_pct:.2f}% below floor {MIN_ELIGIBILITY_AVERAGE}%"
    )
    return False


def _attendance_ok(*, school_id, student_id, reasons: list[str], snapshot: dict) -> bool:
    """True when the attendance rate over the window meets the floor.

    No attendance data on record is NOT adverse — returns True with a note.
    """
    from apps.academics.models import Attendance

    window_start = timezone.now().date() - timedelta(
        days=ELIGIBILITY_ATTENDANCE_WINDOW_DAYS
    )
    records = Attendance.objects.filter(
        school_id=school_id,
        student_id=student_id,
        date__gte=window_start,
    )
    total = records.count()
    if total == 0:
        reasons.append("attendance: no attendance data in window")
        snapshot["attendance_rate"] = None
        return True

    # Excused / late count as attended; only ABSENT counts against the athlete.
    attended = records.exclude(status=Attendance.Status.ABSENT).count()
    rate = (Decimal(attended) / Decimal(total)) * _PERCENT
    snapshot["attendance_rate"] = str(rate)
    if rate >= MIN_ELIGIBILITY_ATTENDANCE_PCT:
        return True
    reasons.append(
        f"attendance: rate {rate:.2f}% below floor {MIN_ELIGIBILITY_ATTENDANCE_PCT}%"
    )
    return False


def _medical_ok(*, school_id, student_id, reasons: list[str]) -> bool:
    """True when a current CLEARED medical clearance exists for the student."""
    today = timezone.now().date()
    ok = MedicalClearance.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=today),
        Q(valid_from__isnull=True) | Q(valid_from__lte=today),
        school_id=school_id,
        student_id=student_id,
        status=MedicalClearance.Status.CLEARED,
    ).exists()
    if not ok:
        reasons.append("medical: no current medical clearance")
    return ok


def _consent_ok(*, membership, reasons: list[str]) -> bool:
    """True when a CONSENTED participation consent exists for the membership."""
    ok = ParticipationConsent.objects.filter(
        school_id=membership.school_id,
        membership=membership,
        decision=ParticipationConsentDecision.CONSENTED,
    ).exists()
    if not ok:
        reasons.append("consent: no guardian consent on record")
    return ok


def _pdp_denies(*, membership, actor) -> bool:
    """Consult the PDP when enforcement is on; True only on an explicit DENY.

    Never raises — a probe/decide crash fails CLOSED for the caller's decision
    only by being ignored here (the caller's own floor governs). An implicit
    deny (no rule matched) is NOT treated as a deny, so schools without an
    athletics policy are unaffected.
    """
    if getattr(settings, "POLICY_PDP_ENFORCEMENT_MODE", "") != "enforce":
        return False
    try:
        from apps.policies.pdp import decide

        decision = decide(
            subject={"user_id": getattr(actor, "pk", None), "role": "COACH"},
            action="field",
            resource={
                "entity": "student_athlete",
                "id": str(membership.student_id),
            },
            school=membership.school,
            log=True,
        )
        return decision.effect == "deny"
    except Exception:  # noqa: BLE001 — PDP consult must never break resolution
        logger.warning(
            "eligibility_pdp_consult_failed membership=%s", membership.pk
        )
        return False


@transaction.atomic
def resolve_eligibility(
    *, membership, request=None, actor=None, persist: bool = True
) -> EligibilityOutcome:
    """Resolve a membership's eligibility to play.

    Computes the four school-scoped predicates, derives a status, optionally
    consults the PDP, and (when ``persist``) writes an ``EligibilityRecord``.
    """
    school_id = membership.school_id
    student_id = membership.student_id
    reasons: list[str] = []
    snapshot: dict = {}

    academic_ok = _academic_ok(
        school=membership.school, student_id=student_id, reasons=reasons, snapshot=snapshot
    )
    attendance_ok = _attendance_ok(
        school_id=school_id, student_id=student_id, reasons=reasons, snapshot=snapshot
    )
    medical_ok = _medical_ok(
        school_id=school_id, student_id=student_id, reasons=reasons
    )
    consent_ok = _consent_ok(membership=membership, reasons=reasons)

    if academic_ok and attendance_ok and medical_ok and consent_ok:
        status = EligibilityRecord.Status.ELIGIBLE
    elif academic_ok and attendance_ok:
        # Academic + attendance floors met; only consent / medical are pending.
        status = EligibilityRecord.Status.PROVISIONAL
    else:
        status = EligibilityRecord.Status.INELIGIBLE

    if _pdp_denies(membership=membership, actor=actor):
        status = EligibilityRecord.Status.INELIGIBLE
        reasons.append("pdp: access denied by policy")

    eligible = status == EligibilityRecord.Status.ELIGIBLE
    snapshot.update(
        {
            "academic_ok": academic_ok,
            "attendance_ok": attendance_ok,
            "medical_ok": medical_ok,
            "consent_ok": consent_ok,
            "status": status,
        }
    )

    record = None
    if persist:
        record = EligibilityRecord.objects.create(
            school=membership.school,
            membership=membership,
            status=status,
            academic_ok=academic_ok,
            attendance_ok=attendance_ok,
            medical_ok=medical_ok,
            consent_ok=consent_ok,
            reason="; ".join(reasons),
            snapshot=snapshot,
            checked_by=actor if getattr(actor, "pk", None) else None,
        )

    return EligibilityOutcome(
        eligible=eligible, status=status, reasons=reasons, record=record
    )


__all__ = ["EligibilityOutcome", "resolve_eligibility"]
