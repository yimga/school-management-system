"""Feature extraction for the grade-prediction model (Wave 4).

Mirrors the at-risk extractor pattern but operates on (student, subject,
term) tuples — the smallest unit at which the model makes a prediction.
A single student appears multiple times per nightly batch (one row per
enrolled subject).

Features extracted (per scoping tuple, over the term):
  * prior_mean_score      — same student's prior-term avg in the same subject
  * mid_term_avg          — avg seq1/seq2 in the current term-to-date
  * mid_term_count        — number of evaluations seen so far this term
  * attendance_rate       — share of present days this term
  * absence_count         — absences this term
  * eval_trend            — slope from earliest to latest eval this term
  * incident_count        — disciplinary incidents in the term
  * days_in_term_so_far   — observability proxy (cold-start signal)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.utils import timezone


@dataclass
class GradePredictionFeatures:
    student_id: str
    subject_id: str
    term_id: str
    prior_mean_score: float = 60.0  # platform-wide default cohort grade
    mid_term_avg: float = 0.0
    mid_term_count: int = 0
    attendance_rate: float = 1.0
    absence_count: int = 0
    eval_trend: float = 0.0
    incident_count: int = 0
    days_in_term_so_far: int = 0

    def as_vector(self) -> list[float]:
        """Stable column order matching `_FEATURE_NAMES` in the scorer."""
        return [
            self.prior_mean_score,
            self.mid_term_avg,
            float(self.mid_term_count),
            self.attendance_rate,
            float(self.absence_count),
            self.eval_trend,
            float(self.incident_count),
            float(self.days_in_term_so_far),
        ]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_grade_prediction_features(
    student, subject, term,
) -> GradePredictionFeatures:
    """Build features for (student, subject, term). Read-only DB calls.

    Never raises — extractor failures default to a neutral feature row
    and the heuristic scorer absorbs the missing signal.
    """
    features = GradePredictionFeatures(
        student_id=str(getattr(student, "id", "") or ""),
        subject_id=str(getattr(subject, "id", "") or ""),
        term_id=str(getattr(term, "id", "") or ""),
    )
    _populate_eval_history(features, student, subject, term)
    _populate_attendance(features, student, term)
    _populate_incidents(features, student, term)
    _populate_term_progress(features, term)
    return features


def _populate_eval_history(features, student, subject, term):
    try:
        from apps.evals.models import Evaluation
    except (ImportError, ModuleNotFoundError):
        return
    try:
        current = list(
            Evaluation.objects.filter(  # tenant-isolation-allow: scoped via student FK (student.school)
                student=student,
                subject_assignment__subject=subject,
                subject_assignment__term=term,
            )
            .only("seq1", "seq2", "exam", "updated_at")
            .order_by("updated_at")
        )
    except (AttributeError, TypeError, ValueError):
        current = []
    scores: list[float] = []
    for ev in current:
        candidates = [
            getattr(ev, "seq1", None),
            getattr(ev, "seq2", None),
        ]
        nums = [float(v) for v in candidates if v is not None]
        if nums:
            scores.append(sum(nums) / len(nums))
    if scores:
        features.mid_term_avg = round(sum(scores) / len(scores), 2)
        features.mid_term_count = len(scores)
        if len(scores) >= 2:
            features.eval_trend = round(scores[-1] - scores[0], 2)
    # Prior-term: same student/subject, term != current.
    try:
        prior = list(
            Evaluation.objects.filter(  # tenant-isolation-allow: scoped via student FK (student.school)
                student=student,
                subject_assignment__subject=subject,
            )
            .exclude(subject_assignment__term=term)
            .only("seq1", "seq2", "exam")
            .order_by("-id")[:8]
        )
    except (AttributeError, TypeError, ValueError):
        prior = []
    prior_scores: list[float] = []
    for ev in prior:
        nums = [
            float(v) for v in [
                getattr(ev, "seq1", None),
                getattr(ev, "seq2", None),
                getattr(ev, "exam", None),
            ]
            if v is not None
        ]
        if nums:
            prior_scores.append(sum(nums) / len(nums))
    if prior_scores:
        features.prior_mean_score = round(
            sum(prior_scores) / len(prior_scores), 2
        )


def _populate_attendance(features, student, term):
    try:
        from apps.academics.models import Attendance
    except (ImportError, ModuleNotFoundError):
        return
    try:
        rows = list(
            Attendance.objects.filter(  # tenant-isolation-allow: scoped via student FK (student.school)
                student=student,
                date__gte=term.start_date,
                date__lte=term.end_date,
            ).only("status")
        )
    except (AttributeError, TypeError, ValueError):
        return
    if not rows:
        return
    total = len(rows)
    present = sum(1 for r in rows if r.status == "present")
    absent = sum(1 for r in rows if r.status == "absent")
    features.attendance_rate = round(present / total, 4)
    features.absence_count = absent


def _populate_incidents(features, student, term):
    try:
        from apps.academics.models import Incident
    except (ImportError, ModuleNotFoundError):
        return
    try:
        features.incident_count = Incident.objects.filter(  # tenant-isolation-allow: scoped via student FK (student.school)
            student=student,
            date__gte=term.start_date,
            date__lte=term.end_date,
        ).count()
    except (AttributeError, TypeError, ValueError):
        return


def _populate_term_progress(features, term):
    try:
        today = timezone.now().date()
        start = getattr(term, "start_date", None)
        if start is None:
            return
        delta = today - start
        features.days_in_term_so_far = max(0, delta.days)
    except (AttributeError, TypeError, ValueError):
        return
