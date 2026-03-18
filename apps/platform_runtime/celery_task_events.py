"""
Tier 4: emit celery_task_started / completed / failed for every Celery task via signals.
Covers all @shared_task without per-task boilerplate. Denylist for noisy internal tasks.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Internal Celery / heartbeat tasks — skip platform events
_CELERY_TASK_EVENT_DENYLIST = frozenset(
    {
        "celery.chord_unlock",
        "celery.chord",
        "celery.accumulate",
        "celery.backend_cleanup",
        "celery.group",
        "config.debug_task",
    }
)


def _task_display_name(task: Any) -> str:
    if task is None:
        return "unknown"
    return getattr(task, "name", None) or getattr(task, "__name__", str(task))


def _school_id_from_kwargs(kwargs: Optional[dict]) -> Optional[Any]:
    if not isinstance(kwargs, dict):
        return None
    for key in ("school_id", "schema_name"):
        v = kwargs.get(key)
        if v is not None:
            return v
    return None


_signals_connected = False


def connect_celery_platform_task_signals() -> None:
    global _signals_connected
    if _signals_connected:
        return
    try:
        from celery.signals import task_failure, task_postrun, task_prerun
    except ImportError:
        logger.debug("celery signals not available")
        return

    def on_prerun(sender=None, task_id=None, task=None, kwargs=None, **kw: Any) -> None:
        name = _task_display_name(task or sender)
        if name in _CELERY_TASK_EVENT_DENYLIST or name.startswith("celery."):
            return
        try:
            from apps.platform_runtime.events import emit_celery_task_lifecycle

            emit_celery_task_lifecycle(
                "started",
                name,
                celery_task_id=str(task_id) if task_id else None,
                school_id=_school_id_from_kwargs(
                    kwargs if isinstance(kwargs, dict) else None
                ),
            )
        except Exception:
            logger.debug("celery_task_started emit skipped", exc_info=True)

    def on_postrun(
        sender=None, task_id=None, task=None, kwargs=None, **kw: Any
    ) -> None:
        name = _task_display_name(task or sender)
        if name in _CELERY_TASK_EVENT_DENYLIST or name.startswith("celery."):
            return
        try:
            from apps.platform_runtime.events import emit_celery_task_lifecycle

            emit_celery_task_lifecycle(
                "completed",
                name,
                celery_task_id=str(task_id) if task_id else None,
                school_id=_school_id_from_kwargs(
                    kwargs if isinstance(kwargs, dict) else None
                ),
            )
        except Exception:
            logger.debug("celery_task_completed emit skipped", exc_info=True)

    def on_failure(
        sender=None, task_id=None, exception=None, kwargs=None, **kw: Any
    ) -> None:
        name = _task_display_name(sender)
        if name in _CELERY_TASK_EVENT_DENYLIST or name.startswith("celery."):
            return
        try:
            from apps.platform_runtime.events import emit_celery_task_lifecycle

            emit_celery_task_lifecycle(
                "failed",
                name,
                celery_task_id=str(task_id) if task_id else None,
                school_id=_school_id_from_kwargs(
                    kwargs if isinstance(kwargs, dict) else None
                ),
                error=str(exception) if exception else "",
            )
        except Exception:
            logger.debug("celery_task_failed emit skipped", exc_info=True)

    task_prerun.connect(on_prerun, weak=False)
    task_postrun.connect(on_postrun, weak=False)
    task_failure.connect(on_failure, weak=False)
    _signals_connected = True
