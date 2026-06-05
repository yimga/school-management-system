from django.test import SimpleTestCase
from django.test.utils import isolate_apps

from apps.schools.tenant_models import TenantManager, TenantOwnedModel


# NOTE: the example model is defined INSIDE each test under @isolate_apps rather
# than at module level. A module-level concrete TenantOwnedModel subclass registers
# itself in the global app registry the moment this module is imported (which Django
# does for every test module during discovery). It has no migration, so it gets no
# DB table — and any code that enumerates concrete TenantOwnedModel subclasses and
# queries them per school (e.g. tenant data/footprint counts) then hits
# `relation "schools_exampletenantownedmodel" does not exist`, aborting the
# transaction for the whole request. Under Postgres + enforced RLS this surfaced as
# a cross-tenant isolation test failing on a poisoned transaction. isolate_apps
# scopes the model to the test's temporary registry so it never leaks globally.
class TenantOwnedModelContractTests(SimpleTestCase):
    @isolate_apps("apps.schools")
    def test_abstract_base_provides_school_fk(self):
        class ExampleTenantOwnedModel(TenantOwnedModel):
            class Meta:
                app_label = "schools"

        field = ExampleTenantOwnedModel._meta.get_field("school")
        # Under isolate_apps the FK target can be the lazy "schools.School"
        # reference rather than the resolved model class; accept either.
        related = field.related_model
        label = related if isinstance(related, str) else related._meta.label
        self.assertEqual(label.lower(), "schools.school")
        self.assertFalse(field.null)

    @isolate_apps("apps.schools")
    def test_default_manager_supports_for_school_scope(self):
        class ExampleTenantOwnedModel(TenantOwnedModel):
            class Meta:
                app_label = "schools"

        self.assertIsInstance(ExampleTenantOwnedModel.objects, TenantManager)
        self.assertTrue(callable(ExampleTenantOwnedModel.objects.for_school))
