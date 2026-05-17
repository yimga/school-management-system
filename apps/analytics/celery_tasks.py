"""Celery task wrappers for the analytics nightly batches.

Each task is a thin shim around a management command so the scheduling
config in `config/settings.CELERY_BEAT_SCHEDULE` references stable task
names that survive command renames.

Tasks are registered under the `analytics.*` namespace and never raise
to the worker — failures are logged and the next scheduled run starts
clean.
"""

from __future__ import annotations

import logging
from io import StringIO

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger("apps.analytics.celery_tasks")


def _safe_call(command: str, **kwargs) -> str:
    buf = StringIO()
    try:
        call_command(command, stdout=buf, stderr=buf, **kwargs)
    except SystemExit as ex:
        # `should_retrain_*` commands signal via SystemExit(10/11); we
        # log but don't propagate to the worker.
        logger.info("analytics.%s exited %s", command, ex.code)
    except Exception:  # noqa: BLE001 — never let nightly fail the worker
        logger.exception("analytics.%s failed", command)
    return buf.getvalue()


@shared_task(name="analytics.compute_nightly_risk")
def compute_nightly_risk_task() -> str:
    return _safe_call("compute_nightly_risk")


@shared_task(name="analytics.compute_nightly_grade_predictions")
def compute_nightly_grade_predictions_task() -> str:
    return _safe_call("compute_nightly_grade_predictions")


@shared_task(name="analytics.build_student_embeddings")
def build_student_embeddings_task() -> str:
    return _safe_call("build_student_embeddings")


@shared_task(name="analytics.send_risk_digest_all")
def send_risk_digest_task() -> str:
    """Fan-out the digest across every active school."""
    return _safe_call("send_risk_digest")


@shared_task(name="analytics.check_at_risk_drift_watchdog")
def check_at_risk_drift_watchdog(artifact: str = "var/at_risk_model.joblib") -> str:
    """Daily watchdog. PSI report only; the `--max-psi` gate is
    intentionally NOT applied here — alerting is the dispatcher's job."""
    return _safe_call(
        "check_at_risk_drift", artifact=artifact, window_days=7,
    )
