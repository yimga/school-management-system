"""Super catalog ModelForm JSON shape validation (grading_rule, plan fields, metadata)."""

from django.db import models
from django.test import SimpleTestCase, TestCase

from apps.global_registries.models import RegionConfig
from apps.plans_entitlements.models import Plan, PlanAddon
from apps.policies_rules.models import FeatureToggleDefinition
from apps.schools.super_views_config_crud import (
    FeatureToggleDefinitionSuperForm,
    PlanAddonSuperForm,
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


class PlanJsonShapeMapTests(SimpleTestCase):
    """Lock ``JSON_SHAPES`` to the columns it claims to mirror.

    The map is only trustworthy while it agrees with the model. These are
    database-free: they read ``_meta``, so they run in milliseconds and fail on a
    rename or a changed ``default=`` long before anything reaches a form.
    """

    FORMS = (PlanSuperForm, PlanAddonSuperForm)

    def test_every_shaped_field_matches_its_column_default(self):
        for form_cls in self.FORMS:
            model = form_cls._meta.model
            for name, expected in form_cls.JSON_SHAPES.items():
                with self.subTest(form=form_cls.__name__, field=name):
                    # Raises FieldDoesNotExist if the column was renamed.
                    field = model._meta.get_field(name)
                    self.assertIs(
                        field.default,
                        expected,
                        f"{model.__name__}.{name} declares default={field.default!r} "
                        f"but {form_cls.__name__}.JSON_SHAPES enforces {expected!r}. "
                        "The column's own default is the authority its readers rely on.",
                    )

    def test_every_json_column_is_shaped_or_hand_validated(self):
        """A new JSONField must not slip in unvalidated.

        This is the point of the map: adding a column to the model without
        deciding its shape fails here rather than in a tenant's pricing call.
        """
        for form_cls in self.FORMS:
            model = form_cls._meta.model
            for field in model._meta.get_fields():
                if not isinstance(field, models.JSONField):
                    continue
                with self.subTest(form=form_cls.__name__, field=field.name):
                    self.assertTrue(
                        field.name in form_cls.JSON_SHAPES
                        or hasattr(form_cls, f"clean_{field.name}"),
                        f"{model.__name__}.{field.name} is a JSONField with no shape "
                        f"check: add it to {form_cls.__name__}.JSON_SHAPES or give it a "
                        f"clean_{field.name} method.",
                    )

    def test_shaped_fields_do_not_shadow_a_hand_written_validator(self):
        """Two validators on one field would stack two errors on one input."""
        for form_cls in self.FORMS:
            for name in form_cls.JSON_SHAPES:
                with self.subTest(form=form_cls.__name__, field=name):
                    self.assertFalse(
                        hasattr(form_cls, f"clean_{name}"),
                        f"{form_cls.__name__}.{name} is both in JSON_SHAPES and has an "
                        f"explicit clean_{name}; keep exactly one.",
                    )


class PlanJsonShapeValidationTests(TestCase):
    """The shapes as the operator meets them: valid JSON, wrong container."""

    def _plan_form(self, **overrides):
        plan = Plan.objects.create(
            name="Shape Test Plan",
            slug="shape-test-plan",
            billing_model=Plan.BillingModel.FLAT,
            is_active=True,
        )
        data = {
            "name": plan.name,
            "slug": plan.slug,
            "billing_model": plan.billing_model,
            "is_active": "on",
            "max_students": "",
            "max_staff": "",
            "base_price": "",
            "price_per_student": "",
            "included_features": "[]",
            "tier_rules": "{}",
        }
        data.update(overrides)
        return PlanSuperForm(data=data, instance=plan)

    def test_billing_cycle_options_rejects_a_scalar(self):
        # '"monthly"' is VALID json — it parses to a str — so only the shape
        # check stands between it and tenant_pricing iterating a string.
        form = self._plan_form(billing_cycle_options='"monthly"')
        self.assertFalse(form.is_valid())
        self.assertIn("billing_cycle_options", form.errors)

    def test_included_usage_rejects_an_array(self):
        form = self._plan_form(included_usage="[]")
        self.assertFalse(form.is_valid())
        self.assertIn("included_usage", form.errors)

    def test_a_correct_container_raises_no_error_on_that_field(self):
        form = self._plan_form(
            billing_cycle_options='["monthly", "annual"]',
            included_usage='{"students": 500}',
        )
        form.is_valid()
        self.assertNotIn("billing_cycle_options", form.errors)
        self.assertNotIn("included_usage", form.errors)

    def test_blank_cleans_to_the_declared_empty_container(self):
        # blank=True + default=list/dict: readers must never receive None.
        form = self._plan_form(billing_cycle_options="", included_usage="")
        form.is_valid()
        self.assertEqual(form.cleaned_data.get("billing_cycle_options"), [])
        self.assertEqual(form.cleaned_data.get("included_usage"), {})

    def test_addon_plan_codes_reject_an_object(self):
        addon = PlanAddon.objects.create(
            code="shape-test-addon", name="Shape Test Addon", price=0
        )
        form = PlanAddonSuperForm(
            data={
                "code": addon.code,
                "name": addon.name,
                "price": "0",
                "is_active": "on",
                "included_in_plan_codes": "{}",
                "regional_price_overrides": "[]",
            },
            instance=addon,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("included_in_plan_codes", form.errors)
        self.assertIn("regional_price_overrides", form.errors)
