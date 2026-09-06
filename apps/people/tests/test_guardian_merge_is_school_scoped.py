"""A guardian-link merge must refuse to cross a school boundary.

Found by an A-Z audit follow-up (2026-07-16).

``merge_service._resolve_pair`` guards every merge with what looks like a
same-school check::

    row_school_id = getattr(row, "school_id", None)
    if row_school_id is not None and str(row_school_id) != str(op.school_id):
        raise MergeBlockedError("... merge is same-school only ...")

``StudentGuardian`` has NO ``school`` field -- it is scoped only transitively,
through ``student -> StudentProfile.school``. So ``getattr(row, "school_id",
None)`` returns ``None`` for every guardian row, ``is not None`` is False, and
the guard is skipped entirely. The rows themselves are loaded by pk through
``_default_manager`` (unscoped), and ``portal/views_merge.py`` derives
``op.school`` from the PRIMARY alone -- so nothing anywhere compares the
secondary's school to the primary's.

The existing ``test_cross_school_refused`` covers ``Kind.STUDENT``, which is
exactly the kind where the guard *does* work (``StudentProfile.school`` is a
real field). ``Kind.GUARDIAN`` was never exercised. The suite certified the
guard on the one shape that could not fail it.

ROOT CAUSE, and the reason the fix is a map rather than another ``getattr``:
soft-probing for a field that only one of the three kinds has degrades
silently to NO GUARD. A check that cannot answer must refuse, not wave the
merge through. ``_KIND_SCHOOL_PATHS`` states each kind's path to its owning
school explicitly, and an unresolvable row is blocked.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.people.merge_service import (
    _KIND_SCHOOL_PATHS,
    MergeBlockedError,
    apply_merge,
    preview_merge,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.people.models_merge import RecordMergeOperation
from apps.schools.models import School

User = get_user_model()


class GuardianMergeSchoolScopeTests(TestCase):
    """The guard must hold for the kind that has no ``school`` field."""

    def setUp(self):
        self.school_a = School.objects.create(
            name="Alpha High", slug="gm-alpha", subdomain="gm-alpha"
        )
        self.school_b = School.objects.create(
            name="Beta High", slug="gm-beta", subdomain="gm-beta"
        )
        self.student_a = StudentProfile.objects.create(
            school=self.school_a, first_name="Ama", last_name="A",
            student_code="GM-A-1",
        )
        self.student_b = StudentProfile.objects.create(
            school=self.school_b, first_name="Ben", last_name="B",
            student_code="GM-B-1",
        )
        self.parent_a = User.objects.create_user(
            username="gm_parent_a", password="pass123", role=User.Role.PARENT,
        )
        self.parent_b = User.objects.create_user(
            username="gm_parent_b", password="pass123", role=User.Role.PARENT,
        )
        # One guardian link in each school. Same human, two accounts -- the
        # duplicate an operator would plausibly try to merge.
        self.link_a = StudentGuardian.objects.create(
            guardian_user=self.parent_a, student=self.student_a,
            phone="+237600000001",
        )
        self.link_b = StudentGuardian.objects.create(
            guardian_user=self.parent_b, student=self.student_b,
            phone="+237600000002",
        )

    def _cross_school_op(self):
        return RecordMergeOperation.objects.create(
            school=self.school_a,
            kind=RecordMergeOperation.Kind.GUARDIAN,
            primary_pk=str(self.link_a.pk),
            secondary_pk=str(self.link_b.pk),  # <- belongs to School B
        )

    def test_studentguardian_now_has_a_school_field_and_the_path_still_ignores_it(self):
        """The canary fired; this is the answer, and the answer is "keep going".

        StudentGuardian gained its own ``school`` FK (people/0075, for the edge
        sync rail, which scopes every entity by school and could not carry a
        link row that had none). The canary asked for the transitive
        student->school path to be revisited. It was, and it stays -- because
        the row's own column is the WEAKER of the two answers.

        ``StudentGuardian.save()`` fills ``school_id`` only ``if self.student_id
        and not self.school_id``: it fills a blank and never corrects a value.
        So a row written with an explicit school -- a sync apply, a bulk_create,
        a queryset update -- keeps that school even when the student it points
        at belongs to a different one. Reading the guard off that column would
        let a wrong or stale stamp answer a question about a child, whereas
        ``student.school_id`` asks the record that actually owns the child.

        The test below proves the distinction is not theoretical.
        """
        names = {f.name for f in StudentGuardian._meta.get_fields()}
        self.assertIn("school", names, "premise changed again -- re-read this test")
        self.assertEqual(
            _KIND_SCHOOL_PATHS["guardian"], ("student", "school_id"),
            "the guardian path must resolve through the STUDENT, not through the "
            "link row's own school column",
        )

    def test_a_stale_school_stamp_cannot_talk_the_guard_across_the_boundary(self):
        """A row whose own school disagrees with its student's is still refused.

        Written with a queryset update precisely because ``save()`` would not
        produce this state -- and neither would a careful caller. A sync apply
        or a hand-repaired row can, and the guard must not believe it.
        """
        StudentGuardian.objects.filter(pk=self.link_b.pk).update(  # tenant-isolation-allow: test-fixture-forges-a-mismatched-stamp
            school=self.school_a
        )
        self.link_b.refresh_from_db()
        self.assertEqual(self.link_b.school_id, self.school_a.pk)
        self.assertNotEqual(self.link_b.student.school_id, self.school_a.pk)

        op = self._cross_school_op()
        with self.assertRaises(MergeBlockedError) as ctx:
            preview_merge(op)
        self.assertIn("different school", str(ctx.exception))

    def test_preview_refuses_a_cross_school_guardian_merge(self):
        op = self._cross_school_op()
        with self.assertRaises(MergeBlockedError) as ctx:
            preview_merge(op)
        self.assertIn("different school", str(ctx.exception))

    def test_apply_refuses_a_cross_school_guardian_merge(self):
        """The hole, at the step that actually re-points the rows.

        The FSM is forced to APPROVED with a queryset update rather than via
        ``approve_merge``: the guard under test blocks the legitimate route to
        APPROVED, so driving the FSM normally would make this test pass on the
        precondition error (``operation must be approved``) without ever
        reaching the school check. The assertion pins the *reason*, so an
        unrelated MergeBlockedError cannot green it either.
        """
        op = self._cross_school_op()
        RecordMergeOperation.objects.filter(pk=op.pk).update(  # tenant-isolation-allow: test-fixture-forces-fsm-state-by-pk
            status=RecordMergeOperation.Status.APPROVED
        )
        op.refresh_from_db()
        with self.assertRaises(MergeBlockedError) as ctx:
            apply_merge(op, actor=None)
        self.assertIn(
            "different school", str(ctx.exception),
            "apply must refuse on the school boundary, not on some other guard",
        )
        # The two FKs the walker would have re-pointed are both financial:
        # finance.invoicepayershare.guardian + finance.referralreward.guardian.
        self.link_b.refresh_from_db()
        self.assertEqual(
            self.link_b.student_id, self.student_b.pk,
            "School B's guardian link was absorbed into School A",
        )

    def test_same_school_guardian_merge_still_previews(self):
        """The guard must not break the legitimate same-school case."""
        second_parent = User.objects.create_user(
            username="gm_parent_a2", password="pass123", role=User.Role.PARENT,
        )
        dup_link = StudentGuardian.objects.create(
            guardian_user=second_parent, student=self.student_a,
            phone="+237600000003",
        )
        op = RecordMergeOperation.objects.create(
            school=self.school_a,
            kind=RecordMergeOperation.Kind.GUARDIAN,
            primary_pk=str(self.link_a.pk),
            secondary_pk=str(dup_link.pk),
        )
        preview = preview_merge(op)
        self.assertIn("repoint", preview)
        op.refresh_from_db()
        self.assertEqual(op.status, RecordMergeOperation.Status.PREVIEWED)


class StudentAndTeacherMergeGuardsUnchangedTests(TestCase):
    """The kinds that already worked must keep working."""

    def setUp(self):
        self.school_a = School.objects.create(
            name="Gamma High", slug="gm-gamma", subdomain="gm-gamma"
        )
        self.school_b = School.objects.create(
            name="Delta High", slug="gm-delta", subdomain="gm-delta"
        )

    def test_cross_school_student_merge_still_refused(self):
        primary = StudentProfile.objects.create(
            school=self.school_a, first_name="P", last_name="One",
            student_code="GM-G-1",
        )
        stranger = StudentProfile.objects.create(
            school=self.school_b, first_name="S", last_name="Two",
            student_code="GM-D-1",
        )
        op = RecordMergeOperation.objects.create(
            school=self.school_a,
            kind=RecordMergeOperation.Kind.STUDENT,
            primary_pk=str(primary.pk),
            secondary_pk=str(stranger.pk),
        )
        with self.assertRaises(MergeBlockedError):
            preview_merge(op)
