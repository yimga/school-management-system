from django.test import TestCase

from apps.siteconfig.models import filter_portal_items


class PortalContentFilterTests(TestCase):
    def test_filter_portal_items_by_role_and_enabled(self):
        items = [
            {"label": "A", "roles": ["PARENT"], "enabled": True},
            {"label": "B", "roles": ["TEACHER"], "enabled": True},
            {"label": "C", "roles": [], "enabled": True},
            {"label": "D", "roles": ["PARENT"], "enabled": False},
        ]

        filtered = filter_portal_items(items, "PARENT")
        labels = [item.get("label") for item in filtered]
        self.assertEqual(labels, ["A", "C"])

    def test_filter_portal_items_with_invalid_input(self):
        self.assertEqual(filter_portal_items(None, "PARENT"), [])
        self.assertEqual(filter_portal_items("not-a-list", "PARENT"), [])
