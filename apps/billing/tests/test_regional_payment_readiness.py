"""Tenant payment readiness tiers (catalog vs campus rails)."""

from __future__ import annotations

from django.test import TestCase

from apps.billing.regional_payment_readiness import (
    compute_payment_readiness,
    readiness_for_marketplace_entitlement_context,
)
from apps.finance.models import (
    ComplianceProfile,
    PaymentRail,
    RegionPaymentProfile,
    TenantPaymentPolicy,
)
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.schools.models import School


class RegionalPaymentReadinessTests(TestCase):
    def tearDown(self):
        clear_profile_cache()

    def test_missing_setup_when_country_not_in_catalog(self):
        school = School.objects.create(
            name="X",
            slug="x-school",
            subdomain="xsch",
            is_active=True,
        )
        profile = ComplianceProfile.objects.create(
            name="Nowhere",
            country_code="ZZ",
            currency_code="USD",
            is_active=True,
        )
        snap = compute_payment_readiness(school, profile)
        self.assertEqual(snap["status"], "MISSING_SETUP")

    def test_ready_when_policy_links_matching_region_profile(self):
        school = School.objects.create(
            name="Cam Co",
            slug="cam-co",
            subdomain="camco",
            is_active=True,
        )
        primary = PaymentRail.objects.create(
            code="cm-mtn-test",
            label="MTN",
            kind=PaymentRail.RailKind.MOBILE_MONEY,
        )
        backup = PaymentRail.objects.create(
            code="cm-ora-test",
            label="Orange",
            kind=PaymentRail.RailKind.MOBILE_MONEY,
        )
        region = RegionPaymentProfile.objects.create(
            country_code="CM",
            name="Cameroon",
            primary_rail=primary,
            backup_rail=backup,
        )
        TenantPaymentPolicy.objects.create(
            school=school,
            region_profile=region,
            allow_manual_offline_proof=True,
        )
        compliance = ComplianceProfile.objects.create(
            name="CM Active",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        snap = compute_payment_readiness(school, compliance)
        self.assertEqual(snap["status"], "READY")
        self.assertEqual(snap["recommended_primary_rail"], "MTN_MOMO")

    def test_fallback_only_without_tenant_policy(self):
        school = School.objects.create(
            name="Loose",
            slug="loose",
            subdomain="loose",
            is_active=True,
        )
        compliance = ComplianceProfile.objects.create(
            name="NG",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )
        snap = compute_payment_readiness(school, compliance)
        self.assertEqual(snap["status"], "FALLBACK_ONLY")

    def test_marketplace_context_snapshot_keys(self):
        school = School.objects.create(
            name="M",
            slug="mkt",
            subdomain="mkt",
            is_active=True,
        )
        compliance = ComplianceProfile.objects.create(
            name="KE",
            country_code="KE",
            currency_code="KES",
            is_active=True,
        )
        ctx = readiness_for_marketplace_entitlement_context(school, compliance)
        self.assertIn("payment_readiness_status", ctx)
        self.assertEqual(ctx["payment_country_code"], "KE")

    def test_profile_metadata_in_checklist_includes_rails(self):
        school = School.objects.create(
            name="Meta",
            slug="meta",
            subdomain="meta",
            is_active=True,
        )
        primary = PaymentRail.objects.create(
            code="ke-test-p",
            label="P",
            kind=PaymentRail.RailKind.CARD,
        )
        backup = PaymentRail.objects.create(
            code="ke-test-b",
            label="B",
            kind=PaymentRail.RailKind.BANK_TRANSFER,
        )
        RegionPaymentProfile.objects.create(
            country_code="KE",
            name="Kenya",
            primary_rail=primary,
            backup_rail=backup,
        )
        TenantPaymentPolicy.objects.create(
            school=school,
            region_profile=RegionPaymentProfile.objects.get(country_code="KE"),
        )
        compliance = ComplianceProfile.objects.create(
            name="KE",
            country_code="KE",
            currency_code="KES",
            is_active=True,
        )
        snap = compute_payment_readiness(school, compliance)
        self.assertEqual(snap["recommended_primary_rail"], "CARD")
        self.assertEqual(snap["recommended_backup_rail"], "BANK")
        self.assertNotEqual(snap["status"], "MISSING_SETUP")
