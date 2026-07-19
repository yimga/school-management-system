"""Celery task registration entrypoint for the lifecycle app.

WHY THIS FILE EXISTS. ``config/celery.py`` calls a BARE ``app.autodiscover_tasks()``,
which imports ONLY each installed app's ``tasks.py``. The lifecycle app's
DR-snapshot ``@shared_task``s live in ``tasks_dr_snapshot.py`` (a module NOT named
``tasks.py``), so without this re-export they were never imported, the
``@shared_task`` decorators never ran, and the beat entry
``lifecycle-tenant-immutable-snapshot-daily`` named an UNREGISTERED task — a
silent no-op. That is precisely why tenant DR immutable snapshots had never been
captured (see scripts/verify_beat_task_registry.py).

SURGICAL BY DESIGN. This imports ONLY ``tasks_dr_snapshot`` and
``tasks_stall_watch`` — three named tasks, each carrying an explicit
``@shared_task(name=...)``. It does NOT enable blanket autodiscovery, so no other
dormant task (bundle-purge / webhook backlog / synthetic-tenant creation lives in
OTHER apps) is woken as a side effect. The tasks it registers:

  * ``lifecycle.capture_tenant_immutable_snapshots_daily`` — the scheduled daily
    DR capture (beat ``lifecycle-tenant-immutable-snapshot-daily`` resolves here).
  * ``lifecycle.verify_tenant_snapshot_restore_integrity`` — an on-demand restore
    drill (not scheduled; inert until called with a school_id; always rolls back).
    Documented in docs/DR_SELF_HOST_RESTORE_RUNBOOK.md §7.
  * ``lifecycle.detect_stalled_onboarding`` — daily onboarding stall-watch (beat
    ``lifecycle-stall-watch`` resolves here). Registered 2026-07-19; its
    module-level imports are trivial (models are resolved lazily inside the task
    body), so waking it pulls in no other dormant task.

Importing the modules runs each ``@shared_task`` decorator regardless of which
names are bound here; the explicit ``import`` + ``__all__`` document intent and
keep linters happy.
"""

from apps.lifecycle.tasks_dr_snapshot import (
    capture_tenant_immutable_snapshots_daily,
    verify_tenant_snapshot_restore_integrity,
)
from apps.lifecycle.tasks_stall_watch import detect_stalled_onboarding

__all__ = [
    "capture_tenant_immutable_snapshots_daily",
    "verify_tenant_snapshot_restore_integrity",
    "detect_stalled_onboarding",
]
