from django.core.management import call_command
from django.test import SimpleTestCase

from apps.siteconfig.tenant_audit import (
    COMMUNICATION_TENANT_MODELS,
    find_missing_explicit_school_fields,
    find_tenant_owned_models_missing_school_fields,
    has_explicit_school_field,
)


class TenantAuditTests(SimpleTestCase):
    def test_communication_models_have_explicit_school_field(self):
        missing = find_missing_explicit_school_fields()
        self.assertEqual(missing, [])

    def test_has_explicit_school_field_reports_false_for_non_tenant_model(self):
        self.assertFalse(has_explicit_school_field("accounts.User"))

    def test_management_command_strict_passes_for_communication_models(self):
        labels = ",".join(COMMUNICATION_TENANT_MODELS)
        call_command("audit_tenant_models", "--models", labels, "--strict")

    def test_tenant_owned_model_subclasses_keep_school_field(self):
        self.assertEqual(find_tenant_owned_models_missing_school_fields(), [])
