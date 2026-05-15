"""Wave O4: at-risk outcome labeling + export tests."""

from __future__ import annotations

import csv
import tempfile
import uuid
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings

from apps.analytics.models import AtRiskOutcomeLabel
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig

User = get_user_model()


def _make_school(plan, region):
    slug = f"o4-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region,
    )


def _make_academic_year(school):
    from apps.academics.models import AcademicYear
    from datetime import date
    return AcademicYear.objects.create(
        school=school,
        name=f"AY-{uuid.uuid4().hex[:6]}",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )


def _make_student(school):
    from apps.people.models import StudentProfile

    user = User.objects.create_user(
        username=f"stu-{uuid.uuid4().hex[:8]}", password="pw",
        first_name="Test", last_name="Student",
    )
    return StudentProfile.objects.create(school=school, user=user, is_active=True)


def _make_admin():
    user = User.objects.create_user(
        username=f"adm-{uuid.uuid4().hex[:8]}", password="pw"
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def _make_student_role_user():
    return User.objects.create_user(
        username=f"stu-{uuid.uuid4().hex[:8]}", password="pw"
    )


def _build_request(method, user, school, post=None):
    factory = RequestFactory()
    if method == "POST":
        req = factory.post("/portal/at-risk/labeling/", data=post or {})
    else:
        req = factory.get("/portal/at-risk/labeling/")
    req.user = user
    req.school = school
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.urls.resolvers import ResolverMatch

    setattr(req, "session", {})
    req._messages = FallbackStorage(req)
    req.resolver_match = ResolverMatch(
        func=lambda r: None, args=(), kwargs={},
        url_name="portal_at_risk_labeling",
    )
    return req


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class LabelingViewTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="O4", slug="o4-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="O4", name="O4land", timezone="UTC", default_currency="USD"
        )

    def test_get_forbidden_for_non_admin(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        req = _build_request("GET", _make_student_role_user(), school)
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 403)

    def test_get_400_when_no_tenant(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        factory = RequestFactory()
        req = factory.get("/portal/at-risk/labeling/")
        req.user = _make_admin()
        from django.urls.resolvers import ResolverMatch
        req.resolver_match = ResolverMatch(
            func=lambda r: None, args=(), kwargs={},
            url_name="portal_at_risk_labeling",
        )
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 400)

    def test_get_400_when_no_academic_year(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        req = _build_request("GET", _make_admin(), school)
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 400)

    def test_get_renders_queue_for_admin(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        _make_academic_year(school)
        _make_student(school)
        req = _build_request("GET", _make_admin(), school)
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("outcome labeling", body.lower())

    def test_post_saves_label(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        student = _make_student(school)
        admin = _make_admin()
        req = _build_request("POST", admin, school, post={
            "student_id": str(student.pk),
            "label": "at_risk",
            "notes": "frequent absences",
        })
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 302)
        outcome = AtRiskOutcomeLabel.objects.get(
            student=student, academic_year=year
        )
        self.assertEqual(outcome.label, "at_risk")
        self.assertEqual(outcome.notes, "frequent absences")
        self.assertEqual(outcome.labeled_by, admin)

    def test_post_overwrites_existing_label(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        student = _make_student(school)
        AtRiskOutcomeLabel.objects.create(
            school=school, student=student, academic_year=year,
            label="not_at_risk", labeled_by=_make_admin(), notes="initial",
        )

        admin = _make_admin()
        req = _build_request("POST", admin, school, post={
            "student_id": str(student.pk),
            "label": "at_risk",
            "notes": "revised after term review",
        })
        at_risk_labeling_queue(req)

        # Still only one row per (student, year).
        self.assertEqual(
            AtRiskOutcomeLabel.objects.filter(student=student, academic_year=year).count(),
            1,
        )
        latest = AtRiskOutcomeLabel.objects.get(student=student, academic_year=year)
        self.assertEqual(latest.label, "at_risk")
        self.assertEqual(latest.notes, "revised after term review")

    def test_post_rejects_unknown_label(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school = _make_school(self.plan, self.region)
        _make_academic_year(school)
        student = _make_student(school)
        req = _build_request("POST", _make_admin(), school, post={
            "student_id": str(student.pk),
            "label": "nonsense_label",
        })
        resp = at_risk_labeling_queue(req)
        # Redirected back with error message; no AtRiskOutcomeLabel created.
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AtRiskOutcomeLabel.objects.count(), 0)

    def test_post_rejects_student_from_other_school(self):
        from apps.portal.views_at_risk_labeling import at_risk_labeling_queue

        school_a = _make_school(self.plan, self.region)
        school_b = _make_school(self.plan, self.region)
        _make_academic_year(school_a)
        # Student belongs to B; admin posts as if logged into A.
        student_in_b = _make_student(school_b)
        req = _build_request("POST", _make_admin(), school_a, post={
            "student_id": str(student_in_b.pk),
            "label": "at_risk",
        })
        resp = at_risk_labeling_queue(req)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AtRiskOutcomeLabel.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ExportCommandTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="O4exp", slug="o4-exp-plan",
            included_features=["core"], is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="O4E", name="O4Eland", timezone="UTC", default_currency="USD"
        )

    def test_export_writes_csv_with_correct_schema(self):
        from apps.analytics.ml.at_risk_features import AtRiskFeatures
        from apps.analytics.ml.synthetic_at_risk_dataset import FEATURE_ORDER

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        s_at_risk = _make_student(school)
        s_not_at_risk = _make_student(school)
        admin = _make_admin()

        AtRiskOutcomeLabel.objects.create(
            school=school, student=s_at_risk, academic_year=year,
            label="at_risk", labeled_by=admin,
        )
        AtRiskOutcomeLabel.objects.create(
            school=school, student=s_not_at_risk, academic_year=year,
            label="not_at_risk", labeled_by=admin,
        )

        # Stub feature extraction so we don't depend on real data.
        def _stub(student):
            return AtRiskFeatures(
                student_id=str(student.pk),
                attendance_rate=0.95, absence_count=2, late_count=1,
                avg_evaluation_score=72.0, evaluation_count=10,
                eval_score_trend=2.5, open_invoice_count=0,
                open_balance_amount=0.0, days_since_last_login=3,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.csv"
            with mock.patch(
                "apps.analytics.ml.at_risk_features.extract_features",
                side_effect=_stub,
            ):
                call_command(
                    "export_at_risk_training_data",
                    "--out", str(out_path),
                    stdout=StringIO(),
                )

            self.assertTrue(out_path.exists())
            with out_path.open() as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(
                    reader.fieldnames, list(FEATURE_ORDER) + ["label"]
                )
                rows = list(reader)
            # 2 labels in; 2 rows out (none are "unknown").
            self.assertEqual(len(rows), 2)
            labels_out = sorted(int(r["label"]) for r in rows)
            self.assertEqual(labels_out, [0, 1])

    def test_export_skips_unknown_labels(self):
        from apps.analytics.ml.at_risk_features import AtRiskFeatures

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        s_a = _make_student(school)
        s_b = _make_student(school)
        admin = _make_admin()
        AtRiskOutcomeLabel.objects.create(
            school=school, student=s_a, academic_year=year,
            label="unknown", labeled_by=admin,
        )
        AtRiskOutcomeLabel.objects.create(
            school=school, student=s_b, academic_year=year,
            label="at_risk", labeled_by=admin,
        )

        def _stub(student):
            return AtRiskFeatures(
                student_id=str(student.pk),
                attendance_rate=0.9, absence_count=1, late_count=0,
                avg_evaluation_score=70.0, evaluation_count=5,
                eval_score_trend=0.0, open_invoice_count=0,
                open_balance_amount=0.0, days_since_last_login=2,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.csv"
            with mock.patch(
                "apps.analytics.ml.at_risk_features.extract_features",
                side_effect=_stub,
            ):
                call_command(
                    "export_at_risk_training_data",
                    "--out", str(out_path),
                    stdout=StringIO(),
                )
            with out_path.open() as fh:
                rows = list(csv.DictReader(fh))
            # Only the at_risk row should be exported; unknown is skipped.
            self.assertEqual(len(rows), 1)

    def test_recovered_label_maps_to_at_risk_target(self):
        from apps.analytics.ml.at_risk_features import AtRiskFeatures

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        student = _make_student(school)
        AtRiskOutcomeLabel.objects.create(
            school=school, student=student, academic_year=year,
            label="recovered", labeled_by=_make_admin(),
        )

        def _stub(student):
            return AtRiskFeatures(
                student_id=str(student.pk),
                attendance_rate=0.9, absence_count=1, late_count=0,
                avg_evaluation_score=70.0, evaluation_count=5,
                eval_score_trend=0.0, open_invoice_count=0,
                open_balance_amount=0.0, days_since_last_login=2,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.csv"
            with mock.patch(
                "apps.analytics.ml.at_risk_features.extract_features",
                side_effect=_stub,
            ):
                call_command(
                    "export_at_risk_training_data",
                    "--out", str(out_path),
                    stdout=StringIO(),
                )
            with out_path.open() as fh:
                row = next(csv.DictReader(fh))
            # 'recovered' → 1 (the student WAS at-risk; that's the training signal).
            self.assertEqual(int(row["label"]), 1)


class AtRiskOutcomeLabelModelTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="O4m", slug="o4-m-plan",
            included_features=["core"], is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="O4M", name="O4Mland", timezone="UTC", default_currency="USD"
        )

    def test_unique_constraint_per_student_year(self):
        from django.db import IntegrityError, transaction

        school = _make_school(self.plan, self.region)
        year = _make_academic_year(school)
        student = _make_student(school)
        admin = _make_admin()

        AtRiskOutcomeLabel.objects.create(
            school=school, student=student, academic_year=year,
            label="at_risk", labeled_by=admin,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AtRiskOutcomeLabel.objects.create(
                    school=school, student=student, academic_year=year,
                    label="not_at_risk", labeled_by=admin,
                )
