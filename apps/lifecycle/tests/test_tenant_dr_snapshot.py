"""Tenant immutable snapshot sign + dual-store capture."""

from pathlib import Path

from django.test import TestCase, override_settings

from apps.lifecycle.tenant_dr_snapshot import (
    capture_daily_snapshot,
    restore_from_snapshot,
    verify_signature,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


@override_settings(SECRET_KEY="test-snapshot-signing-key")
class TenantDrSnapshotTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.school = School.objects.create(
            name="Snap School",
            slug="snap-school",
            subdomain="snap-school",
        )
        self.user = User.objects.create_user(username="snap-admin", password="x")

    def test_capture_writes_dual_store_and_verifies_signature(self):
        meta = capture_daily_snapshot(self.school)
        self.assertTrue(Path(meta["primary_uri"]).is_file())
        self.assertTrue(Path(meta["secondary_uri"]).is_file())
        payload = Path(meta["primary_uri"]).read_bytes()
        self.assertTrue(
            verify_signature(payload, meta["signature_hex"], school_id=str(self.school.pk))
        )
        self.assertTrue(
            verify_signature(payload, meta["signature_hex"], school_id=str(self.school.pk))
        )

    def test_restore_from_snapshot_round_trip(self):
        meta = capture_daily_snapshot(self.school)
        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(self.school.pk),
            expected_sig=meta["signature_hex"],
        )
        self.assertEqual(restored["school_id"], str(self.school.pk))
        self.assertIn("counts", restored)

    def test_tampered_signature_fails_closed(self):
        meta = capture_daily_snapshot(self.school)
        payload = Path(meta["primary_uri"]).read_bytes()
        self.assertFalse(
            verify_signature(payload, "deadbeef" * 8, school_id=str(self.school.pk))
        )

    def test_restore_snapshot_reflects_working_school_aggregates(self):
        from apps.lifecycle.tenant_dr_snapshot import compile_snapshot_payload
        from apps.people.models import TeacherProfile

        TeacherProfile.objects.create(user=self.user, school=self.school)
        StudentProfile.objects.create(
            first_name="Extra",
            last_name="Student",
            date_of_birth="2013-02-02",
            student_code="snap-extra-001",
            school=self.school,
        )
        live = compile_snapshot_payload(self.school)
        meta = capture_daily_snapshot(self.school)
        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(self.school.pk),
            expected_sig=meta["signature_hex"],
        )
        self.assertEqual(restored["counts"], live["counts"])
        self.assertGreaterEqual(restored["counts"]["students"], 1)
        self.assertGreaterEqual(restored["counts"]["teachers"], 1)

    def test_restore_live_tenant_point_in_time_proof(self):
        """Restore payload is capture-time truth; live DB may diverge after snapshot."""
        from apps.lifecycle.tenant_dr_snapshot import compile_snapshot_payload

        StudentProfile.objects.create(
            first_name="Baseline",
            last_name="Student",
            date_of_birth="2012-01-01",
            student_code="snap-live-001",
            school=self.school,
        )
        meta = capture_daily_snapshot(self.school)
        baseline_counts = compile_snapshot_payload(self.school)["counts"]

        StudentProfile.objects.create(
            first_name="Post",
            last_name="Snapshot",
            date_of_birth="2012-06-01",
            student_code="snap-live-002",
            school=self.school,
        )
        live_counts = compile_snapshot_payload(self.school)["counts"]
        self.assertGreater(live_counts["students"], baseline_counts["students"])

        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(self.school.pk),
            expected_sig=meta["signature_hex"],
        )
        self.assertEqual(restored["counts"], baseline_counts)
        self.assertLess(restored["counts"]["students"], live_counts["students"])
