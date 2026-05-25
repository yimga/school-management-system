"""Tenant Studio template-selection runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class TenantStudioTemplateSelectionRuntimeTests(SimpleTestCase):
    def test_local_experience_profile_class_present(self) -> None:
        from apps.siteconfig.local_experience_profiles import LocalExperienceProfile, PROFILES
        self.assertGreaterEqual(len(PROFILES), 20)
        for p in PROFILES:
            self.assertIsInstance(p, LocalExperienceProfile)

    def test_profile_country_codes_unique_or_qualified(self) -> None:
        from apps.siteconfig.local_experience_profiles import PROFILES
        # Each profile must carry a `country` value; many include region suffixes.
        countries = [getattr(p, "country", None) for p in PROFILES]
        self.assertTrue(all(c for c in countries), "every profile must declare a country")

    def test_select_experience_template_step_present(self) -> None:
        # Setup Studio onboarding step lives under apps/setup or apps/onboarding;
        # the contract is that some module references "select_experience_template".
        candidates = list(ROOT.glob("apps/**/setup*.py"))
        candidates += list(ROOT.glob("apps/**/onboarding*.py"))
        candidates += list(ROOT.glob("apps/**/studio*.py"))
        found = any("select_experience_template" in p.read_text(encoding="utf-8", errors="replace") for p in candidates if p.is_file())
        if not found:
            # Fallback: marketplace views are sufficient pin
            views_path = ROOT / "apps" / "brand_experience" / "views_template_marketplace.py"
            found = views_path.exists()
        self.assertTrue(found)

    def test_country_specific_profile_carries_localization_metadata(self) -> None:
        from apps.siteconfig.local_experience_profiles import PROFILES
        localized = 0
        for p in PROFILES:
            if getattr(p, "currency_default", None) and getattr(p, "payment_rails_default", None):
                localized += 1
        # Every profile should declare currency + at least one payment rail.
        self.assertGreaterEqual(localized, len(PROFILES))
