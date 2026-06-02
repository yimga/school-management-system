"""Predictive degrading status — before a run is formally stuck."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.workflow_duration_stats import get_p95_seconds
from apps.platform_runtime.workflow_tracker import _run_age_seconds, is_stuck


def is_degrading(run: Any) -> bool:
    """True when a RUNNING row is slower than ETA but not yet stuck."""

    if getattr(run, "status", "") != "running":
        return False
    if is_stuck(run):
        return False
    age = _run_age_seconds(run)
    if age <= 0:
        return False
    expected = max(int(getattr(run, "expected_duration_seconds", 30) or 30), 5)
    if age > expected:
        return True
    p95 = get_p95_seconds(str(getattr(run, "workflow_key", "") or ""))
    if p95 > 0 and age > int(p95 * 0.85):
        return True
    return False


def resolve_display_status(run: Any) -> str:
    status = getattr(run, "status", "") or "running"
    if status == "running":
        if is_stuck(run):
            return "stuck"
        if is_degrading(run):
            return "degrading"
    return status
