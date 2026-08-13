"""Phase 4 — policy-governed, direction-aware conflict resolution.

Wires the (previously dormant) policy_registry into the delta apply path:
  * LWW master data — newest updated_at wins, direction-independent.
  * Protected / authoritative domains (money fee_payment/invoice_line, grades, identity)
    — CLOUD-AUTHORITATIVE: a cloud->box pull always wins on the box; a box->cloud push or
    an online edit is never silently applied, it becomes a Sync Center conflict.
  * ONLINE_REQUIRED domains (credentials, lifecycle, settlement) — rejected on the sync
    path entirely.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.api.sync_services import _conflict_decision, apply_changes
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict


class ConflictDecisionUnitTests(SimpleTestCase):
    """The pure decision function — the actual policy logic, no DB."""

    def setUp(self):
        self.now = timezone.now()
        self.older = self.now - timedelta(hours=1)
        self.newer = self.now + timedelta(hours=1)

    def test_lww_master_data_newest_wins_regardless_of_direction(self):
        D = _conflict_decision
        self.assertEqual(D("student", None, self.newer, self.now), "apply")
        self.assertEqual(D("student", None, self.older, self.now), "conflict")
        self.assertEqual(D("student", None, None, None), "apply")
        self.assertEqual(D("student", "edge-push", self.older, self.now), "conflict")
        # cloud-pull does NOT let a stale LWW change win — timestamp still governs.
        self.assertEqual(D("academic_year", "cloud-pull", self.older, self.now), "conflict")
        self.assertEqual(D("attendance", None, self.newer, self.now), "apply")  # alias->attendance_record

    def test_money_is_cloud_authoritative(self):
        D = _conflict_decision
        # cloud->box pull always wins on the box, even if the box copy looks newer.
        self.assertEqual(D("fee_payment", "cloud-pull", self.older, self.now), "apply")
        self.assertEqual(D("invoice_line", "cloud-pull", self.newer, self.now), "apply")
        # a box->cloud push (or online edit) of money is NEVER silently applied.
        self.assertEqual(D("fee_payment", "edge-push", self.newer, self.now), "conflict")
        self.assertEqual(D("fee_payment", None, self.newer, self.now), "conflict")
        self.assertEqual(D("payment", "edge-push", self.newer, self.now), "conflict")  # alias->fee_payment

    def test_grades_and_identity_are_protected(self):
        D = _conflict_decision
        self.assertEqual(D("grade", "edge-push", self.newer, self.now), "conflict")  # alias->grade_entry
        self.assertEqual(D("grade", "cloud-pull", self.older, self.now), "apply")
        self.assertEqual(D("user_profile", "edge-push", self.newer, self.now), "conflict")

    def test_online_required_domains_are_rejected(self):
        D = _conflict_decision
        self.assertEqual(D("security_credential", "edge-push", self.newer, self.now), "reject")
        self.assertEqual(D("password", None, self.newer, self.now), "reject")  # alias
        self.assertEqual(D("tenant_lifecycle", "cloud-pull", self.newer, self.now), "reject")

    def test_unregistered_entity_fails_closed_to_protected(self):
        # An entity that is neither in POLICIES nor the explicit LWW-safe allowlist must
        # NOT be treated as two-way LWW — it fails CLOSED to protected/cloud-authoritative,
        # so a never-classified sensitive entity can't be silently overwritten by a box.
        D = _conflict_decision
        self.assertEqual(D("some_unclassified_entity", "edge-push", self.newer, self.now), "conflict")
        self.assertEqual(D("some_unclassified_entity", "cloud-pull", self.older, self.now), "apply")


class ConflictApplyIntegrationTests(TestCase):
    """The wiring end-to-end through apply_changes."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Cf {uid}", slug=f"cf-{uid}", subdomain=f"cf{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"cf_admin_{uid}", password="Test1234", email=f"c{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="N", date_of_birth="2012-01-01"
        )

    def _apply(self, when, *, sync_origin=None, first_name="Changed"):
        return apply_changes(
            str(self.school.id), self.user,
            [{"entity_type": "student", "id": self.student.pk,
              "changes": {"first_name": first_name}, "updated_at": when.isoformat()}],
            persist_conflicts=True, sync_origin=sync_origin,
        )

    def test_lww_stale_change_becomes_conflict(self):
        out = self._apply(timezone.now() - timedelta(hours=1))  # older than the fresh record
        self.assertEqual(out["success_count"], 0, out)
        self.assertEqual(len(out["conflicts"]), 1)
        self.assertTrue(
            SyncConflict.objects.filter(
                school=self.school, entity_type="student", status=SyncConflict.Status.PENDING
            ).exists()
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")  # unchanged

    def test_lww_newer_change_applies(self):
        out = self._apply(timezone.now() + timedelta(hours=1))
        self.assertEqual(out["success_count"], 1, out)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Changed")

    def test_protected_push_does_not_overwrite_even_when_newer(self):
        # Force 'student' to be treated as a protected/authoritative domain.
        with patch(
            "apps.api.sync_services._sync_conflict_policy",
            return_value=("manual_review", True),
        ):
            out = self._apply(timezone.now() + timedelta(hours=1), sync_origin="edge-push")
        self.assertEqual(out["success_count"], 0, out)  # box push must not overwrite
        self.assertEqual(len(out["conflicts"]), 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")

    def test_protected_cloud_pull_wins_even_when_older(self):
        with patch(
            "apps.api.sync_services._sync_conflict_policy",
            return_value=("manual_review", True),
        ):
            out = self._apply(
                timezone.now() - timedelta(hours=1), sync_origin="cloud-pull", first_name="FromCloud"
            )
        self.assertEqual(out["success_count"], 1, out)  # cloud authoritative -> applies
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "FromCloud")
