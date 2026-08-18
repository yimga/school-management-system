"""Feature ② — tenant-admin "Sync with cloud" button + status panel (self-healing).

Covers the observability model, the never-raising runner, and the view/template wiring:
  (a) EdgeSyncRun.record + latest_for
  (b) run_sync_cycle with the flag OFF  -> enabled False, one ok=False run, no raise
  (c) flag ON but transport raises (offline) -> run recorded with error, no raise
  (d) flag ON + patched transport success -> run recorded ok=True with counts
  (e) sync_now POST by an authorized user -> 302 + one EdgeSyncRun created
  (f) the sync_center page renders the status card + both buttons

The HTTP transport (``edge_outbox.post_bundle`` / ``pull_bundle``) is patched throughout
so tests never touch the network.
"""
from __future__ import annotations

import urllib.error
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission as FeaturePermission, User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine import sync_runner
from apps.sync_engine.delta_bundle import export_delta_bundle
from apps.sync_engine.models import EdgeSyncRun

_SIGN_KEY = "edge-sync-ui-test-key"
_POST = "apps.sync_engine.edge_outbox.post_bundle"
_PULL = "apps.sync_engine.edge_outbox.pull_bundle"


def _empty_bundle(school) -> bytes:
    """A valid, signed, zero-row bundle the box can 'pull' and apply without a network."""
    return export_delta_bundle(school_id=str(school.id), rows=[], device_id="test")


# --------------------------------------------------------------------------- #
# (a) Model
# --------------------------------------------------------------------------- #
class EdgeSyncRunModelTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Run {uid}", slug=f"run-{uid}", subdomain=f"run{uid}", is_active=True
        )

    def test_record_creates_a_row_and_ignores_stray_keys(self):
        # ``enabled`` is part of the runner's result dict but NOT a model field — record
        # must drop it rather than raise, so the runner can hand over its result as-is.
        run = EdgeSyncRun.record(
            self.school, mode="dry", ok=True, pushed=2, pulled=5, enabled=True
        )
        self.assertIsNotNone(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.mode, "dry")
        self.assertTrue(run.ok)
        self.assertEqual(run.pushed, 2)
        self.assertEqual(run.pulled, 5)

    def test_latest_for_returns_newest_and_none_when_empty(self):
        self.assertIsNone(EdgeSyncRun.latest_for(self.school))
        self.assertIsNone(EdgeSyncRun.latest_for(None))
        old = EdgeSyncRun.record(self.school, mode="live", ok=False)
        new = EdgeSyncRun.record(self.school, mode="live", ok=True)
        # Force a strictly older timestamp so ``-created_at`` ordering is deterministic.
        EdgeSyncRun.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(EdgeSyncRun.latest_for(self.school).pk, new.pk)


# --------------------------------------------------------------------------- #
# (b)-(d) Runner
# --------------------------------------------------------------------------- #
@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class RunSyncCycleTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Cyc {uid}", slug=f"cyc-{uid}", subdomain=f"cyc{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"cyc_admin_{uid}", password="Test1234", email=f"c{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        # A local change so the outbound delta is non-empty (push is actually attempted).
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_flag_off_records_disabled_run_without_touching_the_network(self):
        with patch(_POST) as post, patch(_PULL) as pull:
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertFalse(result["enabled"])
        self.assertFalse(result["ok"])
        self.assertIn("not enabled", result["message"].lower())
        post.assert_not_called()
        pull.assert_not_called()
        runs = EdgeSyncRun.objects.filter(school=self.school)
        self.assertEqual(runs.count(), 1)
        self.assertFalse(runs.first().ok)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_offline_transport_is_caught_and_recorded_without_raising(self):
        offline = urllib.error.URLError("offline")
        with patch(_POST, side_effect=offline), patch(_PULL, side_effect=offline):
            result = sync_runner.run_sync_cycle(self.school, mode="live")  # must not raise
        self.assertTrue(result["enabled"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])  # the offline reason was captured
        runs = EdgeSyncRun.objects.filter(school=self.school)
        self.assertEqual(runs.count(), 1)
        run = runs.first()
        self.assertFalse(run.ok)
        self.assertTrue(run.error)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_success_records_ok_run_with_counts(self):
        pushed_ok = (200, {"ok": True, "applied": 1, "conflicts": 0})
        pulled_ok = (200, _empty_bundle(self.school), None)
        with patch(_POST, return_value=pushed_ok), patch(_PULL, return_value=pulled_ok):
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["pushed"], 1)  # the student shipped up
        self.assertEqual(result["pulled"], 0)  # empty bundle applied cleanly
        runs = EdgeSyncRun.objects.filter(school=self.school)
        self.assertEqual(runs.count(), 1)
        run = runs.first()
        self.assertTrue(run.ok)
        self.assertGreaterEqual(run.pushed, 1)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_dry_run_is_a_no_write_connectivity_check(self):
        # Dry = a true no-write probe: it confirms the cloud is reachable + the credential
        # is accepted (pull_bundle) but applies NOTHING and posts NOTHING. This is what the
        # pre-offline sync gate runs.
        pulled_ok = (200, _empty_bundle(self.school), None)
        with patch(_POST) as post, patch(_PULL, return_value=pulled_ok) as pull, patch(
            "apps.sync_engine.edge_inbox.apply_pulled_bundle"
        ) as apply_:
            result = sync_runner.run_sync_cycle(self.school, mode="dry")
        post.assert_not_called()  # never pushes
        pull.assert_called_once()  # but DOES confirm the cloud is reachable
        apply_.assert_not_called()  # and applies NOTHING (no cloud->box write)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["pushed"], 0)
        self.assertEqual(result["pulled"], 0)


