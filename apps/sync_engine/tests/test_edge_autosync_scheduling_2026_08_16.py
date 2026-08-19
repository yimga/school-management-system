"""Edge auto-sync wiring — the box syncs automatically when it has internet and
resyncs after a power/network loss, WITHOUT the operator setting up cron.

Every automatic trigger (the /health/-tick in-process scheduler, the Celery-beat
task, the boot entrypoint, the on-connectivity host hook, the edge_autosync command)
converges on one gated, self-resolving, never-raising function:
``edge_scheduler.run_edge_sync_now``. These tests lock:

  * the flag gate (hard no-op unless RMC_EDGE_SYNC_ENABLED) + delegation to the SAME
    never-raising sync_runner.run_sync_cycle the "Sync now" button uses;
  * the box resolving its OWN school with no slug (sole active school, or a pinned
    RMC_EDGE_SCHOOL_SLUG), and no-op'ing when it is ambiguous;
  * the interval knob (default 180s, floor 60s, env-overridable);
  * the in-process scheduler registering the job ONLY on an edge box, auto_eligible;
  * the Celery-beat entry pointing at the same task;
  * the boot entrypoint firing a reconcile, guarded by the flag.
"""
from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.schools.models import School

_RUN_SYNC_CYCLE = "apps.sync_engine.sync_runner.run_sync_cycle"


def _one_active_school(slug="edge-sole"):
    """Make exactly ONE active school exist (deactivate any others first)."""
    School.objects.update(is_active=False)
    return School.objects.create(
        name="Edge Sole", slug=slug, subdomain=slug, is_active=True
    )


@override_settings(RMC_EDGE_SYNC_ENABLED=True)
class RunEdgeSyncNowTests(TestCase):
    def test_delegates_to_run_sync_cycle_for_resolved_school(self):
        school = _one_active_school()
        canned = {"enabled": True, "ok": True, "mode": "live", "pushed": 2,
                  "pulled": 1, "conflicts": 0, "message": "ok"}
        with mock.patch(_RUN_SYNC_CYCLE, return_value=canned) as rsc:
            from apps.sync_engine.edge_scheduler import run_edge_sync_now

            result = run_edge_sync_now()
        rsc.assert_called_once()
        self.assertEqual(rsc.call_args.args[0], school)
        self.assertEqual(rsc.call_args.kwargs.get("mode"), "live")
        self.assertTrue(result["ran"])
        self.assertEqual(result["pushed"], 2)

    def test_no_op_when_no_unambiguous_school(self):
        School.objects.update(is_active=False)  # zero active -> ambiguous
        with mock.patch(_RUN_SYNC_CYCLE) as rsc:
            from apps.sync_engine.edge_scheduler import run_edge_sync_now

            result = run_edge_sync_now()
        rsc.assert_not_called()
        self.assertFalse(result["ran"])
        self.assertIn("school", result["reason"])


class RunEdgeSyncNowGateTests(TestCase):
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_hard_no_op_when_flag_off(self):
        _one_active_school()
        with mock.patch(_RUN_SYNC_CYCLE) as rsc:
            from apps.sync_engine.edge_scheduler import run_edge_sync_now

            result = run_edge_sync_now()
        rsc.assert_not_called()
        self.assertFalse(result["enabled"])
        self.assertFalse(result["ran"])


class ResolveEdgeSchoolTests(TestCase):
    def test_sole_active_school_is_resolved(self):
        school = _one_active_school()
        from apps.sync_engine.edge_scheduler import resolve_edge_school

        self.assertEqual(resolve_edge_school(), school)

    def test_more_than_one_active_is_ambiguous_none(self):
        School.objects.update(is_active=False)
        School.objects.create(name="A", slug="edge-a", subdomain="edge-a", is_active=True)
        School.objects.create(name="B", slug="edge-b", subdomain="edge-b", is_active=True)
        from apps.sync_engine.edge_scheduler import resolve_edge_school

        self.assertIsNone(resolve_edge_school())

    def test_explicit_slug_wins(self):
        School.objects.update(is_active=False)
        School.objects.create(name="A", slug="edge-a", subdomain="edge-a", is_active=True)
        target = School.objects.create(
            name="Pinned", slug="edge-pin", subdomain="edge-pin", is_active=True
        )
        from apps.sync_engine.edge_scheduler import resolve_edge_school

        with mock.patch.dict(os.environ, {"RMC_EDGE_SCHOOL_SLUG": "edge-pin"}):
            self.assertEqual(resolve_edge_school(), target)


