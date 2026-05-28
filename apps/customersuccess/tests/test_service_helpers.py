import sys
from types import ModuleType
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.customersuccess import services


class CustomerSuccessServiceHelperTests(SimpleTestCase):
    def test_get_peer_school_ids_returns_empty_when_school_missing(self):
        self.assertEqual(services.get_peer_school_ids(None), [])

    def test_get_guided_onboarding_steps_uses_stubbed_optional_modules(self):
        class DummySchool:
            pass

        class ExistsManager:
            def __init__(self, exists_value):
                self.exists_value = exists_value

            def filter(self, **kwargs):
                return self

            def exists(self):
                return self.exists_value

            def values_list(self, *args, **kwargs):
                return []

        academics_module = ModuleType("apps.academics.models")
        academics_module.AcademicYear = type(
            "AcademicYear", (), {"objects": ExistsManager(False)}
        )

        people_module = ModuleType("apps.people.models")
        people_module.StudentProfile = type(
            "StudentProfile", (), {"objects": ExistsManager(True)}
        )
        people_module.StudentGuardian = type(
            "StudentGuardian", (), {"objects": ExistsManager(False)}
        )

        portal_module = ModuleType("apps.portal.models")
        portal_module.PendingGuardianInvite = type(
            "PendingGuardianInvite", (), {"objects": ExistsManager(False)}
        )

        finance_module = ModuleType("apps.finance.models")
        finance_module.Invoice = type("Invoice", (), {"objects": ExistsManager(False)})

        class SiteSettingsStub:
            grading_scale = "A-F"
            default_grading_scale = None
            site_name = "RunMyCampus"
            logo = None
            school_name = ""

        def get_effective_site_settings(*, school=None, request=None):
            return SiteSettingsStub()

        fake_modules = {
            "apps.academics.models": academics_module,
            "apps.people.models": people_module,
            "apps.portal.models": portal_module,
            "apps.finance.models": finance_module,
        }

        with patch.dict(sys.modules, fake_modules, clear=False), patch(
            "apps.siteconfig.config_service.get_effective_site_settings",
            get_effective_site_settings,
        ), patch.object(
            services,
            "_onboarding_step_link",
            side_effect=lambda name, **kw: f"/named/{name}/",
        ), patch.object(
            services,
            "_guided_onboarding_csv_link",
            return_value="/siteconfig/guided-onboarding/?embed=1#student-csv-import",
        ):
            steps = services.get_guided_onboarding_steps(DummySchool())

        self.assertTrue(steps)
        self.assertEqual(steps[0]["key"], "academic_year")
        self.assertFalse(steps[0]["done"])
        keys = [s["key"] for s in steps]
        self.assertIn("student_csv_import", keys)
        self.assertIn("guardian_invite", keys)
        self.assertIn("post_fees", keys)
        csv_step = next(s for s in steps if s["key"] == "student_csv_import")
        self.assertTrue(csv_step["done"])
        self.assertEqual(steps[-1]["key"], "dashboard")
        self.assertTrue(steps[-1]["done"])