# --------------------------------------------------------------------------- #
# (e)-(f) View + template
# --------------------------------------------------------------------------- #
_T_HOST = "edge-ui.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY,
)
class SyncNowViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Edge UI School", slug="edge-ui", subdomain="edge-ui", is_active=True
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        # A superuser the runner's pull path can resolve as the apply principal.
        cls.principal = User.objects.create_superuser(
            username="edge_ui_principal", password="x" * 8, email="p@edge.test"
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        self.admin = User.objects.create_user(
            username="edge_ui_admin", password="x" * 8, role=User.Role.ADMIN
        )
        self.admin.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.client.login(username="edge_ui_admin", password="x" * 8)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_sync_now_post_records_a_run_and_redirects(self):
        pulled_ok = (200, _empty_bundle(self.school), None)
        url = reverse("siteconfig:sync_center_sync_now")
        with patch(_POST, return_value=(200, {"ok": True})), patch(_PULL, return_value=pulled_ok):
            resp = self.client.post(url, data={"mode": "dry"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 1)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_on_a_box_the_panel_offers_the_box_initiated_controls(self):
        resp = self.client.get(reverse("siteconfig:sync_center"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("data-rmc-edge-sync-panel", body)
        self.assertIn(reverse("siteconfig:sync_center_sync_now"), body)
        self.assertIn("Dry-run sync", body)
        self.assertIn("Sync now", body)
        self.assertIn("data-rmc-wfp-stay", body)

    def test_on_the_cloud_the_panel_offers_a_resync_queue_not_a_dead_sync_button(self):
        """This assertion used to be the inverse, and it locked in a live defect.

        The page previously rendered "Sync now" / "Dry-run sync" on EVERY deployment. On
        the cloud those cannot work at all — the box is behind NAT, so nothing there can
        be reached — so every click produced a failed cycle and a red EdgeSyncRun row.
        (The flag defaults OFF in tests, which is the cloud shape.) The cloud gets the
        control it can actually honour instead: queue a resync the box collects itself.
        """
        resp = self.client.get(reverse("siteconfig:sync_center"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("data-rmc-edge-sync-panel", body)
        self.assertNotIn("Sync now", body)
        self.assertNotIn("Dry-run sync", body)
        self.assertIn(reverse("siteconfig:sync_center_request_resync"), body)
        self.assertIn("Queue full resync", body)

    def test_posting_sync_now_on_the_cloud_refuses_without_recording_a_failed_run(self):
        """The screenshot symptom: a red "Last sync failed" row created by the UI itself."""
        url = reverse("siteconfig:sync_center_sync_now")
        with patch(_POST) as post, patch(_PULL) as pull:
            resp = self.client.post(url, data={"mode": "live"})
        self.assertEqual(resp.status_code, 302)
        post.assert_not_called()
        pull.assert_not_called()
        self.assertEqual(
            EdgeSyncRun.objects.filter(school=self.school).count(),
            0,
            "a guaranteed-impossible action still wrote a failed run row",
        )

    def test_queue_full_resync_is_idempotent_and_visible(self):
        from apps.sync_engine.models import EdgeSyncDirective

        url = reverse("siteconfig:sync_center_request_resync")
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(
            EdgeSyncDirective.objects.filter(school=self.school, served_at__isnull=True).count(),
            1,
            "pressing twice while the box is offline queued two resyncs",
        )
        body = self.client.get(reverse("siteconfig:sync_center")).content.decode("utf-8")
        self.assertIn("waiting for the box to connect", body)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_sync_now_leaves_http_worker_with_running_row(self):
        """Same-tab leftover: POST must return while the cycle is still open."""

        class Pending:
            def ready(self):
                return False

        url = reverse("siteconfig:sync_center_sync_now")
        with patch(
            "apps.platform_runtime.workflow_telemetry.enqueue_background_job",
            return_value=Pending(),
        ) as enqueued:
            resp = self.client.post(url, data={"mode": "dry"})
        self.assertEqual(resp.status_code, 302)
        enqueued.assert_called_once()
        running = EdgeSyncRun.in_progress_for(self.school)
        self.assertIsNotNone(running)
        self.assertIsNone(running.finished_at)
        kwargs = enqueued.call_args.kwargs
        self.assertEqual(kwargs.get("run_id"), running.pk)
        self.assertEqual(kwargs.get("mode"), "dry")
        self.assertFalse(kwargs.get("block_in_process", True))

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_sync_now_xhr_returns_running_json_without_redirect(self):
        from apps.sync_engine.sync_status import PHASE_RUNNING

        class Pending:
            def ready(self):
                return False

        url = reverse("siteconfig:sync_center_sync_now")
        with patch(
            "apps.platform_runtime.workflow_telemetry.enqueue_background_job",
            return_value=Pending(),
        ):
            resp = self.client.post(
                url,
                data={"mode": "live"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["phase"], PHASE_RUNNING)
        self.assertTrue(body["queued"])
        self.assertIsNotNone(EdgeSyncRun.in_progress_for(self.school))
