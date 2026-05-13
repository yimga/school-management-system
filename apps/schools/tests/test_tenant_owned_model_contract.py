from django.test import SimpleTestCase

from apps.schools.tenant_models import TenantManager, TenantOwnedModel


class ExampleTenantOwnedModel(TenantOwnedModel):
    class Meta:
        app_label = "schools"


class TenantOwnedModelContractTests(SimpleTestCase):
    def test_abstract_base_provides_school_fk(self):
        field = ExampleTenantOwnedModel._meta.get_field("school")
        self.assertEqual(field.related_model._meta.label_lower, "schools.school")
        self.assertFalse(field.null)

    def test_default_manager_supports_for_school_scope(self):
        self.assertIsInstance(ExampleTenantOwnedModel.objects, TenantManager)
        self.assertTrue(callable(ExampleTenantOwnedModel.objects.for_school))
