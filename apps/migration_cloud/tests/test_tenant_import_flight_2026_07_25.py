"""Live import / repair observability for the tenant upload path.

Before this, clicking "Repair this import" (or "Import into my school") queued a
durable BACKGROUND apply, then the review page reverted to a bare "ready to
import" look with no live feedback, no visible outcome, and no signal if the
work sat unclaimed — so a repair that was actually running looked like a dead
button ("I click it and it never repairs anything"). These tests lock the fix:

* ``_import_flight`` reports a queued/running import from the durable apply
  OUTBOX row — the authoritative signal that exists (PENDING → PROCESSING) for
  the whole life of the background apply — refines the label to "running" while
  the row is PROCESSING or the bundle is APPLYING, flags a PENDING row that has
  sat past the threshold as ``stuck`` (no worker draining, surfaced honestly),
  and is IDOR-safe (scoped to this bundle's id).
* ``_progress_payload`` carries those flags and keeps ``done`` False while an
  import is in flight, so the review-page poller watches the apply settle and
  reloads to reveal the result instead of stopping early.
* ``_last_import_summary`` surfaces the most recent LIVE apply totals so the
  outcome (created / updated / held) shows after the page reloads on its own; a
  dry-run preview writes nothing, so its totals are skipped.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.migration_cloud.models import BundleStatus
from apps.migration_cloud.views_tenant_upload import (
    _import_flight,
    _last_import_summary,
    _progress_payload,
)
from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox


class _FakeArtifactManager:
    def __init__(self, artifacts):
        self._artifacts = artifacts

    def all(self):
        return list(self._artifacts)


def _fake_bundle(status, *, mapping=None, artifacts=None):
    """A complete DB-free stand-in exercising the attributes the helpers read."""
    return SimpleNamespace(
        pk=7,
        status=status,
        get_status_display=lambda: f"{status} label",
        progress_snapshot={"stages": []},
        size_summary={},
        mapping_summary=mapping or {},
        reconciliation_summary={},
        artifacts=_FakeArtifactManager(artifacts or []),
    )


class ImportFlightStatusBranchTests(TestCase):
    """The status branch with no active outbox row (empty DB).

    ``APPLYING`` on the bundle is in-flight even with no row; a settled bundle
    with no queued/processing row is not.
    """

    def test_applying_status_is_running_in_flight(self):
        flight = _import_flight(_fake_bundle(BundleStatus.APPLYING))
        self.assertTrue(flight["in_flight"])
        self.assertEqual(flight["phase"], "running")

    def test_applied_with_no_active_row_is_not_in_flight(self):
        self.assertFalse(_import_flight(_fake_bundle(BundleStatus.APPLIED))["in_flight"])

    def test_mapped_with_no_active_row_is_not_in_flight(self):
        self.assertFalse(_import_flight(_fake_bundle(BundleStatus.MAPPED))["in_flight"])


class ImportFlightDegradationTests(TestCase):
    """An unreadable outbox must never break the review page — it degrades to
    "not in flight" (best-effort), the pre-existing behaviour."""

    def test_outbox_read_failure_degrades_to_not_in_flight(self):
        with mock.patch(
            "apps.platform_runtime.models_heavy_work_outbox.HeavyWorkOutbox.objects"
        ) as mgr:
            mgr.filter.side_effect = RuntimeError("db down")
            flight = _import_flight(SimpleNamespace(pk=7, status=BundleStatus.APPLIED))
        self.assertFalse(flight["in_flight"])


class LastImportSummaryTests(SimpleTestCase):
    def test_none_before_any_apply(self):
        self.assertIsNone(_last_import_summary(_fake_bundle(BundleStatus.MAPPED)))

    def test_live_apply_totals_surface(self):
        b = _fake_bundle(
            BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "created": 5,
                    "updated": 2,
                    "quarantined": 3,
                    "dry_run": False,
                }
            },
        )
        s = _last_import_summary(b)
        self.assertEqual((s["created"], s["updated"], s["held"]), (5, 2, 3))

    def test_dry_run_totals_are_skipped(self):
        b = _fake_bundle(
            BundleStatus.MAPPED,
            mapping={"apply_totals": {"created": 5, "quarantined": 0, "dry_run": True}},
        )
        self.assertIsNone(_last_import_summary(b))

    def test_all_zero_totals_are_not_shown(self):
        b = _fake_bundle(
            BundleStatus.APPLIED,
            mapping={"apply_totals": {"created": 0, "updated": 0, "quarantined": 0}},
        )
        self.assertIsNone(_last_import_summary(b))


class ProgressPayloadImportFlagsTests(TestCase):
    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_importing_flags_block_done(self, refresh):
        refresh.return_value = {"stages": []}
        payload = _progress_payload(_fake_bundle(BundleStatus.APPLYING))
        self.assertTrue(payload["importing"])
        self.assertEqual(payload["import_phase"], "running")
        # Poller must keep watching until the apply settles.
        self.assertFalse(payload["done"])

    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_settled_applied_is_done_not_importing(self, refresh):
        refresh.return_value = {"stages": []}
        payload = _progress_payload(_fake_bundle(BundleStatus.APPLIED))
        self.assertFalse(payload["importing"])
        self.assertTrue(payload["done"])


class ImportFlightOutboxTests(TestCase):
    """The queued / running / stuck branch reads the durable apply-outbox row."""

    def _row(self, **kw):
        return HeavyWorkOutbox.objects.create(
            kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
            status=kw.get("status", HeavyWorkOutbox.Status.PENDING),
            bundle_id=kw.get("bundle_id", 7),
            payload=kw.get("payload", {"dry_run": False}),
        )

    def _bundle(self, status=BundleStatus.MAPPED):
        return SimpleNamespace(pk=7, status=status)

    def test_pending_row_marks_queued_in_flight(self):
        self._row()
        flight = _import_flight(self._bundle())
        self.assertTrue(flight["in_flight"])
        self.assertEqual(flight["phase"], "queued")
        self.assertFalse(flight["stuck"])

    def test_processing_row_is_running(self):
        self._row(status=HeavyWorkOutbox.Status.PROCESSING)
        self.assertEqual(_import_flight(self._bundle())["phase"], "running")

    def test_old_pending_row_is_stuck(self):
        row = self._row()
        HeavyWorkOutbox.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(seconds=300)
        )
        flight = _import_flight(self._bundle())
        self.assertTrue(flight["in_flight"])
        self.assertTrue(flight["stuck"])

    def test_settled_row_not_in_flight(self):
        self._row(status=HeavyWorkOutbox.Status.SUCCEEDED)
        self.assertFalse(_import_flight(self._bundle(BundleStatus.APPLIED))["in_flight"])

    def test_row_scoped_to_bundle_id(self):
        # A queued apply for a DIFFERENT bundle must not mark this one in flight.
        self._row(bundle_id=999)
        self.assertFalse(_import_flight(self._bundle(BundleStatus.APPLIED))["in_flight"])

    def test_dry_run_payload_flagged(self):
        self._row(payload={"dry_run": True})
        self.assertTrue(_import_flight(self._bundle())["dry_run"])
