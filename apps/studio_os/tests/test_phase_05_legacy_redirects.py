"""
Phase 5 — Legacy siteconfig URLs redirect to Studio OS (acceptance: old identities not primary).
ROOT_URLCONF is config.urls for default tests.
"""

from django.test import TestCase
from django.urls import reverse


class Phase05LegacyStudioRedirectsTests(TestCase):
    def test_customizer_redirects_to_experience_studio(self):
        r = self.client.get("/siteconfig/customizer/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))

    def test_workflow_hub_redirects_to_automation_studio(self):
        r = self.client.get("/siteconfig/workflow-hub/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:automation"))

    def test_report_library_redirects_to_output_reports_pane(self):
        r = self.client.get("/siteconfig/report-library/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=reports")

    def test_reports_path_redirects_to_output_reports_pane(self):
        r = self.client.get("/siteconfig/reports/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=reports")

    def test_admin_siteconfig_customizer_redirects_to_experience(self):
        r = self.client.get("/admin/siteconfig/customizer/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))
