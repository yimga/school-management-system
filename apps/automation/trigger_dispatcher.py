"""Trigger-to-handler dispatcher.

Routes domain events (payment_success, attendance_saved, marks_submitted, …)
to handlers registered by the workflow / playbook engine. Without this
dispatcher, fired events did not automatically reach matching workflows
even though the trigger catalog enumerated them.

Design:

- A single in-process registry maps ``trigger_key -> [handler_callable]``.
- Handlers register themselves via ``@register_handler("trigger_key")``.
- ``fire(trigger_key, payload, *, school=None, actor=None)`` calls every
  registered handler and records an ``AutomationExecutionLog`` row per
  invocation so dispatch is auditable.
- Errors in one handler do not block the others — they are recorded as
  ``FAILED`` rows and re-raised only when ``raise_on_first_error=True``.
- The dispatcher is import-safe: no Django models at import time;
  ``AutomationExecutionLog`` is imported inside ``fire``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .workflow_trigger_catalog import FULL_TRIGGER_CATALOG_KEYS

logger = logging.getLogger(__name__)


HandlerFn = Callable[[dict, Any, Any], dict | None]


class UnknownTriggerError(KeyError):
    """Raised when a trigger key is not in the documented catalog."""


_REGISTRY: dict[str, list[HandlerFn]] = {key: [] for key in FULL_TRIGGER_CATALOG_KEYS}


def register_handler(trigger_key: str) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator: register a handler for a trigger key.

    The handler signature is ``handler(payload, school, actor) -> dict | None``.
    The returned dict (if any) is recorded in ``execution_summary``.
    """
    if trigger_key not in FULL_TRIGGER_CATALOG_KEYS:
        raise UnknownTriggerError(
            f"Trigger {trigger_key!r} is not in FULL_TRIGGER_CATALOG_KEYS — "
            "extend the catalog before registering a handler."
        )

    def decorator(fn: HandlerFn) -> HandlerFn:
        _REGISTRY[trigger_key].append(fn)
        return fn

    return decorator


def registered_handlers(trigger_key: str) -> list[HandlerFn]:
    """Return the list of handlers registered for a trigger key (read-only view)."""
    if trigger_key not in _REGISTRY:
        raise UnknownTriggerError(f"Unknown trigger key: {trigger_key!r}")
    return list(_REGISTRY[trigger_key])


def clear_registry_for_tests() -> None:
    """Reset the registry — only for use in unit tests."""
    for key in list(_REGISTRY.keys()):
        _REGISTRY[key] = []


def fire(
    trigger_key: str,
    payload: dict,
    *,
    school=None,
    actor=None,
    raise_on_first_error: bool = False,
) -> list[dict[str, Any]]:
    """Dispatch a trigger event to every registered handler.

    Returns a list of result dicts — one per handler — each shaped:
    ``{"handler": <name>, "status": "success"|"failed", "summary": <dict|None>, "error": <str|None>}``

    Each successful invocation produces an ``AutomationExecutionLog`` row.
    Failures produce a FAILED row with the exception message.
    """
    if trigger_key not in _REGISTRY:
        raise UnknownTriggerError(f"Unknown trigger key: {trigger_key!r}")

    payload = payload if isinstance(payload, dict) else {}
    results: list[dict[str, Any]] = []

    # Local import keeps this module import-safe outside Django.
    from apps.automation.models import AutomationExecutionLog

    for handler in _REGISTRY[trigger_key]:
        handler_name = f"{handler.__module__}.{handler.__name__}"
        try:
            summary = handler(payload, school, actor) or {}
            AutomationExecutionLog.objects.create(
                task_name=f"trigger:{trigger_key}:{handler_name}"[:200],
                school=school,
                execution_type=AutomationExecutionLog.ExecutionType.MANUAL,
                completed_at=__import__("django.utils.timezone").utils.timezone.now(),
                status=AutomationExecutionLog.Status.SUCCESS,
                records_processed=int(summary.get("records_processed", 0) or 0),
                execution_summary={"trigger_key": trigger_key, "summary": summary},
                triggered_by=actor,
            )
            results.append(
                {
                    "handler": handler_name,
                    "status": "success",
                    "summary": summary,
                    "error": None,
                }
            )
        except Exception as exc:
            logger.exception(
                "Trigger %s handler %s failed", trigger_key, handler_name
            )
            try:
                AutomationExecutionLog.objects.create(
                    task_name=f"trigger:{trigger_key}:{handler_name}"[:200],
                    school=school,
                    execution_type=AutomationExecutionLog.ExecutionType.MANUAL,
                    completed_at=__import__("django.utils.timezone").utils.timezone.now(),
                    status=AutomationExecutionLog.Status.FAILED,
                    error_message=str(exc)[:2000],
                    execution_summary={"trigger_key": trigger_key, "error": str(exc)},
                    triggered_by=actor,
                )
            except Exception:
                logger.exception("Failed to write FAILED execution log row")
            results.append(
                {
                    "handler": handler_name,
                    "status": "failed",
                    "summary": None,
                    "error": str(exc),
                }
            )
            if raise_on_first_error:
                raise

    return results


__all__ = [
    "UnknownTriggerError",
    "register_handler",
    "registered_handlers",
    "clear_registry_for_tests",
    "fire",
]
