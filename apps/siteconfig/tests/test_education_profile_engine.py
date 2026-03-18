from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.education_profile_engine import (
    ensure_country_profile,
    ensure_region_for_country,
    list_profile_options,
    resolve_profile_for_school,
)
from apps.siteconfig.models import EducationSystemProfile, RegionConfig


class EducationProfileEngineTests(TestCase):
    def test_ensure_region_for_country_creates_region(self):
        region = ensure_region_for_country("JP")
        self.assertIsNotNone(region)
        self.assertEqual(region.code, "JPN")
        self.assertTrue(region.name)

    def test_ensure_country_profile_creates_auto_pack(self):
        region = ensure_region_for_country("JPN")
        profile = ensure_country_profile(
            region=region, sub_system=EducationSystemProfile.SubSystem.EN
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.code, "jpn-en-auto")
        self.assertEqual(profile.region_id, "JPN")
        self.assertTrue((profile.config or {}).get("generated"))

    def test_resolve_profile_for_school_prefers_requested_profile(self):
        uganda = RegionConfig.objects.get(code="UGA")
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
        uganda = RegionConfig.objects.get(code="UGA")
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
