"""
World Engine: Tests for module manifest loader and get_school_type_config (inheritance).
Plan: Manifest loader and get_school_type_config with inheritance; get_tenant_modules returns manifest required_apps.
"""

from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.module_manifest import get_manifest, get_school_type_config
from apps.siteconfig.tenant_config import get_tenant_modules


class ModuleManifestLoaderTests(TestCase):
    """get_manifest() and get_school_type_config() with inheritance."""

    def test_get_manifest_returns_dict(self):
        manifest = get_manifest()
        self.assertIsInstance(manifest, dict)
        self.assertIn("BASE_SCHOOL", manifest)
        self.assertIn("TECHNICAL_COLLEGE", manifest)
        self.assertIn("STEM_ACADEMY", manifest)

    def test_base_school_config_has_required_apps(self):
        cfg = get_school_type_config("BASE_SCHOOL")
        self.assertIn("required_apps", cfg)
        apps = cfg["required_apps"]
        self.assertIn("academics", apps)
        self.assertIn("people", apps)
        self.assertIn("evals", apps)
        self.assertIn("reports", apps)
        self.assertIn("finance", apps)
        self.assertIn("communication", apps)

    def test_technical_college_inherits_base_required_apps(self):
        cfg = get_school_type_config("TECHNICAL_COLLEGE")
        apps = cfg.get("required_apps") or []
        # From BASE_SCHOOL
        self.assertIn("academics", apps)
        self.assertIn("people", apps)
        self.assertIn("evals", apps)
        self.assertIn("reports", apps)
        self.assertIn("finance", apps)
        self.assertIn("communication", apps)
        # From TECHNICAL_COLLEGE
        self.assertIn("workshop_tracker", apps)
        self.assertIn("apprenticeship_mgmt", apps)

    def test_stem_academy_inherits_base_required_apps(self):
        cfg = get_school_type_config("STEM_ACADEMY")
        apps = cfg.get("required_apps") or []
        self.assertIn("academics", apps)
        self.assertIn("robotics_lab", apps)
        self.assertIn("project_based_lms", apps)

    def test_unknown_type_returns_base_school_config(self):
        cfg = get_school_type_config("UNKNOWN_TYPE")
        self.assertIn("required_apps", cfg)
        self.assertIn("academics", cfg.get("required_apps") or [])

    def test_empty_type_returns_base_school_config(self):
        cfg = get_school_type_config("")
        self.assertIn("required_apps", cfg)


class GetTenantModulesWithManifestTests(TestCase):
    """get_tenant_modules(school) returns manifest required_apps when school_type is set."""

    def setUp(self):
        from apps.siteconfig.models import RegionConfig

        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CMR",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )

    def test_none_school_returns_empty(self):
        self.assertEqual(get_tenant_modules(None), [])

    def test_school_with_base_school_type_returns_manifest_apps(self):
        school = School.objects.create(
            name="Base School",
            slug="base-manifest-test",
            subdomain="base-manifest-test",
            is_active=True,
            default_region=self.region,
            school_type="BASE_SCHOOL",
        )
        modules = get_tenant_modules(school)
        self.assertIn("academics", modules)
        self.assertIn("people", modules)
        self.assertIn("evals", modules)
        self.assertIn("reports", modules)
        self.assertIn("finance", modules)
        self.assertIn("communication", modules)

    def test_school_with_technical_college_type_includes_manifest_apps(self):
        school = School.objects.create(
            name="Tech College",
            slug="tech-manifest-test",
            subdomain="tech-manifest-test",
            is_active=True,
            default_region=self.region,
            school_type="TECHNICAL_COLLEGE",
        )
        modules = get_tenant_modules(school)
        self.assertIn("academics", modules)
        self.assertIn("workshop_tracker", modules)
        self.assertIn("apprenticeship_mgmt", modules)

    def test_school_with_stem_academy_type_includes_manifest_apps(self):
        school = School.objects.create(
            name="STEM Academy",
            slug="stem-manifest-test",
            subdomain="stem-manifest-test",
            is_active=True,
            default_region=self.region,
            school_type="STEM_ACADEMY",
        )
        modules = get_tenant_modules(school)
        self.assertIn("academics", modules)
        self.assertIn("robotics_lab", modules)
        self.assertIn("project_based_lms", modules)
