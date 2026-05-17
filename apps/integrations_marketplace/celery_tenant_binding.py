"""
v2.79 — Celery `task_prerun` / `task_postrun` hooks that mirror the request
middleware: bind the active tenant for the duration of the task so any
`send_mail()` issued by the task picks up the per-tenant Anymail credentials.

Pattern: callers pass `school_id=...` in `task.kwargs` (preferred — explicit
and serializable). For migration paths where that's not yet wired, the task
body can call `bind_tenant_for_email(school)` directly.

This module is imported from `IntegrationsMarketplaceConfig.ready()`. When
Celery isn't installed (test envs, sync scripts) the import-time `try`
swallows the failure and these signal handlers simply don't connect — the
fallback resolver returns None and the global ANYMAIL settings apply.

Why signals rather than a Celery base task class:
- Doesn't require every existing task to inherit a new base class
- Composable with Celery's built-in retry/scheduling machinery
- Plays nicely with `shared_task` (no central app instance needed)
"""

from __future__ import annotations

import logging

from apps.integrations_marketplace.email_backend import (
    bind_tenant_for_email,
    clear_tenant_for_email,
)

logger = logging.getLogger(__name__)


def _resolve_school(task_id, sender, **kw):
    """Pull the school out of task kwargs / args without exploding.

    Recognized shapes (in order):
      1. kwargs["school"]  — already a School instance
      2. kwargs["school_id"]  — primary key, hydrated via apps.schools.models.School
      3. args[0]  — when the task signature is `task(school_or_id, ...)` and
         the first positional looks like a School or an int.
    """
    kwargs = kw.get("kwargs") or {}
    if isinstance(kwargs, dict):
        if kwargs.get("school") is not None:
            return kwargs["school"]
        sid = kwargs.get("school_id")
        if sid is not None:
            return _hydrate_school(sid)
    args = kw.get("args") or ()
    if args:
        first = args[0]
        if hasattr(first, "_meta") and hasattr(first, "pk"):
            return first
        if isinstance(first, int):
            return _hydrate_school(first)
    return None


def _hydrate_school(school_id):
    try:
        from apps.schools.models import School
    except ImportError:
        return None
    try:
        return School.objects.filter(pk=school_id).first()
    except Exception:  # noqa: BLE001 — DB hiccup must not break task pipeline
        logger.warning("Could not hydrate School(pk=%s) for tenant binding", school_id)
        return None


def _on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    try:
        school = _resolve_school(task_id, sender, args=args, kwargs=kwargs)
        if school is not None:
            bind_tenant_for_email(school)
    except Exception:  # noqa: BLE001 — never block a task on tenant binding
        logger.exception("Tenant binding pre-run failed for task %s", task_id)


def _on_task_postrun(sender=None, task_id=None, task=None, args=None,
                     kwargs=None, retval=None, state=None, **extra):
    # Always unbind — Celery worker threads/processes are pooled and reused.
    try:
        clear_tenant_for_email()
    except Exception:  # noqa: BLE001
        logger.exception("Tenant unbind post-run failed for task %s", task_id)


try:
    from celery.signals import task_postrun, task_prerun  # type: ignore

    task_prerun.connect(_on_task_prerun, weak=False, dispatch_uid="im_v279_tenant_bind")
    task_postrun.connect(_on_task_postrun, weak=False, dispatch_uid="im_v279_tenant_unbind")
except ImportError:  # pragma: no cover — celery is in production deps
    pass


__all__ = ["_on_task_postrun", "_on_task_prerun"]
