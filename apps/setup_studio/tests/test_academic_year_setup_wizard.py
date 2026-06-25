from django.test import TestCase

from apps.academics.models import AcademicYear, Term
from apps.registries.models import CountryRegistry
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School
from apps.setup_studio.services import get_setup_studio_payload
from apps.setup_studio.wizard_resolvers_operator import write_academic_year_setup


class AcademicYearSetupWizardTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="AYR",
            name="AY Region",
            default_currency="USD",
            grading_scale="0-100",
        )
        CountryRegistry.objects.get_or_create(
            code="US",
            defaults={"name": "United States", "is_active": True},
        )
        self.school = School.objects.create(
            name="AY School",
            slug="ay-school",
            subdomain="ay-school",
            country_code="US",
            timezone="UTC",
            default_region=self.region,
            is_active=True,
        )

    def test_writer_creates_academic_year_and_terms(self):
        write_academic_year_setup(
            school=self.school,
            wizard_key="academic_year_setup",
            step_key="year_dates",
            payload={
                "name": "2026/2027",
                "start_date": "2026-09-01",
                "end_date": "2027-06-30",
                "term_count": 3,
            },
            actor_user_id=None,
        )
        self.assertEqual(AcademicYear.objects.filter(school=self.school).count(), 1)
        ay = AcademicYear.objects.get(school=self.school)
        self.assertTrue(ay.is_active)
        self.assertGreaterEqual(Term.objects.filter(academic_year=ay).count(), 3)

    def test_academic_year_blocker_when_core_blockers_cleared(self):
        from unittest.mock import patch

        from apps.setup_studio import services as svc

        fake_link = "/school/studio/wizards/academic_year_setup/"
        fake_state = {
            "institution_basics": {"done": True, "is_blocker": False, "evidence": "", "link": "#", "label": "Basics", "weight": 1, "group": "foundation", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Basics", "key": "institution_basics"},
            "plan_choice": {"done": True, "is_blocker": True, "evidence": "", "link": "#", "label": "Plan", "weight": 1, "group": "commercial", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Plan", "key": "plan_choice"},
            "blueprint": {"done": True, "is_blocker": True, "evidence": "", "link": "#", "label": "Blueprint", "weight": 1, "group": "runtime", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Blueprint", "key": "blueprint"},
            "branding": {"done": True, "is_blocker": True, "evidence": "", "link": "#", "label": "Brand", "weight": 1, "group": "brand", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Brand", "key": "branding"},
            "select_experience_template": {"done": True, "is_blocker": False, "evidence": "", "link": "#", "label": "Template", "weight": 1, "group": "brand", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Template", "key": "select_experience_template"},
            "starter_stack": {"done": True, "is_blocker": False, "evidence": "", "link": "#", "label": "Stack", "weight": 1, "group": "modules", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Stack", "key": "starter_stack"},
            "data_path": {"done": True, "is_blocker": True, "evidence": "", "link": "#", "label": "Data", "weight": 1, "group": "data", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Data", "key": "data_path"},
            "role_preview": {"done": True, "is_blocker": False, "evidence": "", "link": "#", "label": "Preview", "weight": 1, "group": "preview", "description": "", "recommended_choice": "", "status": "done", "definition_label": "Preview", "key": "role_preview"},
            "launch": {"done": False, "is_blocker": False, "evidence": "Launch readiness is incomplete.", "link": fake_link, "label": "Launch", "weight": 1, "group": "launch", "description": "", "recommended_choice": "", "status": "pending", "definition_label": "Launch", "key": "launch"},
        }
        with patch.object(svc, "_step_state_for_school", return_value=fake_state):
            payload = svc.compile_setup_studio(self.school)
        keys = {b["key"] for b in payload.get("launch_blockers") or []}
        self.assertIn("academic_year", keys)
        self.assertFalse(payload.get("launch_ready"))

    def test_launch_blockers_include_plan_when_incomplete(self):
        payload = get_setup_studio_payload(self.school)
        keys = {b["key"] for b in payload.get("launch_blockers") or []}
        self.assertIn("plan_choice", keys)
        self.assertFalse(payload.get("launch_ready"))
