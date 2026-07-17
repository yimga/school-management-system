"""A guardian-record merge must actually retire the losing link.

Found by an A-Z audit follow-up (2026-07-16/17). Product decision (tombstone)
taken by the operator 2026-07-17.

``merge_service._retire_secondary`` soft-retires the losing row::

    if hasattr(secondary, "is_active"):
        secondary.is_active = False
        ...
    if hasattr(secondary, "merged_into_id"):
        secondary.merged_into = primary
        ...
    if update_fields:
        secondary.save(update_fields=update_fields)

``StudentGuardian`` carried NEITHER field, so ``update_fields`` stayed empty and
NOTHING was saved -- yet ``apply_merge`` still advanced the FSM to APPLIED. The
duplicate link stayed live: it kept showing up in every guardian notification
recipient query, so the parent was **notified twice**. And the idempotency
guard in ``_resolve_pair`` (``refuse if secondary.merged_into_id``) could never
fire, for guardians OR teachers (``TeacherProfile`` also lacked ``merged_into``),
so an already-merged record could be merged again.

Fix (tombstone): ``StudentGuardian`` gains ``is_active`` + ``merged_into`` and
``TeacherProfile`` gains ``merged_into``; every guardian-notification recipient
builder filters ``is_active=True`` (via the new ``.active()`` queryset) so a
retired duplicate is never notified. Deleting the link was rejected as unsafe:
``InvoicePayerShare.guardian`` is CASCADE (would delete payer shares) and
``ReferralReward.guardian`` is PROTECT (would raise). The merge walker re-points
those FKs onto the surviving link first; the retired row is then tombstoned.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.people.merge_service import (
    MergeBlockedError,
    apply_merge,
    approve_merge,
    preview_merge,
)
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.people.models_merge import RecordMergeOperation
from apps.schools.models import School

User = get_user_model()


class GuardianMergeTombstonesTheDuplicateTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(
            name="Tomb High", slug="gm-tomb", subdomain="gm-tomb"
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Kid", last_name="One",
            student_code="GM-T-1",
        )
        self.primary_parent = User.objects.create_user(
            username="gm_tomb_primary", password="p", role=User.Role.PARENT,
        )
        self.dup_parent = User.objects.create_user(
            username="gm_tomb_dup", password="p", role=User.Role.PARENT,
        )
        # Same student, two guardian accounts -- the duplicate an operator
        # merges. Both opt in to email so both are notification recipients.
        self.primary = StudentGuardian.objects.create(
            guardian_user=self.primary_parent, student=self.student,
            email="primary@example.com", receives_email=True,
        )
        self.dup = StudentGuardian.objects.create(
            guardian_user=self.dup_parent, student=self.student,
            email="dup@example.com", receives_email=True,
        )

    def _merge(self, primary, secondary):
        op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.GUARDIAN,
            primary_pk=str(primary.pk),
            secondary_pk=str(secondary.pk),
        )
        preview_merge(op)
        approve_merge(op, actor=None)
        summary = apply_merge(op, actor=None)
        return summary, op

    # --- the tombstone ----------------------------------------------------

    def test_apply_tombstones_the_retired_duplicate(self):
        _summary, op = self._merge(self.primary, self.dup)
        op.refresh_from_db()
        self.assertEqual(op.status, RecordMergeOperation.Status.APPLIED)
        self.dup.refresh_from_db()
        self.assertFalse(
            self.dup.is_active,
            "the retired duplicate was left is_active=True while the FSM "
            "reported APPLIED -- retirement was a no-op",
        )
        self.assertEqual(
            self.dup.merged_into_id, self.primary.pk,
            "the retired duplicate must point at the surviving link",
        )
        # The survivor is untouched.
        self.primary.refresh_from_db()
        self.assertTrue(self.primary.is_active)
        self.assertIsNone(self.primary.merged_into_id)

    # --- the double-notify harm, through the real recipient builder -------

    def test_retired_duplicate_is_dropped_from_guardian_email_recipients(self):
        """The concrete harm: the parent was emailed twice.

        Exercises the real recipient builder, not a hand-rolled query, so the
        assertion tracks what production actually sends.
        """
        from apps.schoolops.tasks import _resolve_guardian_emails

        before = _resolve_guardian_emails(self.student)
        self.assertIn("primary@example.com", before)
        self.assertIn("dup@example.com", before)

        self._merge(self.primary, self.dup)

        after = _resolve_guardian_emails(self.student)
        self.assertIn("primary@example.com", after)
        self.assertNotIn(
            "dup@example.com", after,
            "the retired duplicate is still an email recipient -- the parent "
            "is notified twice after the merge",
        )

    def test_active_queryset_excludes_retired_but_raw_manager_keeps_it(self):
        self._merge(self.primary, self.dup)
        active_ids = set(
            self.student.guardian_links.active().values_list("pk", flat=True)
        )
        self.assertIn(self.primary.pk, active_ids)
        self.assertNotIn(self.dup.pk, active_ids)
        # The row is retired, never deleted -- audit/history still sees it.
        self.assertEqual(self.student.guardian_links.count(), 2)

    # --- idempotency guard, now that merged_into exists -------------------

    def test_re_merging_an_already_retired_duplicate_is_blocked(self):
        self._merge(self.primary, self.dup)  # self.dup now merged_into=primary
        third_parent = User.objects.create_user(
            username="gm_tomb_third", password="p", role=User.Role.PARENT,
        )
        third = StudentGuardian.objects.create(
            guardian_user=third_parent, student=self.student,
            email="third@example.com", receives_email=True,
        )
        op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.GUARDIAN,
            primary_pk=str(third.pk),
            secondary_pk=str(self.dup.pk),  # already merged into self.primary
        )
        with self.assertRaises(MergeBlockedError) as ctx:
            preview_merge(op)
        self.assertIn("already merged", str(ctx.exception))


class TeacherMergeIdempotencyGuardCanNowFireTests(TestCase):
    """The teacher guard was equally dead -- TeacherProfile had no merged_into."""

    def setUp(self):
        self.school = School.objects.create(
            name="Teach High", slug="gm-teach", subdomain="gm-teach"
        )

    def _teacher(self, username: str) -> TeacherProfile:
        return TeacherProfile.objects.create(
            user=User.objects.create_user(
                username=username, password="p", role=User.Role.TEACHER,
            ),
            school=self.school,
        )

    def test_teacherprofile_has_merged_into(self):
        names = {f.name for f in TeacherProfile._meta.get_fields()}
        self.assertIn(
            "merged_into", names,
            "without merged_into the merge idempotency guard can never fire "
            "for teachers",
        )

    def test_re_merging_an_already_merged_teacher_is_blocked(self):
        survivor = self._teacher("gm_teach_survivor")
        retired = self._teacher("gm_teach_retired")
        # Simulate a prior merge having tombstoned `retired`.
        retired.merged_into = survivor
        retired.is_active = False
        retired.save(update_fields=["merged_into", "is_active"])

        third = self._teacher("gm_teach_third")
        op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.TEACHER,
            primary_pk=str(third.pk),
            secondary_pk=str(retired.pk),
        )
        with self.assertRaises(MergeBlockedError) as ctx:
            preview_merge(op)
        self.assertIn("already merged", str(ctx.exception))
