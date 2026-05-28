"""Tests for the at-risk production pipeline commands.

Covers `check_at_risk_drift`, `check_at_risk_calibration`, and
`should_retrain_at_risk`. The drift PSI math is exercised as a pure
function (no DB needed); the calibration and retrain-trigger tests use
SimpleTestCase/TestCase with seeded `RiskFactor` + `AtRiskOutcomeLabel`
rows.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta

try:
    import ortools.sat.python.cp_model  # noqa: F401
    _HAS_ORTOOLS = True
except ImportError:
    _HAS_ORTOOLS = False
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.analytics.management.commands.check_at_risk_drift import (
    _classify,
    _distribution,
    _psi,
)


class PsiMathTests(SimpleTestCase):
    """PSI helpers are pure and Django-independent."""

    def test_identical_distributions_score_zero(self):
        dist = [0.1, 0.2, 0.3, 0.2, 0.1, 0.05, 0.025, 0.025, 0.0, 0.0]
        self.assertAlmostEqual(_psi(dist, dist), 0.0, places=6)

    def test_psi_classifies_correctly(self):
        self.assertEqual(_classify(0.05), "stable")
        self.assertEqual(_classify(0.15), "moderate")
        self.assertEqual(_classify(0.30), "significant")

    def test_distribution_sums_to_one(self):
        scores = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
        dist = _distribution(scores)
        self.assertAlmostEqual(sum(dist), 1.0, places=6)
        self.assertEqual(len(dist), 10)
        # Each bin has exactly one sample → uniform.
        for v in dist:
            self.assertAlmostEqual(v, 0.1, places=6)

    def test_distribution_handles_boundaries(self):
        # 0 → bin 0, 100 → bin 9 (clamped), 50 → bin 5.
        dist = _distribution([0.0, 50.0, 100.0])
        self.assertGreater(dist[0], 0)
        self.assertGreater(dist[5], 0)
        self.assertGreater(dist[9], 0)
        self.assertAlmostEqual(sum(dist), 1.0, places=6)

    def test_shifted_distribution_flags_moderate_or_significant(self):
        ref = [0.5, 0.5, 0, 0, 0, 0, 0, 0, 0, 0]
        moved = [0, 0, 0, 0, 0, 0.5, 0.5, 0, 0, 0]
        self.assertGreater(_psi(ref, moved), 0.25)


class CheckAtRiskDriftCommandTests(TestCase):
    """End-to-end exercise of the drift mgmt command using real RiskFactor rows."""

    def setUp(self):
        from apps.accounts.models import User
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig
        from apps.analytics.models import RiskFactor

        uid = id(self)
        self.region, _ = RegionConfig.objects.get_or_create(
            code=f"D{uid % 10000}",
            defaults={
                "name": "Drift Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"Drift {uid}",
            slug=f"drift-{uid}",
            subdomain=f"drift-{uid}",
            is_active=True,
            default_region=self.region,
        )
        user = User.objects.create_user(
            username=f"drift_student_{uid}",
            email=f"drift_{uid}@example.com",
            password="pwd",
        )
        student = StudentProfile.objects.create(
            school=self.school,
            user=user,
            first_name="Drift",
            last_name="Sample",
            student_code=f"DRF-{uid % 10000}",
        )
        # 50 risk factors spread across bins.
        for i in range(50):
            RiskFactor.objects.create(
                school=self.school,
                student=student,
                score=(i * 2) % 100,  # 0, 2, 4… 98 → covers all bins
                reason_summary="seed",
            )
        self._tmpdir = tempfile.TemporaryDirectory()
        self.artifact = os.path.join(self._tmpdir.name, "model.joblib")
        # Create an empty file so the artifact path resolves.
        with open(self.artifact, "wb") as f:
            f.write(b"placeholder")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_write_reference_then_compare(self):
        # First run: capture reference.
        out = StringIO()
        call_command(
            "check_at_risk_drift",
            "--artifact", self.artifact,
            "--write-reference",
            "--school", self.school.slug,
            stdout=out,
        )
        ref_path = self.artifact + ".distribution.json"
        self.assertTrue(os.path.exists(ref_path))
        ref = json.loads(open(ref_path).read())
        self.assertEqual(len(ref["distribution"]), 10)
        self.assertEqual(ref["sample_size"], 50)

        # Second run: compute PSI — should be near 0 (same data).
        report_path = os.path.join(self._tmpdir.name, "drift.json")
        call_command(
            "check_at_risk_drift",
            "--artifact", self.artifact,
            "--school", self.school.slug,
            "--json", report_path,
            stdout=StringIO(),
        )
        report = json.loads(open(report_path).read())
        self.assertLess(report["psi"], 0.01)
        self.assertEqual(report["classification"], "stable")

    def test_missing_reference_raises(self):
        from django.core.management import CommandError
        with self.assertRaises(CommandError):
            call_command(
                "check_at_risk_drift",
                "--artifact", self.artifact,
                "--school", self.school.slug,
                stdout=StringIO(),
            )


class CheckAtRiskCalibrationCommandTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.academics.models import AcademicYear
        from apps.analytics.models import AtRiskOutcomeLabel, RiskFactor
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"C{uid % 10000}",
            defaults={
                "name": "Cal Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"Cal {uid}",
            slug=f"cal-{uid}",
            subdomain=f"cal-{uid}",
            is_active=True,
            default_region=region,
        )
        self.year = AcademicYear.objects.create(
            name=f"CY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.operator = User.objects.create_user(
            username=f"cal_op_{uid}", email=f"op_{uid}@example.com", password="pwd"
        )
        # Seed 20 students in two prediction bands: 10 in 70-80, 10 in 20-30.
        # In the high band, 8/10 are actually AT_RISK (calibration good).
        # In the low band, 1/10 is AT_RISK (also good).
        # → Per-bin gaps small → ECE small.
        for i in range(20):
            u = User.objects.create_user(
                username=f"cal_s_{uid}_{i}",
                email=f"cal_s_{uid}_{i}@example.com",
                password="pwd",
            )
            student = StudentProfile.objects.create(
                school=self.school,
                user=u,
                first_name=f"S{i}",
                last_name="Student",
                student_code=f"C-{uid % 10000}-{i}",
            )
            high_band = i < 10
            score = 75 if high_band else 25
            RiskFactor.objects.create(
                school=self.school,
                student=student,
                score=score,
                reason_summary="t",
            )
            if high_band:
                label = (
                    AtRiskOutcomeLabel.Label.AT_RISK if i < 8
                    else AtRiskOutcomeLabel.Label.NOT_AT_RISK
                )
            else:
                label = (
                    AtRiskOutcomeLabel.Label.AT_RISK if i == 10
                    else AtRiskOutcomeLabel.Label.NOT_AT_RISK
                )
            AtRiskOutcomeLabel.objects.create(
                school=self.school,
                student=student,
                academic_year=self.year,
                label=label,
                labeled_by=self.operator,
            )

    def test_calibration_report_emitted(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            call_command(
                "check_at_risk_calibration",
                "--school", self.school.slug,
                "--json", tmp.name,
                "--min-samples-per-bin", "3",
                stdout=StringIO(),
            )
            report = json.loads(open(tmp.name).read())
            self.assertEqual(report["labels_total"], 20)
            self.assertEqual(report["joined_to_predictions"], 20)
            # Two non-empty bins, both above min_samples_per_bin.
            counted = [b for b in report["bins"] if b["counted_in_ece"]]
            self.assertEqual(len(counted), 2)
            # ECE should be small (predicted 0.75 vs observed 0.8; 0.25 vs 0.1).
            self.assertLess(report["ece"], 0.20)
        finally:
            os.unlink(tmp.name)

    def test_max_ece_gate_can_fail(self):
        from django.core.management import CommandError
        with self.assertRaises(CommandError):
            call_command(
                "check_at_risk_calibration",
                "--school", self.school.slug,
                "--min-samples-per-bin", "3",
                "--max-ece", "0.001",
                stdout=StringIO(),
            )


class ShouldRetrainAtRiskCommandTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.academics.models import AcademicYear
        from apps.analytics.models import AtRiskOutcomeLabel
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"R{uid % 10000}",
            defaults={
                "name": "Retrain Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"R {uid}",
            slug=f"retrain-{uid}",
            subdomain=f"retrain-{uid}",
            is_active=True,
            default_region=region,
        )
        self.year = AcademicYear.objects.create(
            name=f"RY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.operator = User.objects.create_user(
            username=f"r_op_{uid}", email=f"r_op_{uid}@example.com", password="pwd"
        )
        # 5 labels.
        for i in range(5):
            u = User.objects.create_user(
                username=f"r_s_{uid}_{i}",
                email=f"r_s_{uid}_{i}@example.com",
                password="pwd",
            )
            student = StudentProfile.objects.create(
                school=self.school,
                user=u,
                first_name=f"R{i}",
                last_name="Stud",
                student_code=f"R-{uid % 10000}-{i}",
            )
            AtRiskOutcomeLabel.objects.create(
                school=self.school,
                student=student,
                academic_year=self.year,
                label=AtRiskOutcomeLabel.Label.AT_RISK,
                labeled_by=self.operator,
            )
        self._tmpdir = tempfile.TemporaryDirectory()
        # Recent artifact: mtime = now → age 0 days.
        self.artifact = os.path.join(self._tmpdir.name, "model.joblib")
        with open(self.artifact, "wb") as f:
            f.write(b"x")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_label_threshold_not_crossed(self):
        # 5 labels < threshold 100 → not due → exit 0.
        call_command(
            "should_retrain_at_risk",
            "--artifact", self.artifact,
            "--threshold", "100",
            "--school", self.school.slug,
            stdout=StringIO(),
        )

    def test_label_threshold_crossed_exits_10(self):
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "should_retrain_at_risk",
                "--artifact", self.artifact,
                "--threshold", "3",
                "--school", self.school.slug,
                stdout=StringIO(),
            )
        self.assertEqual(ctx.exception.code, 10)

    def test_max_age_crossed_exits_11(self):
        # Force the artifact to be old by rewriting its mtime to 200 days ago.
        old_ts = (timezone.now() - timedelta(days=200)).timestamp()
        os.utime(self.artifact, (old_ts, old_ts))
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "should_retrain_at_risk",
                "--artifact", self.artifact,
                "--threshold", "999",
                "--max-age-days", "180",
                "--school", self.school.slug,
                stdout=StringIO(),
            )
        self.assertEqual(ctx.exception.code, 11)


@unittest.skipUnless(_HAS_ORTOOLS, "ortools not installed")
class SchedulingSolverConstraintsSmokeTests(TestCase):
    """Smoke test that the expanded CP-SAT model parses and solves a tiny instance."""

    def test_solver_respects_room_capacity_and_availability(self):
        from datetime import time

        from apps.academics.models import (
            AcademicYear,
            Classroom,
            Department,
            Subject,
            SubjectAssignment,
            Term,
        )
        from apps.academics.scheduling import (
            Room,
            TeacherAvailability,
            TimeSlot,
        )
        from apps.academics.scheduling_solver import generate_timetable_with_solver
        from apps.accounts.models import User
        from apps.evals.models import TeacherAssignment, TeacherProfile

        uid = id(self)
        creator = User.objects.create_user(
            username=f"ss_c_{uid}",
            email=f"ss_c_{uid}@example.com",
            password="p",
        )
        teacher_user = User.objects.create_user(
            username=f"ss_t_{uid}",
            email=f"ss_t_{uid}@example.com",
            password="p",
            role=User.Role.TEACHER,
        )
        teacher = TeacherProfile.objects.create(user=teacher_user)
        dept = Department.objects.create(name=f"D-{uid}", code=f"DC{uid % 10000}")
        year = AcademicYear.objects.create(
            name=f"YR-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"T-{uid}",
            academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        classroom = Classroom.objects.create(
            name=f"CR-{uid}", code=f"CRC{uid % 10000}",
            academic_year=year, department=dept,
        )
        subject = Subject.objects.create(name=f"Sub-{uid}")
        sa = SubjectAssignment.objects.create(
            academic_year=year, term=term,
            classroom=classroom, subject=subject,
        )
        TeacherAssignment.objects.create(
            subject_assignment=sa, academic_year=year,
            teacher=teacher, is_active=True,
        )
        # Two rooms — one too small, one big enough.
        Room.objects.create(name=f"R-tiny-{uid}", room_type="CLASSROOM", capacity=5)
        big = Room.objects.create(
            name=f"R-big-{uid}", room_type="CLASSROOM", capacity=200,
        )
        slot_p1 = TimeSlot.objects.create(
            day_of_week=0, start_time=time(9, 0),
            end_time=time(10, 0), slot_name=f"P1-{uid}",
        )
        slot_p2 = TimeSlot.objects.create(
            day_of_week=0, start_time=time(10, 0),
            end_time=time(11, 0), slot_name=f"P2-{uid}",
        )
        # Block teacher on P1.
        TeacherAvailability.objects.create(
            teacher=teacher_user, time_slot=slot_p1, is_available=False,
            preference_level=1,
        )
        TeacherAvailability.objects.create(
            teacher=teacher_user, time_slot=slot_p2, is_available=True,
            preference_level=10,
        )
        schedule = generate_timetable_with_solver(year, term, creator)
        self.assertIsNotNone(schedule)
        entries = list(schedule.entries.all())
        self.assertEqual(len(entries), 1)
        # Must land in the available slot AND the big room.
        self.assertEqual(entries[0].time_slot_id, slot_p2.pk)
        self.assertEqual(entries[0].room_id, big.pk)
