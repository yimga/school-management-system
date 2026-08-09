from django.test import TestCase

from apps.platform_runtime.tenant_direct_remedies import (
    apply_direct_remedy,
    build_direct_remedy,
    override_direct_remedy,
)
from apps.registries.models import CountryRegistry, EducationSystemTypeRegistry
from apps.schools.models import School


class TenantDirectRemedyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Direct Repair", slug="direct-repair")
        CountryRegistry.objects.update_or_create(
            code="CM", defaults={"name": "Cameroon", "is_active": True}
        )
        EducationSystemTypeRegistry.objects.update_or_create(
            code="EN", defaults={"name": "Anglophone", "is_active": True}
        )

    def test_builds_exact_registry_control(self):
        remedy = build_direct_remedy(self.school, "country")
        self.assertEqual(remedy["label"], "Country")
        self.assertIn("CM", {choice["value"] for choice in remedy["choices"]})

    def test_applies_value_and_clears_override(self):
        self.school.settings = {"setup_registry_overrides": {"country": {"reason": "legacy"}}}
        self.school.save(update_fields=["settings"])
        apply_direct_remedy(self.school, field_key="country", value="CM", actor=None)
        self.school.refresh_from_db()
        self.assertEqual(self.school.country_code, "CM")
        self.assertNotIn("country", self.school.settings["setup_registry_overrides"])

    def test_false_positive_override_is_reasoned_and_audited(self):
        override_direct_remedy(
            self.school, field_key="education_system",
            reason="Local accreditation uses a custom hybrid system.", actor=None,
        )
        self.school.refresh_from_db()
        record = self.school.settings["setup_registry_overrides"]["education_system"]
        self.assertIn("custom hybrid", record["reason"])
        self.assertTrue(record["created_at"])

    def test_short_override_reason_is_rejected(self):
        with self.assertRaises(ValueError):
            override_direct_remedy(self.school, field_key="country", reason="no", actor=None)
