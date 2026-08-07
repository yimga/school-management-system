"""
Pass 13.D: feature extraction for the at-risk model.

This is the platform-side feature pipeline. It turns one student (within
one school's scope) into the feature vector the trained scikit-learn /
LightGBM model will consume. Lives outside `ml_inference.py` so the
training notebook + the live inference path can share exactly the same
extraction logic.

When no trained model artifact is present, callers fall back to the
existing heuristic from `apps.analytics.services.AdvancedAnalyticsService.
identify_at_risk_students` — this module just shapes inputs.

Features extracted (per student, over the last `window_days` days):
  - attendance_rate              float in [0, 1]
  - absence_count                int
  - late_count                   int
  - avg_evaluation_score         float in [0, 100]
  - evaluation_count             int
  - eval_score_trend             float (slope, scaled per term)
  - open_invoice_count           int
  - open_balance_amount          float (decimal-cast to native float)
  - days_since_last_login        int (very large when never)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

DEFAULT_WINDOW_DAYS = 60


@dataclass
class AtRiskFeatures:
    student_id: str
    attendance_rate: float = 1.0
    absence_count: int = 0
    late_count: int = 0
    avg_evaluation_score: float = 0.0
    evaluation_count: int = 0
    eval_score_trend: float = 0.0
    open_invoice_count: int = 0
    open_balance_amount: float = 0.0
    days_since_last_login: int = 9999

    def as_vector(self) -> list[float]:
        """Stable column order for the model artifact."""
        return [
            self.attendance_rate,
            float(self.absence_count),
            float(self.late_count),
            self.avg_evaluation_score,
            float(self.evaluation_count),
            self.eval_score_trend,
            float(self.open_invoice_count),
            self.open_balance_amount,
            float(self.days_since_last_login),
        ]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_features(student, *, window_days: int = DEFAULT_WINDOW_DAYS) -> AtRiskFeatures:
    """
    Build an AtRiskFeatures row for `student`. Falls back to sentinel values
    for any signal that throws — feature extraction must never crash the
    nightly batch. Every database call is read-only.
    """
    features = AtRiskFeatures(student_id=str(getattr(student, "id", "") or ""))
    since = timezone.now() - timedelta(days=window_days)

    _populate_attendance(features, student, since)
    _populate_evaluations(features, student, since)
    _populate_finance(features, student)
    _populate_last_login(features, student)

    return features


def _populate_attendance(features: AtRiskFeatures, student, since) -> None:
    try:
        from apps.academics.models import Attendance

        rows = list(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Attendance.objects.filter(student=student, date__gte=since.date()).only(
                "status"
            )
        )
    except Exception:  # noqa: BLE001
        return
    if not rows:
        return
    total = len(rows)
    present = sum(1 for r in rows if r.status == "present")
    absent = sum(1 for r in rows if r.status == "absent")
    late = sum(1 for r in rows if r.status == "late")
    features.attendance_rate = round(present / total, 4) if total else 1.0
    features.absence_count = absent
    features.late_count = late


def _populate_evaluations(features: AtRiskFeatures, student, since) -> None:
    try:
        from apps.evals.models import Evaluation

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        qs = (
            Evaluation.objects.filter(student=student, updated_at__gte=since)
            # The Evaluation fields are seq1_score/seq2_score/exam_score; the old
            # bare seq1/seq2/exam raised FieldError (swallowed below), so these
            # three at-risk ML features were silently pinned to 0.
            .only("seq1_score", "seq2_score", "exam_score", "updated_at")
            .order_by("updated_at")
        )
        rows = list(qs)
    except Exception:  # noqa: BLE001
        return
    if not rows:
        return
    scores: list[float] = []
    for r in rows:
        candidates = [
            getattr(r, "seq1_score", None),
            getattr(r, "seq2_score", None),
            getattr(r, "exam_score", None),
        ]
        nums = [float(v) for v in candidates if v is not None]
        if nums:
            scores.append(sum(nums) / len(nums))
    if scores:
        features.evaluation_count = len(scores)
        features.avg_evaluation_score = round(sum(scores) / len(scores), 2)
        if len(scores) >= 2:
            features.eval_score_trend = round(scores[-1] - scores[0], 2)


def _populate_finance(features: AtRiskFeatures, student) -> None:
    try:
        from apps.finance.models import Invoice
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        invoices = list(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Invoice.objects.filter(student=student)
            .exclude(status__iexact="paid")
            .only("balance_amount")
        )
    except Exception:  # noqa: BLE001
        return
    features.open_invoice_count = len(invoices)
    features.open_balance_amount = float(
        sum(getattr(inv, "balance_amount", 0) or 0 for inv in invoices)
    )


def _populate_last_login(features: AtRiskFeatures, student) -> None:
    user = getattr(student, "user", None) or getattr(student, "linked_user", None)
    if user is None:
        return
    last_login = getattr(user, "last_login", None)
    if last_login is None:
        return
    delta = timezone.now() - last_login
    features.days_since_last_login = max(0, delta.days)
