"""Live Sync Center status, bulk resolve, and queued-beats-failed contract."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.urls import get_resolver, reverse
from django.utils import timezone

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict
from apps.sync_engine.conflict_actions import bulk_resolve
from apps.sync_engine.models import EdgeSyncRun, request_full_resync
from apps.sync_engine.sync_status import PHASE_QUEUED, PHASE_RUNNING, serialize_live_status


_T_HOST = "sync-live.runmycampus.com"


class EdgeSyncRunLifecycleTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Live {uid}", slug=f"live-{uid}", subdomain=f"live{uid}", is_active=True
        )

    def test_begin_then_complete_is_still_one_row(self):
        row = EdgeSyncRun.begin(self.school, mode="live")
        self.assertIsNone(row.finished_at)
        self.assertEqual(EdgeSyncRun.in_progress_for(self.school).pk, row.pk)
        row.complete(ok=True, pushed=3, message="done")
        row.refresh_from_db()
        self.assertTrue(row.ok)
        self.assertIsNotNone(row.finished_at)
        self.assertIsNone(EdgeSyncRun.in_progress_for(self.school))
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 1)

    def test_begin_abandons_a_stale_in_progress_row(self):
        stale = EdgeSyncRun.begin(self.school, mode="live")
        newer = EdgeSyncRun.begin(self.school, mode="live")
        stale.refresh_from_db()
        self.assertIsNotNone(stale.finished_at)
        self.assertFalse(stale.ok)
        self.assertEqual(EdgeSyncRun.in_progress_for(self.school).pk, newer.pk)


class LiveStatusComposerTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Stat {uid}", slug=f"stat-{uid}", subdomain=f"stat{uid}", is_active=True
        )

    def test_queued_resync_beats_last_failed_run(self):
        EdgeSyncRun.record(
            self.school,
            mode="live",
            ok=False,
            error="operator unreachable",
            finished_at=timezone.now() - timedelta(hours=1),
        )
        request_full_resync(self.school)
        payload = serialize_live_status(self.school)
        self.assertEqual(payload["phase"], PHASE_QUEUED)
        self.assertIn("queued", payload["badge"].lower())
        self.assertIsNotNone(payload["pending_resync"])

    def test_in_progress_beats_queued_and_failed(self):
        EdgeSyncRun.record(self.school, mode="live", ok=False, error="old")
        request_full_resync(self.school)
        EdgeSyncRun.begin(self.school, mode="live")
        payload = serialize_live_status(self.school)
        self.assertEqual(payload["phase"], PHASE_RUNNING)

    def test_running_percent_uses_cycle_steps_not_row_counts(self):
        row = EdgeSyncRun.begin(self.school, mode="live")
        payload = serialize_live_status(self.school)
        self.assertEqual(payload["percent_complete"], "0.00")
        self.assertEqual(payload["processed"], 0)
        self.assertEqual(payload["expected"], 2)
        row.checkpoint(pushed=40, pulled=0, message="pushed 40 in 1 bundle(s)")
        payload = serialize_live_status(self.school)
        self.assertEqual(payload["phase"], PHASE_RUNNING)
        self.assertEqual(payload["pushed"], 40)
        self.assertEqual(payload["percent_complete"], "50.00")
        self.assertEqual(payload["processed"], 1)
        self.assertEqual(payload["expected"], 2)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class SyncCenterLiveViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Sync Live School",
            slug="sync-live",
            subdomain="sync-live",
            is_active=True,
        )
        cls.other = School.objects.create(
            name="Other Sync School",
            slug="sync-other",
            subdomain="sync-other",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        self.admin = User.objects.create_user(
            username="sync_live_admin", password="x" * 8, role=User.Role.ADMIN
        )
        self.admin.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.client.login(username="sync_live_admin", password="x" * 8)
        SyncConflict.objects.filter(school=self.school).delete()

    def test_status_json_queued_not_last_failed(self):
        EdgeSyncRun.record(self.school, ok=False, error="stale fail", mode="live")
        request_full_resync(self.school, self.admin)
        SyncConflict.objects.create(
            school=self.school,
            entity_type="homework_submission",
            entity_id=11,
            status=SyncConflict.Status.PENDING,
        )
        resp = self.client.get(reverse("siteconfig:sync_center_status"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["phase"], PHASE_QUEUED)
        page = self.client.get(reverse("siteconfig:sync_center"))
        self.assertContains(page, "Sync queued")
        self.assertContains(page, "data-rmc-wfp-canvas")
        self.assertContains(page, "data-rmc-bulk-table")

    def test_status_route_has_one_owner(self):
        matching = [
            pattern
            for pattern in get_resolver().reverse_dict.getlist("siteconfig:sync_center_status")
            if pattern
        ]
        self.assertEqual(len(matching), 1)

    def test_bulk_resolve_keeps_server_and_ignores_other_school(self):
        mine = SyncConflict.objects.create(
            school=self.school,
            entity_type="homework_submission",
            entity_id=1,
            status=SyncConflict.Status.PENDING,
        )
        other = SyncConflict.objects.create(
            school=self.other,
            entity_type="homework_submission",
            entity_id=2,
            status=SyncConflict.Status.PENDING,
        )
        url = reverse("siteconfig:sync_center_bulk_resolve")
        resp = self.client.post(
            url,
            data=json.dumps({"ids": [mine.pk, other.pk], "resolution": "server"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["resolved"], 1)
        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(mine.status, SyncConflict.Status.RESOLVED_SERVER)
        self.assertEqual(other.status, SyncConflict.Status.PENDING)

    def test_policy_skips_manual_review_entities(self):
        row = SyncConflict.objects.create(
            school=self.school,
            entity_type="invoice",
            entity_id=9,
            status=SyncConflict.Status.PENDING,
        )
        result = bulk_resolve(
            school=self.school,
            ids=[row.pk],
            resolution="policy",
            resolved_by=self.admin,
        )
        row.refresh_from_db()
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(row.status, SyncConflict.Status.PENDING)

    def test_policy_keeps_server_for_authoritative_entity(self):
        row = SyncConflict.objects.create(
            school=self.school,
            entity_type="homework_submission",
            entity_id=3,
            status=SyncConflict.Status.PENDING,
        )
        result = bulk_resolve(
            school=self.school,
            ids=[row.pk],
            resolution="policy",
            resolved_by=self.admin,
        )
        row.refresh_from_db()
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(row.status, SyncConflict.Status.RESOLVED_SERVER)


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_SYNC_BUNDLE_SIGNING_KEY="k")
class RunSyncCycleInProgressTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"CycLive {uid}",
            slug=f"cyclive-{uid}",
            subdomain=f"cyclive{uid}",
            is_active=True,
        )

    def test_success_still_records_exactly_one_finished_run(self):
        from apps.sync_engine import sync_runner
        from apps.sync_engine.delta_bundle import export_delta_bundle

        pulled_ok = (
            200,
            export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="test"),
            None,
        )
        with patch(
            "apps.sync_engine.edge_outbox.post_bundle",
            return_value=(200, {"ok": True}),
        ), patch(
            "apps.sync_engine.edge_outbox.pull_bundle", return_value=pulled_ok
        ):
            result = sync_runner.run_sync_cycle(self.school, mode="dry")
        self.assertTrue(result["ok"], result)
        runs = EdgeSyncRun.objects.filter(school=self.school)
        self.assertEqual(runs.count(), 1)
        self.assertIsNotNone(runs.first().finished_at)
        self.assertIsNone(EdgeSyncRun.in_progress_for(self.school))

    def test_reuses_an_open_row_instead_of_beginning_a_second(self):
        from apps.sync_engine import sync_runner
        from apps.sync_engine.delta_bundle import export_delta_bundle

        open_row = EdgeSyncRun.begin(self.school, mode="dry")
        pulled_ok = (
            200,
            export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="test"),
            None,
        )
        with patch(
            "apps.sync_engine.edge_outbox.post_bundle",
            return_value=(200, {"ok": True}),
        ), patch(
            "apps.sync_engine.edge_outbox.pull_bundle", return_value=pulled_ok
        ):
            result = sync_runner.run_sync_cycle(
                self.school, mode="dry", run_row=open_row
            )
        self.assertTrue(result["ok"], result)
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 1)
        open_row.refresh_from_db()
        self.assertIsNotNone(open_row.finished_at)

    def test_superseded_open_row_is_a_noop(self):
        from apps.sync_engine import sync_runner

        row = EdgeSyncRun.begin(self.school, mode="live")
        row.complete(ok=False, error="abandoned: a newer cycle started")
        result = sync_runner.run_sync_cycle(self.school, mode="live", run_row=row)
        self.assertTrue(result["ok"])
        self.assertIn("superseded", result["message"])
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 1)

    def test_missing_run_id_does_not_open_a_second_cycle(self):
        from apps.sync_engine.tasks import run_sync_cycle_for_school

        result = run_sync_cycle_for_school(
            self.school.pk, mode="dry", run_id=9_999_999
        )
        self.assertEqual(result["error"], "run_not_found")
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 0)


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST, "edge-poll.runmycampus.com"],
    RMC_EDGE_SYNC_ENABLED=True,
)
class EdgeSyncStatusPollAccessTests(TestCase):
    def setUp(self):
        self.client = Client(
            HTTP_HOST="edge-poll.runmycampus.com",
            raise_request_exception=False,
        )
        self.school = School.objects.create(
            name="Edge Poll School",
            slug="edge-poll",
            subdomain="edge-poll",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username="edge_poll_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        self.client.force_login(self.teacher)

    def test_teacher_can_poll_status_on_edge_box(self):
        resp = self.client.get(reverse("siteconfig:sync_center_status"))
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        body = resp.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("percent_complete", body)

    @override_settings(
        RMC_EDGE_OPERATOR_BASE="https://cloud.test",
        RMC_EDGE_SYNC_ENABLED=True,
    )
    @patch.dict("os.environ", {"RMC_EDGE_CREDENTIAL": "edge-test-token"})
    @patch("urllib.request.urlopen")
    def test_teacher_can_probe_cloud_on_edge_box(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_resp
        resp = self.client.post(reverse("siteconfig:sync_center_probe"))
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("pull", body.get("probes") or {})

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_teacher_cannot_poll_status_on_cloud_saas(self):
        resp = self.client.get(reverse("siteconfig:sync_center_status"))
        self.assertEqual(resp.status_code, 403, resp.content[:200])
