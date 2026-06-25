"""Year-close checklist payload for admin surfaces (batch 1739)."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


def build_year_close_checklist(school, *, user: Any = None) -> dict[str, Any]:
    if school is None:
        return {"ok": False, "visible": False, "items": []}

    settings_blob = getattr(school, "settings", None) or {}
    if not isinstance(settings_blob, dict):
        settings_blob = {}
    acks = settings_blob.get("rmc_year_close_acks") or {}
    if not isinstance(acks, dict):
        acks = {}

    from apps.academics.services import get_active_year_and_term
    from apps.academics.year_close import (
        academic_year_close_in_progress,
        evaluate_year_close_blockers,
    )
    from apps.academics.models import AcademicYear

    if not academic_year_close_in_progress(school):
        year, _term = get_active_year_and_term()
        if not year:
            return {"ok": True, "visible": False, "items": []}
        next_year = (
            AcademicYear.objects.filter(school=school, start_date__gt=year.start_date)
            .order_by("start_date")
            .first()
        )
        if not next_year:
            return {"ok": True, "visible": False, "items": []}
        scorecard = evaluate_year_close_blockers(school, year, next_year)
        blockers = scorecard.get("blockers") or []
        if not blockers and scorecard.get("ok"):
            return {"ok": True, "visible": False, "items": []}
        items = [
            {
                "key": b.get("code", ""),
                "label": b.get("message", ""),
                "done": False,
                "blocker": True,
            }
            for b in blockers
        ]
        return {
            "ok": True,
            "visible": bool(items),
            "summary": str(_("Resolve blockers before opening the next academic year")),
            "items": items,
        }

    items = [
        {
            "key": "grades",
            "label": str(_("Finalize term grades")),
            "done": bool(acks.get("grades")),
            "blocker": False,
        },
        {
            "key": "attendance",
            "label": str(_("Lock attendance registers")),
            "done": bool(acks.get("attendance")),
            "blocker": False,
        },
        {
            "key": "fees",
            "label": str(_("Reconcile outstanding fees")),
            "done": bool(acks.get("fees")),
            "blocker": False,
        },
        {
            "key": "reports",
            "label": str(_("Run year-end reports")),
            "done": bool(acks.get("reports")),
            "blocker": False,
        },
        {
            "key": "open_year",
            "label": str(_("Open next academic year")),
            "done": bool(acks.get("open_year")),
            "blocker": False,
        },
    ]
    return {
        "ok": True,
        "visible": True,
        "summary": str(_("Year close in progress")),
        "items": items,
        "offline_action_type": "year_close_ack",
    }
