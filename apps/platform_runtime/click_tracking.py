"""
Click measurement contract — prove workflow efficiency (e.g. fewer clicks), never infer without data.

Definitions
-----------
click
    Deliberate user activation of a control (primary pointer down/up on an actionable
    element that advances intent): buttons, links, toggles, list rows wired as actions.

screen
    Distinct authenticated surface: route load (SPA/page), ``modal:`` open, ``drawer:`` open,
    or ``panel:`` transition. Represent in payloads via ``path`` and optional ``screen_token``.

task
    Named workflow with explicit ``task_start`` → … clicks … → ``task_complete`` bound by
    ``session_run_id``. Instrument templates with ``data-task``, ``data-task-step``, ``data-action``.

Tracked workflows (canonical ``task_code`` values):
``teacher_marks_entry``, ``attendance_export``, ``parent_payment``,
``report_generation``, ``marketplace_install``.

Measurement rule
----------------
A **50% click reduction** claim is **disallowed** unless:

1. Both phases (``baseline`` and ``current``) reach ``MIN_COMPLETED_SESSIONS`` completed runs each.
2. Median clicks per completed run is computed from recorded ``click`` rows only.

Otherwise callers must surface **insufficient data**.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

TRACKED_TASK_CODES: tuple[str, ...] = (
    "teacher_marks_entry",
    "attendance_export",
    "parent_payment",
    "report_generation",
    "marketplace_install",
)

PHASE_BASELINE = "baseline"
PHASE_CURRENT = "current"

# Minimum completed sessions (start + complete present) per phase before comparisons / claims.
MIN_COMPLETED_SESSIONS_DEFAULT = 8

CLAIM_REDUCTION_THRESHOLD_PCT = 50.0

# Public copy for operator dashboard (matches instrumented templates + platform_behavior_track.js)
CLICK_SYSTEM_DEFINITIONS: dict[str, str] = {
    "click": (
        "User activation: a button, link, or meaningful dropdown change that advances intent."
    ),
    "screen": (
        "A route load, modal, drawer, or other major UI state; see path and optional screen token."
    ),
    "task": (
        "A full workflow from task_start to task_complete, bound by a session run id in the browser."
    ),
}


def get_click_system_public_context() -> dict[str, str]:
    """Template-safe labels for the /internal/click-measurement/ dashboard."""
    return dict(CLICK_SYSTEM_DEFINITIONS)


def _median(nums: list[float]) -> float | None:
    if not nums:
        return None
    return float(statistics.median(nums))


def _completed_session_click_counts(
    *,
    school_id: int,
    task_code: str,
    phase: str,
) -> list[int]:
    from apps.platform_runtime.models import ClickTrackEvent

    K = ClickTrackEvent.Kind
    starts = set(
        ClickTrackEvent.objects.filter(
            school_id=school_id,
            task_code=task_code,
            phase=phase,
            kind=K.TASK_START,
        ).values_list("session_run_id", flat=True)
    )
    completes = set(
        ClickTrackEvent.objects.filter(
            school_id=school_id,
            task_code=task_code,
            phase=phase,
            kind=K.TASK_COMPLETE,
        ).values_list("session_run_id", flat=True)
    )
    completed_ids = starts & completes
    out: list[int] = []
    for sid in completed_ids:
        n = ClickTrackEvent.objects.filter(
            school_id=school_id,
            task_code=task_code,
            phase=phase,
            session_run_id=sid,
            kind=K.CLICK,
        ).count()
        out.append(n)
    return out


def get_median_clicks_before_after(
    school_id: int,
    *,
    task_code: str | None = None,
    min_sessions: int = MIN_COMPLETED_SESSIONS_DEFAULT,
) -> dict[str, Any]:
    """
    Compare median clicks per **completed** task session between ``baseline`` and ``current``.

    Returns structured analytics including whether sample sizes allow any comparative claim.
    """
    codes = (task_code,) if task_code else TRACKED_TASK_CODES
    per_task: dict[str, Any] = {}
    baseline_medians: list[float] = []
    current_medians: list[float] = []

    for tc in codes:
        b_counts = _completed_session_click_counts(
            school_id=school_id, task_code=tc, phase=PHASE_BASELINE
        )
        c_counts = _completed_session_click_counts(
            school_id=school_id, task_code=tc, phase=PHASE_CURRENT
        )
        b_med = _median([float(x) for x in b_counts])
        c_med = _median([float(x) for x in c_counts])
        has_any = len(b_counts) > 0 or len(c_counts) > 0
        # Low sample: only when we have some runs but not enough on one or both sides to compare.
        insufficient = has_any and (
            len(b_counts) < min_sessions or len(c_counts) < min_sessions
        )
        reduction_pct: float | None = None
        if b_med is not None and c_med is not None and b_med > 0:
            reduction_pct = round((b_med - c_med) / b_med * 100.0, 2)

        gate = getattr(settings, "FIFTY_PCT_REDUCTION_CLAIM_ALLOWED", False)
        meets_claim = bool(
            gate
            and not insufficient
            and reduction_pct is not None
            and reduction_pct >= CLAIM_REDUCTION_THRESHOLD_PCT
        )

        per_task[tc] = {
            "baseline_completed_sessions": len(b_counts),
            "current_completed_sessions": len(c_counts),
            "baseline_median_clicks": b_med,
            "current_median_clicks": c_med,
            "reduction_pct": reduction_pct,
            "insufficient_data": insufficient,
            "fifty_pct_reduction_claim_allowed": meets_claim,
        }
        if b_med is not None:
            baseline_medians.append(b_med)
        if c_med is not None:
            current_medians.append(c_med)

    overall_baseline = _median(baseline_medians) if baseline_medians else None
    overall_current = _median(current_medians) if current_medians else None
    overall_reduction: float | None = None
    if (
        overall_baseline is not None
        and overall_current is not None
        and overall_baseline > 0
    ):
        overall_reduction = round(
            (overall_baseline - overall_current) / overall_baseline * 100.0,
            2,
        )

    any_task_tracked = any(
        v["baseline_completed_sessions"] > 0 or v["current_completed_sessions"] > 0
        for v in per_task.values()
    )
    tasks_with_runs = [
        v
        for v in per_task.values()
        if v["baseline_completed_sessions"] > 0 or v["current_completed_sessions"] > 0
    ]
    if not tasks_with_runs:
        all_sample_ok = False
    else:
        all_sample_ok = all(not v["insufficient_data"] for v in tasks_with_runs)

    if not any_task_tracked:
        verdict = "insufficient_data"
    elif not all_sample_ok:
        verdict = "insufficient_data"
    elif overall_reduction is None:
        verdict = "not_comparable"
    elif overall_reduction >= CLAIM_REDUCTION_THRESHOLD_PCT:
        verdict = "observed_ge_50_pct"
    else:
        verdict = "below_50_pct"

    fifty_pct_claim_allowed = bool(
        getattr(settings, "FIFTY_PCT_REDUCTION_CLAIM_ALLOWED", False)
        and any_task_tracked
        and all_sample_ok
        and overall_reduction is not None
        and overall_reduction >= CLAIM_REDUCTION_THRESHOLD_PCT
    )

    return {
        "school_id": school_id,
        "task_code_filter": task_code,
        "min_completed_sessions": min_sessions,
        "per_task": per_task,
        "overall_baseline_median_clicks": overall_baseline,
        "overall_current_median_clicks": overall_current,
        "overall_reduction_pct": overall_reduction,
        "insufficient_data": (not any_task_tracked) or (not all_sample_ok),
        "fifty_pct_reduction_claim_allowed": fifty_pct_claim_allowed,
        "verdict": verdict,
    }


def get_conversion_measurement_bundle(
    school_id: int,
    *,
    task_code: str | None = None,
    min_sessions: int = MIN_COMPLETED_SESSIONS_DEFAULT,
) -> dict[str, Any]:
    """
    Single-call bundle for product proof: click-task efficiency (with insufficient-data gates)
    plus per-school funnel timestamps/counts (see apps.schools.funnel_metrics).
    Does not assert cohort-level activation/conversion rates without an analytics aggregation layer.
    """
    from apps.schools.funnel_metrics import get_school_funnel_metrics_snapshot

    clicks = get_median_clicks_before_after(
        school_id,
        task_code=task_code,
        min_sessions=min_sessions,
    )
    return {
        "clicks": clicks,
        "funnel": get_school_funnel_metrics_snapshot(school_id),
    }


def record_click_event(
    *,
    school_id: int,
    user_id: int | None,
    kind: str,
    task_code: str,
    session_run_id: str,
    phase: str,
    task_step: str = "",
    action_code: str = "",
    path: str = "",
    screen_token: str = "",
    extra: dict[str, Any] | None = None,
):
    """
    Persist one analytics row. ``school_id`` must come from request resolution, never raw client input.
    """
    from apps.platform_runtime.models import ClickTrackEvent

    if task_code not in TRACKED_TASK_CODES:
        logger.warning("click_tracking: unknown task_code=%s", task_code)

    return ClickTrackEvent.objects.create(
        kind=kind,
        task_code=task_code[:64],
        task_step=(task_step or "")[:128],
        action_code=(action_code or "")[:128],
        session_run_id=session_run_id[:36],
        phase=phase,
        school_id=school_id,
        user_id=user_id,
        path=(path or "")[:512],
        screen_token=(screen_token or "")[:128],
        extra=extra or {},
    )
