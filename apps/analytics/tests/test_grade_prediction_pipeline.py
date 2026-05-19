"""Wave 7 tests — grade-prediction full suite.

Pipeline-level + math tests; the subprocess training step is excluded
from local tests (same pattern as Wave 1's retrain orchestrator tests).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest.mock as mock
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.management.commands import check_grade_prediction_drift as drift_mod
from apps.analytics.models import (
    GradePrediction,
    GradePredictionLabel,
    GradePredictionModelArtifact,
    GradePredictionShadowComparison,
    GradePredictionShadowRun,
)


class GradeDriftMathTests(SimpleTestCase):
    def test_distribution_sums_to_one(self):
        d = drift_mod._distribution([5, 25, 45, 65, 85])
        self.assertAlmostEqual(sum(d), 1.0, places=6)

    def test_psi_identical_zero(self):
        d = drift_mod._distribution([10, 50, 90])
        self.assertAlmostEqual(drift_mod._psi(d, d), 0.0, places=6)

    def test_classify_bands(self):
        self.assertEqual(drift_mod._classify(0.05), "stable")
        self.assertEqual(drift_mod._classify(0.20), "moderate")
        self.assertEqual(drift_mod._classify(0.30), "significant")


class GradeDriftCommandTests(TestCase):
    def setUp(self):
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        self.region, _ = RegionConfig.objects.get_or_create(
            code=f"GD{uid % 9999}",
            defaults={
                "name": "GD Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"GD {uid}", slug=f"gd-{uid}",
            subdomain=f"gd-{uid}", is_active=True,
            default_region=self.region,
        )
        from apps.academics.models import AcademicYear, Subject, Term
        u = User.objects.create_user(
            username=f"gd_s_{uid}",
            email="s@example.com", password="p",
        )
        student = StudentProfile.objects.create(
            school=self.school, user=u, first_name="GD", last_name="S",
            student_code=f"GD-{uid % 9999}",
        )
        year = AcademicYear.objects.create(
            name=f"GDY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"GDT-{uid}", academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        subj = Subject.objects.create(name=f"M-{uid}")
        for grade in (10, 20, 30, 40, 50, 60, 70, 80, 90, 95):
            GradePrediction.objects.create(
                school=self.school, student=student, subject=subj,
                academic_year=year, term=term, predicted_grade=grade,
            )
        self._tmp = tempfile.TemporaryDirectory()
        self.artifact = os.path.join(self._tmp.name, "g.joblib")
        open(self.artifact, "wb").write(b"placeholder")

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_then_compare(self):
        call_command(
            "check_grade_prediction_drift",
            "--artifact", self.artifact,
            "--write-reference",
            "--school", self.school.slug,
            stdout=StringIO(),
        )
        ref_path = self.artifact + ".grade_distribution.json"
        self.assertTrue(os.path.exists(ref_path))
        report_path = os.path.join(self._tmp.name, "r.json")
        call_command(
            "check_grade_prediction_drift",
            "--artifact", self.artifact,
            "--school", self.school.slug,
            "--json", report_path,
            stdout=StringIO(),
        )
        report = json.loads(open(report_path).read())
        self.assertLess(report["psi"], 0.01)


class GradeCalibrationCommandTests(TestCase):
    def setUp(self):
        from apps.academics.models import AcademicYear, Subject, Term
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"GC{uid % 9999}",
            defaults={
                "name": "GC Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"GC {uid}", slug=f"gc-{uid}",
            subdomain=f"gc-{uid}", is_active=True, default_region=region,
        )
        self.op = User.objects.create_user(
            username=f"gc_op_{uid}", email="o@example.com", password="p",
        )
        year = AcademicYear.objects.create(
            name=f"GCY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"GCT-{uid}", academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        subj = Subject.objects.create(name=f"M-{uid}")
        for i in range(10):
            u = User.objects.create_user(
                username=f"gc_st_{uid}_{i}",
                email=f"st{i}@example.com", password="p",
            )
            stud = StudentProfile.objects.create(
                school=self.school, user=u,
                first_name=f"S{i}", last_name="T",
                student_code=f"GC-{uid % 9999}-{i}",
            )
            pred = 70.0
            actual = 68.0 if i < 5 else 72.0
            GradePrediction.objects.create(
                school=self.school, student=stud, subject=subj,
                academic_year=year, term=term, predicted_grade=pred,
            )
            GradePredictionLabel.objects.create(
                school=self.school, student=stud, subject=subj,
                academic_year=year, term=term,
                actual_grade=actual, labeled_by=self.op,
            )

    def test_calibration_emits_metrics(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            call_command(
                "check_grade_prediction_calibration",
                "--school", self.school.slug,
                "--min-samples-per-bin", "3",
                "--json", tmp.name,
                stdout=StringIO(),
            )
            report = json.loads(open(tmp.name).read())
            # Mean abs error = 2 (all rows off by 2).
            self.assertAlmostEqual(report["overall_mae"], 2.0, delta=0.001)
            self.assertEqual(report["joined"], 10)
            # 1 bin with n=10, counted.
            counted = [b for b in report["bins"] if b["counted"]]
            self.assertEqual(len(counted), 1)
            self.assertEqual(counted[0]["n"], 10)
        finally:
            os.unlink(tmp.name)

    def test_max_overall_mae_gate_fires(self):
        with self.assertRaises(CommandError):
            call_command(
                "check_grade_prediction_calibration",
                "--school", self.school.slug,
                "--min-samples-per-bin", "3",
                "--max-overall-mae", "0.1",
                stdout=StringIO(),
            )


class GradeRegisterPromoteTests(TestCase):
    def test_register_then_promote(self):
        op = User.objects.create_user(
            username=f"gp_rp_{id(self)}", email="o@example.com", password="p",
        )
        tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        tmp.write(b"placeholder")
        tmp.close()
        try:
            call_command(
                "register_grade_prediction_artifact",
                tmp.name,
                "--model-version", "grade_test_v1",
                "--registered-by-username", op.username,
                stdout=StringIO(),
            )
            self.assertEqual(
                GradePredictionModelArtifact.objects.get(
                    model_version="grade_test_v1"
                ).status,
                GradePredictionModelArtifact.Status.CANDIDATE,
            )
            call_command(
                "promote_grade_prediction_artifact",
                "grade_test_v1",
                "--promoted-by-username", op.username,
                stdout=StringIO(),
            )
            row = GradePredictionModelArtifact.objects.get(
                model_version="grade_test_v1"
            )
            self.assertEqual(
                row.status, GradePredictionModelArtifact.Status.PRODUCTION,
            )
        finally:
            os.unlink(tmp.name)


class ShadowGradePredictionTests(TestCase):
    def _seed(self):
        from apps.academics.models import (
            AcademicYear, Classroom, Department, Subject,
            SubjectAssignment, Term,
        )
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"SG{uid % 9999}",
            defaults={
                "name": "SG Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        school = School.objects.create(
            name=f"SG {uid}", slug=f"sg-{uid}",
            subdomain=f"sg-{uid}", is_active=True, default_region=region,
        )
        op = User.objects.create_user(
            username=f"sg_op_{uid}", email="o@example.com", password="p",
        )
        dept = Department.objects.create(name=f"D-{uid}", code=f"DC{uid % 9999}")
        year = AcademicYear.objects.create(
            name=f"SGY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"SGT-{uid}", academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        classroom = Classroom.objects.create(
            name=f"CR-{uid}", code=f"CRC{uid % 9999}",
            academic_year=year, department=dept,
        )
        subj = Subject.objects.create(name=f"M-{uid}")
        SubjectAssignment.objects.create(
            academic_year=year, term=term,
            classroom=classroom, subject=subj,
        )
        for i in range(3):
            u = User.objects.create_user(
                username=f"sg_s_{uid}_{i}",
                email=f"s{i}@example.com", password="p",
            )
            StudentProfile.objects.create(
                school=school, user=u, first_name=f"X{i}", last_name="Y",
                student_code=f"SG-{uid % 9999}-{i}",
                classroom=classroom, is_active=True,
            )
        return school, op, year, term

    def test_skips_without_candidate(self):
        school, op, _, _ = self._seed()
        # Create a production artifact only.
        prod_tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        prod_tmp.write(b"p")
        prod_tmp.close()
        GradePredictionModelArtifact.objects.create(
            model_version="sg_prod", artifact_path=prod_tmp.name,
            trained_at=timezone.now(),
            status=GradePredictionModelArtifact.Status.PRODUCTION,
            registered_by=op, promoted_at=timezone.now(), promoted_by=op,
        )
        try:
            call_command(
                "score_shadow_grade_prediction",
                "--school", school.slug,
                stdout=StringIO(),
            )
            run = GradePredictionShadowRun.objects.get(school=school)
            self.assertEqual(
                run.outcome, GradePredictionShadowRun.Outcome.SKIPPED,
            )
        finally:
            os.unlink(prod_tmp.name)

    def test_shadow_compares_and_summarises(self):
        school, op, _, _ = self._seed()
        prod_tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        prod_tmp.write(b"p")
        prod_tmp.close()
        cand_tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        cand_tmp.write(b"c")
        cand_tmp.close()
        try:
            prod = GradePredictionModelArtifact.objects.create(
                model_version="sg_prod2", artifact_path=prod_tmp.name,
                trained_at=timezone.now(),
                status=GradePredictionModelArtifact.Status.PRODUCTION,
                registered_by=op, promoted_at=timezone.now(), promoted_by=op,
            )
            GradePredictionModelArtifact.objects.create(
                model_version="sg_cand2", artifact_path=cand_tmp.name,
                trained_at=timezone.now(),
                status=GradePredictionModelArtifact.Status.CANDIDATE,
                registered_by=op,
            )

            def _fake(_student, _subject, _term, path):
                return 70.0 if path == prod.artifact_path else 75.0

            with mock.patch(
                "apps.analytics.management.commands."
                "score_shadow_grade_prediction.predict_grade_with_artifact",
                side_effect=_fake,
            ):
                call_command(
                    "score_shadow_grade_prediction",
                    "--school", school.slug,
                    stdout=StringIO(),
                )
            run = GradePredictionShadowRun.objects.filter(
                school=school
            ).order_by("-started_at").first()
            self.assertEqual(run.outcome, GradePredictionShadowRun.Outcome.OK)
            self.assertEqual(run.rows_compared, 3)
            self.assertAlmostEqual(run.mean_abs_delta, 5.0, places=2)
            self.assertAlmostEqual(run.bias, 5.0, places=2)
            self.assertEqual(
                GradePredictionShadowComparison.objects.filter(run=run).count(),
                3,
            )
        finally:
            os.unlink(prod_tmp.name)
            os.unlink(cand_tmp.name)


class ShouldRetrainGradePredictionTests(TestCase):
    def setUp(self):
        from apps.academics.models import AcademicYear, Subject, Term
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"SR{uid % 9999}",
            defaults={
                "name": "SR", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"SR {uid}", slug=f"sr-{uid}",
            subdomain=f"sr-{uid}", is_active=True, default_region=region,
        )
        self.op = User.objects.create_user(
            username=f"sr_op_{uid}", email="o@example.com", password="p",
        )
        year = AcademicYear.objects.create(
            name=f"SRY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"SRT-{uid}", academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        subj = Subject.objects.create(name=f"M-{uid}")
        for i in range(3):
            u = User.objects.create_user(
                username=f"sr_st_{uid}_{i}",
                email=f"st{i}@example.com", password="p",
            )
            stud = StudentProfile.objects.create(
                school=self.school, user=u, first_name=f"X{i}", last_name="Y",
                student_code=f"SR-{uid % 9999}-{i}",
            )
            GradePredictionLabel.objects.create(
                school=self.school, student=stud, subject=subj,
                academic_year=year, term=term,
                actual_grade=75.0, labeled_by=self.op,
            )
        self.tmp = tempfile.TemporaryDirectory()
        self.artifact = os.path.join(self.tmp.name, "g.joblib")
        open(self.artifact, "wb").write(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_threshold_not_crossed(self):
        call_command(
            "should_retrain_grade_prediction",
            "--artifact", self.artifact,
            "--threshold", "100",
            "--school", self.school.slug,
            stdout=StringIO(),
        )

    def test_threshold_crossed_exits_10(self):
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "should_retrain_grade_prediction",
                "--artifact", self.artifact,
                "--threshold", "1",
                "--school", self.school.slug,
                stdout=StringIO(),
            )
        self.assertEqual(ctx.exception.code, 10)
