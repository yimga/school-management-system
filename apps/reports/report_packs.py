from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ReportPack


def list_active_report_packs() -> list[ReportPack]:
    return list(ReportPack.objects.filter(is_active=True).order_by("name", "code"))


def normalize_report_pack_dependencies(pack: ReportPack) -> list[dict[str, Any]]:
    payload = getattr(pack, "dependency_schema", None) or {}
    if not isinstance(payload, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for group, raw_items in payload.items():
        label = str(group).replace("_", " ").strip().title()
        items: list[str] = []
        if isinstance(raw_items, list):
            items = [str(item).strip() for item in raw_items if str(item).strip()]
        elif isinstance(raw_items, Mapping):
            items = [
                str(value).strip() for value in raw_items.values() if str(value).strip()
            ]
        elif raw_items not in (None, ""):
            items = [str(raw_items).strip()]
        if items:
            rows.append({"group": str(group), "label": label, "items": items})
    return rows


def build_report_pack_preview(pack: ReportPack) -> dict[str, Any]:
    config = getattr(pack, "sample_data_config", None) or {}
    if not isinstance(config, Mapping):
        config = {}
    rows = config.get("rows")
    if not isinstance(rows, list) or not rows:
        rows = [
            {"label": "Average", "value": "13.42"},
            {"label": "Promotion", "value": "Promoted"},
            {"label": "Class rank", "value": "4 / 28"},
        ]
    else:
        norm_rows: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            lbl = raw.get("label") or raw.get("name") or "—"
            val = raw.get("value")
            if val is None:
                val = raw.get("val", "—")
            norm_rows.append({"label": str(lbl), "value": str(val)})
        rows = norm_rows or [
            {"label": "Average", "value": "13.42"},
        ]
    summary = config.get("summary")
    if not isinstance(summary, Mapping):
        summary = {
            "report_type": "Term report",
            "sample_student": "Sample learner",
            "notes": "Seeded preview data available for template checks and stakeholder review.",
        }
    return {
        "title": str(config.get("title") or pack.name or pack.code),
        "description": str(config.get("description") or pack.description or "").strip(),
        "rows": rows,
        "summary": dict(summary),
    }
