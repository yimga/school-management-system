"""v4.00.13 — adaptive learning kernel caller.

Closes the v4.00.12 follow-on gap: ``apps/academics/adaptive_scaffold.py``
shipped ``recommend_next_topic`` but nothing invoked it. This module wires
a post-save signal on ``apps.evals.Evaluation`` (the real grade-entry model)
that calls the kernel with the student's last 6 final_score values, then
stashes the recommendation under
``student.extra_data["adaptive_next"]`` (no migration needed — JSONField).

The signal is best-effort: never blocks the grade save, never raises.
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def _normalize_score(raw, max_score=20) -> float | None:
    """Coerce a raw evaluation score to a [0, 1] band."""
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if max_score <= 0:
        return None
    return max(0.0, min(1.0, val / float(max_score)))


def _gather_recent_scores(student, limit: int = 6) -> list[float]:
    """Walk the student's most recent Evaluation rows; normalize final_score."""
    try:
        Evaluation = django_apps.get_model("evals", "Evaluation")
    except Exception:  # noqa: BLE001 — app not installed in this profile
        return []
    if student is None:
        return []
    try:
        rows = (
            Evaluation.objects.filter(student=student)  # tenant-isolation-allow: scoped-via-student-fk-evaluation-recent
            .order_by("-id")[: max(1, int(limit))]
        )
    except Exception:  # noqa: BLE001
        return []
    scores: list[float] = []
    for row in rows:
        raw = getattr(row, "final_score", None) or getattr(row, "total_score", None)
        # Most schools grade out of 20 (FR/CM); fall back to that anchor.
        normalized = _normalize_score(raw, max_score=20)
        if normalized is not None:
            scores.append(normalized)
    return scores


def _persist_recommendation(student, recommendation_dict: dict) -> None:
    """Stash the recommendation on ``student.extra_data["adaptive_next"]``."""
    if student is None or getattr(student, "pk", None) is None:
        return
    try:
        extra = getattr(student, "extra_data", None) or {}
        if not isinstance(extra, dict):
            extra = {}
        extra["adaptive_next"] = recommendation_dict
        student.extra_data = extra
        student.save(update_fields=["extra_data"])
    except Exception as exc:  # noqa: BLE001 — never break grade entry
        logger.debug("adaptive: persist failed for student=%s: %s", getattr(student, "pk", "?"), exc)


def _evaluation_saved(sender, instance, created, **kwargs):  # noqa: ARG001
    """Post-save: compute recommendation, persist to student.extra_data."""
    try:
        from apps.academics.adaptive_scaffold import recommend_next_topic
        from apps.academics.curriculum_map import resolve_topic_siblings
    except Exception:  # noqa: BLE001
        return

    student = getattr(instance, "student", None)
    if student is None:
        return
    scores = _gather_recent_scores(student)
    if not scores:
        return
    try:
        # v4.00.14: curriculum map supplies remedial/follow_on/advanced keys
        # from a default subject→topic chain (school-overridable).
        subject_obj = getattr(instance, "subject", None) or getattr(instance, "subject_assignment", None)
        subject_key = ""
        if subject_obj is not None:
            subject_key = (
                str(getattr(subject_obj, "subject_key", "") or "")
                or str(getattr(subject_obj, "code", "") or "")
                or str(getattr(subject_obj, "slug", "") or "")
                or str(getattr(subject_obj, "name", "") or "")
            )
        if not subject_key:
            subject_key = str(getattr(instance, "subject_id", "") or "")
        current_topic_key = subject_key or "current"

        school = getattr(student, "school", None) or getattr(instance, "school", None)
        school_settings = getattr(school, "settings", None) if school is not None else None
        siblings = resolve_topic_siblings(
            subject_key=subject_key,
            current_topic_key=current_topic_key,
            school_settings=school_settings if isinstance(school_settings, dict) else None,
        )

        rec = recommend_next_topic(
            recent_scores=scores,
            current_topic_key=current_topic_key,
            remedial_topic_key=siblings.get("remedial"),
            follow_on_topic_key=siblings.get("follow_on"),
            advanced_topic_key=siblings.get("advanced"),
        )
        _persist_recommendation(student, {
            "topic_key": rec.topic_key,
            "rationale": rec.rationale,
            "difficulty_band": rec.difficulty_band,
            "confidence": rec.confidence,
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("adaptive: recommend failed: %s", exc)


def connect_adaptive_signals() -> None:
    """Idempotent connector — called from AppConfig.ready()."""
    try:
        Evaluation = django_apps.get_model("evals", "Evaluation")
    except Exception:  # noqa: BLE001
        return
    post_save.connect(_evaluation_saved, sender=Evaluation, dispatch_uid="adaptive_kernel_post_save")
