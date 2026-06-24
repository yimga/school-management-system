from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.education_profile_engine import (
    ensure_country_profile,
    ensure_region_for_country,
    find_region_for_country,
    list_profile_options,
    resolve_profile_for_school,
)
from apps.siteconfig.models import EducationSystemProfile, RegionConfig


class EducationProfileEngineTests(TestCase):
    @staticmethod
    def _uganda_region():
        """Avoid hard dependency on seed data; keep tests decoupled from fixture ordering."""
        existing = RegionConfig.objects.filter(code="UGA").first()
        if existing:
            return existing
        return ensure_region_for_country("UGA")

    def test_ensure_region_for_country_creates_region(self):
        region = ensure_region_for_country("JP")
        self.assertIsNotNone(region)
        self.assertEqual(region.code, "JPN")
        self.assertTrue(region.name)

    def test_find_region_for_country_resolves_alpha2_without_creating(self):
        ensure_region_for_country("US")
        before = RegionConfig.objects.filter(code="USA").count()
        found = find_region_for_country("US")
        self.assertIsNotNone(found)
        self.assertEqual(found.code, "USA")
        self.assertEqual(RegionConfig.objects.filter(code="USA").count(), before)

    def test_find_region_for_country_resolves_alpha3(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="CMR", defaults={"name": "Cameroon"}
        )
        found = find_region_for_country("CMR")
        self.assertIsNotNone(found)
        self.assertEqual(found.code, region.code)

    def test_find_region_for_country_returns_none_for_missing_or_blank(self):
        self.assertIsNone(find_region_for_country(""))
        self.assertIsNone(find_region_for_country("   "))
        self.assertIsNone(find_region_for_country("ZZ"))

    def test_find_region_for_country_never_creates_row(self):
        count_before = RegionConfig.objects.count()
        self.assertIsNone(find_region_for_country("JP"))
        self.assertEqual(RegionConfig.objects.count(), count_before)

    def test_ensure_country_profile_creates_auto_pack(self):
        region = ensure_region_for_country("JPN")
        profile = ensure_country_profile(
            region=region, sub_system=EducationSystemProfile.SubSystem.EN
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.code, "jpn-en-auto")
        self.assertEqual(profile.region_id, "JPN")
        self.assertTrue((profile.config or {}).get("generated"))

    def test_ensure_country_profile_seeds_cameroon_francophone_pack(self):
        region = ensure_region_for_country("CM")
        self.assertIsNotNone(region)
        profile = ensure_country_profile(
            region=region, sub_system=EducationSystemProfile.SubSystem.FR
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.default_language, "fr")
        self.assertIn("Trimestre", (profile.term_labels or [""])[0])
        self.assertEqual(
            (profile.config or {}).get("grading_logic"),
            "numeric_0_20",
        )

    def test_resolve_profile_for_school_prefers_requested_profile(self):
        uganda = self._uganda_region()
        self.assertIsNotNone(uganda)
        EducationSystemProfile.objects.get_or_create(
            code="uga-national-default",
            defaults={
                "name": "Uganda National Default",
                "region": uganda,
                "sub_system": EducationSystemProfile.SubSystem.EN,
                "approval_status": EducationSystemProfile.ApprovalStatus.APPROVED,
                "is_active": True,
            },
        )
        school = School.objects.create(
            name="Engine School",
            slug="engine-school",
            subdomain="engine-school",
            default_region=uganda,
            sub_system=School.SubSystem.EN,
            is_active=False,
        )
        profile = resolve_profile_for_school(
            school,
            requested_profile_code="uga-national-default",
            auto_create=True,
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.code, "uga-national-default")

    def test_list_profile_options_autogenerates_for_country(self):
        options = list_profile_options(country_code="JPN", sub_system="EN")
        self.assertTrue(options)
        codes = [str(item.get("code") or "") for item in options]
        self.assertIn("jpn-en-auto", codes)

    def test_list_profile_options_excludes_non_approved_profiles(self):
        region = ensure_region_for_country("UGA")
        EducationSystemProfile.objects.create(
            code="uga-draft-pack",
            name="Uganda Draft Pack",
            region=region,
            sub_system=EducationSystemProfile.SubSystem.EN,
            approval_status=EducationSystemProfile.ApprovalStatus.DRAFT,
            is_active=True,
            is_default=False,
        )
        options = list_profile_options(country_code="UGA", sub_system="EN")
        codes = [str(item.get("code") or "") for item in options]
        self.assertNotIn("uga-draft-pack", codes)

    def test_resolve_profile_for_school_ignores_non_approved_requested_profile(self):
        uganda = self._uganda_region()
        self.assertIsNotNone(uganda)
        draft = EducationSystemProfile.objects.create(
            code="uga-en-draft-explicit",
            name="Uganda Explicit Draft",
            region=uganda,
            sub_system=EducationSystemProfile.SubSystem.EN,
            approval_status=EducationSystemProfile.ApprovalStatus.DRAFT,
            is_active=True,
        )
        school = School.objects.create(
            name="Draft Validation School",
            slug="draft-validation-school",
            subdomain="draft-validation-school",
            default_region=uganda,
            sub_system=School.SubSystem.EN,
            is_active=False,
        )
        profile = resolve_profile_for_school(
            school,
            requested_profile_code=draft.code,
            auto_create=True,
        )
        self.assertIsNotNone(profile)
        self.assertNotEqual(profile.code, draft.code)
        self.assertEqual(
            profile.approval_status, EducationSystemProfile.ApprovalStatus.APPROVED
        )
