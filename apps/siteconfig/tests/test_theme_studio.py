from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from config.admin import admin_site
from apps.siteconfig.context_processors import site_settings
from apps.siteconfig.models import SiteSettings, ThemePack
from apps.siteconfig.admin import ThemePackAdmin


User = get_user_model()


class ThemeStudioAccessTests(TestCase):
    def setUp(self):
        self.url = reverse("siteconfig:theme_colors")
        self.user = User.objects.create_user(
            username="theme-user",
            email="theme-user@example.com",
            password="password",
        )
        self.manager = User.objects.create_user(
            username="theme-manager",
            email="theme-manager@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.manager.feature_permissions.add(manage_perm)

    def test_theme_studio_requires_settings_manage_permission(self):
        self.client.login(username="theme-user", password="password")
        response = self.client.get(self.url, follow=True)
        self.assertIn(response.status_code, (403, 200))
        if response.status_code == 200:
            self.assertTrue(
                any("/authentication/login/" in redirect for redirect, _code in response.redirect_chain),
                "Expected redirect to login for users without settings.manage permission.",
            )

    def test_theme_studio_allows_user_with_settings_manage_permission(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            any("/authentication/login/" in redirect for redirect, _code in response.redirect_chain),
            "User with settings.manage should not be redirected to login.",
        )


class ThemeResolutionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = SiteSettings.get_solo()
        self.admin_pack = ThemePack.objects.create(
            name="Admin Theme",
            slug="admin-theme-resolution-test",
            primary_color="#111111",
            accent_color="#222222",
            background_color="#0f172a",
            applies_to_admin=True,
            is_active=True,
        )
        self.site.primary_color = "#123456"
        self.site.accent_color = "#654321"
        self.site.admin_theme_pack = self.admin_pack
        self.site.save()

    def _context(self):
        request = self.factory.get("/admin/")
        request.user = AnonymousUser()
        request.session = {}
        return site_settings(request)

    def test_admin_use_site_primary_true_forces_site_colors(self):
        self.site.admin_use_site_primary = True
        self.site.save(update_fields=["admin_use_site_primary"])

        ctx = self._context()
        self.assertEqual(ctx["ADMIN_RESOLVED_PRIMARY"], "#123456")
        self.assertEqual(ctx["ADMIN_RESOLVED_ACCENT"], "#654321")

    def test_admin_use_site_primary_false_uses_admin_pack_colors(self):
        self.site.admin_use_site_primary = False
        self.site.save(update_fields=["admin_use_site_primary"])

        ctx = self._context()
        self.assertEqual(ctx["ADMIN_RESOLVED_PRIMARY"], "#111111")
        self.assertEqual(ctx["ADMIN_RESOLVED_ACCENT"], "#222222")


class ThemePackSelectorTemplateTests(TestCase):
    def test_selector_renders_themepack_datasets_for_apply_engine(self):
        pack = ThemePack.objects.create(
            name="Selector Pack",
            slug="selector-pack",
            primary_color="#0d6efd",
            accent_color="#198754",
            background_color="#f8fafc",
            applies_to_admin=True,
            is_active=True,
            palette={
                "admin_dashboard": {
                    "primary": "#0d6efd",
                    "accent": "#198754",
                    "dashboard_bg": "#f8fafc",
                    "surface": "#ffffff",
                    "success": "#22c55e",
                    "warning": "#f59e0b",
                    "danger": "#ef4444",
                }
            },
        )

        html = render_to_string(
            "admin/components/admin_dashboard_palette_selector.html",
            {
                "admin_theme_packs": [pack],
                "admin_theme_packs_by_group": [("Test Group", [pack])],
            },
        )

        self.assertIn("theme-pack-auto-apply", html)
        self.assertIn("data-success=\"#22c55e\"", html)
        self.assertIn("data-warning=\"#f59e0b\"", html)
        self.assertIn("data-danger=\"#ef4444\"", html)


class ThemeStudioSingleSurfaceTests(TestCase):
    def test_sitesettings_theme_fieldset_is_launcher_only(self):
        model_admin = admin_site._registry[SiteSettings]
        theme_fieldset = next(
            config for title, config in model_admin.fieldsets if title == "Theme & Experience"
        )
        self.assertEqual(theme_fieldset["fields"], ("theme_color_tools_link_block",))

    def test_theme_launcher_uses_back_link_with_stay_theme_flag(self):
        model_admin = admin_site._registry[SiteSettings]
        site = SiteSettings.get_solo()
        html = model_admin.theme_color_tools_link_block(site)
        self.assertIn("stay_theme%3D1", html)

    def test_themepack_admin_hidden_from_system_configuration_menu(self):
        model_admin = admin_site._registry[ThemePack]
        self.assertIsInstance(model_admin, ThemePackAdmin)
        request = RequestFactory().get("/admin/")
        perms = model_admin.get_model_perms(request)
        self.assertEqual(perms, {})
