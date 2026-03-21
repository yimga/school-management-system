from django.test import TestCase

from apps.brand_experience.experience_packs import (
    compare_experience_packs,
    get_effective_experience_pack,
    resolve_experience_theme_pack,
    rollback_experience_pack,
)
from apps.brand_experience.models import ThemePack
from apps.packages.models import ExperiencePack, InstalledPackage, PackageChangeLog
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School
from apps.siteconfig.branding import resolve_brand_profile


class ExperiencePackServiceTests(TestCase):
    def setUp(self):
        self.portal_theme = ThemePack.objects.create(
            name="Portal Theme", slug="portal-theme", is_active=True
        )
        self.fallback_theme = ThemePack.objects.create(
            name="Fallback Theme", slug="fallback-theme", is_active=True
        )
        self.school = School.objects.create(
            name="Experience Academy",
            slug="experience-academy",
            subdomain="experience-academy",
            is_active=True,
            settings={"experience_pack_code": "exp-portal"},
        )
        self.pack = ExperiencePack.objects.create(
            code="exp-portal",
            name="Portal Experience",
            theme_pack_id=self.portal_theme.pk,
            layout_schema={"sections": [{"code": "hero"}]},
            communication_style={"tone": "warm"},
            is_active=True,
        )
        self.alt_pack = ExperiencePack.objects.create(
            code="exp-ops",
            name="Ops Experience",
            theme_pack_id=self.fallback_theme.pk,
            layout_schema={"sections": [{"code": "metrics"}]},
            communication_style={"tone": "formal"},
            is_active=True,
        )

    def test_get_effective_experience_pack_uses_school_settings(self):
        resolved = get_effective_experience_pack(self.school)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.code, "exp-portal")

    def test_resolve_experience_theme_pack_is_used_by_branding(self):
        site = get_platform_site_settings_record(create=True)
        site.theme_pack_id = self.fallback_theme.pk
        site.save(update_fields=["theme_pack_id"])

        resolved_theme = resolve_experience_theme_pack(self.school)
        brand = resolve_brand_profile(school=self.school, site=site)

        self.assertIsNotNone(resolved_theme)
        self.assertEqual(resolved_theme.pk, self.portal_theme.pk)
        self.assertEqual(brand["theme_pack_id"], self.portal_theme.pk)

    def test_compare_experience_packs_reports_changed_sections(self):
        comparison = compare_experience_packs(self.pack, self.alt_pack)
        self.assertEqual(comparison["base_code"], "exp-portal")
        self.assertIn("theme_pack_id", comparison["changed_sections"])
        self.assertIn("layout_schema", comparison["changes"])

    def test_rollback_experience_pack_deactivates_installed_package(self):
        installed = InstalledPackage.objects.create(
            package_id=self.pack.code,
            package_type="theme",
            version="1.0.0",
            school=self.school,
            scope="tenant",
            is_active=True,
        )

        result = rollback_experience_pack(self.school)

        installed.refresh_from_db()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["rolled_back"])
        self.assertFalse(installed.is_active)
        self.assertEqual(
            PackageChangeLog.objects.filter(
                package_id=self.pack.code, action="rollback"
            ).count(),
            1,
        )

    def test_rollback_experience_pack_deactivates_exp_pack_prefixed_row(self):
        InstalledPackage.objects.create(
            package_id="exp-pack:exp-portal",
            package_type="experience_pack",
            version="1.0.0",
            school=self.school,
            scope="tenant",
            is_active=True,
        )
        result = rollback_experience_pack(self.school)
        self.assertTrue(result["ok"], result)
        self.assertFalse(
            InstalledPackage.objects.filter(
                school=self.school,
                package_id="exp-pack:exp-portal",
                is_active=True,
            ).exists()
        )
        self.assertGreaterEqual(
            PackageChangeLog.objects.filter(
                package_id="exp-pack:exp-portal", action="rollback"
            ).count(),
            1,
        )
