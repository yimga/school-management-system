from django.test import SimpleTestCase, override_settings

from apps.tenancy.checks import shared_model_tenant_constraint_checks


class SharedModelTenantConstraintChecksTests(SimpleTestCase):
    @override_settings(USE_DJANGO_TENANTS=True)
    def test_current_mixed_shared_models_use_soft_cross_schema_relations(self):
        errors = shared_model_tenant_constraint_checks(None)
        self.assertFalse(
            [error for error in errors if error.id == "tenancy.E007"],
            msg=f"Unexpected constrained shared-to-tenant relations: {errors}",
        )
