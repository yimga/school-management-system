"""Output Studio native panes: report card builder in canvas (no iframe)."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.reports.models import ReportPack


class OutputNativeReportCardBuilderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="out_native_builder",
            email="onb@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_output_pane_builder_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=builder"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="builder"')

    def test_output_pane_reports_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=reports"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="reports"')

    def test_output_pane_credentials_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=credentials"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="credentials"')

    def test_output_studio_horizontal_tabs_and_dependency_native(self):
        response = self.client.get(reverse("studio_os:output") + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "studio-os__output-tabs")
        self.assertContains(response, 'data-studio-output-native="dependency"')

    def test_output_pack_previews_render_when_packs_exist(self):
        ReportPack.objects.create(
            code="preview-pack-tabs",
            name="Preview Pack",
            description="For Output Studio preview cards.",
            dependency_schema={"templates": ["a", "b"]},
            sample_data_config={
                "title": "Ops digest",
                "rows": [{"label": "Attendance", "value": "96%"}],
            },
            is_active=True,
        )
        response = self.client.get(reverse("studio_os:output") + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-studio-output-pack-previews")
        self.assertContains(response, "preview-pack-tabs")
