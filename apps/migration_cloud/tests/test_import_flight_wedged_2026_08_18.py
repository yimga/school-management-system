"""A claimed-but-dead import must stop presenting as progress.

Reported from production: the review page showed "Importing your data… Working…"
for eight hours while nothing ran. ``_import_flight`` computed its ``stuck`` flag
ONLY inside ``if pending and not running``, so it could report exactly one stall
mode -- "queued, no worker took it". The commonest real failure is the opposite:
a worker CLAIMS the apply and then dies (deploy, OOM, the Postgres
connection-exhaustion incident), which leaves the bundle at APPLYING. That is
``running=True``, never ``pending``, so ``stuck`` stayed False and the tenant was
shown an animated progress bar indefinitely, with the honest recovery affordance
never surfacing.

``repair.applying_stale_by_time`` already existed as the project's single source
of truth for "wedged apply" and is used by the repair path and the durable-retry
self-heal -- ``_import_flight`` simply never asked it. These tests pin that it
does, and that it stays conservative: a LIVE apply still reads as working, so the
fix cannot turn a slow-but-healthy import into a false alarm.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.models import BundleStatus, MigrationBundle
from apps.migration_cloud.views_tenant_upload import _import_flight
from apps.schools.models import School


def _backdate(bundle, minutes):
    """updated_at is auto_now, so only a queryset update can age the heartbeat."""
    stamp = timezone.now() - timedelta(minutes=minutes)
    MigrationBundle.objects.filter(pk=bundle.pk).update(updated_at=stamp)
    bundle.refresh_from_db()
    return bundle


class ImportFlightWedgedTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Flight {uid}", slug=f"flight-{uid}", subdomain=f"flight{uid}", is_active=True
        )

    def _bundle(self, status):
        return MigrationBundle.objects.create(school=self.school, status=status)

    def test_apply_that_stopped_heartbeating_is_reported_stuck(self):
        bundle = _backdate(self._bundle(BundleStatus.APPLYING), minutes=90)
        flight = _import_flight(bundle)
        self.assertTrue(flight["in_flight"])
        self.assertEqual(flight["phase"], "running")
        self.assertTrue(
            flight["stuck"],
            "a claimed apply with a 90-minute-cold heartbeat was reported as healthy "
            "progress -- this is the endless-spinner bug",
        )

    def test_live_apply_is_not_a_false_alarm(self):
        bundle = self._bundle(BundleStatus.APPLYING)  # heartbeat is now
        flight = _import_flight(bundle)
        self.assertTrue(flight["in_flight"])
        self.assertEqual(flight["phase"], "running")
        self.assertFalse(flight["stuck"], "a live apply must still read as working")

    def test_settled_bundle_is_not_in_flight_at_all(self):
        bundle = _backdate(self._bundle(BundleStatus.APPLIED), minutes=90)
        flight = _import_flight(bundle)
        self.assertFalse(flight["in_flight"])
        self.assertFalse(flight["stuck"])
