"""Tenant ComplianceProfile provisioning seed (Phase B).

Guards the P0 crash: a freshly provisioned tenant schema has zero ComplianceProfile rows, and
Invoice.profile is a PROTECT, non-null FK, so fee generation would raise IntegrityError. The seed
guarantees one active profile exists. The helper reads only school.country_code / .settings / .name,
so a lightweight stub stands in for a full School (keeps the test schema-agnostic and fast).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.finance.provisioning_seed import ensure_tenant_compliance_profile


def _school(name="New Test High", country_code="CM", settings=None):
    return SimpleNamespace(
        name=name,
        country_code=country_code,
        settings=settings if settings is not None else {},
    )


class TenantComplianceProfileSeedTests(TestCase):
    def test_creates_active_profile_when_none_exist(self):
        self.assertFalse(ComplianceProfile.objects.exists())
        cp = ensure_tenant_compliance_profile(_school(country_code="CM"))
        self.assertIsNotNone(cp)
        self.assertTrue(cp.is_active)
        self.assertEqual(cp.country_code, "CM")
        self.assertEqual(ComplianceProfile.objects.filter(is_active=True).count(), 1)

    def test_idempotent_no_duplicate_on_rerun(self):
        ensure_tenant_compliance_profile(_school())
        ensure_tenant_compliance_profile(_school())
        self.assertEqual(ComplianceProfile.objects.count(), 1)

    def test_returns_existing_active_profile_without_creating(self):
        first = ensure_tenant_compliance_profile(_school(name="A", country_code="US"))
        # A different school resolving later must NOT create a second profile.
        second = ensure_tenant_compliance_profile(_school(name="B", country_code="GB"))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ComplianceProfile.objects.count(), 1)

    def test_currency_from_school_settings(self):
        cp = ensure_tenant_compliance_profile(
            _school(country_code="CM", settings={"default_currency": "XAF"})
        )
        self.assertEqual(cp.currency_code, "XAF")
        self.assertEqual(cp.currency_symbol, "XAF")

    def test_defaults_to_ww_usd_without_country_or_currency(self):
        cp = ensure_tenant_compliance_profile(_school(country_code="", settings={}))
        self.assertEqual(cp.country_code, "WW")
        self.assertEqual(cp.currency_code, "USD")

    def test_seeded_profile_resolves_via_invoice_fallback(self):
        """The exact resolution invoice creation uses must now return a row."""
        ensure_tenant_compliance_profile(_school())
        resolved = ComplianceProfile.objects.filter(is_active=True).first()
        self.assertIsNotNone(resolved)
