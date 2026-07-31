"""Phase 3: safe, idempotent auto-repair for a failed / incomplete bundle.

repair_bundle re-applies a broken bundle idempotently (upsert — no duplicates)
and re-verifies. These tests lock the CONSERVATIVE guardrails: repair is offered
only for genuinely-broken applies and is REFUSED (never papered over) for the
unsafe cases — financial control-total failures, non-atomic finance, and
reconciled / in-flight / not-yet-applied bundles.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.migration_cloud import repair as repair_mod
from apps.migration_cloud.models import BundleStatus, FinancialMismatchError
from apps.migration_cloud.repair import repair_bundle, repair_readiness


class _Arts:
    def __init__(self, arts):
        self._a = arts

    def all(self):
        return list(self._a)


def _finance_artifact():
    return SimpleNamespace(path_within_bundle="finance.csv", assigned_domain="finance")


class FakeBundle:
    """DB-free stand-in exercising exactly the attributes repair.py reads."""

    def __init__(self, **kw):
        self.pk = 7
        self.status = kw.get("status", BundleStatus.FAILED)
        self.size_summary = kw.get("size", {})
        self.mapping_summary = kw.get("mapping", {})
        self.reconciliation_summary = kw.get("recon", {})
        self.discovery_summary = kw.get("discovery", {})
        self.artifacts = _Arts(kw.get("arts", []))
        self.apply_atomic = kw.get("apply_atomic", False)
        # repair.py's _applying_is_stale reads updated_at to decide whether an
        # APPLYING bundle is a wedged/abandoned apply (repairable) vs one that
        # is actively in flight (NOT repairable). A real bundle always has this
        # (auto_now); default to "just now" so an APPLYING fake models an
        # in-flight apply. Pass updated_at=<old datetime> to model a stale one.
        self.updated_at = kw.get("updated_at", timezone.now())

    def mark_status(self, new_status, *, summary_patch=None):
        self.status = new_status
        if summary_patch:
            self.size_summary = {**self.size_summary, **summary_patch}

    def refresh_from_db(self):
        pass


def _quarantined(n):
    return {"apply_totals": {"quarantined": n}}


class RepairReadinessTests(SimpleTestCase):
    def test_failed_no_finance_is_repairable(self):
        r = repair_readiness(FakeBundle(status=BundleStatus.FAILED))
        self.assertTrue(r.repairable)
        self.assertEqual(r.blockers, [])

    def test_financial_guardrail_lock_refused(self):
        r = repair_readiness(FakeBundle(
            status=BundleStatus.FAILED,
            size={"financial_guardrail_failed": True},
        ))
        self.assertFalse(r.repairable)
        self.assertIn("financial_guardrail_failed", r.blockers)

    def test_finance_non_atomic_refused(self):
        r = repair_readiness(FakeBundle(
            status=BundleStatus.FAILED,
            arts=[_finance_artifact()],
            apply_atomic=False,
        ))
        self.assertFalse(r.repairable)
        self.assertIn("finance_requires_atomic", r.blockers)

    def test_finance_atomic_allowed(self):
        r = repair_readiness(FakeBundle(
            status=BundleStatus.FAILED,
            arts=[_finance_artifact()],
            apply_atomic=True,
        ))
        self.assertTrue(r.repairable)

    def test_applied_with_held_rows_is_repairable(self):
        r = repair_readiness(FakeBundle(
            status=BundleStatus.APPLIED,
            mapping=_quarantined(12),
        ))
        self.assertTrue(r.repairable)
        self.assertEqual(r.issue_count, 12)

    def test_applied_with_visible_drift_is_repairable(self):
        r = repair_readiness(FakeBundle(
            status=BundleStatus.APPLIED,
            recon={"notes": ["students: only 40 row(s) are visible in the school"]},
        ))
        self.assertTrue(r.repairable)

    def test_applied_clean_not_repairable(self):
        r = repair_readiness(FakeBundle(status=BundleStatus.APPLIED))
        self.assertFalse(r.repairable)

    def test_reconciled_not_repairable(self):
        r = repair_readiness(FakeBundle(status=BundleStatus.RECONCILED))
        self.assertFalse(r.repairable)

    def test_applying_not_repairable(self):
        r = repair_readiness(FakeBundle(status=BundleStatus.APPLYING))
        self.assertFalse(r.repairable)

    def test_pre_apply_not_repairable(self):
        r = repair_readiness(FakeBundle(status=BundleStatus.MAPPED))
        self.assertFalse(r.repairable)


class RepairBundleTests(SimpleTestCase):
    def _patch_get(self, fake):
        return mock.patch.object(repair_mod.MigrationBundle.objects, "get", return_value=fake)

    def test_refuses_without_running(self):
        fake = FakeBundle(status=BundleStatus.RECONCILED)
        with self._patch_get(fake):
            res = repair_bundle(bundle_id=7)
        self.assertFalse(res.ran)
        self.assertFalse(res.ok)
        self.assertEqual(res.after_status, BundleStatus.RECONCILED)  # untouched

    def test_financial_mismatch_reported_not_suppressed(self):
        fake = FakeBundle(status=BundleStatus.FAILED)

        def _boom(*a, **k):
            fake.status = BundleStatus.FAILED  # apply_bundle marks it FAILED
            raise FinancialMismatchError("totals off")

        with self._patch_get(fake), \
                mock.patch("apps.migration_cloud.orchestrator.apply_bundle", side_effect=_boom):
            res = repair_bundle(bundle_id=7)
        self.assertTrue(res.ran)
        self.assertFalse(res.ok)
        self.assertIn("financial_guardrail_failed", res.blockers)

    def test_success_path_reapplies_and_reverifies(self):
        fake = FakeBundle(status=BundleStatus.FAILED)

        def _apply(*, bundle_id, dry_run):
            fake.status = BundleStatus.APPLIED  # apply landed the rows
            return SimpleNamespace(total_created=5, total_updated=2, total_quarantined=1)

        with self._patch_get(fake), \
                mock.patch("apps.migration_cloud.orchestrator.apply_bundle", side_effect=_apply), \
                mock.patch("apps.migration_cloud.reconciliation.reconcile_bundle") as recon:
            res = repair_bundle(bundle_id=7)
        self.assertTrue(res.ran)
        self.assertTrue(res.ok)
        self.assertEqual(res.created, 5)
        self.assertEqual(res.updated, 2)
        self.assertEqual(res.quarantined, 1)
        self.assertEqual(res.after_status, BundleStatus.APPLIED)
        recon.assert_called_once()  # re-verify ran


class BuildRepairPanelTests(SimpleTestCase):
    """The review-page panel only appears when there is something to act on."""

    def test_hidden_on_fresh_pre_import_bundle(self):
        from apps.migration_cloud.views_tenant_upload import _build_repair

        self.assertIsNone(_build_repair(FakeBundle(status=BundleStatus.MAPPED)))

    def test_hidden_on_clean_applied_bundle(self):
        from apps.migration_cloud.views_tenant_upload import _build_repair

        self.assertIsNone(_build_repair(FakeBundle(status=BundleStatus.APPLIED)))

    def test_shown_when_repairable(self):
        from apps.migration_cloud.views_tenant_upload import _build_repair

        panel = _build_repair(FakeBundle(status=BundleStatus.FAILED))
        self.assertIsNotNone(panel)
        self.assertTrue(panel["repairable"])

    def test_shown_with_reason_on_financial_lock(self):
        from apps.migration_cloud.views_tenant_upload import _build_repair

        panel = _build_repair(FakeBundle(
            status=BundleStatus.FAILED,
            size={"financial_guardrail_failed": True},
        ))
        self.assertIsNotNone(panel)
        self.assertFalse(panel["repairable"])
        self.assertIn("financial_guardrail_failed", panel["blockers"])
