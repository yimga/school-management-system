"""Pilot scorecard validation and reference redaction."""

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.pilot_evidence import (
    build_pilot_dashboard_rows,
    validate_scorecard_schema,
)


class PilotEvidenceTests(SimpleTestCase):
    def test_schema_valid_on_repo_file(self):
        from apps.platform_runtime.pilot_evidence import load_raw_scorecard

        raw = load_raw_scorecard()
        issues = validate_scorecard_schema(raw)
        self.assertEqual(issues, [], msg=issues)

    def test_schema_rejects_missing_non_pii_keys(self):
        raw = {
            "schema_version": 1,
            "pilots": [
                {
                    "slot": 9,
                    "country_region": "XX",
                    "modules_enabled": [],
                }
            ],
        }
        issues = validate_scorecard_schema(raw)
        self.assertTrue(issues)

    def test_public_reference_redacts_without_approval(self):
        raw = {
            "schema_version": 1,
            "lane": "test",
            "north_star_metric": "m",
            "workflow_evidence_template": {},
            "pilots": [
                {
                    "slot": 1,
                    "school_name": "Secret School",
                    "country_region": "CM",
                    "modules_enabled": [],
                    "onboarding_status": "x",
                    "first_action_completed": False,
                    "first_result_completed": False,
                    "attendance_completed": False,
                    "marks_completed": False,
                    "report_generated": False,
                    "invoice_created": False,
                    "receipt_or_payment_captured": False,
                    "parent_portal_viewed": False,
                    "offline_sync_used": False,
                    "defects_found": 0,
                    "defects_resolved": 0,
                    "testimonial_permission_status": "requested",
                    "reference_status": "public_reference",
                    "evidence_link_or_notes": "",
                    "pilot_verdict": "not_started",
                    "admin_contact": "",
                    "teacher_contact": "",
                    "parent_test_user": "",
                    "go_live_blockers": [],
                    "critical_bugs": [],
                    "user_feedback_notes": "",
                    "payment_method": "",
                    "offline_sync_required": False,
                    "time_to_first_value_hours": None,
                }
            ],
        }
        ctx = build_pilot_dashboard_rows(raw)
        p0 = ctx["pilots"][0]
        self.assertEqual(p0.get("school_name"), "")

    def test_schema_rejects_public_reference_without_evidence_and_approval(self):
        raw = {
            "schema_version": 1,
            "pilots": [
                {
                    "slot": 1,
                    "school_name": "Named School",
                    "country_region": "CM",
                    "modules_enabled": ["attendance"],
                    "onboarding_status": "complete",
                    "first_action_completed": True,
                    "first_result_completed": True,
                    "attendance_completed": True,
                    "marks_completed": True,
                    "report_generated": True,
                    "invoice_created": True,
                    "receipt_or_payment_captured": True,
                    "parent_portal_viewed": True,
                    "offline_sync_used": False,
                    "defects_found": 0,
                    "defects_resolved": 0,
                    "testimonial_permission_status": "requested",
                    "reference_status": "public_reference",
                    "evidence_link_or_notes": "",
                    "pilot_verdict": "public_reference_ready",
                }
            ],
        }
        issues = validate_scorecard_schema(raw)
        self.assertTrue(any("evidence_link_or_notes" in issue for issue in issues))
        self.assertTrue(any("requires public reference" in issue for issue in issues))

    def test_schema_rejects_unknown_pilot_verdict(self):
        raw = {
            "schema_version": 1,
            "pilots": [
                {
                    "slot": 1,
                    "country_region": "CM",
                    "modules_enabled": [],
                    "onboarding_status": "not_started",
                    "first_action_completed": False,
                    "first_result_completed": False,
                    "attendance_completed": False,
                    "marks_completed": False,
                    "report_generated": False,
                    "invoice_created": False,
                    "receipt_or_payment_captured": False,
                    "parent_portal_viewed": False,
                    "offline_sync_used": False,
                    "defects_found": 0,
                    "defects_resolved": 0,
                    "testimonial_permission_status": "not_requested",
                    "reference_status": "none",
                    "evidence_link_or_notes": "",
                    "pilot_verdict": "verified_live",
                }
            ],
        }
        issues = validate_scorecard_schema(raw)
        self.assertTrue(any("invalid pilot_verdict" in issue for issue in issues))


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class PilotEvidenceDashboardHttpTests(TestCase):
    def test_dashboard_200(self):
        User.objects.create_user(
            username="pilot_dash",
            password="x" * 8,
            is_superuser=True,
        )
        c = Client()
        self.assertTrue(c.login(username="pilot_dash", password="x" * 8))
        url = reverse("platform_runtime:pilot_evidence_dashboard")
        r = c.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Pilot evidence", r.content.decode("utf-8", errors="replace"))
