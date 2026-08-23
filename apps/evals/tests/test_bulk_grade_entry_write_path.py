"""Seals for the three holes in the bulk grade-entry workbench.

1. **The write bypassed the model.** ``POST /evals/teacher/marks/bulk/`` ended in
   ``qs.update(**{field: value})`` — the exact pattern apps/evals/README.md
   forbids. The raw score column was written while ``final_score`` /
   ``normalized_value`` stayed frozen at their pre-write values (they are
   recomputed only inside ``Evaluation.save()``), ``full_clean()`` never ran so
   the fail-closed score ceiling in ``Evaluation.clean()`` was skipped, and
   ``post_save`` never fired so no ``GradeAudit`` row — the append-only evidence
   record for a grade dispute — was written for a bulk change. The view also
   never called ``assert_period_writable``, so a hard-closed academic year still
   accepted bulk grade mutation here while the three other evals write paths
   refused it.

2. **The tenant guard was orphaned.** Both the GET and the POST scoped on
   ``request.user.active_school`` — an attribute that exists nowhere in the
   codebase. ``user_school_id`` was therefore unconditionally ``None``, the
   school filter never applied, and the write queryset stayed
   ``Evaluation.objects.filter(pk__in=int_ids)`` with no tenant predicate at
   all, despite the inline comment claiming "bulk update across tenants is never
   legitimate".

3. **The score ceiling was always 20.** ``_resolve_subject_max`` probed
   ``subject_assignment.grading_scale`` / ``.scale``; SubjectAssignment has
   neither field, so the helper always fell through to ``Decimal("20")``. A
   teacher at a percentage school got HTTP 400 ``value_out_of_range`` for 75 and
   the workbench was unusable.

These drive the real view through RequestFactory so ``request.school`` — the
only tenant binding the view may trust — is set explicitly per case, rather than
left to whatever a test host happens to resolve to.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import AssessmentWeights, Evaluation, GradeAudit
from apps.evals.views_bulk_grade_entry import BulkGradeEntryView
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School

_UNSET = object()
URL = "/evals/teacher/marks/bulk/"


class BulkGradeEntryWritePathTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.a = self._tenant("a", score_scale=20)
        self.b = self._tenant("b", score_scale=20)

    # --- fixtures ---------------------------------------------------------

    def _tenant(self, tag: str, *, score_scale: int) -> SimpleNamespace:
        school = School.objects.create(
            name=f"Bulk {tag}", slug=f"bulk-{tag}", subdomain=f"bulk-{tag}"
        )
        year = AcademicYear.objects.create(
            name=f"2025/2026-{tag}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=school,
        )
        term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=year,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            school=school,
        )
        department = Department.objects.create(
            name="Science", code=f"SCI-{tag}", school=school
        )
        specialty = Specialty.objects.create(
            name="General", code=f"GEN-{tag}", department=department, school=school
        )
        classroom = Classroom.objects.create(
            name="Form 1", code=f"F1-{tag}", academic_year=year,
            department=department, school=school,
        )
        subject = Subject.objects.create(name=f"Math {tag}", school=school)
        assignment = SubjectAssignment.objects.create(
            academic_year=year, term=term, classroom=classroom,
            specialty=specialty, subject=subject, coefficient=1, school=school,
        )
        student = StudentProfile.objects.create(
            school=school, first_name="Ada", last_name=tag.upper(),
            student_code=f"BULK-{tag}", academic_year=year,
            classroom=classroom, specialty=specialty,
        )
        teacher = TeacherProfile.objects.create(
            user=User.objects.create_user(
                username=f"bulk_teacher_{tag}", password="p", role=User.Role.TEACHER
            ),
            school=school,
        )
        # Year-level default: read both by AssessmentWeights.get_for (score
        # computation) and by resolve_school_score_scale (the ceiling).
        AssessmentWeights.objects.create(
            school=school, academic_year=year, term=None, classroom=None,
            seq1_weight=30, seq2_weight=30, exam_weight=40,
            mock_weight=0, practical_weight=0, score_scale=score_scale,
        )
        # Seed the two coursework components at mid-scale so the row is legal
        # on ANY of the scales this fixture builds (a 10 would be rejected by
        # Evaluation.clean() on a 4.0 GPA school).
        base = (Decimal(score_scale) / 2).quantize(Decimal("0.01"))
        evaluation = Evaluation.objects.create(
            school=school, academic_year=year, term=term,
            subject_assignment=assignment, student=student, teacher=teacher,
            seq1_score=base, seq2_score=base,
        )
        return SimpleNamespace(
            school=school, year=year, term=term, classroom=classroom,
            assignment=assignment, student=student, teacher=teacher,
            evaluation=evaluation,
        )

    # --- request helpers --------------------------------------------------

    def _post(self, tenant, payload, *, school=_UNSET, user=None):
        request = self.factory.post(
            URL, data=json.dumps(payload), content_type="application/json"
        )
        request.user = user or tenant.teacher.user
        # RequestFactory has no CSRF middleware to stamp a token; the view's
        # csrf_protect would otherwise 403 every POST for the wrong reason.
        request._dont_enforce_csrf_checks = True
        if school is not _UNSET:
            request.school = school
        else:
            request.school = tenant.school
        return BulkGradeEntryView.as_view()(request)

    def _get_context(self, tenant, query, *, school=_UNSET) -> dict:
        """Drive the real GET and return the context it rendered with.

        ``render()`` is intercepted rather than executed: the workbench extends
        portal_base, whose chrome needs middleware this RequestFactory request
        does not run, and the assertions here are about the context the view
        BUILT, not about the HTML.
        """
        request = self.factory.get(URL, data=query)
        request.user = tenant.teacher.user
        request.school = tenant.school if school is _UNSET else school
        with patch(
            "apps.evals.views_bulk_grade_entry.render",
            return_value=HttpResponse("rendered"),
        ) as render_mock:
            response = BulkGradeEntryView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render_mock.call_count, 1, "the GET body never ran")
        return render_mock.call_args[0][2]

    @staticmethod
    def _body(response) -> dict:
        return json.loads(response.content.decode())

    # ================================================================== #
    # 1. the write must go through Evaluation.save()
    # ================================================================== #

    def test_bulk_apply_recomputes_final_score(self) -> None:
        before = self.a.evaluation.final_score
        response = self._post(
            self.a,
            {
                "evaluation_ids": [self.a.evaluation.pk],
                "field": "exam_score",
                "value": "18",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        # Vacuity guard: the request has to have reached and written the row.
        self.assertEqual(self._body(response)["applied"], 1)

        self.a.evaluation.refresh_from_db()
        self.assertEqual(self.a.evaluation.exam_score, Decimal("18.00"))
        self.assertNotEqual(
            self.a.evaluation.final_score,
            before,
            "queryset .update() writes the raw column and leaves final_score "
            "frozen -- rankings, degree audit, EWS and frozen transcripts all "
            "read the stored column",
        )
        # 30/30/40 on 10, 10, 18.
        self.assertEqual(self.a.evaluation.final_score, Decimal("13.20"))

    def test_bulk_apply_writes_a_grade_audit_row(self) -> None:
        before = GradeAudit.objects.filter(evaluation=self.a.evaluation).count()
        response = self._post(
            self.a,
            {
                "evaluation_ids": [self.a.evaluation.pk],
                "field": "exam_score",
                "value": "18",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._body(response)["applied"], 1)
        self.assertEqual(
            GradeAudit.objects.filter(evaluation=self.a.evaluation).count(),
            before + 1,
            "a bulk grade change left no entry in the append-only evidence "
            "record a grade dispute is settled from",
        )

    def test_bulk_apply_refuses_a_hard_closed_year(self) -> None:
        # Control first: the identical request succeeds while the year is open,
        # so a refusal below cannot be the request being malformed.
        payload = {
            "evaluation_ids": [self.a.evaluation.pk],
            "field": "exam_score",
            "value": "18",
        }
        self.assertEqual(self._post(self.a, payload).status_code, 200)

        AcademicYear.objects.filter(pk=self.a.year.pk).update(is_locked=True)
        payload["value"] = "5"
        response = self._post(self.a, payload)
        self.assertEqual(response.status_code, 409, response.content)

        self.a.evaluation.refresh_from_db()
        self.assertEqual(
            self.a.evaluation.exam_score,
            Decimal("18.00"),
            "a hard-closed year still accepted a bulk grade mutation here, "
            "while the three other evals write paths refuse it",
        )

    def test_a_gpa_school_refuses_a_mark_of_18(self) -> None:
        """The over-admit the score ceiling exists to prevent.

        With the ceiling hardcoded at 20 the view waved an 18 through on a 4.0
        GPA scale, and ``.update()`` then bypassed ``Evaluation.clean()`` -- the
        guard that was rewritten specifically to fail closed -- so the mark
        landed in the column silently.
        """
        gpa = self._tenant("gpa", score_scale=4)
        response = self._post(
            gpa,
            {
                "evaluation_ids": [gpa.evaluation.pk],
                "field": "exam_score",
                "value": "18",
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        gpa.evaluation.refresh_from_db()
        self.assertIsNone(
            gpa.evaluation.exam_score,
            "an 18 landed on a 4.0 GPA scale: the view's ceiling was 20 and "
            ".update() skipped full_clean()",
        )

    # ================================================================== #
    # 2. the tenant guard must be real and mandatory
    # ================================================================== #

    def test_bulk_apply_cannot_touch_another_schools_rows(self) -> None:
        response = self._post(
            self.a,
            {
                "evaluation_ids": [self.a.evaluation.pk, self.b.evaluation.pk],
                "field": "exam_score",
                "value": "18",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        # Vacuity guard: without this, "b unchanged" would also pass if the
        # whole request had been rejected.
        self.assertEqual(
            self._body(response)["applied"],
            1,
            "the caller's own row must still be written -- otherwise the "
            "isolation assertion below proves nothing",
        )

        self.b.evaluation.refresh_from_db()
        self.assertIsNone(
            self.b.evaluation.exam_score,
            "a pk from another tenant was written: the guard read "
            "request.user.active_school, which does not exist, so the school "
            "filter never applied",
        )

    def test_bulk_apply_refuses_without_tenant_context(self) -> None:
        response = self._post(
            self.a,
            {
                "evaluation_ids": [self.a.evaluation.pk],
                "field": "exam_score",
                "value": "18",
            },
            school=None,
        )
        self.assertEqual(response.status_code, 403)
        self.a.evaluation.refresh_from_db()
        self.assertIsNone(self.a.evaluation.exam_score)

    def test_get_will_not_load_another_schools_roster(self) -> None:
        context = self._get_context(
            self.a,
            {
                "subject_assignment": str(self.b.assignment.pk),
                "term": str(self.b.term.pk),
            },
        )
        self.assertIsNone(context["subject_assignment"])
        self.assertEqual(context["rows"], [])

    def test_get_loads_the_callers_own_roster(self) -> None:
        """Control for the test above: the same shape must work in-tenant."""
        context = self._get_context(
            self.a,
            {
                "subject_assignment": str(self.a.assignment.pk),
                "term": str(self.a.term.pk),
            },
        )
        self.assertIsNotNone(context["subject_assignment"])
        self.assertEqual(len(context["rows"]), 1)

    # ================================================================== #
    # 3. the score ceiling must be the school's, not a hardcoded 20
    # ================================================================== #

    def test_percentage_school_accepts_a_mark_of_75(self) -> None:
        percent = self._tenant("pct", score_scale=100)
        response = self._post(
            percent,
            {
                "evaluation_ids": [percent.evaluation.pk],
                "field": "exam_score",
                "value": "75",
            },
        )
        self.assertEqual(
            response.status_code,
            200,
            "_resolve_subject_max probed two attributes SubjectAssignment does "
            "not have, so every school was bounded at /20 and the workbench "
            "was unusable at a percentage school",
        )
        percent.evaluation.refresh_from_db()
        self.assertEqual(percent.evaluation.exam_score, Decimal("75.00"))

    def test_twenty_point_school_still_rejects_a_mark_of_75(self) -> None:
        response = self._post(
            self.a,
            {
                "evaluation_ids": [self.a.evaluation.pk],
                "field": "exam_score",
                "value": "75",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._body(response)["error"], "value_out_of_range")
        self.assertEqual(self._body(response)["max"], "20")

    def test_get_renders_the_schools_own_max_score(self) -> None:
        percent = self._tenant("pct2", score_scale=100)
        context = self._get_context(
            percent,
            {
                "subject_assignment": str(percent.assignment.pk),
                "term": str(percent.term.pk),
            },
        )
        self.assertEqual(
            context["max_score"],
            "100",
            "the workbench advertised a 0-20 range at a percentage school",
        )
