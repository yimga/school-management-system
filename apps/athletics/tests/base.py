"""Shared tenant-graph fixture for the athletics test battery.

Builds a complete, school-scoped academic + athletics graph so every module in
the battery can lean on one construction idiom (cloned from
``apps/evals/tests`` + ``apps/migration_cloud/tests/test_landers_fk_resolution``).
Everything is school-scoped; a second tenant is one ``build_tenant("b")`` call
away for the isolation negatives.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.athletics.models import (
    MedicalClearance,
    Season,
    Sport,
    Team,
    TeamMembership,
)
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.school_events.models import EventVenue
from apps.schools.models import School

User = get_user_model()


class AthleticsFixtureMixin:
    """Factory helpers for a full athletics-capable tenant graph."""

    def build_tenant(self, tag: str = "a") -> SimpleNamespace:
        """One school with the academic + athletics scaffold and one student."""
        school = School.objects.create(
            name=f"Athletics {tag.upper()} School",
            slug=f"ath-{tag}",
            subdomain=f"ath-{tag}",
        )
        year = AcademicYear.objects.create(
            school=school,
            name=f"2025/2026-{tag}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        department = Department.objects.create(
            school=school, name="Physical Education", code=f"PE-{tag}"
        )
        specialty = Specialty.objects.create(
            school=school, department=department, name="General", code=f"GEN-{tag}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=department,
            name="Form 4A",
            code=f"F4A-{tag}",
        )
        subject = Subject.objects.create(school=school, name=f"Games-{tag}")
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        teacher_user = User.objects.create_user(
            username=f"coach_{tag}", password="pass123"
        )
        if hasattr(teacher_user, "role"):
            teacher_user.role = User.Role.TEACHER
            teacher_user.save(update_fields=["role"])
        teacher = TeacherProfile.objects.create(user=teacher_user, school=school)
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
        )
        student = StudentProfile.objects.create(
            school=school,
            first_name="Ath",
            last_name=f"Lete{tag}",
            student_code=f"STD-{tag}-1",
            admission_number=f"ADM-{tag}-1",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
        )
        venue = EventVenue.objects.create(
            school=school, name=f"Main Field {tag}", code=f"main-field-{tag}"
        )
        sport = Sport.objects.create(school=school, name="Football", code=f"football-{tag}")
        season = Season.objects.create(
            school=school,
            sport=sport,
            academic_year=year,
            name=f"2025-2026 Fall {tag}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 1, 31),
            status=Season.Status.ACTIVE,
        )
        team = Team.objects.create(
            school=school,
            sport=sport,
            season=season,
            name=f"Senior Boys 1st XI {tag}",
            home_venue=venue,
            status=Team.Status.ACTIVE,
        )
        return SimpleNamespace(
            school=school,
            year=year,
            department=department,
            specialty=specialty,
            classroom=classroom,
            subject=subject,
            term=term,
            teacher_user=teacher_user,
            teacher=teacher,
            assignment=assignment,
            student=student,
            venue=venue,
            sport=sport,
            season=season,
            team=team,
        )

    # -- membership helpers -------------------------------------------------

    def add_member(self, fx, *, student=None, status=TeamMembership.Status.ACTIVE,
                   jersey_number=None, team=None) -> TeamMembership:
        return TeamMembership.objects.create(
            school=fx.school,
            team=team or fx.team,
            student=student or fx.student,
            status=status,
            jersey_number=jersey_number,
        )

    # -- academic / attendance / medical helpers ---------------------------

    def set_weights(self, fx, *, exam_weight=100, score_scale=100) -> AssessmentWeights:
        """Deterministic weights: ``total_score == exam_score`` on a 0-100 scale.

        Two moves are needed. (1) ``Evaluation.clean()`` caps each score at the
        school's operational scale (``resolve_school_score_scale`` reads the
        PROVISIONED school-wide default weights, which the country pack seeds at
        20), so every school-scoped weights row is bumped to 0-100 first. (2) the
        compute path (``AssessmentWeights.get_for(year, classroom, term)``) must
        find a classroom+term row weighted 100% on the exam so ``total_score``
        equals the exam score.
        """
        # (1) permissive score ceiling so exam_score up to 100 validates.
        AssessmentWeights.objects.filter(school=fx.school).update(
            score_scale=score_scale
        )
        # (2) the exact row the compute path resolves.
        weights, created = AssessmentWeights.objects.get_or_create(
            academic_year=fx.year,
            classroom=fx.classroom,
            term=fx.term,
            defaults={
                "school": fx.school,
                "seq1_weight": 0,
                "seq2_weight": 0,
                "exam_weight": exam_weight,
                "mock_weight": 0,
                "practical_weight": 0,
                "score_scale": score_scale,
            },
        )
        if not created:
            AssessmentWeights.objects.filter(pk=weights.pk).update(
                seq1_weight=0, seq2_weight=0, exam_weight=exam_weight,
                mock_weight=0, practical_weight=0, score_scale=score_scale,
            )
        return weights

    def make_evaluation(self, fx, *, exam_score, student=None) -> Evaluation:
        self.set_weights(fx)
        return Evaluation.objects.create(
            school=fx.school,
            academic_year=fx.year,
            term=fx.term,
            subject_assignment=fx.assignment,
            student=student or fx.student,
            teacher=fx.teacher,
            exam_score=Decimal(str(exam_score)),
        )

    def make_attendance(self, fx, *, present, absent, student=None) -> None:
        """Create ``present`` PRESENT + ``absent`` ABSENT records on distinct days."""
        base_day = timezone.now().date() - timedelta(days=5)
        student = student or fx.student
        day = 0
        for _ in range(present):
            Attendance.objects.create(
                school=fx.school,
                student=student,
                classroom=fx.classroom,
                date=base_day - timedelta(days=day),
                status=Attendance.Status.PRESENT,
            )
            day += 1
        for _ in range(absent):
            Attendance.objects.create(
                school=fx.school,
                student=student,
                classroom=fx.classroom,
                date=base_day - timedelta(days=day),
                status=Attendance.Status.ABSENT,
            )
            day += 1

    def make_clearance(self, fx, *, student=None,
                       status=MedicalClearance.Status.CLEARED,
                       valid_from=None, valid_until=None) -> MedicalClearance:
        return MedicalClearance.objects.create(
            school=fx.school,
            student=student or fx.student,
            sport=fx.sport,
            status=status,
            valid_from=valid_from,
            valid_until=valid_until,
            notes="Fit to play. No known conditions.",
        )


class BaseAthleticsTestCase(AthleticsFixtureMixin, TestCase):
    """One tenant graph (``self.fx``) built in setUp for single-tenant cases."""

    def setUp(self):
        super().setUp()
        self.fx = self.build_tenant("a")
