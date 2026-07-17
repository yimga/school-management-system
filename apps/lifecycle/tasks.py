"""Celery task registration entrypoint for the lifecycle app.

WHY THIS FILE EXISTS. ``config/celery.py`` calls a BARE ``app.autodiscover_tasks()``,
which imports ONLY each installed app's ``tasks.py``. The lifecycle app's
DR-snapshot ``@shared_task``s live in ``tasks_dr_snapshot.py`` (a module NOT named
``tasks.py``), so without this re-export they were never imported, the
``@shared_task`` decorators never ran, and the beat entry
``lifecycle-tenant-immutable-snapshot-daily`` named an UNREGISTERED task — a
silent no-op. That is precisely why tenant DR immutable snapshots had never been
captured (see scripts/verify_beat_task_registry.py).

SURGICAL BY DESIGN. This imports ONLY ``tasks_dr_snapshot`` — the two DR-snapshot
tasks. It deliberately does NOT touch ``tasks_stall_watch`` (which has no
``@shared_task`` anyway) and does NOT enable blanket autodiscovery, so no other
dormant task (bundle-purge / webhook backlog / synthetic-tenant creation lives in
OTHER apps) is woken as a side effect. Both tasks it registers are DR:

  * ``lifecycle.capture_tenant_immutable_snapshots_daily`` — the scheduled daily
    capture (the beat entry above resolves to this).
  * ``lifecycle.verify_tenant_snapshot_restore_integrity`` — an on-demand restore
    drill (not scheduled; inert until called with a school_id; always rolls back).
    Documented in docs/DR_SELF_HOST_RESTORE_RUNBOOK.md §7.

Importing the module runs both ``@shared_task`` decorators regardless of which
names are bound here; the explicit ``import`` + ``__all__`` document intent and
keep linters happy.
"""

from apps.lifecycle.tasks_dr_snapshot import (
    capture_tenant_immutable_snapshots_daily,
    verify_tenant_snapshot_restore_integrity,
)

__all__ = [
    "capture_tenant_immutable_snapshots_daily",
    "verify_tenant_snapshot_restore_integrity",
]
