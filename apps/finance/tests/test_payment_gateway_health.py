"""Gateway health abstraction — no live charges, fake adapters in tests."""

from __future__ import annotations

from django.test import TestCase

from apps.finance.models import ComplianceProfile, PaymentGatewayHealthSnapshot
from apps.finance.payment_fallback_engine import MANUAL_FALLBACK_CODE, select_effective_rail
from apps.finance.payment_gateway_health import (
    GatewayHealthStatus,
    availability_map_from_rows,
    build_gateway_health_rows,
    next_operator_action,
    record_gateway_health_snapshots,
)
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.integrations_marketplace.models import Integration
from apps.schools.models import School


class PaymentGatewayHealthTests(TestCase):
    def tearDown(self):
        clear_profile_cache()

    def test_missing_credentials_does_not_crash_for_momo_without_integration(self):
        school = School.objects.create(
            name="Momo School",
            slug="momo-school",
            subdomain="momosch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="CM",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        rows = build_gateway_health_rows(school, cp)
        prim = next(r for r in rows if r.get("rail_code") == "MTN_MOMO")
        self.assertEqual(prim["status"], GatewayHealthStatus.MISSING_CREDENTIALS)

    def test_momo_ready_when_integration_has_base_url(self):
        Integration.objects.create(
            name="MTN",
            slug="mtn-payments-health",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "base_url": "https://sandbox.momo.example/",
            },
        )
        school = School.objects.create(
            name="CM2",
            slug="cm2",
            subdomain="cm2sch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="CM",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        rows = build_gateway_health_rows(school, cp)
        prim = next(r for r in rows if r.get("rail_code") == "MTN_MOMO")
        self.assertEqual(prim["status"], GatewayHealthStatus.READY)

    def test_degraded_when_integration_missing_base_url(self):
        Integration.objects.create(
            name="MTN deg",
            slug="mtn-deg",
            provider="payments",
            enabled=True,
            config={"provider_slug": "mtn_momo"},
        )
        school = School.objects.create(
            name="CM3",
            slug="cm3",
            subdomain="cm3sch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="CM",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        rows = build_gateway_health_rows(school, cp)
        prim = next(r for r in rows if r.get("rail_code") == "MTN_MOMO")
        self.assertEqual(prim["status"], GatewayHealthStatus.DEGRADED)

    def test_card_external_required_honest(self):
        school = School.objects.create(
            name="US1",
            slug="us1",
            subdomain="us1sch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="US",
            country_code="US",
            currency_code="USD",
            is_active=True,
        )
        rows = build_gateway_health_rows(school, cp)
        card_row = next(r for r in rows if r.get("rail_code") == "CARD")
        self.assertEqual(card_row["status"], GatewayHealthStatus.EXTERNAL_REQUIRED)

    def test_fake_provider_records_ready_status(self):
        school = School.objects.create(
            name="Fake",
            slug="fake",
            subdomain="fakesch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="NG",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )

        def fake_checker(rail_code, catalog, policy, compliance_profile):
            return {
                "rail_code": rail_code,
                "provider_key": "fake_psp",
                "status": GatewayHealthStatus.READY,
                "message": "Synthetic adapter OK.",
                "action_required": "",
            }

        rows = build_gateway_health_rows(school, cp, checker=fake_checker)
        record_gateway_health_snapshots(school, rows)
        self.assertTrue(
            PaymentGatewayHealthSnapshot.objects.filter(
                school=school,
                status=GatewayHealthStatus.READY,
            ).exists()
        )

    def test_degraded_primary_recommends_backup_via_next_action(self):
        rows = [
            {
                "rail_code": "BANK",
                "role": "primary",
                "status": GatewayHealthStatus.DEGRADED,
                "message": "",
                "action_required": "",
                "provider_key": "",
            },
            {
                "rail_code": "CARD",
                "role": "backup",
                "status": GatewayHealthStatus.READY,
                "message": "",
                "action_required": "",
                "provider_key": "",
            },
        ]
        msg = next_operator_action(rows, {"operator_ready_label": "x"})
        self.assertIn("backup", msg.lower())

    def test_all_online_rails_down_selects_manual(self):
        chain_keys = [
            "MTN_MOMO",
            "ORANGE_MOMO",
            "BANK",
            "CASH",
        ]
        avail = {k: False for k in chain_keys}
        eff = select_effective_rail("CM", avail)
        self.assertEqual(eff["selected_rail"], MANUAL_FALLBACK_CODE)

    def test_primary_ready_used_in_availability_map(self):
        rows = [
            {
                "rail_code": "BANK",
                "status": GatewayHealthStatus.READY,
                "role": "primary",
            }
        ]
        amap = availability_map_from_rows(rows)
        self.assertTrue(amap.get("BANK"))
