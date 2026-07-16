"""Provisioning watchdog — the fix for "stuck at Preparing your campus workspace".

Proves the heartbeat-aware, single-flighted resume:
  * a LIVE run (fresh heartbeat) is never disturbed;
  * a heartbeat-DEAD ``running`` run (process died mid-migrate) is re-driven once,
    the zombie cancelled — the exact pre-activation ``tenant_schema`` death the
    reconcile beat is structurally blind to;
  * a settled school is a no-op;
  * repeated poll ticks collapse to ONE resume (single-flight) — no thundering herd;
  * the system sweep finds dead runs off a plain query, and the previously-broken
    ``-updated_at`` sweep no longer raises ``FieldError``.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School
from apps.schools import provision_watchdog as pw
from apps.schools.tasks import provision_school_sync


def _make_run(school, *, status="running", heartbeat_age_seconds=0) -> WorkflowRun:
    run = WorkflowRun.objects.create(
        workflow_key="tenant_school_provision",
        school_id=str(school.id),
        status=status,
        total_steps=5,
        current_step_ordinal=3,
        current_step_name="tenant_schema",
        expected_duration_seconds=600,
    )
    # last_heartbeat_at is auto_now_add; .update() bypasses it to backdate.
    if heartbeat_age_seconds:
        WorkflowRun.objects.filter(pk=run.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(seconds=heartbeat_age_seconds)
        )
    run.refresh_from_db()
    return run


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    PROVISION_RESUME_STALE_SECONDS=120,
    PROVISION_RESUME_MAX_PER_HOUR=12,
)
class ProvisionWatchdogTests(TestCase):
    def setUp(self):
        cache.clear()  # single-flight lock + hourly counter live in the cache
        self.school = School.objects.create(
            name="Watchdog Academy",
            slug="watchdog-academy",
            subdomain="watchdog-academy",
            is_active=False,
        )

    def test_live_run_is_not_resumed(self):
        _make_run(self.school, status="running", heartbeat_age_seconds=5)
        self.assertTrue(pw.provisioning_drive_is_live(self.school))
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            result = pw.resume_provision_if_stuck(self.school, reason="test")
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "in_flight")
        kick.assert_not_called()

    def test_dead_run_is_resumed_once_and_zombie_cancelled(self):
        run = _make_run(self.school, status="running", heartbeat_age_seconds=600)
        self.assertFalse(pw.provisioning_drive_is_live(self.school))
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            result = pw.resume_provision_if_stuck(self.school, reason="test")
        self.assertEqual(result["action"], "resumed")
        kick.assert_called_once()
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")

    def test_settled_school_is_noop(self):
        self.school.is_active = True
        self.school.settings = {
            "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
        }
        self.school.save(update_fields=["is_active", "settings"])
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            result = pw.resume_provision_if_stuck(self.school, reason="test")
        self.assertEqual(result["reason"], "settled")
        kick.assert_not_called()

    def test_single_flight_debounces_repeated_polls(self):
        _make_run(self.school, status="running", heartbeat_age_seconds=600)
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            first = pw.resume_provision_if_stuck(self.school, reason="poll-1")
            second = pw.resume_provision_if_stuck(self.school, reason="poll-2")
        self.assertEqual(first["action"], "resumed")
        self.assertEqual(second["action"], "none")
        self.assertEqual(second["reason"], "debounced")
        kick.assert_called_once()  # exactly one migrate re-drive, not a herd

    def test_hourly_cap_stops_runaway_resumes(self):
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            resumed = 0
            for i in range(20):
                cache.delete(f"{pw._CACHE_PREFIX}:lock:{self.school.id}")  # bypass debounce
                _make_run(self.school, status="running", heartbeat_age_seconds=600)
                r = pw.resume_provision_if_stuck(self.school, reason=f"poll-{i}")
                if r["action"] == "resumed":
                    resumed += 1
                elif r["action"] == "capped":
                    break
            self.assertLessEqual(resumed, 12)
            self.assertEqual(kick.call_count, resumed)

    def test_sweep_finds_and_resumes_dead_run(self):
        _make_run(self.school, status="running", heartbeat_age_seconds=600)
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            summary = pw.resume_stuck_provisions(limit=10, reason="sweep-test")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["resumed"], 1)
        kick.assert_called_once()

    def test_failed_provision_auto_requeue_sweep_has_no_fielderror(self):
        # Regression: the sweep ordered by `-updated_at`, a field WorkflowRun does
        # not have → FieldError swallowed → the sweep silently did nothing.
        _make_run(self.school, status="failed", heartbeat_age_seconds=600)
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )

        result = workflow_failed_provision_auto_requeue_sweep_task()
        self.assertTrue(result.get("ok"), msg=f"sweep raised/failed: {result}")
        self.assertNotIn("FieldError", str(result))


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisioningRecursionGuardTests(TestCase):
    """Finding 2 backstop: a failing provision must create EXACTLY ONE drive.

    The provisioning-autopilot policy (migration 0086) is active in the test DB, so
    a failed run's finalize would — without the guards — auto-apply requeue_provision
    and re-dispatch provisioning INLINE (eager), recursing through _do_provision and
    poisoning nested atomic blocks (TransactionManagementError). Two independent
    guards prevent that: finalize_run(auto_apply=False) and the _active_provision_drives
    re-entrancy contextvar. This test fails loudly if a future change (e.g. a Celery
    upgrade that copies context, or dropping auto_apply=False) reopens the recursion.
    """

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Recursion Guard Academy",
            slug="recursion-guard",
            subdomain="recursion-guard",
            is_active=False,
        )

    @patch("apps.schools.tasks._do_provision_tracked")
    def test_failing_provision_creates_exactly_one_run(self, mock_tracked):
        mock_tracked.side_effect = ValueError("simulated persistent failure")
        with self.assertRaises(ValueError):
            provision_school_sync(str(self.school.id), contact_email="owner@recursion.test")
        runs = WorkflowRun.objects.filter(
            workflow_key="tenant_school_provision", school_id=str(self.school.id)
        )
        self.assertEqual(
            runs.count(), 1,
            f"expected exactly ONE provision run (no auto-fix recursion), got {runs.count()}",
        )
        self.assertEqual((runs.first().status or "").lower(), "failed")


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class UnstickThenFreshProvisionDemoTests(TestCase):
    """End-to-end demo of the user's ask: find a stuck job → unstick it → provision a
    fresh school → confirm nothing gets stuck. Real provision_school_sync (RLS mode)."""

    def setUp(self):
        cache.clear()

    def test_unstick_stuck_job_then_fresh_provision_completes(self):
        from django.core.management import call_command

        from apps.schools.provisioning_progress import (
            resolve_portal_ready,
            resolve_provisioning_progress,
        )

        # 1. A STUCK school: heartbeat-dead running provision (process died mid-migrate).
        stuck = School.objects.create(
            name="Stuck Demo School", slug="zzt-stuck-demo", subdomain="zzt-stuck-demo",
            is_active=False,
        )
        _make_run(stuck, status="running", heartbeat_age_seconds=600)
        self.assertFalse(pw.provisioning_drive_is_live(stuck), "run should read as dead")

        # 2. Unstick it via the operator command (mock the daemon-thread kick).
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            call_command("unstick_provisions")
        self.assertTrue(kick.called, "unstick should re-drive the dead provision")
        # zombie run was cancelled by the watchdog:
        self.assertFalse(
            WorkflowRun.objects.filter(
                school_id=str(stuck.id), status="running"
            ).exists(),
            "the heartbeat-dead run should be cancelled, not left running",
        )

        # 3. FRESH provision of a brand-new school through the REAL pipeline.
        fresh = School.objects.create(
            name="Fresh Demo School", slug="fresh-demo", subdomain="fresh-demo",
            is_active=False,
        )
        provision_school_sync(str(fresh.id), contact_email="owner@fresh-demo.test")
        fresh.refresh_from_db()

        # 4. It completed and is NOT stuck.
        self.assertTrue(resolve_portal_ready(fresh), "fresh provision should reach portal-ready")
        prog = resolve_provisioning_progress(fresh)
        self.assertIn(prog.get("status"), ("succeeded", "running"))
        self.assertFalse(prog.get("stuck"), "fresh provision must not be stuck")
        # No heartbeat-dead running run for the fresh school.
        self.assertFalse(pw.provisioning_drive_is_live(fresh) is None)


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class FlightDeckRestartActionTests(TestCase):
    """The workflow flight deck MUST offer a restart/requeue action on a stuck job.

    Regression: can_operator_requeue_provisioning() gated on the legacy
    provisioning_in_flight(), which calls ANY status="running" row "in flight" —
    including a heartbeat-DEAD one that records no error. That HID the operator's
    Requeue action on exactly the stuck jobs needing a kickoff. Liveness is now
    judged by heartbeat freshness.
    """

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Deck Restart Academy", slug="deck-restart", subdomain="deck-restart",
            is_active=False,
        )

    def _actions_for(self, run):
        from apps.platform_runtime.workflow_flight_deck_actions import (
            build_operator_actions,
        )
        from apps.platform_runtime.workflow_tracker import serialize_workflow_run

        payload = serialize_workflow_run(run)
        return [a.get("kind") for a in build_operator_actions(run=run, payload=payload)]

    def test_stuck_job_offers_restart_action(self):
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning

        run = _make_run(self.school, status="running", heartbeat_age_seconds=600)
        self.assertTrue(
            can_operator_requeue_provisioning(self.school),
            "a heartbeat-dead provision MUST be requeueable by the operator",
        )
        self.assertIn(
            "requeue_provision", self._actions_for(run),
            "the flight deck must expose a restart/requeue action on a stuck job",
        )

    def test_live_job_does_not_offer_restart(self):
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning

        _make_run(self.school, status="running", heartbeat_age_seconds=5)
        self.assertFalse(
            can_operator_requeue_provisioning(self.school),
            "a genuinely live provision must NOT be restartable (avoid double-migrate)",
        )
