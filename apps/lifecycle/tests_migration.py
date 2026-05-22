"""Wave L5 — migration auto-launch + status snapshot."""

from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School

from .models import SchoolLifecycleStage
from .services_migration import (
    ensure_draft_migration_bundle,
    tenant_status_snapshot,
)


class EnsureDraftMigrationBundleTests(TestCase):
    def test_no_op_when_no_intent(self):
        school = School.objects.create(
            name="NoIntent", slug="no-intent", subdomain="no-intent"
        )
        bundle = ensure_draft_migration_bundle(school)
        self.assertIsNone(bundle)

    def test_no_op_when_intent_not_dict(self):
        school = School.objects.create(
            name="WrongIntent",
            slug="wrong-intent",
            subdomain="wrong-intent",
            settings={"migration_intent": "powerschool"},  # wrong shape
        )
        bundle = ensure_draft_migration_bundle(school)
        self.assertIsNone(bundle)

    def test_creates_draft_when_intent_present(self):
        school = School.objects.create(
            name="WithIntent",
            slug="with-intent",
            subdomain="with-intent",
            settings={
                "migration_intent": {
                    "vendor": "powerschool",
                    "intake_method": "file_upload",
                }
            },
        )
        bundle = ensure_draft_migration_bundle(school)
        self.assertIsNotNone(bundle)
        # Lifecycle stage MIGRATING should be recorded.
        self.assertTrue(
            SchoolLifecycleStage.objects.filter(
                school=school,
                stage=SchoolLifecycleStage.Stage.MIGRATING,
            ).exists()
        )

    def test_idempotent_when_pending_bundle_exists(self):
        school = School.objects.create(
            name="Idem",
            slug="idem-school",
            subdomain="idem-school",
            settings={
                "migration_intent": {
                    "vendor": "blackbaud",
                    "intake_method": "url",
                }
            },
        )
        b1 = ensure_draft_migration_bundle(school)
        b2 = ensure_draft_migration_bundle(school)
        self.assertEqual(b1.id, b2.id)

    def test_normalizes_unknown_intake_method(self):
        school = School.objects.create(
            name="UnknownMethod",
            slug="unknown-method",
            subdomain="unknown-method",
            settings={
                "migration_intent": {
                    "vendor": "alma",
                    "intake_method": "telepathy",  # invalid
                }
            },
        )
        bundle = ensure_draft_migration_bundle(school)
        if bundle is None:
            self.skipTest("Migration Cloud unavailable in this env")
        # Should normalize to file_upload default.
        self.assertEqual(bundle.intake_method, "file_upload")


class TenantStatusSnapshotTests(TestCase):
    def test_returns_empty_for_no_bundles(self):
        school = School.objects.create(
            name="Empty", slug="empty-status", subdomain="empty-status"
        )
        snap = tenant_status_snapshot(school)
        self.assertEqual(snap["bundles"], [])
        self.assertIsNone(snap["active_bundle"])

    def test_returns_active_bundle_when_present(self):
        school = School.objects.create(
            name="WithBundle",
            slug="with-bundle-status",
            subdomain="with-bundle-status",
            settings={
                "migration_intent": {
                    "vendor": "powerschool",
                    "intake_method": "file_upload",
                }
            },
        )
        bundle = ensure_draft_migration_bundle(school)
        if bundle is None:
            self.skipTest("Migration Cloud unavailable in this env")
        snap = tenant_status_snapshot(school)
        self.assertEqual(len(snap["bundles"]), 1)
        self.assertIsNotNone(snap["active_bundle"])
        self.assertEqual(snap["active_bundle"]["status"], "PENDING")
