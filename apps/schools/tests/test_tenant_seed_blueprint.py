"""Tests for tenant seed blueprint and operational lifecycle (batch 1726)."""

from django.test import TestCase

from apps.platform_runtime.tenant_operational_lifecycle import (
    ALL_OPERATIONAL_STATES,
    resolve_operational_lifecycle_state,
    validate_operational_transition,
)
from apps.schools.models import School
from apps.schools.tenant_seed_blueprint import (
    DEFAULT_DISPLAY_NAME,
    DEFAULT_SLUG,
    apply_tenant_seed_blueprint,
    blueprint_status,
)
from apps.sync_engine.tenant_manifest_compiler import SCHEMA_VERSION


class OperationalLifecycleTests(TestCase):
    def test_none_school_is_conception(self) -> None:
        result = resolve_operational_lifecycle_state(None)
        self.assertEqual(result["state"], "conception")

    def test_all_states_declared(self) -> None:
        self.assertGreaterEqual(len(ALL_OPERATIONAL_STATES), 14)

    def test_valid_transition(self) -> None:
        self.assertTrue(
            validate_operational_transition("provisioning", "country_setup")
        )


class TenantSeedBlueprintTests(TestCase):
    def test_blueprint_applies_to_demo_school(self) -> None:
        school = School.objects.filter(slug=DEFAULT_SLUG).first()
        if school is None:
            school = School.objects.create(
                slug=DEFAULT_SLUG,
                name="Placeholder",
                is_active=True,
            )
        applied = apply_tenant_seed_blueprint(school_slug=DEFAULT_SLUG)
        self.assertIsNotNone(applied)
        assert applied is not None
        self.assertEqual(applied.name, DEFAULT_DISPLAY_NAME)
        status = blueprint_status(applied)
        self.assertTrue(status["has_manifest_snapshot"])
        self.assertGreaterEqual(SCHEMA_VERSION, 2)
