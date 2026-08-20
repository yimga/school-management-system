"""Flight Deck scenario simulation — failure isolate + success archive.

Staff-only preset used by the operator dashboard. The worker is the same
code path as live @track_workflow runs so SSE, pipeline stages, remediator,
and apply-fix resume are real — not a CSS-only demo.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from apps.platform_runtime.workflow_attention_gateway import (
    SIMULATION_ERROR_MESSAGE,
    SIMULATION_ERROR_TYPE,
    SIMULATION_FAIL_STEP,
    SIMULATION_STEP_LABELS,
    SIMULATION_STEPS,
    SIMULATION_WORKFLOW_KEY,
    simulation_remediation,
)

logger = logging.getLogger(__name__)

SIMULATION_SOURCE = "flight_deck_simulation"


class SimulationTokenExpired(PermissionError):
    """Raised at the simulated Integration Test breaker."""


def simulation_enabled() -> bool:
    from django.conf import settings

    if getattr(settings, "DEBUG", False):
        return True
    return os.environ.get("RMC_ALLOW_WORKFLOW_E2E_DEMO", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def simulation_step_delay_seconds() -> float:
    raw = os.environ.get("RMC_WORKFLOW_SIM_DELAY_MS", "350").strip()
    try:
        millis = max(0, int(raw))
    except (TypeError, ValueError):
        millis = 350  # magic-number-allow: default-ui-sim-step-delay-ms
    return millis / 1000.0


def _apply_step_labels(run: Any) -> None:
    try:
        from apps.platform_runtime.models import WorkflowStep

        for name, label in SIMULATION_STEP_LABELS.items():
            WorkflowStep.objects.filter(run=run, name=name).update(label=label[:160])  # magic-number-allow: string-truncation-cap
    except Exception:
        logger.debug("simulation_step_labels_failed", extra={"run_id": getattr(run, "pk", None)})


def _log(run: Any, message: str, *, processed: int, expected: int, status: str) -> None:
    try:
        from apps.platform_runtime.workflow_telemetry import update_and_broadcast_progress

        update_and_broadcast_progress(
            processed=processed,
            expected=expected,
            log_message=message,
            run=run,
            school_id=str(getattr(run, "school_id", "") or ""),
            tenant_schema=str(getattr(run, "tenant_schema", "") or ""),
            workflow_key=SIMULATION_WORKFLOW_KEY,
            task_type="FLIGHT_DECK_SIMULATION",
            status=status,
        )
    except Exception:
        logger.debug("simulation_telemetry_failed", extra={"run_id": getattr(run, "pk", None)})


def begin_simulation_run(*, request: Any = None, path: str) -> Any:
    from apps.platform_runtime.workflow_tracker import begin_run, push_workflow_run

    run = begin_run(
        workflow_key=SIMULATION_WORKFLOW_KEY,
        steps=SIMULATION_STEPS,
        request=request,
        expected_duration_seconds=12,
        payload={
            "source": SIMULATION_SOURCE,
            "simulation_path": path,
            "resume_auto_fix_kind": "resume_from_checkpoint",
        },
    )
    if run is None:
        return None
    _apply_step_labels(run)
    push_workflow_run(run)
    return run


def _sleep(delay_seconds: float) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def run_simulation_worker(
    run: Any,
    *,
    path: str,
    delay_seconds: Optional[float] = None,
    resume_from: str = "",
) -> Any:
    """Execute (or resume) a simulation run. Always finalizes the row."""

    from apps.platform_runtime.workflow_tracker import (
        finalize_run,
        pop_workflow_run,
        workflow_step,
    )

    delay = simulation_step_delay_seconds() if delay_seconds is None else max(0.0, delay_seconds)
    fail = str(path or "").lower() != "success"
    start_index = 0
    if resume_from:
        try:
            start_index = list(SIMULATION_STEPS).index(resume_from)
        except ValueError:
            start_index = 0
    expected = len(SIMULATION_STEPS)
    try:
        for index, name in enumerate(SIMULATION_STEPS):
            if index < start_index:
                continue
            processed = index + 1
            _log(
                run,
                f"Executing {SIMULATION_STEP_LABELS.get(name, name)}",
                processed=processed,
                expected=expected,
                status="running",
            )
            with workflow_step(run, name, payload={"phase": index + 1, "path": path}):
                _sleep(delay)
                if fail and name == SIMULATION_FAIL_STEP and not resume_from:
                    raise SimulationTokenExpired(SIMULATION_ERROR_MESSAGE)
            _log(
                run,
                f"Completed {SIMULATION_STEP_LABELS.get(name, name)}",
                processed=processed,
                expected=expected,
                status="running",
            )
        _log(
            run,
            "Simulation archived to Success Logs",
            processed=expected,
            expected=expected,
            status="succeeded",
        )
        finalize_run(run, status="succeeded")
    except SimulationTokenExpired as exc:
        try:
            run.suggested_remediation = simulation_remediation()
            run.error_summary = {
                "type": SIMULATION_ERROR_TYPE,
                "message": SIMULATION_ERROR_MESSAGE,
            }
            run.save(update_fields=["suggested_remediation", "error_summary"])
        except Exception:
            logger.debug("simulation_remediation_persist_failed", exc_info=True)
        _log(
            run,
            f"Blocked at Integration Test: {SIMULATION_ERROR_MESSAGE}",
            processed=3,
            expected=expected,
            status="failed",
        )
        finalize_run(run, status="failed", error=exc, auto_apply=False)
        try:
            from apps.platform_runtime.models import WorkflowRun as RunModel

            RunModel.objects.filter(pk=run.pk).update(
                suggested_remediation=simulation_remediation(),
                error_summary={
                    "type": SIMULATION_ERROR_TYPE,
                    "message": SIMULATION_ERROR_MESSAGE,
                },
            )
        except Exception:
            logger.debug("simulation_remediation_persist_failed", extra={"run_id": getattr(run, "pk", None)})
    except Exception as exc:
        finalize_run(run, status="failed", error=exc)
    finally:
        pop_workflow_run(run)
    try:
        run.refresh_from_db()
    except Exception:
        pass
    return run


def resume_simulation_from_failure(run: Any, *, delay_seconds: Optional[float] = None) -> dict[str, Any]:
    """Resume a failed simulation at the Integration Test breaker, then archive."""

    from apps.platform_runtime.models import WorkflowRun, WorkflowStep
    from apps.platform_runtime.workflow_tracker import push_workflow_run

    if run is None or getattr(run, "workflow_key", "") != SIMULATION_WORKFLOW_KEY:
        return {"ok": False, "reason": "not_simulation_run"}
    WorkflowStep.objects.filter(run=run, name=SIMULATION_FAIL_STEP).update(
        status="done"
    )
    WorkflowRun.objects.filter(pk=run.pk).update(
        status="running",
        current_step_name=SIMULATION_FAIL_STEP,
        current_step_ordinal=3,
        ended_at=None,
        suggested_remediation={},
        error_summary={},
    )
    run.refresh_from_db()
    push_workflow_run(run)
    delay = 0.0 if delay_seconds is None else delay_seconds
    run_simulation_worker(
        run,
        path="success",
        delay_seconds=delay,
        resume_from="cloud_deploy",
    )
    try:
        run.refresh_from_db()
    except Exception:
        pass
    return {
        "ok": True,
        "applied": "resume_from_checkpoint",
        "refresh_deck": True,
        "healing_poll_ms": 800,  # magic-number-allow: flight-deck-sim-resume-poll-ms
        "operator_message": "Token issue patched. Remaining steps completed and archived to Success Logs.",
        "status": getattr(run, "status", ""),
        "attention_bucket": "success_logs",
    }
