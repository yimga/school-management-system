"""Eligibility resolver — the four-predicate gate + status derivation.

``resolve_eligibility`` computes academic / attendance / medical / consent and
derives ELIGIBLE (all four) / PROVISIONAL (academic+attendance ok, consent or
medical pending) / INELIGIBLE (an academic or attendance FLOOR breached). No
academic/attendance data on record is NOT adverse (returns True with a note).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import Subject, SubjectAssignment
from apps.athletics.models import (
    EligibilityRecord,
    MedicalClearance,
    ParticipationConsent,
    TeamMembership,
)
from apps.athletics.services.eligibility import resolve_eligibility
from apps.athletics.tests.base import AthleticsFixtureMixin, BaseAthleticsTestCase
from apps.evals.grading_provisioning import resolve_school_score_scale
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile


class EligibilityResolverTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)

    def _consent(self):
        """Mint + record a CONSENTED participation consent for the membership."""
        raw, consent = ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent.",
        )
        consent.consent()
        return consent

    def test_all_four_pass_is_eligible(self):
        self.make_evaluation(self.fx, exam_score=80)
        self.make_attendance(self.fx, present=3, absent=1)  # 75% -> meets floor
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.eligible)
        self.assertEqual(outcome.status, EligibilityRecord.Status.ELIGIBLE)

    def test_consent_missing_is_not_eligible(self):
        self.make_evaluation(self.fx, exam_score=80)
        self.make_attendance(self.fx, present=4, absent=0)
        self.make_clearance(self.fx)
        # No consent recorded.
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.eligible)
        self.assertEqual(outcome.status, EligibilityRecord.Status.PROVISIONAL)
        self.assertFalse(outcome.record.consent_ok)

    def test_medical_missing_is_not_eligible(self):
        self.make_evaluation(self.fx, exam_score=80)
        self.make_attendance(self.fx, present=4, absent=0)
        self._consent()
        # No medical clearance.
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.eligible)
        self.assertEqual(outcome.status, EligibilityRecord.Status.PROVISIONAL)
        self.assertFalse(outcome.record.medical_ok)

    def test_no_academic_or_attendance_data_is_not_adverse(self):
        # With medical + consent present and NO evals / NO attendance, the two
        # data-absent predicates return True, so the athlete is ELIGIBLE.
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.academic_ok)
        self.assertTrue(outcome.record.attendance_ok)
        self.assertTrue(outcome.eligible)
        self.assertEqual(outcome.status, EligibilityRecord.Status.ELIGIBLE)

    def test_provisional_when_only_consent_and_medical_missing(self):
        # No academic/attendance data (both True), but no medical + no consent.
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertEqual(outcome.status, EligibilityRecord.Status.PROVISIONAL)
        self.assertFalse(outcome.eligible)
        self.assertFalse(outcome.record.medical_ok)
        self.assertFalse(outcome.record.consent_ok)

    def test_academic_below_floor_is_ineligible(self):
        self.make_evaluation(self.fx, exam_score=30)  # 30 < 50 floor
        self.make_attendance(self.fx, present=4, absent=0)
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertEqual(outcome.status, EligibilityRecord.Status.INELIGIBLE)
        self.assertFalse(outcome.eligible)
        self.assertFalse(outcome.record.academic_ok)

    def test_attendance_below_floor_is_ineligible(self):
        self.make_evaluation(self.fx, exam_score=80)
        self.make_attendance(self.fx, present=2, absent=2)  # 50% < 75 floor
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertEqual(outcome.status, EligibilityRecord.Status.INELIGIBLE)
        self.assertFalse(outcome.eligible)
        self.assertFalse(outcome.record.attendance_ok)

    def test_incomplete_evaluations_are_excluded_from_average(self):
        # One COMPLETE eval at 80 (=80% on /100) plus two INCOMPLETE evals whose
        # exam is ungraded — their total_score computes to 0.0, which pre-fix
        # dragged the mean to ~26.7% and wrongly marked the athlete INELIGIBLE.
        self.make_evaluation(self.fx, exam_score=80)  # fx.assignment: complete
        for i in range(2):
            subject = Subject.objects.create(school=self.fx.school, name=f"Extra{i}-a")
            assignment = SubjectAssignment.objects.create(
                school=self.fx.school, academic_year=self.fx.year, term=self.fx.term,
                classroom=self.fx.classroom, specialty=self.fx.specialty, subject=subject,
            )
            # seq1_score set so "at least one score" passes; exam ungraded ->
            # is_complete_for_ranking is False (exam is the only weighted component).
            Evaluation.objects.create(
                school=self.fx.school, academic_year=self.fx.year, term=self.fx.term,
                subject_assignment=assignment, student=self.fx.student,
                teacher=self.fx.teacher, seq1_score=Decimal("5"),
            )
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.academic_ok)
        self.assertEqual(outcome.status, EligibilityRecord.Status.ELIGIBLE)
        # Only the complete eval (80) counts — the two 0.0 rows are excluded.
        self.assertAlmostEqual(
            float(outcome.record.snapshot["academic_average"]), 80.0, places=1
        )

    def test_academic_exactly_at_floor_is_eligible(self):
        # Boundary: average == MIN_ELIGIBILITY_AVERAGE (50) is eligible (>=).
        self.make_evaluation(self.fx, exam_score=50)
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.academic_ok)
        self.assertTrue(outcome.eligible)

    def test_both_academic_and_attendance_below_floor_ineligible(self):
        self.make_evaluation(self.fx, exam_score=20)  # < 50
        self.make_attendance(self.fx, present=1, absent=3)  # 25% < 75
        self.make_clearance(self.fx)
        self._consent()
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertEqual(outcome.status, EligibilityRecord.Status.INELIGIBLE)
        self.assertFalse(outcome.record.academic_ok)
        self.assertFalse(outcome.record.attendance_ok)

    def test_persist_true_writes_record(self):
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertIsNotNone(outcome.record)
        self.assertTrue(
            EligibilityRecord.objects.filter(pk=outcome.record.pk).exists()
        )

    def test_persist_false_returns_no_record(self):
        outcome = resolve_eligibility(membership=self.membership, persist=False)
        self.assertIsNone(outcome.record)
        self.assertFalse(
            EligibilityRecord.objects.filter(membership=self.membership).exists()
        )


class MedicalValidFromTests(BaseAthleticsTestCase):
    """A CLEARED clearance is only 'current' once its validity window has opened.

    The fix adds ``valid_from`` null-or-<=today to ``_medical_ok``; pre-fix a
    clearance dated to START in the future still satisfied medical.
    """

    def setUp(self):
        super().setUp()
        self.membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)

    def test_future_valid_from_does_not_satisfy_medical(self):
        today = timezone.now().date()
        self.make_clearance(
            self.fx, status=MedicalClearance.Status.CLEARED,
            valid_from=today + timedelta(days=30),
        )
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.record.medical_ok)

    def test_past_valid_from_satisfies_medical(self):
        today = timezone.now().date()
        self.make_clearance(
            self.fx, status=MedicalClearance.Status.CLEARED,
            valid_from=today - timedelta(days=1),
        )
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.medical_ok)

    def test_null_valid_from_satisfies_medical(self):
        self.make_clearance(
            self.fx, status=MedicalClearance.Status.CLEARED, valid_from=None
        )
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.medical_ok)


class AcademicScaleNormalizationTests(AthleticsFixtureMixin, TestCase):
    """Regression for the scale-unaware academic predicate (bug #2 fix).

    ``MIN_ELIGIBILITY_AVERAGE`` (50) is a PERCENTAGE; the raw ``total_score``
    average is on the school's operational scale. On a /20 school a raw average
    of 15 is 75% — ABOVE the floor — even though 15 < 50 in raw points. The
    pre-fix code compared raw-vs-50, so this athlete would have been marked
    INELIGIBLE; the fix normalizes via ``resolve_school_score_scale`` first. This
    class runs on a dedicated /20 school (the base fixture forces /100), so it
    exercises the normalization path the /100 tests cannot.
    """

    def setUp(self):
        super().setUp()
        self.fx = self.build_tenant("s20")
        self._pin_scale_20()

    def _pin_scale_20(self):
        # School operational (default) scale = 20 — do NOT bump to 100.
        updated = AssessmentWeights.objects.filter(
            school=self.fx.school, term=None, classroom=None
        ).update(score_scale=20)
        if not updated:
            AssessmentWeights.objects.create(
                school=self.fx.school, academic_year=self.fx.year,
                term=None, classroom=None, score_scale=20,
            )
        # Classroom compute row weighted 100% on the exam so total_score == exam_score.
        weights, created = AssessmentWeights.objects.get_or_create(
            academic_year=self.fx.year, classroom=self.fx.classroom, term=self.fx.term,
            defaults={
                "school": self.fx.school, "seq1_weight": 0, "seq2_weight": 0,
                "exam_weight": 100, "mock_weight": 0, "practical_weight": 0,
                "score_scale": 20,
            },
        )
        if not created:
            AssessmentWeights.objects.filter(pk=weights.pk).update(
                seq1_weight=0, seq2_weight=0, exam_weight=100,
                mock_weight=0, practical_weight=0, score_scale=20,
            )

    def _student(self, tag):
        return StudentProfile.objects.create(
            school=self.fx.school, first_name="S", last_name=tag,
            admission_number=f"ADM-s20-{tag}", academic_year=self.fx.year,
            classroom=self.fx.classroom, specialty=self.fx.specialty,
        )

    def _athlete(self, tag, exam_score):
        student = self._student(tag)
        membership = self.add_member(
            self.fx, student=student, status=TeamMembership.Status.ACTIVE
        )
        Evaluation.objects.create(
            school=self.fx.school, academic_year=self.fx.year, term=self.fx.term,
            subject_assignment=self.fx.assignment, student=student,
            teacher=self.fx.teacher, exam_score=Decimal(str(exam_score)),
        )
        self.make_clearance(self.fx, student=student)
        _raw, consent = ParticipationConsent.mint(
            membership=membership, guardian_name="Parent",
            guardian_email=f"parent-{tag}@example.com", consent_text="I consent.",
        )
        consent.consent()
        return membership

    def test_school_operational_scale_is_20(self):
        self.assertEqual(int(resolve_school_score_scale(self.fx.school)), 20)

    def test_raw_15_of_20_is_75pct_academic_ok_and_eligible(self):
        # Raw avg 15 < 50 (raw) but 75% >= 50% floor — the pre-fix logic would
        # have marked this INELIGIBLE; normalization makes it ELIGIBLE.
        membership = self._athlete("hi", exam_score=15)
        outcome = resolve_eligibility(membership=membership, persist=True)
        self.assertTrue(outcome.record.academic_ok)
        self.assertEqual(outcome.status, EligibilityRecord.Status.ELIGIBLE)
        self.assertTrue(outcome.eligible)
        self.assertIn("academic_average_pct", outcome.record.snapshot)
        self.assertAlmostEqual(
            float(outcome.record.snapshot["academic_average_pct"]), 75.0, places=1
        )

    def test_raw_8_of_20_is_40pct_academic_not_ok_and_ineligible(self):
        membership = self._athlete("lo", exam_score=8)
        outcome = resolve_eligibility(membership=membership, persist=True)
        self.assertFalse(outcome.record.academic_ok)
        self.assertEqual(outcome.status, EligibilityRecord.Status.INELIGIBLE)
        self.assertAlmostEqual(
            float(outcome.record.snapshot["academic_average_pct"]), 40.0, places=1
        )
