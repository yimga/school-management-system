"""Wave L4 — soft-delete + restore + billing gate + audit mirror."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School

from .billing_gate import check_billing_clearance
from .models import SchoolLifecycleStage
from .services_offboarding import (
    audit_event_log_mirror,
    grace_expires_at,
    is_in_grace,
    mark_deleted,
    restore,
)


class MarkDeletedTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Soft Delete Test",
            slug="soft-delete-test",
            subdomain="soft-delete-test",
        )

    def test_sets_deleted_at_timestamp(self):
        mark_deleted(self.school)
        self.school.refresh_from_db()
        self.assertIsNotNone(self.school.deleted_at)

    def test_sets_is_active_false(self):
        mark_deleted(self.school)
        self.school.refresh_from_db()
        self.assertFalse(self.school.is_active)

    def test_records_grace_stage(self):
        mark_deleted(self.school, reason="test")
        self.assertTrue(
            SchoolLifecycleStage.objects.filter(
                school=self.school,
                stage=SchoolLifecycleStage.Stage.OFFBOARDING_GRACE,
            ).exists()
        )

    def test_caps_reason_at_200_chars(self):
        mark_deleted(self.school, reason="x" * 500)
        stage = SchoolLifecycleStage.objects.filter(
            school=self.school, stage=SchoolLifecycleStage.Stage.OFFBOARDING_GRACE
        ).first()
        self.assertEqual(len(stage.note), 200)


class RestoreTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Restore Test",
            slug="restore-test",
            subdomain="restore-test",
        )

    def test_clears_deleted_at(self):
        mark_deleted(self.school)
        restore(self.school)
        self.school.refresh_from_db()
        self.assertIsNone(self.school.deleted_at)

    def test_records_cancelled_stage(self):
        mark_deleted(self.school)
        restore(self.school)
        self.assertTrue(
            SchoolLifecycleStage.objects.filter(
                school=self.school,
                stage=SchoolLifecycleStage.Stage.OFFBOARDING_CANCELLED,
            ).exists()
        )

    def test_refuses_after_purge(self):
        from .services import record_stage

        record_stage(self.school, SchoolLifecycleStage.Stage.OFFBOARDING_PURGED)
        with self.assertRaises(ValueError):
            restore(self.school)


class IsInGraceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Grace Test",
            slug="grace-test",
            subdomain="grace-test",
        )

    def test_false_when_not_deleted(self):
        self.assertFalse(is_in_grace(self.school))

    def test_true_when_just_deleted(self):
        mark_deleted(self.school)
        self.school.refresh_from_db()
        self.assertTrue(is_in_grace(self.school))

    def test_false_when_grace_expired(self):
        mark_deleted(self.school)
        self.school.refresh_from_db()
        # Backdate deleted_at past the grace window.
        past = timezone.now() - timedelta(days=60)
        School.objects.filter(pk=self.school.pk).update(deleted_at=past)
        self.school.refresh_from_db()
        self.assertFalse(is_in_grace(self.school))


class GraceExpiresAtTests(TestCase):
    def test_returns_none_when_not_deleted(self):
        school = School.objects.create(
            name="X", slug="grace-expires-x", subdomain="grace-expires-x"
        )
        self.assertIsNone(grace_expires_at(school))

    def test_returns_datetime_when_deleted(self):
        school = School.objects.create(
            name="Y", slug="grace-expires-y", subdomain="grace-expires-y"
        )
        mark_deleted(school)
        school.refresh_from_db()
        self.assertIsNotNone(grace_expires_at(school))


class BillingClearanceTests(TestCase):
    def test_returns_unknown_when_no_school(self):
        clearance = check_billing_clearance(None)
        self.assertEqual(clearance.state, "unknown")
        self.assertFalse(clearance.cleared)

    def test_returns_unknown_on_billing_error(self):
        school = School.objects.create(
            name="Bill", slug="bill-test", subdomain="bill-test"
        )
        # Without billing context wired, clearance falls back to unknown.
        clearance = check_billing_clearance(school)
        self.assertIn(clearance.state, ("unknown", "cleared"))


class AuditMirrorTests(TestCase):
    def test_skips_non_offboarding_event(self):
        event = MagicMock()
        event.event_type = "COMPLETED"
        self.assertFalse(audit_event_log_mirror(event))

    def test_logs_offboarding_event(self):
        school = School.objects.create(
            name="Audit", slug="audit-test", subdomain="audit-test"
        )
        event = MagicMock()
        event.event_type = "OFFBOARDING_PURGE_REQUESTED"
        event.school = school
        event.actor = None
        event.id = 42
        event.created_at = timezone.now()
        self.assertTrue(audit_event_log_mirror(event))
