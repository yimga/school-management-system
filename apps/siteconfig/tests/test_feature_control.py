"""Tests for Feature Control Panel.

Host topology (established empirically — no single host satisfies every case):

* The panel's canonical operator home is the **manager host**. The shared
  ``OperatorSiteconfigManagerShellMiddleware`` force-redirects any control-plane user
  (a superuser is always one) off ``siteconfig:feature_control_panel`` to the manager
  host on every OTHER host, and only the manager-host *non-embed* GET renders the full
  operator page (portal wrapper carrying the literal "Feature Control Panel" plus the
  capability body). So every superuser-driven case runs on the manager host.
* A tenant admin who holds only ``settings.feature_control`` (and therefore has NO
  control-plane access) is blocked from the manager host by
  ``ManagerHostControlPlaneRequiredMiddleware`` (403). Such a user reaches the panel
  only on their own **tenant host**, where the view renders the embed body (the
  full-page wrapper is a manager-host-only render, so its capability form — "Save
  changes" — is what proves access there).
* The no-permission (403) and anonymous (login redirect) cases resolve at the view's
  ``@require_permission`` gate before any host redirect, so they keep exercising the
  default base host unchanged.

The persisted platform singleton read back by the persist/save cases is host-independent
(``_resolve_feature_control_site`` always targets ``get_platform_site_settings_record``).
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.test_utils.http_clients import (
    login_manager_client,
    login_tenant_admin_client,
)

User = get_user_model()

MANAGER_HOST = "manager.runmycampus.com"
TENANT_BASE = "runmycampus.com"
TENANT_SUBDOMAIN = "fc-panel"
TENANT_HOST = f"{TENANT_SUBDOMAIN}.{TENANT_BASE}"

# The base-domain resolver reads ``MULTI_TENANT_BASE_DOMAIN`` so the host classifier
# recognises the manager / tenant hosts; ROOT_URLCONF pins the right host urlconf.
_MANAGER_OVERRIDES = dict(
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN=TENANT_BASE,
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", TENANT_BASE, MANAGER_HOST],
)
_TENANT_OVERRIDES = dict(
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN=TENANT_BASE,
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
        "localhost",
        TENANT_BASE,
        TENANT_HOST,
        MANAGER_HOST,
    ],
)


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

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _manager_panel_url():
        return reverse(
            "siteconfig:feature_control_panel", urlconf="config.manager_urls"
        )

    def _login_manager_superuser(self):
        """Manager-host operator client for the superuser (confirmed TOTP + MFA-verified)."""
        return login_manager_client(self.superuser, password="testpass123")

    def _grant_feature_control(self, user):
        from apps.accounts.models import AccessRole, Permission

        perm, _ = Permission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control", "description": ""},
        )
        role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", defaults={"name": "IT Admin", "description": ""}
        )
        role.permissions.add(perm)
        user.role = "IT_ADMIN"
        user.roles.add(role)
        user.save()

    def _create_tenant_school(self):
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        region = RegionConfig.objects.create(
            code=f"FCP{uuid.uuid4().hex[:6].upper()}",
            name="Feature control panel region",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        return School.objects.create(
            name="Feature control panel school",
            slug=TENANT_SUBDOMAIN,
            subdomain=TENANT_SUBDOMAIN,
            is_active=True,
            default_region=region,
            settings={},
        )

    # -- access control -----------------------------------------------------
    @override_settings(**_MANAGER_OVERRIDES)
    def test_superuser_can_access(self):
        """Superuser can access Feature Control Panel (manager-host operator page)."""
        client = self._login_manager_superuser()
        response = client.get(self._manager_panel_url(), HTTP_HOST=MANAGER_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)
        self.assertIn(b"Save changes", response.content)

    def test_user_without_permission_forbidden(self):
        """User without settings.feature_control receives 403."""
        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    @override_settings(**_TENANT_OVERRIDES)
    def test_user_with_permission_can_access(self):
        """User with settings.feature_control permission can access (tenant host)."""
        self._grant_feature_control(self.staff_user)
        school = self._create_tenant_school()
        client = login_tenant_admin_client(
            self.staff_user,
            password="testpass123",
            host=TENANT_HOST,
            school=school,
            role="ADMIN",
        )
        url = (
            reverse("siteconfig:feature_control_panel", urlconf="config.tenant_urls")
            + "?embed=1"
        )
        response = client.get(url, HTTP_HOST=TENANT_HOST)
        self.assertEqual(response.status_code, 200)
        # A perm-only tenant admin reaches the panel on their tenant host, where the
        # view renders the embed body. The full-page "Feature Control Panel" wrapper is
        # a manager-host-only render; the capability form ("Save changes") proves the
        # panel rendered for this user.
        self.assertIn(b"Save changes", response.content)

    def test_anonymous_redirected_to_login(self):
        """Anonymous user redirected to login."""
        url = reverse("siteconfig:feature_control_panel") + "?embed=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    # -- rendered capabilities + persistence (superuser / manager host) -----
    @override_settings(**_MANAGER_OVERRIDES)
    def test_offline_feature_flags_rendered(self):
        """New offline/PWA toggles are visible in Feature Control."""
        client = self._login_manager_superuser()
        response = client.get(self._manager_panel_url(), HTTP_HOST=MANAGER_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Portal PWA", response.content)
        self.assertIn(b"Offline Attendance Sync", response.content)
        self.assertIn(b"Offline Grade Sync", response.content)
        self.assertIn(b"Connection Status Bar", response.content)

    @override_settings(**_MANAGER_OVERRIDES)
    def test_offline_feature_flags_persist(self):
        """Posting Feature Control saves new backend offline flags."""
        client = self._login_manager_superuser()
        panel_url = self._manager_panel_url()
        page = client.get(panel_url, HTTP_HOST=MANAGER_HOST)
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
        response = client.post(
            panel_url, data=payload, HTTP_HOST=MANAGER_HOST, follow=True
        )
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

    @override_settings(**_MANAGER_OVERRIDES)
    def test_ministry_feature_flags_render_and_persist(self):
        """Ministry integrations should be togglable from Feature Control."""
        client = self._login_manager_superuser()
        panel_url = self._manager_panel_url()
        response = client.get(panel_url, HTTP_HOST=MANAGER_HOST)
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
        response = client.post(
            panel_url, data=payload, HTTP_HOST=MANAGER_HOST, follow=True
        )
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        flags = site.backend_feature_flags or {}
        self.assertTrue(flags.get("enable_ministry_api_cartescolaire"))
        self.assertTrue(flags.get("enable_ministry_api_dgi"))
        self.assertTrue(flags.get("enable_ministry_live_sync"))

    @override_settings(**_MANAGER_OVERRIDES)
    def test_backend_experience_flags_and_list_density(self):
        """Backend dashboard module/viz toggles and list density are configurable."""
        client = self._login_manager_superuser()
        panel_url = self._manager_panel_url()
        response = client.get(panel_url, HTTP_HOST=MANAGER_HOST)
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
        response = client.post(
            panel_url, data=payload, HTTP_HOST=MANAGER_HOST, follow=True
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
        # Template copy is "You're not connected right now." (was "You are currently
        # offline"); assert an apostrophe-free substring of the current heading.
        self.assertIn(b"not connected right now", response.content)

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

    @override_settings(**_MANAGER_OVERRIDES)
    def test_feature_control_save_accepts_global_city_ids(self):
        cities = GlobalGeoCatalog.search_cities(
            country_code="JPN", query="Tokyo", limit=5
        )
        self.assertTrue(cities)
        city = cities[0]
        client = self._login_manager_superuser()
        payload = {
            "action": "save",
            "weather_country_code": "JPN",
            "weather_city_id": str(city["id"]),
        }
        response = client.post(
            self._manager_panel_url(),
            data=payload,
            HTTP_HOST=MANAGER_HOST,
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
