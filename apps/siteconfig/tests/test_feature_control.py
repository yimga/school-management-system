"""Tests for Feature Control Panel."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.global_catalog import GlobalGeoCatalog

User = get_user_model()


class FeatureControlPanelTest(TestCase):
    """Test Feature Control Panel view."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super", email="super@test.com", password="testpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staff",
            email="staff@test.com",
            password="testpass123",
            is_staff=True,
        )
        self.client = Client()

    def test_superuser_can_access(self):
        """Superuser can access Feature Control Panel."""
        self.client.login(username="super", password="testpass123")
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)
        self.assertIn(b"Save changes", response.content)

    def test_user_without_permission_forbidden(self):
        """User without settings.feature_control receives 403."""
        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_user_with_permission_can_access(self):
        """User with settings.feature_control permission can access."""
        from apps.accounts.models import AccessRole, Permission

        perm, _ = Permission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control", "description": ""},
        )
        role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", defaults={"name": "IT Admin", "description": ""}
        )
        role.permissions.add(perm)
        self.staff_user.role = "IT_ADMIN"
        self.staff_user.roles.add(role)
        self.staff_user.save()

        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)

    def test_anonymous_redirected_to_login(self):
        """Anonymous user redirected to login."""
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    def test_offline_feature_flags_rendered(self):
        """New offline/PWA toggles are visible in Feature Control."""
        self.client.login(username="super", password="testpass123")
        response = self.client.get(
            reverse("siteconfig:feature_control_panel") + "?embed=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Portal PWA", response.content)
        self.assertIn(b"Offline Attendance Sync", response.content)
        self.assertIn(b"Offline Grade Sync", response.content)
        self.assertIn(b"Connection Status Bar", response.content)

    def test_offline_feature_flags_persist(self):
        """Posting Feature Control saves new backend offline flags."""
        self.client.login(username="super", password="testpass123")
        panel_url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        page = self.client.get(panel_url)
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
            "feature_backend_flags.show_offline_status_bar": "on",
            "feature_backend_flags.request_persistent_browser_storage": "on",
        }
        response = self.client.post(panel_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        flags = site.backend_feature_flags or {}
        self.assertTrue(site.enable_offline_mode)
        self.assertTrue(flags.get("enable_portal_pwa"))
        self.assertTrue(flags.get("show_offline_status_bar", True))
        self.assertTrue(flags.get("enable_offline_form_queue"))
        self.assertTrue(flags.get("enable_offline_attendance_sync"))
        self.assertTrue(flags.get("enable_offline_grade_sync"))
        self.assertTrue(flags.get("enable_offline_background_sync"))

    def test_ministry_feature_flags_render_and_persist(self):
        """Ministry integrations should be togglable from Feature Control."""
        self.client.login(username="super", password="testpass123")
        response = self.client.get(
            reverse("siteconfig:feature_control_panel") + "?embed=1"
        )
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
        response = self.client.post(
            reverse("siteconfig:feature_control_panel") + "?embed=1",
            data=payload,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        flags = site.backend_feature_flags or {}
        self.assertTrue(flags.get("enable_ministry_api_cartescolaire"))
        self.assertTrue(flags.get("enable_ministry_api_dgi"))
        self.assertTrue(flags.get("enable_ministry_live_sync"))

    def test_backend_experience_flags_and_list_density(self):
        """Backend dashboard module/viz toggles and list density are configurable."""
        self.client.login(username="super", password="testpass123")
        response = self.client.get(
            reverse("siteconfig:feature_control_panel") + "?embed=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Backend Warm Palette", response.content)
        self.assertIn(b"Backend Module: Overview", response.content)
        self.assertIn(b"Backend Module: Planner", response.content)

        payload = {
            "action": "save",
            "feature_backend_flags.backend_warm_palette": "on",
            "feature_backend_flags.backend_reduce_card_flatness": "on",
            "feature_backend_flags.backend_high_depth_surfaces": "on",
            "feature_backend_flags.backend_layout_equal_heights": "on",
            "feature_backend_flags.backend_viz_show_progress_rings": "on",
            "feature_backend_flags.backend_module_overview": "on",
            "feature_backend_flags.backend_module_admin_portal": "on",
            "feature_backend_flags.backend_module_planner": "on",
            "backend_layout_max_items_per_list": "7",
        }
        response = self.client.post(
            reverse("siteconfig:feature_control_panel") + "?embed=1",
            data=payload,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        flags = site.backend_feature_flags or {}
        self.assertTrue(flags.get("backend_warm_palette"))
        self.assertTrue(flags.get("backend_reduce_card_flatness"))
        self.assertTrue(flags.get("backend_high_depth_surfaces"))
        self.assertTrue(flags.get("backend_layout_equal_heights"))
        self.assertTrue(flags.get("backend_viz_show_progress_rings"))
        self.assertTrue(flags.get("backend_module_overview"))
        self.assertTrue(flags.get("backend_module_admin_portal"))
        self.assertTrue(flags.get("backend_module_planner"))
        self.assertEqual(flags.get("backend_layout_max_items_per_list"), 7)

    def test_offline_fallback_page_available(self):
        """Offline fallback route exists for service worker navigation fallback."""
        response = self.client.get(reverse("offline"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You are currently offline", response.content)

    def test_weather_city_api_returns_global_catalog_city(self):
        self.client.login(username="super", password="testpass123")
        response = self.client.get(
            reverse("siteconfig:feature_control_weather_cities"),
            {"country_code": "JPN", "q": "Tokyo", "limit": 20},
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload.get("country_code"), "JPN")
        city_names = [
            str(item.get("city", "")).lower() for item in payload.get("cities", [])
        ]
        self.assertIn("tokyo", city_names)

    def test_feature_control_save_accepts_global_city_ids(self):
        self.client.login(username="super", password="testpass123")
        cities = GlobalGeoCatalog.search_cities(
            country_code="JPN", query="Tokyo", limit=5
        )
        self.assertTrue(cities)
        city = cities[0]
        payload = {
            "action": "save",
            "weather_country_code": "JPN",
            "weather_city_id": str(city["id"]),
        }
        response = self.client.post(
            reverse("siteconfig:feature_control_panel") + "?embed=1",
            data=payload,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        flags = site.backend_feature_flags or {}
        self.assertEqual(str(flags.get("header_weather_country_code")), "JPN")
        self.assertEqual(str(flags.get("header_weather_city")), str(city["city"]))
        self.assertEqual(
            str(flags.get("header_weather_timezone")), str(city["timezone"])
        )
