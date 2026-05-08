from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class TenantSchoolAppleClassExperienceTests(SimpleTestCase):
    def test_tenant_school_admin_has_next_action_and_drawer(self):
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-tenant-school-admin",
            "School Readiness Score",
            "Next Best Action",
            "apple_class_quick_profile_drawer.html",
            "without exposing platform-only actions",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_tenant_school_admin_does_not_expose_global_registry(self):
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8").lower()
        self.assertNotIn("global registry", text)
