from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.brand_experience.models import PlatformGlobalBranding, ThemePack
from apps.siteconfig.models import SiteSettings


class NormalizeUIConfigCommandTests(TestCase):
    def setUp(self):
        SiteSettings.objects.all().delete()
        ThemePack.objects.all().delete()
        PlatformGlobalBranding.objects.all().delete()

    def _ensure_site(self):
        SiteSettings.objects.get_or_create(pk=1)

    def test_sets_site_theme_as_single_default(self):
        self._ensure_site()
        t1 = ThemePack.objects.create(name="Theme A", slug="theme-a", is_default=False)
        t2 = ThemePack.objects.create(name="Theme B", slug="theme-b", is_default=False)
        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
        pgb.theme_pack = t2
        pgb.save()

        out = StringIO()
        call_command("normalize_ui_config", stdout=out)

        t1.refresh_from_db()
        t2.refresh_from_db()
        pgb.refresh_from_db()

        self.assertFalse(t1.is_default)
        self.assertTrue(t2.is_default)
        self.assertEqual(pgb.theme_pack_id, t2.pk)

    def test_pins_admin_theme_when_site_theme_is_not_admin_capable(self):
        self._ensure_site()
        site_theme = ThemePack.objects.create(
            name="Site Theme",
            slug="site-theme",
            is_default=True,
            applies_to_admin=False,
            is_active=True,
        )
        admin_theme = ThemePack.objects.create(
            name="Admin Theme",
            slug="admin-theme",
            applies_to_admin=True,
            is_active=True,
            is_default=False,
        )
        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
        pgb.theme_pack = site_theme
        pgb.admin_theme_pack = None
        pgb.save()

        call_command("normalize_ui_config")
        pgb.refresh_from_db()

        self.assertEqual(pgb.admin_theme_pack_id, admin_theme.pk)

    def test_replaces_inactive_site_theme_with_active_theme(self):
        self._ensure_site()
        inactive = ThemePack.objects.create(
            name="Inactive Theme",
            slug="inactive-theme",
            is_default=True,
            is_active=False,
        )
        active = ThemePack.objects.create(
            name="Active Theme",
            slug="active-theme",
            is_default=False,
            is_active=True,
        )
        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
        pgb.theme_pack = inactive
        pgb.save()

        call_command("normalize_ui_config")
        pgb.refresh_from_db()
        active.refresh_from_db()
        inactive.refresh_from_db()

        self.assertEqual(pgb.theme_pack_id, active.pk)
        self.assertTrue(active.is_default)
        self.assertFalse(inactive.is_default)

    def test_replaces_invalid_admin_theme_with_admin_capable_fallback(self):
        self._ensure_site()
        site_theme = ThemePack.objects.create(
            name="Site Theme",
            slug="site-theme-2",
            is_default=True,
            is_active=True,
            applies_to_admin=False,
        )
        invalid_admin = ThemePack.objects.create(
            name="Invalid Admin Theme",
            slug="invalid-admin-theme",
            is_default=False,
            is_active=True,
            applies_to_admin=False,
        )
        valid_admin = ThemePack.objects.create(
            name="Valid Admin Theme",
            slug="valid-admin-theme",
            is_default=False,
            is_active=True,
            applies_to_admin=True,
        )
        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
        pgb.theme_pack = site_theme
        pgb.admin_theme_pack = invalid_admin
        pgb.save()

        call_command("normalize_ui_config")
        pgb.refresh_from_db()

        self.assertEqual(pgb.admin_theme_pack_id, valid_admin.pk)
