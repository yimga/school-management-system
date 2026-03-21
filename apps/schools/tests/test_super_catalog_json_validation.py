"""Super catalog ModelForm JSON shape validation (grading_rule, plan fields, metadata)."""

from django.test import TestCase

from apps.global_registries.models import RegionConfig
from apps.plans_entitlements.models import Plan
from apps.policies_rules.models import FeatureToggleDefinition
from apps.schools.super_views_config_crud import (
    FeatureToggleDefinitionSuperForm,
    PlanSuperForm,
    RegionConfigSuperForm,
)


class SuperCatalogJsonValidationTests(TestCase):
    def test_region_grading_rule_must_be_object(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="ZZ",
            defaults={
                "name": "ZZ Test",
                "default_language": "en",
                "timezone": "UTC",
            },
        )
        form = RegionConfigSuperForm(
            data={
                "code": region.code,
                "name": region.name,
                "default_language": "en",
                "timezone": "UTC",
                "decimal_separator": ".",
                "thousands_separator": ",",
                "date_format": "DD/MM/YYYY",
                "calendar_system": "gregorian",
                "grading_scale": "0-20",
                "default_currency": "XAF",
                "academic_year_start_month": 9,
                "term_count_per_year": 3,
                "grading_rule": "[]",
                "school_registration_number_format": "",
                "student_id_format": "",
                "certificate_template_name": "standard",
                "enable_online_admissions": "on",
                "enable_parent_portal": "on",
                "enable_student_portal": "on",
                "is_rtl": "",
            },
            instance=region,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("grading_rule", form.errors)

    def test_plan_included_features_must_be_array(self):
        plan = Plan.objects.create(
            name="Json Test Plan",
            slug="json-test-plan",
            billing_model=Plan.BillingModel.FLAT,
            is_active=True,
        )
        form = PlanSuperForm(
            data={
                "name": plan.name,
                "slug": plan.slug,
                "billing_model": plan.billing_model,
                "is_active": "on",
                "max_students": "",
                "max_staff": "",
                "base_price": "",
                "price_per_student": "",
                "included_features": "{}",
                "tier_rules": "{}",
            },
            instance=plan,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("included_features", form.errors)

    def test_plan_tier_rules_rejects_scalar_json(self):
        plan = Plan.objects.create(
            name="Tier Test Plan",
            slug="tier-test-plan",
            billing_model=Plan.BillingModel.TIERED,
            is_active=True,
        )
        form = PlanSuperForm(
            data={
                "name": plan.name,
                "slug": plan.slug,
                "billing_model": plan.billing_model,
                "is_active": "on",
                "max_students": "",
                "max_staff": "",
                "base_price": "",
                "price_per_student": "",
                "included_features": "[]",
                "tier_rules": '"only"',
            },
            instance=plan,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("tier_rules", form.errors)

    def test_feature_toggle_metadata_must_be_object(self):
        row, _ = FeatureToggleDefinition.objects.get_or_create(
            key="zz_json_test_toggle",
            defaults={
                "label": "ZZ JSON test",
                "scope": FeatureToggleDefinition.Scope.GLOBAL,
            },
        )
        form = FeatureToggleDefinitionSuperForm(
            data={
                "key": row.key,
                "label": row.label,
                "description": "",
                "category": "",
                "scope": row.scope,
                "owner": "",
                "source": "",
                "default_enabled": "",
                "is_active": "on",
                "metadata": "[]",
            },
            instance=row,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("metadata", form.errors)
