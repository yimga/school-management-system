"""
Phase 5 — Legacy admin paths (siteconfig + related portal manage surfaces) redirect into Studio OS.
ROOT_URLCONF is config.urls for default tests.
"""

from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from unittest.mock import patch


class Phase05LegacyStudioRedirectsTests(TestCase):
    def test_customizer_redirects_to_experience_studio(self):
        r = self.client.get("/siteconfig/customizer/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))

    def test_workflow_hub_redirects_to_automation_studio(self):
        r = self.client.get("/siteconfig/workflow-hub/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:automation"))

    def test_workflow_hub_preserves_query_string_on_redirect(self):
        r = self.client.get("/siteconfig/workflow-hub/?foo=1&bar=2", follow=False)
        self.assertEqual(r.status_code, 302)
        target = urlparse(r.url)
        self.assertEqual(target.path, urlparse(reverse("studio_os:automation")).path)
        self.assertEqual(parse_qs(target.query), {"foo": ["1"], "bar": ["2"]})

    def test_report_library_redirects_to_output_reports_pane(self):
        r = self.client.get("/siteconfig/report-library/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=reports")

    def test_report_library_preserves_query_string_on_redirect(self):
        r = self.client.get("/siteconfig/report-library/?foo=1", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?foo=1&pane=reports")

    def test_report_library_does_not_override_explicit_pane_query(self):
        r = self.client.get("/siteconfig/report-library/?pane=documents", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=documents")

    def test_reports_path_redirects_to_output_reports_pane(self):
        r = self.client.get("/siteconfig/reports/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=reports")

    def test_reports_path_preserves_query_string_on_redirect(self):
        r = self.client.get("/siteconfig/reports/?foo=1", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?foo=1&pane=reports")

    def test_reports_path_does_not_override_explicit_pane_query(self):
        r = self.client.get("/siteconfig/reports/?pane=documents", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=documents")

    def test_admin_siteconfig_customizer_redirects_to_experience(self):
        r = self.client.get("/admin/siteconfig/customizer/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))

    def test_clear_preview_customizer_path_redirects_to_canonical_clear_preview(self):
        r = self.client.get(
            "/siteconfig/customizer/clear-preview/?next=/portal/parent/", follow=False
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("siteconfig:clear_preview") + "?next=/portal/parent/")

    def test_theme_experience_path_redirects_to_experience_studio(self):
        user = User.objects.create_user(
            username="legacy_theme_redirect",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/theme-experience/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))

    @patch("apps.schools.control_plane.user_can_access_studio_on_request", return_value=True)
    def test_theme_colors_redirects_staff_to_experience_studio(self, _mock_can_access):
        user = User.objects.create_user(
            username="legacy_theme_colors_to_studio",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/theme-colors/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:experience"))

    @patch("apps.schools.control_plane.user_can_access_studio_on_request", return_value=False)
    def test_theme_colors_redirects_to_standalone_when_studio_unavailable(
        self, _mock_can_access
    ):
        user = User.objects.create_user(
            username="legacy_theme_colors_to_standalone",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/theme-colors/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("siteconfig:theme_colors") + "?standalone=1")

    @patch("apps.schools.control_plane.user_can_access_studio_on_request", return_value=True)
    def test_theme_colors_embed_renders_page(self, _mock_can_access):
        user = User.objects.create_user(
            username="legacy_theme_colors_embed",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/theme-colors/?embed=1", follow=False)
        self.assertEqual(r.status_code, 200)

    def test_feature_control_redirects_to_studio_control_when_not_embedded(self):
        user = User.objects.create_user(
            username="legacy_feature_control_to_studio",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/feature-control/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:control"))

    def test_feature_control_embed_renders_panel(self):
        user = User.objects.create_user(
            username="legacy_feature_control_embed",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/siteconfig/feature-control/?embed=1", follow=False)
        self.assertEqual(r.status_code, 200)

    def test_document_library_manage_redirects_to_output_documents_when_not_embedded(self):
        user = User.objects.create_user(
            username="legacy_doc_library_redirect",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/portal/backend/documents/", follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("studio_os:output") + "?pane=documents")

    def test_document_library_manage_embed_renders(self):
        user = User.objects.create_user(
            username="legacy_doc_library_embed",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        r = self.client.get("/portal/backend/documents/?embed=1", follow=False)
        self.assertEqual(r.status_code, 200)