class EdgeSyncIntervalTests(SimpleTestCase):
    def _interval(self, value):
        from apps.sync_engine.edge_scheduler import edge_sync_interval_seconds

        env = {} if value is None else {"RMC_EDGE_SYNC_INTERVAL_SECONDS": value}
        with mock.patch.dict(os.environ, env, clear=False):
            if value is None:
                os.environ.pop("RMC_EDGE_SYNC_INTERVAL_SECONDS", None)
            return edge_sync_interval_seconds()

    def test_default_is_180(self):
        self.assertEqual(self._interval(None), 180)

    def test_custom_value_honoured(self):
        self.assertEqual(self._interval("300"), 300)

    def test_floored_at_60(self):
        self.assertEqual(self._interval("5"), 60)

    def test_garbage_falls_back_to_default(self):
        self.assertEqual(self._interval("not-a-number"), 180)


class EdgeAutosyncCommandTests(TestCase):
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_command_reports_no_op_when_flag_off(self):
        out = StringIO()
        call_command("edge_autosync", stdout=out)
        self.assertIn("off", out.getvalue().lower())

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_command_runs_cycle_and_reports_counts(self):
        _one_active_school()
        canned = {"enabled": True, "ok": True, "mode": "live", "pushed": 3,
                  "pulled": 4, "conflicts": 0, "message": "Sync complete"}
        out = StringIO()
        with mock.patch(_RUN_SYNC_CYCLE, return_value=canned):
            call_command("edge_autosync", stdout=out)
        text = out.getvalue()
        self.assertIn("pushed 3", text)
        self.assertIn("pulled 4", text)


class EdgeSyncSchedulingWiringTests(SimpleTestCase):
    def test_celery_beat_entry_points_at_the_task(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE.get("edge-sync-cycle")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["task"], "sync_engine.edge_sync_cycle")

    def test_shared_task_registered_under_expected_name(self):
        from apps.sync_engine import tasks

        if tasks.shared_task is None:  # celery absent (not the case here) -> skip
            self.skipTest("celery not installed")
        self.assertEqual(tasks.edge_sync_cycle_task.name, "sync_engine.edge_sync_cycle")

    def test_inprocess_registration_only_on_edge_box(self):
        from apps.platform_runtime import periodic

        on = {}
        with override_settings(RMC_EDGE_SYNC_ENABLED=True):
            periodic._maybe_register_edge_sync_job(on)
        self.assertIn("sync_engine.edge_sync_cycle", on)
        job = on["sync_engine.edge_sync_cycle"]
        self.assertTrue(job.auto_eligible)
        # The job is now registered at the fast TICK cadence, not the sync interval:
        # registering at 180s put a 180s floor under reacting to a wake (the network
        # returning, a local write, an operator click).
        self.assertLessEqual(job.interval_seconds, 15)
        # What the old ">= 60" assertion was really protecting is that a misconfigured
        # box cannot hammer the cloud. That guarantee MOVED rather than disappeared: a
        # fast tick is not a fast cycle, because apps.sync_engine.cadence gates whether
        # each tick becomes real work. Assert the guarantee where it now lives.
        from apps.sync_engine import cadence

        self.assertGreaterEqual(cadence.steady_seconds(), 30)
        self.assertGreaterEqual(
            cadence.backoff_cap_seconds(), cadence.steady_seconds()
        )

        off = {}
        with override_settings(RMC_EDGE_SYNC_ENABLED=False):
            periodic._maybe_register_edge_sync_job(off)
        self.assertNotIn("sync_engine.edge_sync_cycle", off)

    def test_ensure_default_jobs_installs_edge_job_on_edge_box(self):
        from apps.platform_runtime import periodic

        saved_installed = periodic._DEFAULTS_INSTALLED
        saved_job = periodic._REGISTRY.get("sync_engine.edge_sync_cycle")

        def _restore():
            periodic._DEFAULTS_INSTALLED = saved_installed
            if saved_job is None:
                periodic._REGISTRY.pop("sync_engine.edge_sync_cycle", None)
            else:
                periodic._REGISTRY["sync_engine.edge_sync_cycle"] = saved_job

        self.addCleanup(_restore)
        periodic._DEFAULTS_INSTALLED = False
        periodic._REGISTRY.pop("sync_engine.edge_sync_cycle", None)
        with override_settings(RMC_EDGE_SYNC_ENABLED=True):
            periodic.ensure_default_jobs()
        self.assertIn("sync_engine.edge_sync_cycle", periodic._REGISTRY)

    def test_entrypoint_fires_boot_reconcile_guarded_by_flag(self):
        root = Path(__file__).resolve().parents[3]
        entry = (root / "deploy" / "selfhost" / "entrypoint.web.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("edge_autosync", entry)
        self.assertIn("RMC_EDGE_SYNC_ENABLED", entry)
