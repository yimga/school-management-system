"""Graduation pathway + elective matcher — in-repo Subject catalog (no paid CRM)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pathway_settings(school: Any) -> dict[str, Any]:
    return dict((getattr(school, "settings", None) or {}).get("graduation_pathway") or {})


def _save_pathway(school: Any, blob: dict[str, Any]) -> None:
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["graduation_pathway"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def set_pathway_objective(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    objective = payload.get("value") or payload.get("objective") or "university_general"
    blob = _pathway_settings(school)
    blob["objective"] = str(objective)
    _save_pathway(school, blob)
    return {"ok": True, "objective": blob["objective"]}


def enable_credit_audit(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("enabled", True)
    blob = _pathway_settings(school)
    blob["credit_metric_audit"] = bool(enabled)
    _save_pathway(school, blob)
    return {"ok": True, "credit_metric_audit": blob["credit_metric_audit"]}


def match_elective_courses(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    from apps.academics.models import Subject

    selected = payload.get("value") or payload.get("course_ids") or []
    if not isinstance(selected, list):
        selected = [selected]
    names = list(
        Subject.objects.filter(school=school, name__in=selected).values_list("name", flat=True)[:50]
    )
    blob = _pathway_settings(school)
    blob["matched_courses"] = names or selected
    blob["matcher"] = "academics.Subject.name_filter"
    _save_pathway(school, blob)
    return {"ok": True, "matched_courses": blob["matched_courses"]}


def lock_pathway(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    locked = payload.get("value")
    if locked is None:
        locked = payload.get("locked", True)
    blob = _pathway_settings(school)
    blob["locked"] = bool(locked)
    _save_pathway(school, blob)
    return {"ok": True, "locked": blob["locked"]}
