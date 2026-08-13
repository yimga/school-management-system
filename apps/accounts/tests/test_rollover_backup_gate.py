"""Pre-rollover backup/export gate (M29 / EOY gap #3).

Year-end rollover is destructive — it moves every active student out of the
source year and can lock it. Before any student is moved, the apply path must
have EITHER a recent M28 tenant DR snapshot for the school
(``apps.lifecycle.models_dr_snapshot.TenantImmutableSnapshot``, written by
``apps.lifecycle.tenant_dr_snapshot.capture_daily_snapshot``) OR an explicit
operator override.

Two layers of proof:

* **Helper contract** — ``require_pre_rollover_backup`` passes when a recent
  snapshot exists, passes when overridden, and RAISES otherwise (incl. a stale
  snapshot outside the freshness window).
* **MUST-FIRE on the real apply path** — ``_apply_rollover_proposal_impl``:
  (1) with no backup and no override the apply is REFUSED and NO student is
  moved / the proposal stays APPROVED (the gate fired before any write);
  (2) with ``override_backup_gate=True`` it proceeds and completes;
  (3) with a seeded backup and NO override it also proceeds.

Test (1) fails on the pre-gate code (which applied unconditionally) and passes
after; the helper tests fail-to-import on pre-gate code (the module is new).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.accounts.rollover_backup import (
    BACKUP_REQUIRED_MESSAGE,
    recent_backup_exists,
    require_pre_rollover_backup,
)
from apps.accounts.tasks import _apply_rollover_proposal_impl
from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot
from apps.people.enrollment_services import ensure_enrollment
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin


def _seed_snapshot(school, *, age_days=0):
    """Create a TenantImmutableSnapshot for ``school``, optionally back-dated."""
    snap = TenantImmutableSnapshot.objects.create(
        school=school,
        snapshot_date=timezone.now().date(),
        primary_uri="/snapshots/test.json.gz",
        secondary_uri="",
        payload_sha256="0" * 64,
        signature_hex="0" * 128,
        byte_size=123,
    )
    if age_days:
        # created_at is auto_now_add, so back-date it explicitly to simulate an
        # old snapshot outside the freshness window.
        TenantImmutableSnapshot.objects.filter(pk=snap.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
    return snap


class RequirePreRolloverBackupHelperTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("backup-helper")

    def test_recent_backup_present_returns_backup_present(self):
        _seed_snapshot(self.school)
        self.assertTrue(recent_backup_exists(self.school))
        self.assertEqual(
            require_pre_rollover_backup(self.school, self.year_1),
            "backup-present",
        )

    def test_no_backup_no_override_raises(self):
        self.assertFalse(recent_backup_exists(self.school))
        with self.assertRaises(ValidationError) as ctx:
            require_pre_rollover_backup(self.school, self.year_1)
        self.assertIn(BACKUP_REQUIRED_MESSAGE, ctx.exception.messages)

    def test_no_backup_with_override_returns_operator_override(self):
        self.assertEqual(
            require_pre_rollover_backup(
                self.school, self.year_1, override=True, created_by=None
            ),
            "operator-override",
        )

    def test_stale_backup_outside_window_raises(self):
        _seed_snapshot(self.school, age_days=30)
        self.assertFalse(recent_backup_exists(self.school))
        with self.assertRaises(ValidationError):
            require_pre_rollover_backup(self.school, self.year_1)

    def test_backup_for_other_school_does_not_satisfy_gate(self):
        # A backup for a DIFFERENT school must not unlock this school's rollover.
        other = type(self.school).objects.create(
            slug="other-bk", name="Other BK", subdomain="other-bk"
        )
        _seed_snapshot(other)
        with self.assertRaises(ValidationError):
            require_pre_rollover_backup(self.school, self.year_1)


class AsyncRolloverBackupGateApplyTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("backup-apply")
        self.student = self.make_student("BK-1")
        # An open source-year enrollment so the apply has something to move.
        ensure_enrollment(self.student)

        self.actor = User.objects.create_user(
            username="rollover-approver",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.proposal = RolloverProposal.objects.create(
            school=self.school,
            source_year=self.year_1,
            target_year=self.year_2,
            status=RolloverProposal.Status.APPROVED,
            created_by=self.actor,
            approved_by=self.actor,
        )
        RolloverProposalItem.objects.create(
            proposal=self.proposal,
            student=self.student,
            current_classroom_id=self.grade5_y1.pk,
            suggested_next_classroom=self.grade6_y2,
            approved_next_classroom=self.grade6_y2,
            promotion_status="PROMOTED",
        )

    def test_apply_without_backup_and_without_override_is_refused(self):
        # MUST-FIRE: pre-gate code applied unconditionally; the gate now refuses.
        result = _apply_rollover_proposal_impl(self.proposal.id)

        self.assertFalse(result["ok"], result)
        self.assertIn("backup", result["error"].lower())
        self.assertNotIn("updated", result)  # no move summary — nothing ran

        # Proposal untouched and NO student moved: the gate fired before any write.
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, RolloverProposal.Status.APPROVED)
        self.assertIsNone(self.student.enrollment_for_year(self.year_2))

    def test_apply_with_override_proceeds_and_completes(self):
        result = _apply_rollover_proposal_impl(
            self.proposal.id, override_backup_gate=True
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated"], 1, result)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, RolloverProposal.Status.APPLIED)
        self.assertEqual(
            self.student.enrollment_for_year(self.year_2).classroom_id,
            self.grade6_y2.pk,
        )

    def test_apply_with_seeded_backup_proceeds_without_override(self):
        _seed_snapshot(self.school)

        result = _apply_rollover_proposal_impl(self.proposal.id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated"], 1, result)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, RolloverProposal.Status.APPLIED)
