"""#5 EAV — country identity catalog must land at provision Phase B."""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.metadata.models import DynamicFieldDefinition
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class EavCatalogProvisioningTests(TestCase):
    def test_india_provision_seeds_aadhaar_and_udise(self):
        school = School.objects.create(
            name="IN EAV Academy",
            slug="in-eav-academy",
            subdomain="in-eav-academy",
            country_code="IN",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(school.id), contact_email="owner@in-eav.test")

        keys = set(
            DynamicFieldDefinition.objects.filter(
                school=school, entity_type="people.studentprofile", is_active=True
            ).values_list("field_key", flat=True)
        )
        self.assertIn("aadhaar_reference", keys)
        self.assertIn("udise_code", keys)

    def test_uae_provision_seeds_civil_registry(self):
        school = School.objects.create(
            name="AE EAV Academy",
            slug="ae-eav-academy",
            subdomain="ae-eav-academy",
            country_code="AE",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(school.id), contact_email="owner@ae-eav.test")

        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=school,
                field_key="civil_registry_id",
                entity_type="people.studentprofile",
                is_active=True,
            ).exists()
        )

    def test_cameroon_provision_seeds_waec(self):
        school = School.objects.create(
            name="CM EAV Academy",
            slug="cm-eav-academy",
            subdomain="cm-eav-academy",
            country_code="CM",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(school.id), contact_email="owner@cm-eav.test")

        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=school,
                field_key="waec_candidate_number",
                entity_type="people.studentprofile",
                is_active=True,
            ).exists()
        )

    def test_seed_honesty_blank_country_ok(self):
        from apps.metadata.country_eav_catalog import seed_country_eav_definitions

        school = School.objects.create(
            name="Blank CC",
            slug="blank-cc",
            subdomain="blank-cc",
            country_code="",
            is_active=True,
        )
        result = seed_country_eav_definitions(school=school, country_code="")
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "no_country_code")
        self.assertEqual(result["expected"], 0)

    def test_country_change_reseeds_catalog(self):
        """Metric #5: School.save country flip reseeds identity EAV (IN→AE)."""
        school = School.objects.create(
            name="CC Flip Academy",
            slug="cc-flip-academy",
            subdomain="cc-flip-academy",
            country_code="IN",
            is_active=True,
        )
        from apps.metadata.country_eav_catalog import seed_country_eav_definitions

        seed_country_eav_definitions(school=school, country_code="IN")
        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=school, field_key="aadhaar_reference", is_active=True
            ).exists()
        )

        school.country_code = "AE"
        school.save(update_fields=["country_code"])

        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=school,
                field_key="civil_registry_id",
                entity_type="people.studentprofile",
                is_active=True,
            ).exists()
        )
