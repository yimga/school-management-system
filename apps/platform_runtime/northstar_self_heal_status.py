"""North Star self-heal report interpretation for operator surfaces."""

from __future__ import annotations

_PASS_STATUSES = frozenset({"PASS", "SELF_HEALED_PASS", "OK"})
_IGNORE_ATTENTION_STATUSES = frozenset({"", "NOT RUN", "NOT_RUN"})


def self_heal_requires_attention(report: dict | None) -> bool:
    """True when an operator insight card should warn about self-heal."""
    if not report:
        return False
    unsafe = list(report.get("unsafe_ticket_paths") or [])
    if unsafe:
        return True
    status = (report.get("status") or "not run").strip().upper()
    if status in _PASS_STATUSES:
        return False
    if status in _IGNORE_ATTENTION_STATUSES:
        return False
    return "FAIL" in status


def self_heal_display_status(report: dict | None) -> str:
    """Human-readable status label for KPI tiles."""
    return (report.get("status") or "not run").strip() if report else "not run"
