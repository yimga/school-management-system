"""Tests for the two seeder commands shipped post-Wave 10:
`seed_default_digest_recipients` and `seed_grade_prediction_labels_from_history`.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import GradePredictionLabel, RiskDigestRecipient
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = abs(hash(cls.__name__))
        cls.region, _ = RegionConfig.objects.get_or_create(
            code=f"SD{uid % 9999}",
            defaults={
                "name": "SD", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        cls.school = School.objects.create(
            name=f"Sd {uid}", slug=f"sd-{uid}",
            subdomain=f"sd-{uid}", is_active=True,
            default_region=cls.region,
        )


class SeedDigestRecipientsTests(_Base):
    def _admin_user(self, *, username, email, role="ADMIN"):
        """Create a user AND link it to the test school as an admin member.

        The seeder scopes to a school's admins via SchoolMembership (proper
        multi-tenant scoping) — the legacy flat User.role is not enough for it
        to discover the user, so a bare create_user(role=...) is invisible to it.
        """
        from apps.schools.models import SchoolMembership

        user = User.objects.create_user(
            username=username, email=email, password="p", role=role,
        )
        SchoolMembership.objects.create(user=user, school=self.school, role=role)
        return user

    def test_dry_run_does_not_write(self):
        self._admin_user(
            username=f"sd_p_{id(self)}",
            email="principal@example.com", role="PRINCIPAL",
        )
        out = StringIO()
        call_command(
            "seed_default_digest_recipients", "--dry-run",
            stdout=out,
        )
        self.assertIn("Would create", out.getvalue())
        self.assertEqual(RiskDigestRecipient.objects.count(), 0)

    def test_live_run_creates_disabled_rows(self):
        self._admin_user(
            username=f"sd_a_{id(self)}",
            email="admin1@example.com", role="ADMIN",
        )
        call_command("seed_default_digest_recipients", stdout=StringIO())
        rows = RiskDigestRecipient.objects.all()
        self.assertGreater(rows.count(), 0)
        for r in rows:
            # Default is disabled — operator opts each one in.
            self.assertFalse(r.enabled)

    def test_enable_flag_writes_enabled(self):
        self._admin_user(
            username=f"sd_e_{id(self)}",
            email="adminenable@example.com", role="ADMIN",
        )
        call_command("seed_default_digest_recipients", "--enable", stdout=StringIO())
        rows = RiskDigestRecipient.objects.all()
        self.assertGreater(rows.count(), 0)
        for r in rows:
            self.assertTrue(r.enabled)

    def test_idempotent_rerun(self):
        self._admin_user(
            username=f"sd_i_{id(self)}",
            email="adminidem@example.com", role="ADMIN",
        )
        call_command("seed_default_digest_recipients", stdout=StringIO())
        first = RiskDigestRecipient.objects.count()
        self.assertGreater(first, 0)
        out = StringIO()
        call_command("seed_default_digest_recipients", stdout=out)
        self.assertEqual(RiskDigestRecipient.objects.count(), first)
        self.assertIn("skipped", out.getvalue())

    def test_no_email_user_skipped(self):
        self._admin_user(
            username=f"sd_ne_{id(self)}",
            email="", role="ADMIN",
        )
        call_command("seed_default_digest_recipients", stdout=StringIO())
        self.assertEqual(RiskDigestRecipient.objects.count(), 0)


class SeedGradeLabelsTests(_Base):
    def setUp(self):
        from apps.academics.models import (
            AcademicYear, Classroom, Department, Specialty, Subject,
            SubjectAssignment, Term,
        )
        from apps.evals.models import AssessmentWeights

        uid = id(self)
        self.op = User.objects.create_user(
            username=f"sgl_op_{uid}", email="op@example.com", password="p",
        )
        u = User.objects.create_user(
            username=f"sgl_s_{uid}", email="s@example.com", password="p",
        )
        self.dept = Department.objects.create(
            name=f"D-{uid}", code=f"DC{uid % 9999}",
        )
        # `specialty` is now a required PROTECT FK on SubjectAssignment (part of its
        # unique_together), and Evaluation.clean() cross-checks that the student's
        # specialty matches the assignment's — so the student and the assignment
        # must share one specialty, class, and year.
        self.specialty = Specialty.objects.create(
            department=self.dept, name=f"S-{uid}", code=f"SP{uid % 9999}",
        )
        self.year = AcademicYear.objects.create(
            name=f"SGLY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.term = Term.objects.create(
            name=f"SGLT-{uid}", academic_year=self.year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        self.classroom = Classroom.objects.create(
            name=f"CR-{uid}", code=f"CRC{uid % 9999}",
            academic_year=self.year, department=self.dept,
        )
        self.subject = Subject.objects.create(name=f"M-{uid}")
        self.sa = SubjectAssignment.objects.create(
            academic_year=self.year, term=self.term,
            classroom=self.classroom, subject=self.subject,
            specialty=self.specialty,
        )
        self.student = StudentProfile.objects.create(
            school=self.school, user=u,
            first_name="GL", last_name="Stud",
            student_code=f"SGL-{uid % 9999}",
            academic_year=self.year, classroom=self.classroom,
            specialty=self.specialty,
        )
        # Evaluation.save() recomputes final_score from the component scores via the
        # school's AssessmentWeights, and clean() bounds every component by the
        # school's score scale. Bind a /100 percentage scale weighted entirely on
        # the exam component, so a single exam_score flows through unchanged as
        # final_score — the value the seeder reads back as actual_grade.
        AssessmentWeights.objects.create(
            school=self.school, academic_year=self.year,
            term=None, classroom=None,
            seq1_weight=0, seq2_weight=0, exam_weight=100,
            mock_weight=0, practical_weight=0,
            score_scale=100, grading_scale="percentage",
        )

    def _make_evaluation(self, *, exam_score, legacy_final_none=False):
        """Create a saved Evaluation whose computed final_score == exam_score.

        With ``legacy_final_none`` the row's final_score is nulled AFTER save
        (bypassing the recompute) to reproduce a legacy row written before
        final_score was persisted — the only real case where the seeder falls
        back to exam_score.
        """
        from apps.evals.models import Evaluation
        from apps.people.models import TeacherProfile

        teacher_user = User.objects.create_user(
            username=f"sgl_t_{id(self.subject)}_{exam_score}_{legacy_final_none}",
            email="t@example.com", password="p",
        )
        teacher = TeacherProfile.objects.create(user=teacher_user)
        ev = Evaluation.objects.create(
            school=self.school,
            academic_year=self.year, term=self.term,
            subject_assignment=self.sa, student=self.student,
            teacher=teacher,
            exam_score=exam_score,
        )
        if legacy_final_none:
            Evaluation.objects.filter(pk=ev.pk).update(final_score=None)
            ev.refresh_from_db()
        return ev

    def test_seeds_from_final_score(self):
        self._make_evaluation(exam_score=72.5)
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            stdout=StringIO(),
        )
        labels = GradePredictionLabel.objects.filter(
            student=self.student, subject=self.subject,
        )
        self.assertEqual(labels.count(), 1)
        self.assertAlmostEqual(labels.first().actual_grade, 72.5, places=3)

    def test_falls_back_to_exam_score(self):
        self._make_evaluation(exam_score=68.0, legacy_final_none=True)
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            stdout=StringIO(),
        )
        label = GradePredictionLabel.objects.get(student=self.student)
        self.assertAlmostEqual(label.actual_grade, 68.0, places=3)

    def test_skips_when_neither_score(self):
        from apps.evals.models import Evaluation

        ev = self._make_evaluation(exam_score=50.0)
        # clean() forbids SAVING a row with no component score, so reach the
        # "no usable score" state by clearing both the computed final_score and
        # the raw exam_score the seeder reads.
        Evaluation.objects.filter(pk=ev.pk).update(final_score=None, exam_score=None)
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            stdout=StringIO(),
        )
        self.assertEqual(GradePredictionLabel.objects.count(), 0)

    def test_min_score_filter(self):
        self._make_evaluation(exam_score=30.0)
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            "--min-score", "50",
            stdout=StringIO(),
        )
        self.assertEqual(GradePredictionLabel.objects.count(), 0)

    def test_idempotent_via_unique_constraint(self):
        self._make_evaluation(exam_score=82.0)
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            stdout=StringIO(),
        )
        first = GradePredictionLabel.objects.count()
        # Same evaluation → same (student, subject, year, term) → unique constraint hits.
        call_command(
            "seed_grade_prediction_labels_from_history",
            "--labeled-by-username", self.op.username,
            stdout=StringIO(),
        )
        self.assertEqual(GradePredictionLabel.objects.count(), first)

    def test_refuses_unknown_operator(self):
        with self.assertRaises(CommandError):
            call_command(
                "seed_grade_prediction_labels_from_history",
                "--labeled-by-username", "nope_does_not_exist",
                stdout=StringIO(),
            )
