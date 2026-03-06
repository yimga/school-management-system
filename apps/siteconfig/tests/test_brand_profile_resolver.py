from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.branding import brand_css_vars, resolve_brand_profile
from apps.siteconfig.models import BrandProfile, BrandSettings, SiteSettings


class BrandProfileResolverTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.get_solo()
        self.site.primary_color = "#101820"
        self.site.accent_color = "#ff6f00"
        self.site.tagline = "Platform default"
        self.site.save()
        self.school = School.objects.create(
            name="Resolver School",
            slug="resolver-school",
            subdomain="resolver-school",
            is_active=True,
            primary_color="#223344",
            accent_color="#445566",
            logo_url="https://legacy.example/logo.png",
        )

    def test_brand_profile_overrides_legacy_brand_sources(self):
        BrandSettings.objects.create(
            school=self.school,
            logo_url="https://legacy-brand.example/logo.png",
            primary_color="#112233",
            accent_color="#334455",
            custom_css=".legacy { color: red; }",
        )
        BrandProfile.objects.create(
            school=self.school,
            logo_url="https://brand-profile.example/logo.svg",
            favicon_url="https://brand-profile.example/favicon.ico",
            primary_color="#abcdef",
            accent_color="#fedcba",
            font_family="IBM Plex Sans",
            tokens={"primary": "#abcdef", "accent": "#fedcba"},
            custom_css=".brand { color: blue; }",
        )

        brand = resolve_brand_profile(school=self.school, site=self.site)

        self.assertEqual(brand["source"], "brand_profile")
        self.assertEqual(brand["logo_url"], "https://brand-profile.example/logo.svg")
        self.assertEqual(brand["favicon_url"], "https://brand-profile.example/favicon.ico")
        self.assertEqual(brand["primary_color"], "#abcdef")
        self.assertEqual(brand["accent_color"], "#fedcba")
        self.assertEqual(brand["font_family"], "IBM Plex Sans")
        self.assertIn("--primary: #abcdef;", brand_css_vars(brand))
        self.assertIn("--accent: #fedcba;", brand_css_vars(brand))

    def test_school_fields_backfill_when_brand_profile_missing(self):
        brand = resolve_brand_profile(school=self.school, site=self.site)

        self.assertEqual(brand["source"], "school")
        self.assertEqual(brand["logo_url"], "https://legacy.example/logo.png")
        self.assertEqual(brand["primary_color"], "#223344")
        self.assertEqual(brand["accent_color"], "#445566")
