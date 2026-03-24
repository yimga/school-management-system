"""Phase B Batch 1: PlatformGlobalBranding singleton sync and resolver merge."""

from django.test import TestCase

from apps.brand_experience.models import PlatformGlobalBranding, ThemePack
from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)


class PlatformGlobalBrandingSyncTests(TestCase):
    def test_apply_theme_experience_state_writes_theme_pack_to_branding_singleton(self):
        site = get_platform_site_settings_record(create=True)
        pack = ThemePack.objects.create(
            name="Sync Test Pack",
            slug="sync-test-pack",
            is_active=True,
        )
        site.apply_theme_experience_state(
            field_updates={"theme_pack": pack},
            save=True,
        )

        row = PlatformGlobalBranding.objects.get(pk=1)
        self.assertEqual(row.theme_pack_id, pack.pk)

    def test_effective_site_settings_prefers_platform_global_branding(self):
        site = get_platform_site_settings_record(create=True)
        pack_a = ThemePack.objects.create(
            name="Pack A",
            slug="pack-a-pgb",
            is_active=True,
        )
        pack_b = ThemePack.objects.create(
            name="Pack B",
            slug="pack-b-pgb",
            is_active=True,
        )
        site.apply_theme_experience_state(
            field_updates={"theme_pack": pack_a},
            save=True,
        )

        row = PlatformGlobalBranding.objects.get(pk=1)
        row.theme_pack = pack_b
        row.save(update_fields=["theme_pack"])

        invalidate_effective_site_settings_cache()
        resolved = get_effective_site_settings()
        self.assertEqual(resolved.theme_pack_id, pack_b.pk)


class VerifyPhaseBHelpersTests(TestCase):
    def test_merge_runs_without_error_when_row_missing(self):
        PlatformGlobalBranding.objects.filter(pk=1).delete()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        from apps.brand_experience.branding_singleton_sync import (
            merge_platform_global_branding_into_base,
        )
        from copy import copy

        base = copy(site)
        merge_platform_global_branding_into_base(base)
        # No row: base unchanged for theme (still from copy)
        self.assertEqual(base.theme_pack_id, site.theme_pack_id)
