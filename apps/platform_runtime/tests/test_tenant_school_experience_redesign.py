from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class TenantSchoolExperienceRedesignTests(SimpleTestCase):
    def test_school_settings_has_title_primary_action_tenant_safety_and_mobile_marker(self):
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8")
        self.assertIn("School Configuration Center", text)
        self.assertIn("world_class_page_hero.html", text)
        self.assertIn("primary_url", text)
        self.assertIn("School readiness score", text)
        self.assertIn("tenant_scoped_only", text)
        self.assertIn("data-world-class-mobile-layout", text)
        self.assertNotIn("system_closure_map", text)
        self.assertNotIn("global registries", text.lower())

    def test_tenant_setup_surfaces_show_external_blockers_honestly(self):
        for name in ("tenant_blueprint_setup.html", "tenant_pack_setup.html"):
            with self.subTest(name=name):
                text = (ROOT / "templates" / "platform_runtime" / name).read_text(encoding="utf-8")
                self.assertIn("world_class_page_hero.html", text)
                self.assertIn("external", text.lower())
                self.assertIn("approval", text.lower())
                self.assertIn("world_class_readiness_meter.html", text)
