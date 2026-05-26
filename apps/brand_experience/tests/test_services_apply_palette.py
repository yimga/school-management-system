"""Per-domain integration tests for apps.brand_experience.services.

Covers ``apply_palette`` + ``install_brand_assets`` — the helpers the Unified
Wizard Framework's whitelabel writer calls via ``_try_domain_integration``.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.brand_experience import services
from apps.schools.models import School
from apps.siteconfig.models_global_experience import BrandProfile


class ApplyPaletteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Palette School",
            slug="palette-school",
            subdomain="palette-school",
            is_active=True,
        )

    def test_apply_palette_creates_brand_profile_and_writes_fields(self):
        self.assertFalse(BrandProfile.objects.filter(school=self.school).exists())

        ok = services.apply_palette(
            self.school,
            palette_key="kerala_heritage_emerald",
            primary_color_hex="#0D7A4D",
            secondary_color_hex="#F4B840",
            type_scale_anchor="comfortable",
        )
        self.assertTrue(ok)

        profile = BrandProfile.objects.get(school=self.school)
        self.assertEqual(profile.primary_color, "#0D7A4D")
        self.assertEqual(profile.secondary_color, "#F4B840")
        self.assertEqual(profile.tokens.get("palette_key"), "kerala_heritage_emerald")
        self.assertEqual(profile.tokens.get("type_scale_anchor"), "comfortable")

    def test_apply_palette_partial_inputs_skip_empty(self):
        """None / blank inputs do NOT clobber existing values."""
        BrandProfile.objects.create(
            school=self.school,
            primary_color="#111111",
            secondary_color="#222222",
            tokens={"palette_key": "preexisting", "type_scale_anchor": "spacious"},
        )

        ok = services.apply_palette(
            self.school,
            primary_color_hex="#FF00FF",  # only primary
        )
        self.assertTrue(ok)

        profile = BrandProfile.objects.get(school=self.school)
        self.assertEqual(profile.primary_color, "#FF00FF")
        self.assertEqual(profile.secondary_color, "#222222")  # preserved
        self.assertEqual(profile.tokens.get("palette_key"), "preexisting")
        self.assertEqual(profile.tokens.get("type_scale_anchor"), "spacious")

    def test_apply_palette_no_inputs_returns_false(self):
        ok = services.apply_palette(self.school)
        self.assertFalse(ok)

    def test_apply_palette_none_school_returns_false(self):
        self.assertFalse(
            services.apply_palette(None, primary_color_hex="#0D7A4D")
        )


class InstallBrandAssetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Asset School",
            slug="asset-school",
            subdomain="asset-school",
            is_active=True,
        )

    def test_install_brand_assets_records_filename_and_size(self):
        logo = SimpleUploadedFile("logo.png", b"x" * 512, content_type="image/png")
        favicon = SimpleUploadedFile("favicon.ico", b"x" * 1024, content_type="image/x-icon")

        ok = services.install_brand_assets(
            self.school,
            logo=logo,
            favicon=favicon,
            alt_text="School logo",
        )
        self.assertTrue(ok)

        profile = BrandProfile.objects.get(school=self.school)
        self.assertEqual(profile.assets["logo"]["name"], "logo.png")
        self.assertEqual(profile.assets["logo"]["size"], 512)
        self.assertEqual(profile.assets["favicon"]["name"], "favicon.ico")
        self.assertEqual(profile.assets["favicon"]["size"], 1024)
        self.assertEqual(profile.assets["alt_text"], "School logo")

    def test_install_brand_assets_string_filename_records_name_only(self):
        ok = services.install_brand_assets(self.school, logo="standalone-logo.svg")
        self.assertTrue(ok)
        profile = BrandProfile.objects.get(school=self.school)
        self.assertEqual(profile.assets["logo"], {"name": "standalone-logo.svg"})

    def test_install_brand_assets_no_inputs_returns_false(self):
        self.assertFalse(services.install_brand_assets(self.school))

    def test_install_brand_assets_none_school_returns_false(self):
        self.assertFalse(services.install_brand_assets(None, logo="x.png"))
