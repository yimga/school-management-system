from django.test import SimpleTestCase

from apps.portal.help_section_nav import (
    admin_catalog_section_nav_items,
    manager_help_section_nav_items,
    tenant_help_section_nav_items,
)


class HelpSectionNavTests(SimpleTestCase):
    def test_manager_help_nav_includes_sections(self):
        sections = [
            {"id": "discover", "title": "Discover"},
            {"id": "govern", "title": "Govern"},
        ]
        items = manager_help_section_nav_items(sections, include_featured=True)
        ids = [i["id"] for i in items]
        self.assertIn("rmc-persona-help-heading", ids)
        self.assertIn("rmc-help-featured-heading", ids)
        self.assertIn("rmc-help-section-discover", ids)
        self.assertIn("rmc-help-section-govern", ids)

    def test_tenant_help_nav_has_four_anchors(self):
        items = tenant_help_section_nav_items()
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]["id"], "rmc-help-quick-lane")

    def test_admin_catalog_nav_count(self):
        items = admin_catalog_section_nav_items()
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]["id"], "rmc-admin-sec-hero")
