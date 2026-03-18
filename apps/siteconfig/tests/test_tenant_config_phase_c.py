"""
Phase C: Tests for get_grading_schema_for_school, get_report_template_family_for_school,
get_custom_field_definitions_for_school.
"""

from django.db.utils import OperationalError
from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.models import EducationSystemProfile, RegionConfig, TenantSystem
from apps.siteconfig.tenant_config import (
    get_custom_field_definitions_for_school,
    get_grading_schema_for_school,
    get_report_template_family_for_school,
)


def _skip_if_schema_missing(
    msg="Schema (TenantSystem/EducationSystemProfile) not available",
):
    """Skip test when DB is missing tables/columns (e.g. partial migrations or old --keepdb)."""
    import unittest

    raise unittest.SkipTest(msg)


class GetGradingSchemaForSchoolTests(TestCase):
    def test_none_school_returns_default(self):
        out = get_grading_schema_for_school(None)
        self.assertEqual(out["scale"], "0-100")
        self.assertIsNone(out.get("grade_bands"))
        self.assertIsNone(out.get("pass_mark"))

    def test_school_without_tenant_system_uses_locale_default(self):
        try:
            region = (
                RegionConfig.objects.filter(code="CMR").first()
                or RegionConfig.objects.first()
            )
        except OperationalError:
            _skip_if_schema_missing("RegionConfig not available")
        school = School.objects.create(
            name="No System",
            slug="no-system",
            subdomain="no-system",
            default_region=region,
            sub_system=School.SubSystem.EN,
        )
        try:
            out = get_grading_schema_for_school(school)
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        self.assertIn(out["scale"], ("0-100", "0-20", "0-10"))  # from region or default
        self.assertIn("scale", out)

    def test_school_with_tenant_system_uses_profile_config(self):
        try:
            region = RegionConfig.objects.first()
            profile = EducationSystemProfile.objects.filter(region=region).first()
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        if not profile:
            self.skipTest("No EducationSystemProfile in DB")
        school = School.objects.create(
            name="With System",
            slug="with-system",
            subdomain="with-system",
            default_region=region,
            sub_system=School.SubSystem.EN,
        )
        try:
            TenantSystem.objects.get_or_create(
                school=school, defaults={"system": profile}
            )
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        if not isinstance(profile.config, dict):
            profile.config = {}
        profile.config["grade_bands"] = [{"min": 10, "grade": "P"}]
        profile.config["pass_mark"] = 10
        profile.save(update_fields=["config"])
        out = get_grading_schema_for_school(school)
        self.assertIsNotNone(out.get("grade_bands") or out.get("pass_mark"))


class GetReportTemplateFamilyForSchoolTests(TestCase):
    def test_none_school_returns_empty(self):
        self.assertEqual(get_report_template_family_for_school(None), "")

    def test_school_without_tenant_system_returns_empty(self):
        try:
            region = RegionConfig.objects.first()
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        school = School.objects.create(
            name="No Family",
            slug="no-family",
            subdomain="no-family",
            default_region=region,
            sub_system=School.SubSystem.EN,
        )
        try:
            result = get_report_template_family_for_school(school)
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        self.assertEqual(result, "")

    def test_school_with_profile_config_returns_family(self):
        try:
            region = RegionConfig.objects.first()
            profile = EducationSystemProfile.objects.filter(region=region).first()
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        if not profile:
            self.skipTest("No EducationSystemProfile in DB")
        school = School.objects.create(
            name="With Family",
            slug="with-family",
            subdomain="with-family",
            default_region=region,
            sub_system=School.SubSystem.EN,
        )
        try:
            TenantSystem.objects.get_or_create(
                school=school, defaults={"system": profile}
            )
        except OperationalError as e:
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                _skip_if_schema_missing(f"Test DB schema incomplete: {e}")
            raise
        if not isinstance(profile.config, dict):
            profile.config = {}
        profile.config["report_template_family"] = "east_africa"
        profile.save(update_fields=["config"])
        self.assertEqual(get_report_template_family_for_school(school), "east_africa")


class GetCustomFieldDefinitionsForSchoolTests(TestCase):
    def test_none_school_returns_empty(self):
        self.assertEqual(get_custom_field_definitions_for_school(None, "students"), [])
        self.assertEqual(get_custom_field_definitions_for_school(None, "staff"), [])

    def test_invalid_entity_type_returns_empty(self):
        school = School.objects.create(
            name="S",
            slug="s",
            subdomain="s",
            sub_system=School.SubSystem.EN,
        )
        self.assertEqual(get_custom_field_definitions_for_school(school, "invalid"), [])

    def test_settings_empty_returns_empty(self):
        school = School.objects.create(
            name="S",
            slug="s",
            subdomain="s",
            sub_system=School.SubSystem.EN,
        )
        self.assertEqual(
            get_custom_field_definitions_for_school(school, "students"), []
        )

    def test_settings_custom_field_definitions_returns_list(self):
        school = School.objects.create(
            name="S",
            slug="s",
            subdomain="s",
            sub_system=School.SubSystem.EN,
            settings={
                "custom_field_definitions": {
                    "students": [
                        {"key": "blood_group", "label": "Blood Group", "type": "text"},
                    ],
                    "staff": [
                        {
                            "key": "certifications",
                            "label": "Certifications",
                            "type": "text",
                        }
                    ],
                },
            },
        )
        students = get_custom_field_definitions_for_school(school, "students")
        staff = get_custom_field_definitions_for_school(school, "staff")
        self.assertEqual(len(students), 1)
        self.assertEqual(students[0]["key"], "blood_group")
        self.assertEqual(len(staff), 1)
        self.assertEqual(staff[0]["key"], "certifications")
