"""Institutional board reporting kernel — aggregates via in-repo BI services."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def refresh_board_kpi_snapshot(*, school: Any, kpi_keys: list[str] | None = None) -> dict[str, Any]:
    from apps.reports.bi_services import ExecutiveReportingService

    if school is None:
        return {}
    end = timezone.now()
    start = end - timedelta(days=90)
    sid = str(getattr(school, "pk", ""))
    finance = ExecutiveReportingService.get_financial_summary(start, end, school_id=sid)
    snapshot = _json_safe(
        {
            "finance": finance,
            "kpi_keys": kpi_keys or [],
            "generated_at": end.isoformat(),
        }
    )
    settings = dict(getattr(school, "settings", None) or {})
    settings["board_reporting"] = snapshot
    school.settings = settings
    school.save(update_fields=["settings"])
    return snapshot


def apply_enabled_executive_kpis(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    raw = payload.get("value") or payload.get("kpi_keys") or []
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    kpi_keys = [str(k) for k in raw]
    settings = dict(getattr(school, "settings", None) or {})
    board = dict(settings.get("board_reporting") or {})
    board["enabled_kpis"] = kpi_keys
    settings["board_reporting"] = board
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "enabled_kpis": kpi_keys}


def apply_predictions_policy(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("predictions_enabled", True)
    settings = dict(getattr(school, "settings", None) or {})
    board = dict(settings.get("board_reporting") or {})
    board["predictions_enabled"] = bool(enabled)
    settings["board_reporting"] = board
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "predictions_enabled": bool(enabled)}
