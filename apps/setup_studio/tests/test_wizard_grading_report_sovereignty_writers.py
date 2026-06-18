"""Grading, report card, sovereignty, analytics KPI wizard writer tests (batch 5)."""

from __future__ import annotations

from django.test import TestCase

from apps.evals.models import GradingScale
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.wizard_resolvers import (
    write_alumni_graduation_capture,
    write_analytics_kpis,
    write_grading_metrics,
    write_grading_track,
    write_report_card_attendance,
    write_report_card_columns,
    write_sovereignty_routing,
    write_sovereignty_statutory,
)


class GradingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Grading School",
            slug="grading-school",
            subdomain="grading-school",
            country_code="CM",
            is_active=True,
        )

    def test_tracks_and_metrics_create_grading_scale(self):
        write_grading_track(
            school=self.school,
            wizard_key="polymorphic_grading_curricula",
            step_key="track_selection",
            payload={"value": ["ib_diploma", "cambridge_igcse"]},
            actor_user_id=1,
        )
        write_grading_metrics(
            school=self.school,
            wizard_key="polymorphic_grading_curricula",
            step_key="assessment_metrics",
            payload={
                "grading_scale": "percentage",
                "pass_threshold": "50",
                "rubric_levels": 5,
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        grading = (self.school.settings or {}).get("grading", {})
        self.assertIn("ib_diploma", grading.get("curriculum_tracks", []))
        scale = GradingScale.objects.get(school=self.school, code="wizard-default")
        self.assertTrue(scale.is_default)
        self.assertEqual(scale.config.get("pass_threshold"), 50.0)


class ReportCardWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Report School",
            slug="report-school",
            subdomain="report-school",
            country_code="US",
            is_active=True,
        )

    def test_columns_and_attendance_block(self):
        write_report_card_columns(
            school=self.school,
            wizard_key="report_card_template_studio",
            step_key="grade_columns",
            payload={"value": ["term_grade", "class_rank"]},
            actor_user_id=1,
        )
        write_report_card_attendance(
            school=self.school,
            wizard_key="report_card_template_studio",
            step_key="attendance_block",
            payload={
                "show_attendance_summary": True,
                "attendance_threshold_warning_pct": "85",
                "show_punctuality_score": False,
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        rc = (self.school.settings or {}).get("report_card", {})
        self.assertEqual(rc.get("grade_columns"), ["term_grade", "class_rank"])
        self.assertTrue(rc.get("attendance_block", {}).get("show_attendance_summary"))


class SovereigntyWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="NG", defaults={"name": "Nigeria"})
        self.school = School.objects.create(
            name="Sovereign School",
            slug="sovereign-school",
            subdomain="sovereign-school",
            country_code="NG",
            is_active=True,
        )

    def test_routing_and_statutory_persisted(self):
        write_sovereignty_routing(
            school=self.school,
            wizard_key="multi_campus_local_sovereignty",
            step_key="dynamic_core_routing",
            payload={"value": "tenant_schema_primary"},
            actor_user_id=1,
        )
        write_sovereignty_statutory(
            school=self.school,
            wizard_key="multi_campus_local_sovereignty",
            step_key="statutory_alignment",
            payload={"value": "gst_einvoice_in"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        sk = (self.school.settings or {}).get("sovereignty", {})
        self.assertEqual(sk.get("dynamic_core_routing"), "tenant_schema_primary")
        self.assertEqual(sk.get("statutory_schema"), "gst_einvoice_in")
        self.assertTrue((self.school.settings or {}).get("sovereignty_kernel_ready"))


class AnalyticsAndAlumniWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Analytics School",
            slug="analytics-school",
            subdomain="analytics-school",
            country_code="CM",
            is_active=True,
        )

    def test_kpi_selection_and_graduation_capture(self):
        write_analytics_kpis(
            school=self.school,
            wizard_key="institutional_performance_board_reporting",
            step_key="executive_kpi_selection",
            payload={"value": ["enrollment_retention_pct", "parent_nps"]},
            actor_user_id=1,
        )
        write_alumni_graduation_capture(
            school=self.school,
            wizard_key="alumni_engagement_pipeline",
            step_key="graduation_capture",
            payload={"auto_promote_alumni": True, "capture_transcript_snapshot": True},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        board = (self.school.settings or {}).get("board_reporting", {})
        alumni = (self.school.settings or {}).get("alumni_engagement", {})
        self.assertEqual(
            board.get("enabled_kpis"),
            ["enrollment_retention_pct", "parent_nps"],
        )
        self.assertTrue(alumni.get("graduation_capture", {}).get("auto_promote_alumni"))
