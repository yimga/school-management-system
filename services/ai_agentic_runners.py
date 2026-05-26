"""Wave P-B (v3.95.1 — 2026-05-26) — Agentic AI runner bridge.

Bridges the Wave K agentic action kernel to actual application services.

Each runner here is paired 1:1 with a registered action in
``services.ai_agentic._REGISTRY``. The runner does the actual work — query
ORM, call existing service helpers — and returns a result dict.

Safety:
- All runners here are READ-ONLY by design. Mutating runners live in the
  per-action service modules and are explicitly opt-in (the operator wires
  them via ``execute_action(..., runner=their_runner)``).
- Runners fail-soft: every exception is caught by the kernel
  (``execute_action`` already wraps the runner call in try/except).
- No PII in logs.

Boundary: NO direct ``services.ai_gateway`` imports. NO direct ORM imports
outside the function scope (imports inside the runner so test environments
without the full Django stack can still import this module).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .ai_agentic import ActionContext, ProposedAction


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read-only runners
# ---------------------------------------------------------------------------

def run_summarize_attendance_report(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Real summary: count present / absent / late for the given class today.

    Params expected: ``class_id`` (str), ``date_range`` (str, default 'today').

    Returns a dict shaped for the agentic UI:
        {"summary": "5A: 28/30 present today (93%) — 2 absent.",
         "metrics": {...}}
    """
    class_id = str((proposed.params or {}).get("class_id") or "").strip()
    if not class_id:
        return {"summary": "Need a class_id to summarize attendance.",
                "metrics": {}}

    metrics = {"present": 0, "absent": 0, "late": 0, "total": 0}
    try:
        from datetime import date  # local import
        from apps.academics.models import AttendanceRecord  # type: ignore
        # Today's records. Scope-narrowed by class_id; tenant safety is
        # enforced by the model's default manager.
        today = date.today()
        qs = AttendanceRecord.objects.filter(
            classroom_id=class_id, date=today,
        )
        for rec in qs.values("status"):
            status = (rec.get("status") or "").lower()
            metrics["total"] += 1
            if status in ("present", "p"):
                metrics["present"] += 1
            elif status in ("absent", "a"):
                metrics["absent"] += 1
            elif status in ("late", "l", "tardy"):
                metrics["late"] += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "summarize_attendance_report runner: model query failed err=%s",
            exc,
        )
        return {"summary": "Attendance data unavailable.", "metrics": metrics}

    if metrics["total"] == 0:
        return {"summary": f"No attendance recorded for {class_id} today.",
                "metrics": metrics}
    pct = round(100.0 * metrics["present"] / metrics["total"], 1)
    return {
        "summary": (
            f"{class_id}: {metrics['present']}/{metrics['total']} present "
            f"({pct}%) — {metrics['absent']} absent, {metrics['late']} late."
        ),
        "metrics": metrics,
    }


def run_summarize_outstanding_fees(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Sum outstanding fees for a class, or platform-wide if no class given."""
    class_id = str((proposed.params or {}).get("class_id") or "").strip()
    totals = {"count": 0, "outstanding_minor": 0, "currency": ""}
    try:
        from apps.finance.models import StudentInvoice  # type: ignore
        qs = StudentInvoice.objects.filter(is_paid=False)
        if class_id:
            qs = qs.filter(student__current_class_id=class_id)
        for row in qs.values("outstanding_amount", "currency_code"):
            amt = row.get("outstanding_amount") or 0
            try:
                # ORM may return Decimal — convert to minor int.
                from decimal import Decimal
                totals["outstanding_minor"] += int(Decimal(amt) * 100)
            except Exception:  # noqa: BLE001
                continue
            totals["count"] += 1
            if not totals["currency"]:
                totals["currency"] = row.get("currency_code") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "summarize_outstanding_fees runner: model query failed err=%s",
            exc,
        )
        return {"summary": "Finance data unavailable.", "totals": totals}

    if totals["count"] == 0:
        return {"summary": "No outstanding invoices.", "totals": totals}
    scope = f"class {class_id}" if class_id else "platform-wide"
    return {
        "summary": (
            f"{totals['count']} outstanding invoice"
            f"{'s' if totals['count'] != 1 else ''} ({scope}); "
            f"total {totals['outstanding_minor']} minor units {totals['currency']}."
        ),
        "totals": totals,
    }


def run_draft_parent_announcement(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Produce a parent-friendly draft announcement. Pure text — no I/O."""
    params = proposed.params or {}
    topic = str(params.get("topic") or "").strip() or "an update from school"
    audience = str(params.get("audience") or "all_parents").strip()
    locale = str(params.get("locale") or "en").strip()

    audience_label = {
        "all_parents": "Dear parents",
        "primary_parents": "Dear primary-section parents",
        "secondary_parents": "Dear secondary-section parents",
        "year_12_parents": "Dear Year 12 parents",
    }.get(audience, "Dear parents")

    body = (
        f"{audience_label},\n\n"
        f"We're writing to share {topic}. Further details will be available "
        f"in your parent portal under Announcements. Replies to this thread "
        f"reach the school office during open hours.\n\n"
        f"Thank you,\nSchool Office"
    )
    return {
        "draft": body,
        "audience": audience,
        "locale": locale,
        "estimated_read_seconds": max(15, len(body) // 12),
    }


# ---------------------------------------------------------------------------
# Runner registry
# ---------------------------------------------------------------------------

_RUNNERS: dict[str, Callable[[ProposedAction, ActionContext], dict[str, Any]]] = {
    "summarize_attendance_report": run_summarize_attendance_report,
    "summarize_outstanding_fees": run_summarize_outstanding_fees,
    "draft_parent_announcement": run_draft_parent_announcement,
}


def get_runner_for(action: str):
    """Return the bridged runner for a given action, or None when not yet
    implemented (e.g. mutating actions intentionally have no auto-runner —
    the caller must supply their own)."""
    return _RUNNERS.get(action)


def list_bridged_actions() -> tuple[str, ...]:
    return tuple(_RUNNERS.keys())
