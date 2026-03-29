from django.test import TestCase


class SuperTenant360PhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "templates" / "schools" / "super_tenant_360.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#tenant-360-main"', text)
        self.assertIn('id="tenant-360-main"', text)
