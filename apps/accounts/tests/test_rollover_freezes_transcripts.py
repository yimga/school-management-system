"""Year-end rollover produces the immutable grade archive (M29 / EOY, Fix A).

The rollover apply path moved every active student out of the source year and
GRADUATED some to ``is_active=False`` (alumni) — but it never invoked
``batch_freeze_transcripts``, so NO immutable transcript was ever cut. These
MUST-FIRE tests lock the corrected contract on the async apply path
(``_apply_rollover_proposal_impl``):

1. locking the source year freezes an ImmutableTranscript for EVERY active
   student BEFORE the move — including the graduating cohort that the move then
   flips to ``is_active=False`` (which ``batch_freeze_transcripts``, is_active
   only, would otherwise skip). FAILS on pre-fix code (no freeze at all);
2. without ``lock_source`` the year is not being closed, so no archive is cut
   (control);
3. a freeze failure is NON-FATAL — the rollover still completes.
"""

from unittest import mock

from django.test import TestCase

from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.accounts.tasks import _apply_rollover_proposal_impl
from apps.people.enrollment_services import ensure_enrollment
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin
from apps.student360.models import ImmutableTranscript


class RolloverFreezesTranscriptsTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("freeze-roll")
        # A student who will GRADUATE (alumni; is_active flips False on apply)...
        self.graduate = self.make_student("GRAD-1")
        self.score(self.graduate, 16, 15, 17)
        ensure_enrollment(self.graduate)
        # ...and one who PROMOTES to the next class.
        self.promoter = self.make_student("PROMO-1")
        self.score(self.promoter, 14, 13, 15)
        ensure_enrollment(self.promoter)

        self.actor = User.objects.create_user(
            username="freeze-roll-approver",
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
            student=self.graduate,
            current_classroom_id=self.grade5_y1.pk,
            is_graduate=True,
            approved_next_classroom=None,
            promotion_status="",
        )
        RolloverProposalItem.objects.create(
            proposal=self.proposal,
            student=self.promoter,
            current_classroom_id=self.grade5_y1.pk,
            suggested_next_classroom=self.grade6_y2,
            approved_next_classroom=self.grade6_y2,
            promotion_status="PROMOTED",
        )

    def test_rollover_with_lock_freezes_both_cohorts_including_graduate(self):
        result = _apply_rollover_proposal_impl(
            self.proposal.id, lock_source=True, override_backup_gate=True
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduated"], 1, result)
        self.assertEqual(result["updated"], 1, result)

        # The graduate is now inactive (moved to alumni)...
        self.graduate.refresh_from_db()
        self.assertFalse(self.graduate.is_active)

        # ...yet BOTH students have a frozen source-year transcript, proving the
        # freeze ran BEFORE the move (while the graduate was still active).
        self.assertTrue(
            ImmutableTranscript.objects.filter(
                student=self.graduate, academic_year=self.year_1
            ).exists(),
            "the graduating cohort's final transcript must be frozen",
        )
        self.assertTrue(
            ImmutableTranscript.objects.filter(
                student=self.promoter, academic_year=self.year_1
            ).exists(),
        )
        # Freeze counts are surfaced on the apply result.
        self.assertIsNotNone(result.get("frozen"))
        self.assertGreaterEqual(result["frozen"]["created"], 2, result)

    def test_rollover_without_lock_does_not_freeze(self):
        # No lock_source => the year is not being closed, so no archive is cut.
        result = _apply_rollover_proposal_impl(
            self.proposal.id, override_backup_gate=True
        )
        self.assertTrue(result["ok"], result)
        self.assertIsNone(result.get("frozen"))
        self.assertFalse(
            ImmutableTranscript.objects.filter(academic_year=self.year_1).exists()
        )

    def test_freeze_failure_is_non_fatal(self):
        # Force the freeze to blow up; the rollover must still complete.
        with mock.patch(
            "apps.academics.year_close.batch_freeze_transcripts",
            side_effect=RuntimeError("boom"),
        ):
            result = _apply_rollover_proposal_impl(
                self.proposal.id, lock_source=True, override_backup_gate=True
            )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduated"], 1, result)
        self.assertEqual(result["updated"], 1, result)
        self.assertIsNone(result.get("frozen"))
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, RolloverProposal.Status.APPLIED)
