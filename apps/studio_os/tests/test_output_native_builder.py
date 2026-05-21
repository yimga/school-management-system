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

    def test_output_pane_documents_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=documents"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="documents"')

    def test_output_pane_branding_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=branding"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="branding"')

    def test_output_pane_policy_renders_native_marker(self):
        url = reverse("studio_os:output") + "?pane=policy"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-studio-output-native="policy"')

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

    # ---- v3.54.0 extensions: readiness cockpit grammar ----

    def test_dependency_pane_includes_readiness_cockpit(self):
        """v3.54.0: readiness cockpit pane renders above dependency content."""
        response = self.client.get(reverse("studio_os:output") + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-rmc-output-cockpit="1"')
        self.assertContains(response, "rmc-output-tiles")

    def test_dependency_pane_has_readiness_service_state(self):
        """v3.54.0: readiness pane is honest about service state (derived vs offline)."""
        response = self.client.get(reverse("studio_os:output") + "?pane=dependency")
        body = response.content.decode("utf-8", errors="replace")
        # One of three honest states must appear; never a fake "Live" without basis.
        self.assertTrue(
            ('data-state="online"' in body) or ('data-state="offline"' in body),
            msg="Readiness cockpit must declare an honest service state.",
        )
