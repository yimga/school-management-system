"""Tests for Feature Control Panel."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.models import SiteSettings

User = get_user_model()


class FeatureControlPanelTest(TestCase):
    """Test Feature Control Panel view."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super", email="super@test.com", password="testpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )
        self.client = Client()

    def test_superuser_can_access(self):
        """Superuser can access Feature Control Panel."""
        self.client.login(username="super", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)
        self.assertIn(b"Save changes", response.content)

    def test_user_without_permission_forbidden(self):
        """User without settings.feature_control receives 403."""
        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_user_with_permission_can_access(self):
        """User with settings.feature_control permission can access."""
        from apps.accounts.models import AccessRole, Permission

        perm = Permission.objects.get(code="settings.feature_control")
        role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", defaults={"name": "IT Admin", "description": ""}
        )
        role.permissions.add(perm)
        self.staff_user.role = "IT_ADMIN"
        self.staff_user.roles.add(role)
        self.staff_user.save()

        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)

    def test_anonymous_redirected_to_login(self):
        """Anonymous user redirected to login."""
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    def test_offline_feature_flags_rendered(self):
        """New offline/PWA toggles are visible in Feature Control."""
        self.client.login(username="super", password="testpass123")
        response = self.client.get(reverse("siteconfig:feature_control_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Portal PWA", response.content)
        self.assertIn(b"Offline Attendance Sync", response.content)
        self.assertIn(b"Offline Grade Sync", response.content)

    def test_offline_feature_flags_persist(self):
        """Posting Feature Control saves new backend offline flags."""
        self.client.login(username="super", password="testpass123")
        page = self.client.get(reverse("siteconfig:feature_control_panel"))
        self.assertEqual(page.status_code, 200)

        # Minimal post only sets selected switches to on.
        payload = {
            "action": "save",
            "feature_enable_offline_mode": "on",
            "feature_backend_flags.enable_portal_pwa": "on",
            "feature_backend_flags.enable_offline_form_queue": "on",
            "feature_backend_flags.enable_offline_attendance_sync": "on",
            "feature_backend_flags.enable_offline_grade_sync": "on",
            "feature_backend_flags.enable_offline_background_sync": "on",
            "feature_backend_flags.request_persistent_browser_storage": "on",
        }
        response = self.client.post(reverse("siteconfig:feature_control_panel"), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        site = SiteSettings.get_solo()
        flags = site.backend_feature_flags or {}
        self.assertTrue(site.enable_offline_mode)
        self.assertTrue(flags.get("enable_portal_pwa"))
        self.assertTrue(flags.get("enable_offline_form_queue"))
        self.assertTrue(flags.get("enable_offline_attendance_sync"))
        self.assertTrue(flags.get("enable_offline_grade_sync"))
        self.assertTrue(flags.get("enable_offline_background_sync"))

    def test_ministry_feature_flags_render_and_persist(self):
        """Ministry integrations should be togglable from Feature Control."""
        self.client.login(username="super", password="testpass123")
        response = self.client.get(reverse("siteconfig:feature_control_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ministry API (Cartescolaire)", response.content)
        self.assertIn(b"Ministry API (DGI)", response.content)
        self.assertIn(b"Ministry Live Sync", response.content)

        payload = {
            "action": "save",
            "feature_backend_flags.enable_ministry_api_cartescolaire": "on",
            "feature_backend_flags.enable_ministry_api_dgi": "on",
            "feature_backend_flags.enable_ministry_live_sync": "on",
        }
        response = self.client.post(reverse("siteconfig:feature_control_panel"), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        site = SiteSettings.get_solo()
        flags = site.backend_feature_flags or {}
        self.assertTrue(flags.get("enable_ministry_api_cartescolaire"))
        self.assertTrue(flags.get("enable_ministry_api_dgi"))
        self.assertTrue(flags.get("enable_ministry_live_sync"))

    def test_offline_fallback_page_available(self):
        """Offline fallback route exists for service worker navigation fallback."""
        response = self.client.get(reverse("offline"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You are currently offline", response.content)
