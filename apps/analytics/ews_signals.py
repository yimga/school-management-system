"""
N28 / BR-06: mirror nightly RiskFactor rows into StudentAtRiskSignal when the
student has a linked portal user — deepens EWS beyond dashboard-only RiskFactor.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.analytics.models import RiskFactor, StudentAtRiskSignal

_AMBER_MIN = 50.0


@receiver(post_save, sender=RiskFactor)
def sync_student_at_risk_signal_from_risk_factor(
    sender, instance: RiskFactor, **kwargs
) -> None:
    student = instance.student
    uid = getattr(student, "user_id", None)
    if not uid:
        return
    score = float(instance.score)
    if score < _AMBER_MIN:
        return

    factors = {
        "risk_factor_id": instance.pk,
        "reason": (instance.reason_summary or "")[:500],
        "band": instance.band,
        "computed_at": instance.computed_at.isoformat()
        if instance.computed_at
        else None,
    }

    sig, created = StudentAtRiskSignal.objects.get_or_create(
        school_id=instance.school_id,
        student_user_id=uid,
        defaults={
            "score": score,
            "factors": factors,
            "status": StudentAtRiskSignal.Status.OPEN,
        },
    )
    if created:
        return
    if sig.status in (
        StudentAtRiskSignal.Status.RESOLVED,
        StudentAtRiskSignal.Status.DISMISSED,
    ):
        return
    sig.score = score
    sig.factors = factors
    sig.save(update_fields=["score", "factors", "updated_at"])
