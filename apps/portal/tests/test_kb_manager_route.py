from django.test import SimpleTestCase
from django.urls import resolve


class ManagerKbRouteTests(SimpleTestCase):
    def test_manager_kb_resolves_to_kb_namespace(self):
        match = resolve("/kb/", urlconf="config.manager_urls")
        self.assertEqual(match.view_name, "kb:kb_home")
