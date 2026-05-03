"""Management command ``check_payment_gateways`` — metadata-only posture."""

from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.finance.models import ComplianceProfile, PaymentGatewayHealthSnapshot
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.integrations_marketplace.models import Integration
from apps.schools.models import School


class CheckPaymentGatewaysCommandTests(TestCase):
    databases = {"default"}

    def tearDown(self):
        clear_profile_cache()

    def setUp(self):
        self.school = School.objects.create(
            name="GW Cmd School",
            slug="gw-cmd-school",
            subdomain="gwcmdsch",
            country_code="CM",
            is_active=True,
        )
        ComplianceProfile.objects.create(
            name="CM Corridor",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )

    def test_momo_missing_credentials_without_integration(self):
        buf = StringIO()
        call_command(
            "check_payment_gateways",
            school=self.school.slug,
            provider="mtn_momo",
            mode="metadata",
            stdout=buf,
        )
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["mode"], "metadata")
        st = payload["results"][0]["status"]
        self.assertEqual(st, "missing_credentials")
        self.assertTrue(
            PaymentGatewayHealthSnapshot.objects.filter(school=self.school).exists()
        )

    def test_momo_ready_when_integration_complete(self):
        Integration.objects.create(
            name="MTN GW",
            slug="mtn-gw-cmd",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "base_url": "https://sandbox.momo.example/",
                "api_key": "nonempty-hint",
            },
        )
        buf = StringIO()
        call_command(
            "check_payment_gateways",
            school=self.school.slug,
            provider="mtn_momo",
            stdout=buf,
        )
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["results"][0]["status"], "ready")

    def test_card_returns_external_required(self):
        buf = StringIO()
        call_command(
            "check_payment_gateways",
            school=self.school.slug,
            provider="card",
            stdout=buf,
        )
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["results"][0]["status"], "external_required")

    def test_stdout_never_echoes_integration_secret_values(self):
        secret_token = "rmc_super_secret_integration_token_xyzzy_999"
        Integration.objects.create(
            name="Stripe GW",
            slug="stripe-gw-cmd",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "stripe",
                "secret_key": "sk_test_" + secret_token,
            },
        )
        buf = StringIO()
        call_command(
            "check_payment_gateways",
            school=self.school.slug,
            provider="stripe",
            stdout=buf,
        )
        out = buf.getvalue()
        self.assertNotIn(secret_token, out)
        payload = json.loads(out)
        self.assertIn(payload["results"][0]["status"], ("ready", "degraded"))
