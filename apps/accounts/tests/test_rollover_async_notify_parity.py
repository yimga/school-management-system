"""Async rollover apply — guardian-notify parity + lock completion (M29 / EOY).

* **Fix 2 — notify parity.** ``apps.accounts.tasks._apply_rollover_proposal_impl``
  accepted ``notify_parents`` and IGNORED it: a queued rollover with "Notify
  parents" ticked sent nothing, while the synchronous ``rollover_year`` view sent
  a per-guardian in-app notification. The task now calls the same shared helper
  (``_notify_guardians_of_rollover``).
* **Fix 4 control.** The normal rollover locks the SOURCE year *after* moving the
  cohort; wiring a year-lock guard into ``open_enrollment`` must NOT break that —
  the apply still completes end-to-end and the source ends up locked.

Both tests exercise the real task impl, so they fail on the pre-fix code (zero
notifications) and pass after.
"""

from django.test import TestCase

from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.accounts.tasks import _apply_rollover_proposal_impl
from apps.finance.models import Notification as FinanceNotification
from apps.people.enrollment_services import ensure_enrollment
from apps.people.models import StudentGuardian
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin


class AsyncRolloverNotifyParityTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("async-notify")
        self.student = self.make_student("NOTIFY-1")
        # An open enrollment in the source year, so the move has something to
        # close and derive the outcome from.
        ensure_enrollment(self.student)

        self.guardian_user = User.objects.create_user(
            username="guardian-async-notify",
            password="pass12345",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian_user,
            student=self.student,
            receives_sms=False,
        )

        self.proposal = RolloverProposal.objects.create(
            school=self.school,
            source_year=self.year_1,
            target_year=self.year_2,
            status=RolloverProposal.Status.APPROVED,
            created_by=self.guardian_user,  # any user; identity is not asserted
        )
        RolloverProposalItem.objects.create(
            proposal=self.proposal,
            student=self.student,
            current_classroom_id=self.grade5_y1.pk,
            suggested_next_classroom=self.grade6_y2,
            approved_next_classroom=self.grade6_y2,
            promotion_status="PROMOTED",
        )

    def _guardian_notification_count(self):
        return FinanceNotification.objects.filter(
            recipient=self.guardian_user
        ).count()

    def test_async_apply_notifies_guardians_when_requested(self):
        # MUST-FIRE: pre-fix the task ignored notify_parents -> zero rows.
        self.assertEqual(self._guardian_notification_count(), 0)

        # override_backup_gate=True: the pre-rollover backup gate (M29 / EOY
        # gap #3) refuses an un-backed-up apply; this test predates the gate and
        # asserts notify parity, so it explicitly overrides.
        result = _apply_rollover_proposal_impl(
            self.proposal.id,
            lock_source=True,
            notify_parents=True,
            override_backup_gate=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated"], 1, result)

        # Fix 2: the guardian now has a class-assignment notification.
        self.assertGreaterEqual(self._guardian_notification_count(), 1)

        # Fix 4 control: the rollover that locks the source AFTER the move still
        # completed end-to-end.
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, RolloverProposal.Status.APPLIED)
        self.year_1.refresh_from_db()
        self.assertTrue(self.year_1.is_locked)
        self.assertEqual(
            self.student.enrollment_for_year(self.year_2).classroom_id,
            self.grade6_y2.pk,
        )

    def test_async_apply_without_notify_flag_sends_nothing(self):
        # override_backup_gate=True — see note above (this test asserts the
        # no-notify path, not the backup gate).
        result = _apply_rollover_proposal_impl(
            self.proposal.id, notify_parents=False, override_backup_gate=True
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(self._guardian_notification_count(), 0)
