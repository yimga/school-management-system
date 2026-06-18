"""Exam schedule orchestration wizard → certification session + invigilation policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exam_settings(school: Any) -> dict[str, Any]:
    return dict((getattr(school, "settings", None) or {}).get("exam_orchestration") or {})


def _save_exam(school: Any, blob: dict[str, Any]) -> None:
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["exam_orchestration"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def configure_exam_window(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    window = {
        "exam_window_label": payload.get("exam_window_label"),
        "window_start_date": str(payload.get("window_start_date") or ""),
        "window_end_date": str(payload.get("window_end_date") or ""),
        "results_publish_date": str(payload.get("results_publish_date") or ""),
    }
    blob = _exam_settings(school)
    blob["window"] = window
    _save_exam(school, blob)

    session_id = None
    label = (window.get("exam_window_label") or "").strip()
    if label:
        from apps.academics.models import AcademicYear, CertificationExamSession

        year = (
            AcademicYear.objects.filter(school=school, is_active=True)
            .order_by("-start_date")
            .first()
        )
        if year is not None:
            session, _ = CertificationExamSession.objects.get_or_create(
                school=school,
                academic_year=year,
                board=CertificationExamSession.Board.OTHER,
                level=CertificationExamSession.Level.OTHER,
                name=label[:120],
                defaults={"is_active": True},
            )
            session_id = session.pk
    return {"ok": True, "window": window, "certification_session_id": session_id}


def configure_room_strategy(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    strategy = payload.get("value") or payload.get("room_strategy") or "by_subject_then_room"
    blob = _exam_settings(school)
    blob["room_strategy"] = str(strategy)
    _save_exam(school, blob)
    return {"ok": True, "room_strategy": blob["room_strategy"]}


def configure_invigilation(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    inv = {
        "invigilator_count_per_room": int(payload.get("invigilator_count_per_room") or 1),
        "max_invigilation_hours_per_teacher_per_day": int(
            payload.get("max_invigilation_hours_per_teacher_per_day") or 6
        ),
        "subject_teacher_exempt": bool(payload.get("subject_teacher_exempt", True)),
        "auto_balance_load": bool(payload.get("auto_balance_load", True)),
    }
    blob = _exam_settings(school)
    blob["invigilation"] = inv
    _save_exam(school, blob)
    return {"ok": True, "invigilation": inv}


def configure_results_pipeline(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    pipeline = {
        "auto_release_to_parents": bool(payload.get("auto_release_to_parents", False)),
        "require_admin_approval_before_release": bool(
            payload.get("require_admin_approval_before_release", True)
        ),
        "include_class_rank": bool(payload.get("include_class_rank", False)),
        "include_subject_teacher_comment": bool(payload.get("include_subject_teacher_comment", True)),
    }
    blob = _exam_settings(school)
    blob["results_pipeline"] = pipeline
    _save_exam(school, blob)
    return {"ok": True, "results_pipeline": pipeline}
