"""End-to-end: run one school year from setup to rollover, then start the next.

Lane D of the pre-go-live audit built an eight-phase driver script for this arc
and never ran it -- the suite could not create a database (see
config/settings_test and the TEST MIRROR fix). A driver script proves the arc
once, on one operator's machine, against whatever the dev database happened to
hold. This is the same arc as a test: it runs on every push, builds its own
school, and fails when a step in the chain stops working.

The arc, in the order a head teacher lives it:

  1. set the year up          terms, classrooms, subjects, assignments, roll
  2. teach                    attendance + marks against a subject assignment
  3. govern the marks         grade approval requests reach APPROVED
  4. publish                  TermPublishStatus for the whole school
  5. bill                     invoices raised, one paid, one left owing
  6. close the year           the blocker scorecard actually clears
  7. roll over                clone structure into the next year
  8. carry the debt forward   arrears become an opening balance next year

Each phase asserts the thing the NEXT phase depends on, so a break is reported
where it happens rather than as a mystery at the end.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    ClassroomPromotionMapping,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.services_year_setup import clone_academic_year
from apps.academics.year_close import (
    evaluate_year_close_blockers,
    execute_year_close,
)
from apps.accounts.models import User
from apps.evals.models import Evaluation, GradeApprovalRequest
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)
from apps.finance.services import carry_forward_arrears, recalculate_invoice
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.models import PromotionRule, TermPublishStatus
from apps.reports.services import grade_approval_publish_readiness
from apps.schools.models import School, SchoolMembership

TERM_NAMES = ["Term 1", "Term 2", "Term 3"]


class SchoolYearEndToEndJourneyTests(TestCase):
    """One school, one full year, then the next one."""

    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.uid = uid
        cls.school = School.objects.create(
            name="Journey College " + uid,
            slug="jc-" + uid,
            subdomain="jc" + uid,
            is_active=True,
        )
        cls.head = User.objects.create_superuser(
            username="jc_head_" + uid,
            email="head" + uid + "@example.test",
            password="Test1234!x",
        )
        SchoolMembership.objects.create(
            user=cls.head, school=cls.school, role="ADMIN", is_primary=True
        )
        cls.teacher_user = User.objects.create_user(
            username="jc_teacher_" + uid, password="Test1234!x"
        )
        cls.teacher = TeacherProfile.objects.create(user=cls.teacher_user)
        # ComplianceProfile carries no school column -- it is COUNTRY scoped.
        cls.profile = ComplianceProfile.objects.create(
            name="CM " + uid, country_code="CM"
        )

    # -- helpers ---------------------------------------------------------

    def _build_year(self, name, start_year):
        year = AcademicYear.objects.create(
            school=self.school,
            name=name,
            start_date=dt.date(start_year, 9, 1),
            end_date=dt.date(start_year + 1, 6, 30),
            is_active=False,
        )
        for i, tname in enumerate(TERM_NAMES, start=1):
            Term.objects.create(
                school=self.school,
                academic_year=year,
                name=tname,
                start_date=dt.date(start_year, 9, 1) + dt.timedelta(days=100 * (i - 1)),
                end_date=dt.date(start_year, 9, 1) + dt.timedelta(days=100 * i - 10),
            )
        return year

    def _invoice(self, student, year, amount, ref_suffix):
        inv = Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            academic_year=year,
            student=student,
            reference="INV-" + self.uid + "-" + ref_suffix,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=dt.date(2026, 10, 1),
            due_date=dt.date(2026, 10, 31),
            total_amount=Decimal(amount),
        )
        InvoiceLine.objects.create(
            invoice=inv,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal(amount),
            amount=Decimal(amount),
        )
        return inv

    # -- the journey -----------------------------------------------------

    def test_full_year_journey_start_to_finish_and_rollover(self):
        # ---------- 1. SET THE YEAR UP ----------
        year1 = self._build_year("2026/2027", 2026)
        terms = list(Term.objects.filter(academic_year=year1).order_by("start_date"))
        self.assertEqual(
            len(terms), 3, "a year needs its three terms before anything else"
        )

        dept = Department.objects.create(
            name="Sciences " + self.uid, code="SCI" + self.uid[:5], school=self.school
        )
        specialty = Specialty.objects.create(
            school=self.school,
            department=dept,
            name="General",
            code="GEN" + self.uid[:5],
        )
        classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year1,
            department=dept,
            name="Form 5A",
            code="F5A" + self.uid[:5],
        )
        subject = Subject.objects.create(
            school=self.school, name="Mathematics", code="MTH" + self.uid[:5]
        )
        assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=year1,
            term=terms[0],
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=Decimal("4.00"),
        )
        students = [
            StudentProfile.objects.create(
                school=self.school,
                first_name=name,
                last_name="Journey",
                date_of_birth="2011-05-05",
                student_code="STD" + self.uid + str(i),
                academic_year=year1,
                classroom=classroom,
                specialty=specialty,
            )
            for i, name in enumerate(["Ada", "Bih", "Che"])
        ]
        self.assertEqual(
            StudentProfile.objects.filter(classroom=classroom).count(),
            3,
            "roll must be populated before a teacher can mark it",
        )

        # ---------- 2. TEACH ----------
        for s in students:
            Attendance.objects.create(
                school=self.school,
                student=s,
                classroom=classroom,
                date=dt.date(2026, 9, 15),
                status=Attendance.Status.PRESENT,
            )
        self.assertEqual(Attendance.objects.filter(classroom=classroom).count(), 3)

        # Marks: two comfortably passing, one clearly failing, so promotion has
        # something real to decide.
        scores = [Decimal("15.00"), Decimal("12.00"), Decimal("4.00")]
        for s, score in zip(students, scores):
            Evaluation.objects.create(
                school=self.school,
                academic_year=year1,
                term=terms[0],
                subject_assignment=assignment,
                student=s,
                teacher=self.teacher,
                seq1_score=score,
            )
        self.assertEqual(
            Evaluation.objects.filter(subject_assignment=assignment).count(), 3
        )

        # ---------- 3. GOVERN THE MARKS ----------
        # A term with evaluations but no approval record is NOT publishable --
        # that is the governance contract, so assert the refusal before the pass.
        pre = grade_approval_publish_readiness(year1.pk, terms[0].pk)
        self.assertFalse(
            pre["ready_for_publish"],
            "marks with no approval record must not be publishable",
        )
        self.assertEqual(pre["missing_count"], 1)

        GradeApprovalRequest.objects.create(
            teacher=self.teacher,
            academic_year=year1,
            term=terms[0],
            subject_assignment=assignment,
            status=GradeApprovalRequest.Status.APPROVED,
            requested_by=self.teacher_user,
            reviewed_by=self.head,
            reviewed_at=timezone.now(),
        )
        post = grade_approval_publish_readiness(year1.pk, terms[0].pk)
        self.assertTrue(
            post["ready_for_publish"],
            "approved marks must become publishable, got " + repr(post),
        )

        # ---------- 4. PUBLISH ----------
        # Negative control, and the reason phase 6 means anything. Before the
        # terms are published the close scorecard must REFUSE. Without this the
        # later assertEqual(scorecard["ok"], True) would also pass against a
        # scorecard that had stopped checking -- a gate that cannot fail is not
        # a gate.
        year2 = self._build_year("2027/2028", 2027)
        unready = evaluate_year_close_blockers(self.school, year1, year2)
        self.assertFalse(
            unready["ok"], "an unpublished year must not be closeable"
        )
        self.assertIn(
            "terms_unpublished",
            [b["code"] for b in unready["blockers"]],
            "the refusal must name the unpublished terms, not fail for some "
            "unrelated reason: " + repr(unready["blockers"]),
        )
        self.assertEqual(unready["counts"]["unpublished_terms"], 3)

        for t in terms:
            TermPublishStatus.objects.create(
                academic_year=year1,
                term=t,
                classroom=None,
                is_published=True,
                published_at=timezone.now(),
                published_by=self.head,
            )
        self.assertEqual(
            TermPublishStatus.objects.filter(
                academic_year=year1, is_published=True
            ).count(),
            3,
        )

        # ---------- 5. BILL ----------
        paid = self._invoice(students[0], year1, "50000.00", "paid")
        Payment.objects.create(
            school=self.school,
            invoice=paid,
            student=students[0],
            reference_number="PAY-" + self.uid + "-1",
            amount=Decimal("50000.00"),
            method=PaymentMethodCode.CASH,
        )
        owing = self._invoice(students[1], year1, "50000.00", "owing")
        recalculate_invoice(paid)
        recalculate_invoice(owing)
        paid.refresh_from_db()
        owing.refresh_from_db()
        self.assertEqual(
            paid.computed_balance,
            Decimal("0.00"),
            "a fully paid invoice must show no balance",
        )
        self.assertGreater(
            owing.computed_balance,
            Decimal("0.00"),
            "an unpaid invoice must still show a balance -- phase 8 depends on it",
        )

        # ---------- 6. CLOSE THE YEAR ----------
        scorecard = evaluate_year_close_blockers(self.school, year1, year2)
        self.assertTrue(
            scorecard["ok"],
            "a fully published, fully approved year must clear the close "
            "scorecard; blockers="
            + repr([b["code"] for b in scorecard["blockers"]]),
        )

        dry = execute_year_close(self.school, year1, year2, dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dry_run"], "dry_run=True must not write")
        year1.refresh_from_db()
        self.assertFalse(
            year1.is_locked, "a dry run must leave the source year unlocked"
        )

        # ---------- 7. ROLL OVER ----------
        PromotionRule.objects.create(
            academic_year=year1, classroom=None, promotion_average=Decimal("10.00")
        )
        stats = clone_academic_year(year1, year2)
        self.assertGreater(
            stats["classrooms_created"], 0, "rollover must carry classrooms forward"
        )
        self.assertGreater(
            stats["subject_assignments_created"],
            0,
            "rollover must carry the teaching structure forward",
        )
        cloned = Classroom.objects.filter(academic_year=year2)
        self.assertTrue(cloned.exists())
        for c in cloned:
            self.assertEqual(
                c.school_id,
                self.school.pk,
                "every cloned row must be stamped with the owning school",
            )
            self.assertLessEqual(
                len(c.code),
                30,
                "cloned classroom code " + repr(c.code) + " overflows max_length",
            )

        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=year1,
            source_classroom=classroom,
            target_year=year2,
            target_classroom=cloned.first(),
        )
        self.assertEqual(
            ClassroomPromotionMapping.objects.filter(
                source_year=year1, target_year=year2
            ).count(),
            1,
            "auto-promotion returns early when no mapping exists",
        )

        # ---------- 8. CARRY THE DEBT FORWARD ----------
        created = carry_forward_arrears(year1, year2)
        self.assertEqual(
            created, 1, "exactly the one student who still owes gets an opening balance"
        )
        arrears = Invoice.objects.get(
            academic_year=year2, student=students[1], reference__startswith="ARREARS-"
        )
        self.assertEqual(arrears.total_amount, Decimal("50000.00"))
        self.assertEqual(
            arrears.school_id,
            self.school.pk,
            "an arrears invoice must belong to the school that raised the debt",
        )
        self.assertFalse(
            Invoice.objects.filter(
                academic_year=year2,
                student=students[0],
                reference__startswith="ARREARS-",
            ).exists(),
            "the student who paid in full must not be billed again",
        )

        # Idempotence: the rollover wizard is re-runnable, so a second pass must
        # not double-bill a family.
        again = carry_forward_arrears(year1, year2)
        self.assertEqual(again, 0, "re-running rollover must not duplicate arrears")
        self.assertEqual(
            Invoice.objects.filter(
                academic_year=year2, reference__startswith="ARREARS-"
            ).count(),
            1,
        )
