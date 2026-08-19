"""The Sync Center live-status endpoint — the surface that PROVES sync ran.

The Sync Center used to render one row of counters and go stale until reload, so "did
the sync actually work?" needed a refresh reflex. Worse, counters alone are weak
evidence: they cannot separate "12 rows moved" from "one row bounced 12 times", and a
zero is ambiguous between "nothing to do" and "nothing happened".

These lock the three independent kinds of evidence the endpoint returns, and the property
that matters most for an observability surface: it must NEVER 500. A status panel that
crashes is indistinguishable from a sync that crashed.
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.schools.models import School
from apps.sync_engine.models import EdgeSyncRun, SyncApplyLedger


class _StatusBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Status Academy", slug="status-academy", subdomain="status-academy",
            is_active=True,
        )
        cls.user = get_user_model().objects.create_user(
            username="status.admin", password="x", is_staff=True, is_superuser=True,
        )

    def _call(self):
        from apps.siteconfig.views_sync_center import sync_center_status

        request = RequestFactory().get("/siteconfig/sync-center/status/")
        request.user = self.user
        request.school = self.school
        request.tenant = self.school
        request.public_host_kind = None
        return sync_center_status(request)

    def _payload(self):
        response = self._call()
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content.decode("utf-8"))


class StatusPayloadTests(_StatusBase):
    def test_an_empty_school_reports_honest_emptiness_not_an_error(self):
        data = self._payload()
        self.assertTrue(data["ok"])
        self.assertIsNone(data["latest_run"])
        self.assertEqual(data["recent_runs"], [])
        self.assertEqual(data["recent_records"], [])
        self.assertEqual(data["totals"]["runs"], 0)

    def test_a_run_appears_with_its_counts_and_a_server_computed_age(self):
        """Age is computed SERVER-side: a box and a laptop rarely agree on the clock, and
        a confidently wrong "synced 4s ago" is worse than no number."""
        started = timezone.now()
        EdgeSyncRun.record(
            self.school, mode="live", ok=True, pushed=4, pulled=2, conflicts=1,
            created=1, upserted=5, message="pushed 4 in 1 bundle(s)",
            started_at=started, finished_at=timezone.now(),
        )
        data = self._payload()
        latest = data["latest_run"]
        self.assertTrue(latest["ok"])
        self.assertEqual(latest["pushed"], 4)
        self.assertEqual(latest["pulled"], 2)
        self.assertIsNotNone(latest["age_seconds"])
        self.assertIsNotNone(latest["duration_ms"])

    def test_records_carry_the_direction_they_travelled(self):
        """This is the receipt. A count can be fabricated by a bug; a list of records an
        operator can go and open cannot."""
        SyncApplyLedger.objects.create(
            school=self.school, entity_type="student_note", local_pk="9001",
            applied_updated_at=timezone.now(), origin="cloud-pull",
        )
        SyncApplyLedger.objects.create(
            school=self.school, entity_type="academic_year", local_pk="7",
            applied_updated_at=timezone.now(), origin="edge-push",
        )
        records = self._payload()["recent_records"]
        self.assertEqual(len(records), 2)
        self.assertEqual({r["origin"] for r in records}, {"cloud-pull", "edge-push"})
        for record in records:
            self.assertTrue(record["entity_type"])
            self.assertTrue(record["local_pk"])
            self.assertIsNotNone(record["age_seconds"])

    def test_totals_separate_failures_from_throughput(self):
        for ok, pushed in ((True, 3), (True, 2), (False, 0)):
            EdgeSyncRun.record(self.school, mode="live", ok=ok, pushed=pushed, pulled=0)
        totals = self._payload()["totals"]
        self.assertEqual(totals["runs"], 3)
        self.assertEqual(totals["pushed"], 5)
        self.assertEqual(totals["failed"], 1)

    def test_another_school_s_evidence_is_never_visible(self):
        other = School.objects.create(
            name="Other", slug="other-school", subdomain="other-school", is_active=True,
        )
        EdgeSyncRun.record(other, mode="live", ok=True, pushed=99, pulled=99)
        SyncApplyLedger.objects.create(
            school=other, entity_type="leak", local_pk="1",
            applied_updated_at=timezone.now(), origin="cloud-pull",
        )
        data = self._payload()
        self.assertEqual(data["recent_runs"], [])
        self.assertEqual(data["recent_records"], [])
        self.assertEqual(data["totals"]["pushed"], 0)

    def test_history_is_capped_so_the_polled_payload_stays_cheap(self):
        from apps.siteconfig.views_sync_center import _STATUS_RUN_LIMIT

        for index in range(_STATUS_RUN_LIMIT + 6):
            EdgeSyncRun.record(self.school, mode="live", ok=True, pushed=index)
        self.assertEqual(len(self._payload()["recent_runs"]), _STATUS_RUN_LIMIT)

    def test_no_school_in_context_is_a_409_not_a_crash(self):
        from apps.siteconfig.views_sync_center import sync_center_status

        request = RequestFactory().get("/siteconfig/sync-center/status/")
        request.user = self.user
        request.school = None
        self.assertEqual(sync_center_status(request).status_code, 409)


class StatusResilienceTests(_StatusBase):
    """A broken status panel must not be indistinguishable from broken sync."""

    def test_a_failing_cadence_helper_degrades_instead_of_500ing(self):
        with mock.patch(
            "apps.sync_engine.cadence.snapshot", side_effect=RuntimeError("cache down")
        ):
            data = self._payload()
        self.assertTrue(data["ok"])
        self.assertIsNone(data["cadence"])

    def test_a_failing_ledger_read_degrades_instead_of_500ing(self):
        EdgeSyncRun.record(self.school, mode="live", ok=True, pushed=1)
        with mock.patch(
            "apps.sync_engine.models.SyncApplyLedger.objects.filter",
            side_effect=RuntimeError("table gone"),
        ):
            data = self._payload()
        self.assertTrue(data["ok"])
        self.assertEqual(data["recent_records"], [])
        # The rest of the evidence still comes through.
        self.assertIsNotNone(data["latest_run"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_the_cloud_side_says_so_rather_than_pretending_to_be_a_box(self):
        self.assertFalse(self._payload()["edge_sync_enabled"])
