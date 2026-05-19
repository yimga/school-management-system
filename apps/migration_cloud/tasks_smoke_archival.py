"""v3.40.0 Agent 13 — smoke-result archival shim.

Agent 8 owns ``apps/migration_cloud/tasks_smoke.py`` and built the
nightly smoke task. We layer a Celery ``task_postrun`` signal handler
on top of it so each completed run's structured summary is archived
to ``var/smoke-results/<utc-iso>.json`` for trend graphing — WITHOUT
modifying Agent 8's file.

Public surface:

  * :func:`archive_smoke_run(summary_dict)` — writes one file. Returns
    the written ``Path`` (callers use it for test assertions; nothing
    in production code reads the return value).
  * :func:`_on_smoke_task_postrun(...)` — Celery signal handler;
    safe-noop when ``sender.name`` doesn't match the nightly smoke
    task.
  * :func:`register_smoke_archival_signal()` — idempotent registration
    helper invoked from ``apps/migration_cloud/apps.py::ready()``.

Logging hygiene: never logs the smoke payload contents (which can
include section names + counts only, but defensively we still log
just the filename + section count).

Failure mode: every write is wrapped — a disk-full / permission error
NEVER propagates back into the Celery task path. A failed archive
write surfaces as a single ``warning`` log line and the run continues.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Module-level guard so register_smoke_archival_signal() is idempotent
# under double-import (Agent 7's signals_intake module also touches
# apps.py::ready(); we don't want to wire the same handler twice).
_SIGNAL_WIRED = False

_NIGHTLY_SMOKE_TASK_NAME = (
    "apps.migration_cloud.tasks_smoke.run_smoke_against_synthetic_tenant"
)


def _var_dir() -> Path:
    """Resolve ``var/`` under BASE_DIR; settings may be unconfigured at
    signal-wire time (e.g. management-command import paths), in which
    case we fall back to CWD-relative ``var/``."""
    try:
        from django.conf import settings
        base = getattr(settings, "BASE_DIR", None)
        if base is not None:
            return Path(base) / "var"
    except Exception:
        pass
    return Path("var")


def _utc_iso_filename_stamp() -> str:
    """Compact UTC-ISO stamp safe as a filename component."""
    return datetime.now(tz=dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _coerce_summary(value: Any) -> dict:
    """Coerce a Celery task result into a JSON-serializable dict.

    Agent 8's nightly task returns a dict with status + counts. A
    failed task may return a string traceback or raise — we wrap
    accordingly so the archive always succeeds with structurally-
    consistent JSON.
    """
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {"status": "noop", "result_was_none": True}
    return {"status": "unknown", "result_repr": repr(value)[:240]}


def archive_smoke_run(summary_dict: Any) -> Path | None:
    """Write one smoke-run JSON file. Returns the Path or None on error.

    The filename is the UTC-ISO stamp + .json. Files NEVER overwrite —
    collisions inside the same second get a numeric suffix.
    """
    try:
        var_dir = _var_dir()
        results_dir = var_dir / "smoke-results"
        results_dir.mkdir(parents=True, exist_ok=True)

        stamp = _utc_iso_filename_stamp()
        out_path = results_dir / f"{stamp}.json"
        suffix_n = 0
        while out_path.exists():
            suffix_n += 1
            out_path = results_dir / f"{stamp}-{suffix_n}.json"

        coerced = _coerce_summary(summary_dict)
        # Record the archival metadata separately from the source
        # summary so a future trend graph can distinguish "when the
        # archival ran" from "when the smoke ran".
        envelope = {
            "archived_at_utc_iso": datetime.now(tz=dt_timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ",
            ),
            "summary": coerced,
        }
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(envelope, fh, sort_keys=True, indent=2)

        # Defensive log — never the full payload, only the path + a
        # count of summary keys.
        logger.info(
            "migration_cloud.tasks_smoke_archival.archived "
            "path=%s summary_keys=%s",
            out_path.name, len(coerced),
        )
        return out_path
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.tasks_smoke_archival.archive_failed err_type=%s",
            type(exc).__name__,
        )
        return None


def _on_smoke_task_postrun(sender=None, task_id=None, task=None, args=None,
                          kwargs=None, retval=None, state=None, **_extras):
    """Celery ``task_postrun`` handler — archives the nightly smoke result.

    Safe-noop when ``sender`` is anything other than the registered
    nightly-smoke task name. NEVER raises; a thrown exception inside a
    Celery signal handler can break the worker dispatch loop.
    """
    try:
        # ``sender`` is the Task object; ``sender.name`` is the
        # registered task name. Some Celery versions pass the name as
        # the kwarg ``task``; we accept either.
        name = getattr(sender, "name", None) or getattr(task, "name", None) or ""
        if name != _NIGHTLY_SMOKE_TASK_NAME:
            return
        archive_smoke_run(retval)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.tasks_smoke_archival.signal_handler_failed err_type=%s",
            type(exc).__name__,
        )


def register_smoke_archival_signal() -> bool:
    """Wire :func:`_on_smoke_task_postrun` into Celery's task_postrun signal.

    Idempotent: a second call is a no-op. Returns ``True`` on first
    successful wire, ``False`` on subsequent calls or when celery is
    not installed.

    Called from ``apps/migration_cloud/apps.py::ready()`` AFTER Agent
    7's ``signals_intake.register_signal_handlers()`` so a failure in
    either does not block the other.
    """
    global _SIGNAL_WIRED
    if _SIGNAL_WIRED:
        return False
    try:
        from celery.signals import task_postrun
    except ImportError:
        logger.info(
            "migration_cloud.tasks_smoke_archival: celery not installed; "
            "signal wire skipped"
        )
        return False
    try:
        task_postrun.connect(
            _on_smoke_task_postrun,
            dispatch_uid="apps.migration_cloud.tasks_smoke_archival",
            weak=False,
        )
        _SIGNAL_WIRED = True
        logger.info(
            "migration_cloud.tasks_smoke_archival: task_postrun signal wired"
        )
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.tasks_smoke_archival: signal_wire_failed err_type=%s",
            type(exc).__name__,
        )
        return False


__all__ = [
    "archive_smoke_run",
    "register_smoke_archival_signal",
]
