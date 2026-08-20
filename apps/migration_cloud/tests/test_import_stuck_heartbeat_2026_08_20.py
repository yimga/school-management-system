"""A dead apply must not be kept "alive" by an unrelated write.

Reported from production (2026-08-20): "Importing your data…" ran for more than
24 hours. The 2026-08-18 fix had already taught ``_import_flight`` to ask
``repair.applying_stale_by_time``, so a wedged apply *should* have surfaced
Repair after 30 minutes. It did not, because of how staleness was measured.

``applying_stale_by_time`` read ``MigrationBundle.updated_at``, which is
``auto_now`` — so **every** save to the bundle re-stamps it, not just the
orchestrator's deliberate heartbeat. ``MigrationCloudProgressView`` is a GET
poller that called ``refresh_snapshot(bundle=bundle)`` with the default
``persist=True``, and that persists via
``bundle.save(update_fields=["progress_snapshot", "updated_at"])``. So for as
long as anyone had a progress page open, the staleness clock was re-armed every
few seconds and a bundle whose apply worker had died still read as healthy
progress — an animated bar, forever, with the honest recovery affordance never
surfacing.

Two changes are pinned here:

* the read-only poller no longer persists (no write, no fake heartbeat), and
* staleness is measured from the progress-EVENT stream, which only a live apply
  appends to, so no unrelated save can mask a dead import again.

Plus the third leg of the same report: a *finished* import must say it finished.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.migration_cloud.live_import_attention import compose_live_import
from apps.migration_cloud.models import (
    BundleStatus,
    MigrationBundle,
    MigrationProgressEvent,
)
from apps.migration_cloud.repair import applying_stale_by_time
from apps.migration_cloud.tests.test_repair_2026_07_13 import FakeBundle, _quarantined
from apps.schools.models import School


def _age_event(event, *, minutes):
    """created_at is auto_now_add, so only a queryset update can age an event."""
    stamp = timezone.now() - timedelta(minutes=minutes)
    MigrationProgressEvent.objects.filter(pk=event.pk).update(created_at=stamp)
    return stamp


class ApplyStalenessIgnoresUnrelatedSavesTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Stale {uid}", slug=f"stale-{uid}", subdomain=f"stale{uid}", is_active=True
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school, status=BundleStatus.APPLYING
        )

    def _event(self, *, minutes_old):
        ev = MigrationProgressEvent.objects.create(
            bundle=self.bundle, kind="artifact_progress", stage="APPLYING"
        )
        _age_event(ev, minutes=minutes_old)
        return ev

    def test_cold_apply_is_stuck_even_though_a_viewer_just_saved_the_bundle(self):
        """The exact production shape: dead apply + a polling viewer's write."""
        self._event(minutes_old=90)
        # A read-only viewer persisting its snapshot — the fake heartbeat.
        self.bundle.progress_snapshot = {"stages": []}
        self.bundle.save(update_fields=["progress_snapshot", "updated_at"])
        self.bundle.refresh_from_db()

        # updated_at is now fresh...
        self.assertLess((timezone.now() - self.bundle.updated_at).total_seconds(), 60)
        # ...but the apply itself has been silent for 90 minutes, so it is stuck.
        self.assertTrue(
            applying_stale_by_time(self.bundle),
            "an unrelated save re-armed the staleness clock and hid a dead apply "
            "— this is the 24-hour endless-spinner bug",
        )

    def test_live_apply_is_not_a_false_alarm(self):
        self._event(minutes_old=1)
        self.assertFalse(
            applying_stale_by_time(self.bundle), "a live apply must still read as working"
        )

    def test_settled_bundle_is_never_stale(self):
        self._event(minutes_old=90)
        MigrationBundle.objects.filter(pk=self.bundle.pk).update(status=BundleStatus.APPLIED)
        self.bundle.refresh_from_db()
        self.assertFalse(applying_stale_by_time(self.bundle))

    def test_falls_back_to_updated_at_when_no_event_exists(self):
        """Empty event stream (pruned/never emitted) still degrades honestly."""
        stamp = timezone.now() - timedelta(minutes=90)
        MigrationBundle.objects.filter(pk=self.bundle.pk).update(updated_at=stamp)
        self.bundle.refresh_from_db()
        self.assertTrue(applying_stale_by_time(self.bundle))


class OperatorProgressPollerDoesNotWriteTests(SimpleTestCase):
    """The DAG progress endpoint is a viewer; viewers must not heartbeat."""

    @mock.patch("apps.migration_cloud.views._tenant_scoped_bundle")
    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_progress_view_requests_persist_false(self, refresh, scoped):
        from apps.migration_cloud.views import MigrationCloudProgressView

        refresh.return_value = {"stages": []}
        scoped.return_value = SimpleNamespace(
            pk=11,
            status=BundleStatus.APPLYING,
            progress_events=SimpleNamespace(
                order_by=lambda *_a, **_k: SimpleNamespace(values=lambda *a, **k: [])
            ),
        )
        request = SimpleNamespace(GET={"format": "json"}, user=SimpleNamespace(is_staff=True))
        MigrationCloudProgressView().get(request, bundle_id=11)

        self.assertTrue(refresh.called, "the view should still compute a snapshot")
        self.assertFalse(
            refresh.call_args.kwargs.get("persist", True),
            "the operator progress poller persisted on every GET, which re-stamped "
            "auto_now updated_at and masked a dead apply",
        )


class ImportSuccessIsAnnouncedTests(SimpleTestCase):
    """A completed import must report success, not merely stop animating."""

    def test_clean_terminal_apply_is_succeeded(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "quarantined": 0,
                    "created": 105,
                    "updated": 4,
                    "applied_at": "2026-08-20T08:00:00+00:00",
                }
            },
        )
        live = compose_live_import(bundle, flight={"in_flight": False})
        self.assertTrue(live["succeeded"])
        self.assertEqual(live["percent"], 100.0)
        self.assertIsNone(live["remediator"])

    def test_in_flight_import_is_not_succeeded(self):
        bundle = FakeBundle(status=BundleStatus.APPLYING, mapping=_quarantined(0))
        live = compose_live_import(
            bundle, flight={"in_flight": True, "phase": "running", "stuck": False}
        )
        self.assertFalse(live["succeeded"])

    def test_held_rows_block_success(self):
        bundle = FakeBundle(status=BundleStatus.APPLIED, mapping=_quarantined(3))
        live = compose_live_import(bundle, flight={"in_flight": False})
        self.assertFalse(live["succeeded"])
        self.assertIsNotNone(live["remediator"])
