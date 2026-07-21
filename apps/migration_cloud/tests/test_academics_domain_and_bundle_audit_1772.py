"""Academics canonical domain + bundle advance/apply audit (batch 1772)."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    DOMAIN_CANONICAL_HEADERS,
    guess_domain_from_filename,
    is_valid_canonical_domain,
)
from apps.migration_cloud.models_audit import MigrationCloudAuditEventType


class AcademicsCanonicalDomainTests(SimpleTestCase):
    def test_academics_in_canonical_headers(self):
        self.assertIn("academics", DOMAIN_CANONICAL_HEADERS)
        headers = DOMAIN_CANONICAL_HEADERS["academics"]
        self.assertIn("subject_code", headers)
        self.assertIn("subject_name", headers)
        self.assertTrue(is_valid_canonical_domain("academics"))

    def test_course_filename_routes_to_academics_not_sections(self):
        self.assertEqual(guess_domain_from_filename("courses.csv"), "academics")
        self.assertEqual(guess_domain_from_filename("subjects.xlsx"), "academics")
        self.assertEqual(guess_domain_from_filename("section_roster.csv"), "sections")


class BundleAuditEventTypeTests(SimpleTestCase):
    def test_bundle_lifecycle_types_registered(self):
        registered = {c.value for c in MigrationCloudAuditEventType}
        self.assertIn("migration.bundle.advanced", registered)
        self.assertIn("migration.bundle.applied", registered)


class BundleLifecycleAuditEmitTests(TestCase):
    def test_safe_bundle_audit_writes_row(self):
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        from apps.migration_cloud.services.bundle_lifecycle_audit import (
            safe_bundle_audit,
        )
        from apps.schools.models import School

        school = School.objects.create(
            name="UAT Audit School",
            subdomain="uat-mc-audit-bundle",
        )
        # Minimal stand-in with school + pk for the helper.
        bundle = type("B", (), {"pk": 4242, "school": school})()
        before = MigrationCloudAuditEvent.objects.count()
        safe_bundle_audit(
            bundle,
            MigrationCloudAuditEventType.BUNDLE_ADVANCED.value,
            payload_summary={"bundle_id": "4242", "status": "mapped"},
        )
        self.assertEqual(MigrationCloudAuditEvent.objects.count(), before + 1)
        ev = MigrationCloudAuditEvent.objects.order_by("-created_at").first()
        self.assertEqual(ev.event_type, "migration.bundle.advanced")
        self.assertEqual(ev.payload_summary.get("bundle_id"), "4242")
