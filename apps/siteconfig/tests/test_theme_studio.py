import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.brand_experience.models import ThemePack
from apps.runtime_blueprints.models import ReportCardStyle
from config.admin import tenant_admin_site
from apps.siteconfig.context_processors import site_settings
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.forms import THEME_PUBLISH_GUARDED_FIELDS, ThemeColorsForm
from apps.siteconfig.models import SiteSettings
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

    def _theme_form_payload(self, **overrides):
        site = get_platform_site_settings_record(create=True)
        payload = {}
        form = ThemeColorsForm(instance=site)
        for field_name in ThemeColorsForm.Meta.fields:
            value = form.initial.get(field_name, getattr(site, field_name, ""))
            if hasattr(value, "pk"):
                value = value.pk
            if isinstance(value, bool):
                if value:
                    payload[field_name] = "on"
                continue
            if isinstance(value, (dict, list)):
                payload[field_name] = json.dumps(value)
            elif value in (None, ""):
                payload[field_name] = ""
            else:
                payload[field_name] = str(value)

        payload.update(overrides)
        for field_name, value in list(payload.items()):
            if value is False:
                payload.pop(field_name, None)
        return payload

    def test_theme_studio_requires_settings_manage_permission(self):
        self.client.login(username="theme-user", password="password")
        response = self.client.get(self.url, follow=True)
        self.assertIn(response.status_code, (403, 200))
        if response.status_code == 200:
            self.assertTrue(
                any(
                    "/authentication/login/" in redirect
                    for redirect, _code in response.redirect_chain
                ),
                "Expected redirect to login for users without settings.manage permission.",
            )

    def test_theme_studio_allows_user_with_settings_manage_permission(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            any(
                "/authentication/login/" in redirect
                for redirect, _code in response.redirect_chain
            ),
            "User with settings.manage should not be redirected to login.",
        )

    def test_theme_studio_catalog_includes_active_non_admin_pack(self):
        ThemePack.objects.create(
            name="Portal Pack",
            slug="portal-pack-theme-studio",
            primary_color="#3366ff",
            accent_color="#22aa88",
            is_active=True,
            applies_to_admin=False,
        )
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal Pack")

    def test_theme_colors_form_admin_pack_queryset_excludes_non_admin_packs(self):
        non_admin_pack = ThemePack.objects.create(
            name="Non Admin Pack",
            slug="non-admin-pack-theme-studio",
            primary_color="#334155",
            accent_color="#22d3ee",
            is_active=True,
            applies_to_admin=False,
        )
        form = ThemeColorsForm(instance=get_platform_site_settings_record(create=True))
        admin_ids = set(
            form.fields["admin_theme_pack"].queryset.values_list("id", flat=True)
        )
        theme_ids = set(form.fields["theme_pack"].queryset.values_list("id", flat=True))
        self.assertNotIn(non_admin_pack.id, admin_ids)
        self.assertIn(non_admin_pack.id, theme_ids)

    def test_theme_studio_rejects_non_admin_pack_for_admin_theme_field(self):
        non_admin_pack = ThemePack.objects.create(
            name="Non Admin Submit Pack",
            slug="non-admin-submit-pack-theme-studio",
            primary_color="#0f172a",
            accent_color="#ef4444",
            is_active=True,
            applies_to_admin=False,
        )
        self.client.login(username="theme-manager", password="password")
        payload = self._theme_form_payload(
            admin_theme_pack=str(non_admin_pack.id),
            preview_confirmed="1",
        )
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        site = get_platform_site_settings_record(create=True)
        self.assertNotEqual(site.admin_theme_pack_id, non_admin_pack.id)

    def test_theme_studio_renders_admin_use_site_primary_guard(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-use-site-primary-guard")

    def test_theme_studio_renders_active_state_strip(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "theme-draft-status-badge")
        self.assertContains(response, "theme-contrast-status-badge")
        self.assertContains(response, "theme-active-source")
        self.assertContains(response, "theme-active-site-pack")
        self.assertContains(response, "theme-active-admin-pack")
        self.assertContains(response, "theme-pack-parity-note")
        self.assertContains(response, "theme-last-saved-meta")
        self.assertContains(response, "theme-publish-governor-note")
        self.assertContains(response, "theme-last-change-audit")
        self.assertContains(response, "theme-preview-confirmed")
        self.assertContains(response, "cps-keep-theme-pack")
        self.assertContains(response, "cps-active-preset-note")

    def test_theme_studio_color_palette_starts_collapsed_for_compact_layout(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="cps-body" style="display: none;"')

    def test_theme_studio_blocks_publish_without_preview_for_governed_changes(self):
        self.client.login(username="theme-manager", password="password")
        site = get_platform_site_settings_record(create=True)
        payload = self._theme_form_payload(
            primary_color="#111111",
            accent_color="#047857",
        )
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        site.refresh_from_db()
        self.assertNotEqual(site.primary_color, "#111111")

        self.assertContains(response, "theme-last-change-audit")

    def test_theme_studio_allows_publish_when_preview_confirmed(self):
        self.client.login(username="theme-manager", password="password")
        payload = self._theme_form_payload(
            primary_color="#1e3a8a",
            accent_color="#047857",
            preview_confirmed="1",
        )
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        site = get_platform_site_settings_record(create=True)
        self.assertEqual(site.primary_color, "#1e3a8a")
        self.assertContains(response, "theme-last-change-audit")

        self.assertContains(response, "theme-last-change-audit")

    def test_theme_studio_blocks_report_style_default_change_without_preview_confirmation(
        self,
    ):
        style_a = ReportCardStyle.objects.create(
            slug="report-style-a-theme-guard",
            name="Report Style A",
            term_template="reports/term_report_cameroon_modern.html",
            annual_template="reports/annual_report_cameroon_modern.html",
            primary_color="#0d173b",
            accent_color="#007bff",
            is_active=True,
        )
        style_b = ReportCardStyle.objects.create(
            slug="report-style-b-theme-guard",
            name="Report Style B",
            term_template="reports/term_report_cameroon_modern.html",
            annual_template="reports/annual_report_cameroon_modern.html",
            primary_color="#2d4739",
            accent_color="#76a665",
            is_active=True,
        )
        site = get_platform_site_settings_record(create=True)
        site.default_term_report_style = style_a
        site.save(update_fields=["default_term_report_style"])

        self.client.login(username="theme-manager", password="password")
        payload = self._theme_form_payload(
            default_term_report_style=str(style_b.id),
            primary_color="#0d173b",
            accent_color="#007bff",
            header_bg_color="#0d173b",
            footer_bg_color="#0f172a",
            success_color="#22c55e",
            warning_color="#fbbf24",
            danger_color="#ef4444",
        )
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        site.refresh_from_db()
        self.assertEqual(site.default_term_report_style_id, style_a.id)
        self.assertContains(response, "Live preview confirmation is required")

    def test_theme_publish_guarded_fields_include_report_style_defaults(self):
        self.assertIn("default_term_report_style", THEME_PUBLISH_GUARDED_FIELDS)
        self.assertIn("default_annual_report_style", THEME_PUBLISH_GUARDED_FIELDS)

    def test_theme_studio_catalog_uses_compact_scroll_region(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "theme-pack-catalog-scroll")
        self.assertContains(response, "theme-pack-catalog-hint")
        self.assertContains(response, "min(44vh, 340px)")

    def test_theme_studio_catalog_shows_active_site_and_admin_labels(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "theme-pack-active-site-label")
        self.assertContains(response, "theme-pack-active-admin-label")

    def test_theme_studio_renders_enhanced_device_preview_layout(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "preview-metrics-grid")
        self.assertContains(response, "preview-chart-bars")
        self.assertContains(response, 'data-preview-mode="mobile"')

    def test_theme_studio_auto_seeds_catalog_when_admin_packs_missing(self):
        ThemePack.objects.all().delete()
        ThemePack.objects.create(
            name="Minimal Starter",
            slug="minimal-starter-pack",
            primary_color="#1d4ed8",
            accent_color="#0ea5e9",
            is_active=True,
            applies_to_admin=False,
        )
        self.client.login(username="theme-manager", password="password")

        with patch("apps.siteconfig.views.call_command") as mocked_call_command:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mocked_call_command.assert_called_once_with("seed_admin_dashboard_palettes")

    def test_legacy_theme_experience_route_redirects_to_theme_studio(self):
        self.client.login(username="theme-manager", password="password")
        response = self.client.get(
            reverse("siteconfig:theme_experience_redirect"),
            {
                "next": "/admin/siteconfig/sitesettings/1/change/#section-theme-experience"
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("siteconfig:theme_colors"), response.url)
        self.assertIn(
            "next=%2Fadmin%2Fsiteconfig%2Fsitesettings%2F1%2Fchange%2F%23section-theme-experience",
            response.url,
        )


class ThemeResolutionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = get_platform_site_settings_record(create=True)
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

    def test_site_settings_theme_resolution_prefers_brand_experience_owner_surface(
        self,
    ):
        self.site.theme_pack = self.admin_pack
        self.site.save(update_fields=["theme_pack"])

        resolved = self.site.active_theme

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved._meta.app_label, "brand_experience")

    def test_get_admin_theme_uses_owner_theme_selection_surface(self):
        resolved = self.site.get_admin_theme()

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, self.admin_pack.pk)

    def test_theme_colors_form_initials_use_theme_experience_settings(self):
        self.site.skip_theme_publish_guard = True
        self.site.default_refresh_rate = 75
        self.site.save(
            update_fields=["skip_theme_publish_guard", "default_refresh_rate"]
        )

        form = ThemeColorsForm(instance=self.site)

        self.assertTrue(form.initial["skip_theme_publish_guard"])
        self.assertEqual(form.initial["default_refresh_rate"], 75)

    def test_theme_colors_form_save_uses_theme_experience_write_contract(self):
        form = ThemeColorsForm(instance=self.site)
        payload = {}
        for field_name in ThemeColorsForm.Meta.fields:
            value = form.initial.get(field_name, getattr(self.site, field_name, ""))
            if hasattr(value, "pk"):
                value = value.pk
            if isinstance(value, bool):
                if value:
                    payload[field_name] = "on"
                continue
            if isinstance(value, (dict, list)):
                payload[field_name] = json.dumps(value)
            elif value in (None, ""):
                payload[field_name] = ""
            else:
                payload[field_name] = str(value)
        payload["primary_color"] = "#1e3a8a"
        payload["accent_color"] = "#047857"

        form = ThemeColorsForm(payload, instance=self.site)
        self.assertTrue(form.is_valid(), form.errors)

        with patch.object(
            self.site,
            "apply_theme_experience_state",
            wraps=self.site.apply_theme_experience_state,
        ) as mocked_apply:
            saved = form.save()

        self.assertEqual(saved.pk, self.site.pk)
        mocked_apply.assert_called_once()
        kwargs = mocked_apply.call_args.kwargs
        self.assertTrue(kwargs["save"])
        self.assertEqual(kwargs["field_updates"]["primary_color"], "#1e3a8a")
        self.assertEqual(kwargs["field_updates"]["accent_color"], "#047857")

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
        site = get_platform_site_settings_record(create=True)
        site.theme_pack = pack
        site.admin_theme_pack = pack
        site.save(update_fields=["theme_pack", "admin_theme_pack"])

        html = render_to_string(
            "admin/components/admin_dashboard_palette_selector.html",
            {
                "admin_theme_packs": [pack],
                "admin_theme_packs_by_group": [("Test Group", [pack])],
                "site_settings": site,
            },
        )

        self.assertIn("theme-pack-auto-apply", html)
        self.assertIn("theme-pack-apply-site", html)
        self.assertIn("theme-pack-filter", html)
        self.assertIn('data-site-active="1"', html)
        self.assertIn('data-admin-active="1"', html)
        self.assertIn("Site active", html)
        self.assertIn("Admin active", html)
        self.assertIn('data-success="#22c55e"', html)
        self.assertIn('data-warning="#f59e0b"', html)
        self.assertIn('data-danger="#ef4444"', html)


class ThemeStudioSingleSurfaceTests(TestCase):
    def test_sitesettings_theme_fieldset_is_launcher_only(self):
        model_admin = tenant_admin_site._registry[SiteSettings]
        theme_fieldset = next(
            config
            for title, config in model_admin.fieldsets
            if title == "Theme & Experience"
        )
        self.assertEqual(theme_fieldset["fields"], ("theme_color_tools_link_block",))

    def test_sitesettings_branding_fieldset_does_not_expose_theme_pack_editor(self):
        model_admin = tenant_admin_site._registry[SiteSettings]
        branding_fieldset = next(
            config for title, config in model_admin.fieldsets if title == "Branding"
        )
        self.assertNotIn("theme_pack", branding_fieldset["fields"])

    def test_theme_launcher_uses_back_link_with_stay_theme_flag(self):
        model_admin = tenant_admin_site._registry[SiteSettings]
        site = get_platform_site_settings_record(create=True)
        html = model_admin.theme_color_tools_link_block(site)
        self.assertIn("stay_theme%3D1", html)

    def test_themepack_admin_hidden_from_system_configuration_menu(self):
        model_admin = tenant_admin_site._registry[ThemePack]
        self.assertIsInstance(model_admin, ThemePackAdmin)
        request = RequestFactory().get("/admin/")
        perms = model_admin.get_model_perms(request)
        self.assertEqual(perms, {})

    def test_themepack_admin_changeform_redirects_to_theme_studio(self):
        model_admin = tenant_admin_site._registry[ThemePack]
        request = RequestFactory().get("/admin/siteconfig/themepack/1/change/")
        response = model_admin.changeform_view(request, object_id="1")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("siteconfig:theme_colors"))


class ThemeStudioApplyScriptTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.node_binary = shutil.which("node")
        cls.script_path = (
            Path(settings.BASE_DIR) / "static" / "js" / "theme-studio-apply.js"
        )

    def test_apply_from_dataset_sets_admin_and_site_pack_when_enabled(self):
        if not self.node_binary:
            self.skipTest("Node.js is required for JS behavior regression tests.")

        node_test_script = r"""
const fs = require('fs');
const vm = require('vm');

const scriptPath = process.argv[1];

function makeSelect(id) {
  return {
    id,
    value: '',
    events: [],
    dispatchEvent(ev) {
      this.events.push(ev && ev.type ? ev.type : 'unknown');
      return true;
    }
  };
}

const elements = {
  id_admin_theme_pack: makeSelect('id_admin_theme_pack'),
  id_theme_pack: makeSelect('id_theme_pack')
};

const document = {
  getElementById(id) {
    return elements[id] || null;
  },
  querySelector() {
    return null;
  }
};

const window = {};
function Event(type, opts) {
  this.type = type;
  this.bubbles = !!(opts && opts.bubbles);
}

const context = { window, document, Event, console };
vm.createContext(context);
vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context);

context.window.ThemeStudio.applyFromDataset(
  { packId: '42' },
  { setPack: true, setSitePack: true }
);

if (elements.id_admin_theme_pack.value !== '42') {
  throw new Error('Admin theme pack was not set by applyFromDataset');
}
if (elements.id_theme_pack.value !== '42') {
  throw new Error('Site theme pack was not set by setSitePack');
}
if (!elements.id_admin_theme_pack.events.includes('change')) {
  throw new Error('Admin theme pack change event was not dispatched');
}
if (!elements.id_theme_pack.events.includes('change')) {
  throw new Error('Site theme pack change event was not dispatched');
}

console.log('ok');
"""
        completed = subprocess.run(
            [self.node_binary, "-e", node_test_script, str(self.script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"Node regression test failed.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
        )
        self.assertIn("ok", completed.stdout.strip())
