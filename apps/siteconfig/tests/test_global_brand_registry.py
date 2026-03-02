from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.brand_registry import resolve_global_brand_context
from apps.siteconfig.models import GlobalBrandRegistry, RegionConfig
from apps.siteconfig.tenant_config import get_tenant_locale


class GlobalBrandRegistryTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="CAN",
            name="Canada",
            default_language="en",
            timezone="America/Toronto",
            date_format="DD/MM/YYYY",
            grading_scale="0-100",
            default_currency="CAD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        self.school = School.objects.create(
            name="Maple Academy",
            slug="maple-academy",
            subdomain="maple-academy",
            default_region=self.region,
            is_active=True,
        )

    def test_resolve_brand_context_uses_registry_defaults(self):
        GlobalBrandRegistry.objects.create(
            iso_code="CA",
            country_name="Canada",
            primary_language="fr",
            labels_map={"student": "Eleve", "teacher": "Enseignant"},
            ui_config={"date_format": "YYYY-MM-DD"},
            currency_code="CAD",
            is_active=True,
        )
        context = resolve_global_brand_context(school=self.school)
        self.assertEqual(context["iso_code"], "CA")
        self.assertEqual(context["primary_language"], "fr")
        self.assertEqual(context["currency_code"], "CAD")
        self.assertEqual(context["labels_map"]["student"], "Eleve")
        self.assertEqual(context["ui_config"]["date_format"], "YYYY-MM-DD")

    def test_tenant_locale_hydrates_labels_and_school_overrides(self):
        GlobalBrandRegistry.objects.create(
            iso_code="CA",
            country_name="Canada",
            primary_language="fr",
            labels_map={"student": "Eleve"},
            ui_config={"is_rtl": True, "date_format": "YYYY-MM-DD"},
            currency_code="CAD",
            is_active=True,
        )
        self.school.settings = {
            "labels_map": {"student": "Apprenant"},
            "currency": "CAD",
        }
        self.school.save(update_fields=["settings"])

        locale = get_tenant_locale(school=self.school)
        self.assertEqual(locale["locale"], "fr")
        self.assertEqual(locale["labels_map"]["student"], "Apprenant")
        self.assertEqual(locale["currency"], "CAD")
        self.assertEqual(locale["date_format"], "YYYY-MM-DD")
        self.assertTrue(locale["is_rtl"])
