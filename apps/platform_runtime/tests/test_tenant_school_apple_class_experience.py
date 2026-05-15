from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class TenantSchoolAppleClassExperienceTests(SimpleTestCase):
    def test_tenant_school_admin_has_next_action_and_drawer(self):
        """v2.53 (2026-05-15): "School Readiness Score" and "Next Best Action"
        tokens removed from above-the-fold here — those were a duplicate
        apple_class_metric_card + glass_panel restating the value already
        shown by ``world_class_summary_strip`` (School readiness 74%). The
        setup drawer + the tenant-safe shell-root attribute survive as the
        load-bearing experience contract.
        """
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-tenant-school-admin",
            "apple_class_quick_profile_drawer.html",
            "without exposing platform-only actions",
            # Readiness coverage now comes from the consolidated summary strip:
            "world_class_summary_strip.html",
            "School readiness",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_tenant_school_admin_does_not_expose_global_registry(self):
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8").lower()
        self.assertNotIn("global registry", text)
