"""Report card template studio wizard → tenant report-card layout policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_card_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    return dict((getattr(school, "settings", None) or {}).get("report_card") or {})


def _save_report_card(school: Any | None, blob: dict[str, Any]) -> None:
    if school is None:
        return
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["report_card"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def _normalize_multi(payload: dict[str, Any]) -> list[Any]:
    raw = payload.get("value") or payload.get("columns") or []
    if isinstance(raw, list):
        return raw
    return [raw] if raw else []


def apply_template_anchor(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    template = payload.get("value") or payload.get("template")
    blob = _report_card_blob(school)
    blob["template_anchor"] = template
    _save_report_card(school, blob)
    return {"ok": True, "template_anchor": template}


def apply_grade_columns(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    columns = [str(c) for c in _normalize_multi(payload)]
    blob = _report_card_blob(school)
    blob["grade_columns"] = columns
    _save_report_card(school, blob)
    return {"ok": True, "grade_columns": columns}


def apply_attendance_block(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    block = {
        k: payload.get(k)
        for k in (
            "show_attendance_summary",
            "attendance_threshold_warning_pct",
            "show_punctuality_score",
        )
        if k in payload
    }
    blob = _report_card_blob(school)
    blob["attendance_block"] = block
    _save_report_card(school, blob)
    return {"ok": True, "attendance_block": block}
