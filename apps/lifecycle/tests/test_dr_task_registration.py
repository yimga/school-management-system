"""Prove the tenant DR snapshot task is REGISTERED in the live Celery registry.

The beat entry ``lifecycle-tenant-immutable-snapshot-daily`` (config/settings.py)
names ``lifecycle.capture_tenant_immutable_snapshots_daily``. That task lives in
``apps/lifecycle/tasks_dr_snapshot.py`` — a module NOT named ``tasks.py``. Celery's
bare ``app.autodiscover_tasks()`` (config/celery.py) imports ONLY each app's
``tasks.py``, so without an explicit re-export the module is never imported, the
``@shared_task`` decorator never runs, and beat looks the task name up, finds
nothing, and the job silently never fires. That is exactly why tenant DR
snapshots had never been captured.

They assert on the task registry, not on DB rows — but Celery's Django fixup runs
``run_checks()`` during ``import_default_modules()`` and some app checks query the
DB, so these are ``TestCase`` (DB available), exactly the environment the CI gate
``scripts/verify_beat_task_registry.py`` probes in. They reproduce the same import
work a real worker/beat process does so the registry under assertion is the one
production would actually have.

RULE ZERO discipline: the presence of the ``@shared_task`` name in source proves
NOTHING about whether the module is imported. Only the live registry knows — so
these tests probe ``app.tasks`` after forcing autodiscovery, never grep source.
"""

from __future__ import annotations

from django.test import TestCase

CAPTURE_TASK = "lifecycle.capture_tenant_immutable_snapshots_daily"
RESTORE_DRILL_TASK = "lifecycle.verify_tenant_snapshot_restore_integrity"
# Third legitimate lifecycle task: the onboarding stall-watch, re-exported from
# tasks_stall_watch.py via tasks.py and wired to beat lifecycle-stall-watch
# (registered 2026-07-19, commit 20de8b8ad). It is surgical, not blanket
# autodiscovery — so the "wakes no other task" guard below allows exactly these
# three and still fails on a FOURTH unexpected task.
STALL_WATCH_TASK = "lifecycle.detect_stalled_onboarding"

# Beat entry key -> task name it must resolve to (config/settings.py).
_BEAT_ENTRY = "lifecycle-tenant-immutable-snapshot-daily"


def _registered_task_names() -> set[str]:
    """The live Celery task registry after production-equivalent autodiscovery."""
    from config.celery import app

    # Same import work a real worker/beat does — imports every app's tasks.py.
    app.loader.import_default_modules()
    return set(app.tasks.keys())


class TenantDrSnapshotTaskRegistrationTests(TestCase):
    # import_default_modules() runs Django system checks; some query the DB.
    databases = "__all__"

    def test_capture_task_is_registered(self):
        """The scheduled DR-capture task must resolve in the live registry.

        FAILS on a tree where apps/lifecycle has no tasks.py re-export (the task
        is invisible to autodiscovery); PASSES once it is registered.
        """
        registered = _registered_task_names()
        self.assertIn(
            CAPTURE_TASK,
            registered,
            f"{CAPTURE_TASK} is NOT registered — its beat entry {_BEAT_ENTRY!r} is a "
            "silent no-op and tenant DR snapshots never run. The @shared_task lives in "
            "apps/lifecycle/tasks_dr_snapshot.py, which bare autodiscover_tasks() never "
            "imports (no apps/lifecycle/tasks.py). Re-export it from tasks.py.",
        )

    def test_restore_drill_task_is_registered(self):
        """The on-demand restore-integrity drill task must also resolve.

        It shares tasks_dr_snapshot.py with the capture task, so importing that
        module (via tasks.py) registers both. Documented in
        docs/DR_SELF_HOST_RESTORE_RUNBOOK.md §7.
        """
        registered = _registered_task_names()
        self.assertIn(RESTORE_DRILL_TASK, registered)

    def test_beat_entry_task_name_matches_registered_task(self):
        """The beat schedule entry must name a task that actually resolves."""
        from config.celery import app

        registered = _registered_task_names()
        schedule = app.conf.beat_schedule or {}
        self.assertIn(_BEAT_ENTRY, schedule, "beat entry disappeared from settings")
        entry = schedule[_BEAT_ENTRY]
        task_name = entry.get("task") if isinstance(entry, dict) else getattr(entry, "task", None)
        self.assertEqual(task_name, CAPTURE_TASK)
        self.assertIn(
            task_name,
            registered,
            f"beat entry {_BEAT_ENTRY!r} names {task_name!r}, which is not registered — "
            "a silent no-op.",
        )

    def test_registering_dr_tasks_wakes_no_other_task(self):
        """The lifecycle app must contribute ONLY its three known named tasks.

        Guards against a blanket-autodiscovery fix that would wake dangerous
        dormant tasks (bundle-purge / webhook backlog / synthetic-tenant). Every
        ``lifecycle.*`` task in the live registry must be one of the two
        DR-snapshot tasks or the onboarding stall-watch — and nothing else.
        """
        registered = _registered_task_names()
        lifecycle_tasks_in_registry = {
            k for k in registered if k.startswith("lifecycle.")
        }
        self.assertEqual(
            lifecycle_tasks_in_registry,
            {CAPTURE_TASK, RESTORE_DRILL_TASK, STALL_WATCH_TASK},
            "apps/lifecycle registered an unexpected task — only the two DR-snapshot "
            "tasks and the onboarding stall-watch may come from this app.",
        )
