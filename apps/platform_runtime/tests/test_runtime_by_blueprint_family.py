"""
Phase 12 / Plan: Tests grouped by blueprint family.
Verifies runtime.modules.admissions and runtime.modules.gradebook shape
across different tenant contexts (no real school required; empty ctx gives default shape).
Test matrix with real fixtures: one test builds runtime from a real School in DB.
"""
from django.test import TestCase

from apps.tenancy.context import TenantContext
from apps.platform_runtime.runtime_resolver import build_tenant_runtime

# Blueprint families from plan (Phase 3 seed); used to group expectations.
BLUEPRINT_FAMILIES = (
    "early_learning",
    "primary",
    "secondary",
    "combined",
    "international",
    "technical",
    "tertiary",
    "multi_campus",
)


class RuntimeModulesByBlueprintFamilyTests(TestCase):
    """Runtime module config shape is consistent regardless of blueprint family (empty ctx = defaults)."""

    def test_modules_admissions_has_expected_keys(self):
        """runtime.modules.admissions has keys required for admissions flows."""
        ctx = TenantContext.empty(host="test.com")
        runtime = build_tenant_runtime(ctx, request=None)
        adm = runtime.modules.admissions
        self.assertIsInstance(adm, dict)
        # Plan: education_levels, required_documents, optional_documents, numbering_strategy, workflow, etc.
        self.assertIn("numbering_strategy", adm)
        self.assertIn("required_documents", adm)
        self.assertIn("workflow", adm)

    def test_modules_gradebook_has_expected_keys(self):
        """runtime.modules.gradebook has keys required for evals/grading."""
        ctx = TenantContext.empty(host="test.com")
        runtime = build_tenant_runtime(ctx, request=None)
        gb = runtime.modules.gradebook
        self.assertIsInstance(gb, dict)
        self.assertIn("pass_mark", gb)
        self.assertIn("grading_family", gb)
        self.assertIn("publish_workflow", gb)

    def test_modules_finance_has_expected_keys(self):
        """runtime.modules.finance has keys required for finance config."""
        ctx = TenantContext.empty(host="test.com")
        runtime = build_tenant_runtime(ctx, request=None)
        finance = runtime.modules.finance
        self.assertIsInstance(finance, dict)
        self.assertIn("currency", finance)
        self.assertIn("approval_workflow", finance)

    def test_runtime_admissions_respects_policy_override(self):
        """Multi-policy: when policy is passed, runtime.modules.admissions reflects it (no hardcoded default)."""
        ctx = TenantContext.empty(host="tenant.test.com")
        policy = {
            "admissions": {
                "numbering_strategy": "campus_year_sequence",
                "required_documents": ["birth_certificate", "transfer_letter"],
            },
        }
        runtime = build_tenant_runtime(ctx, request=None, policy=policy)
        adm = runtime.modules.admissions
        self.assertIsInstance(adm, dict)
        self.assertEqual(adm.get("numbering_strategy"), "campus_year_sequence")
        self.assertEqual(adm.get("required_documents"), ["birth_certificate", "transfer_letter"])

    def test_runtime_from_real_school_fixture(self):
        """Test matrix with real fixtures: build runtime from a School in DB and assert module shape."""
        from apps.schools.models import School

        school = School.objects.create(
            name="Test Matrix School",
            slug="test-matrix-runtime-fixture",
            is_active=True,
        )
        try:
            ctx = TenantContext(
                tenant_id=str(school.id),
                schema_name=None,
                school_id=school.id,
                country=getattr(school, "country_code", None) or None,
                timezone=getattr(school, "timezone", None),
                feature_flags=getattr(school, "features", None) or {},
                policy_overrides=getattr(school, "settings", None) or {},
                host="test-matrix.example.com",
            )
            runtime = build_tenant_runtime(ctx, request=None, school=school)
            self.assertIsNotNone(runtime._school)
            self.assertEqual(runtime._school.id, school.id)
            self.assertIn("numbering_strategy", runtime.modules.admissions)
            self.assertIn("pass_mark", runtime.modules.gradebook)
            self.assertIn("currency", runtime.modules.finance)
        finally:
            school.delete()
