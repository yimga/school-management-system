"""Tests for seed_finance_defaults management command (Phase B write contract)."""

from django.core.management import call_command
from django.test import TestCase

from apps.finance.models import ComplianceProfile, RegionPaymentProfile
from apps.platform_runtime.models import RuntimeDefaults


class SeedFinanceDefaultsCommandTests(TestCase):
    def test_sets_cameroon_pointer_when_runtime_compliance_profile_empty(self):
        rd, _ = RuntimeDefaults.objects.get_or_create(pk=1, defaults={"payload": {}})
        rd.compliance_profile_id = None
        rd.save(update_fields=["compliance_profile_id", "updated_at"])

        call_command("seed_finance_defaults")

        cameroon = ComplianceProfile.objects.get(name="Cameroon OHADA", country_code="CM")
        rd.refresh_from_db()
        self.assertEqual(rd.compliance_profile_id, cameroon.pk)

    def test_does_not_overwrite_existing_compliance_profile_pointer(self):
        existing = ComplianceProfile.objects.create(
            name="Preseed Hold",
            country_code="ZZ",
        )
        rd, _ = RuntimeDefaults.objects.get_or_create(pk=1, defaults={"payload": {}})
        rd.compliance_profile_id = existing.pk
        rd.save(update_fields=["compliance_profile_id", "updated_at"])

        call_command("seed_finance_defaults")

        rd.refresh_from_db()
        self.assertEqual(rd.compliance_profile_id, existing.pk)

    def test_creates_region_payment_profile_for_catalog_cm(self):
        call_command("seed_finance_defaults")
        rp = RegionPaymentProfile.objects.get(country_code="CM")
        self.assertIsNotNone(rp.primary_rail_id)
        self.assertIsNotNone(rp.backup_rail_id)
