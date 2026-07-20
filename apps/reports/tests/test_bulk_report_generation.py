"""A school must be able to produce a class's report cards without 200 parents clicking.

Before this, the only three sites that created a ``ReportCard`` were the two
parent-download views and the e2e seed helper — so a seeded 200-student term had
3 report cards. These lock the bulk verb's contract: it honours the same gates,
reports WHY each student was skipped, stamps ``school`` (a NULL there 404s
tenant-scoped QR verification), writes the hash ledger, and is idempotent.

The scoping test is the load-bearing one: the per-row ``school`` FK is nullable
and routinely NULL under schema-per-tenant, so a bare ``filter(school=school)``
silently drops almost the whole roll — it matched 1 student of 20 on the real
Buea tenant, which reads as "small class", not "scoping bug".
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

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
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.bulk_generation import (
    SKIP_FEE_BLOCKED,
    SKIP_NO_MARKS,
    generate_term_report_cards,
)
from apps.reports.models import ReportCard, TermPublishStatus
from apps.schools.models import School

_PDF = b"%PDF-1.4 bulk-test"


def _render(request, template_name, context):
    return _PDF


class BulkReportGenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Buea Bulk School",
            slug="buea-bulk-school",
            subdomain="buea-bulk-school",
            country_code="CM",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school, name="General", code="GEN-BULK"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=dept, name="General", code="GENSPEC-BULK"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 1",
            code="F1-BULK",
        )
        subject = Subject.objects.create(school=cls.school, name="Mathematics")
        cls.assignment = SubjectAssignment.objects.create(
            school=cls.school,
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=subject,
            coefficient=1,
        )
        teacher_user = User.objects.create_user(
            username="bulk_teacher", password="x", role=User.Role.TEACHER
        )
        cls.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=cls.school
        )
        AssessmentWeights.objects.create(
            school=cls.school, academic_year=cls.year, score_scale=20
        )
        TermPublishStatus.objects.create(
            academic_year=cls.year, term=cls.term, classroom=None, is_published=True
        )
        # Two students WITH marks; the second deliberately carries school=NULL,
        # which is the seeded shape under schema-per-tenant.
        cls.marked = cls._student("BULK-1", school=cls.school)
        cls.marked_null_school = cls._student("BULK-2", school=None)
        for student in (cls.marked, cls.marked_null_school):
            Evaluation.objects.create(
                school=cls.school,
                academic_year=cls.year,
                term=cls.term,
                subject_assignment=cls.assignment,
                student=student,
                teacher=cls.teacher,
                seq1_score=Decimal("14.00"),
                seq2_score=Decimal("15.00"),
                exam_score=Decimal("16.00"),
            )
        # One student with no marks at all.
        cls.unmarked = cls._student("BULK-3", school=cls.school)

    @classmethod
    def _student(cls, code, *, school):
        return StudentProfile.objects.create(
            school=school,
            first_name="Ndi",
            last_name=code,
            student_code=code,
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=cls.specialty,
            is_active=True,
        )

    def _run(self, **kw):
        kw.setdefault("pdf_renderer", _render)
        return generate_term_report_cards(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            **kw,
        ).as_dict()

    def test_includes_students_whose_school_fk_is_null(self):
        """The scoping bug: a bare filter(school=...) drops the seeded roll."""
        result = self._run()
        seen = {d["student_code"] for d in result["details"]}
        self.assertIn("BULK-2", seen, "NULL-school student vanished from the run")
        self.assertEqual(result["students"], 3)

    def test_generates_for_marked_students_and_stamps_school(self):
        result = self._run()
        self.assertEqual(result["generated"], 2, result["reasons"])
        cards = ReportCard.objects.filter(term=self.term)
        self.assertEqual(cards.count(), 2)
        self.assertEqual(
            cards.filter(school__isnull=True).count(),
            0,
            "a NULL school 404s tenant-scoped QR verification",
        )

    def test_unmarked_student_is_skipped_not_issued_a_blank_card(self):
        result = self._run()
        self.assertEqual(result["reasons"].get(SKIP_NO_MARKS), 1)
        self.assertFalse(
            ReportCard.objects.filter(student=self.unmarked).exists(),
            "issued a report card with no subjects on it",
        )

    def test_dry_run_writes_nothing_but_still_reports(self):
        result = self._run(dry_run=True)
        self.assertEqual(result["generated"], 2)
        self.assertEqual(ReportCard.objects.count(), 0)

    def test_is_idempotent(self):
        self._run()
        first = ReportCard.objects.count()
        again = self._run()
        self.assertEqual(ReportCard.objects.count(), first)
        statuses = {d["status"] for d in again["details"] if d["status"] != "skipped"}
        self.assertNotIn("created", statuses)

    def test_unpublished_term_is_skipped_unless_overridden(self):
        TermPublishStatus.objects.all().delete()
        blocked = self._run()
        self.assertEqual(blocked["generated"], 0)
        forced = self._run(enforce_publish=False)
        self.assertEqual(forced["generated"], 2)

    def test_fee_blocked_students_are_reported_with_an_actionable_reason(self):
        from apps.finance.models import ComplianceProfile, Invoice

        profile = ComplianceProfile.objects.create(
            name="Bulk Fee", country_code="CM", currency_code="XAF"
        )
        Invoice.objects.create(
            profile=profile,
            school=self.school,
            academic_year=self.year,
            student=self.marked,
            reference="INV-BULK-1",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=date(2025, 9, 5),
            due_date=date(2025, 10, 5),
            total_amount=Decimal("165000.00"),
            balance_amount=Decimal("165000.00"),
        )
        result = self._run()
        self.assertEqual(result["reasons"].get(SKIP_FEE_BLOCKED), 1)
        note = next(
            d["note"] for d in result["details"] if d["reason"] == SKIP_FEE_BLOCKED
        )
        self.assertIn("165000.00", note)

        # ...and the school can still archive them deliberately.
        forced = self._run(enforce_fee_clearance=False)
        self.assertEqual(forced["generated"], 2)

    def test_one_bad_student_does_not_abandon_the_rest(self):
        def _boom(request, template_name, context):
            if context.get("student") is self.marked:
                raise RuntimeError("render exploded")
            return _PDF

        result = self._run(pdf_renderer=_boom)
        self.assertGreaterEqual(result["generated"] + result["skipped"], 3)
        self.assertEqual(result["students"], 3)
