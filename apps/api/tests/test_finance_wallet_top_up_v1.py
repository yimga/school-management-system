"""POST /api/v1/finance/wallet/top-up JSON contract (batch 15 #143)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


class FinanceWalletTopUpV1Tests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Wallet API School",
            slug="wallet-api-school",
            subdomain="wallet-api-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="wallet-api-admin",
            email="wallet-api-admin@example.com",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def _host(self):
        return {"HTTP_HOST": f"{self.school.subdomain}.runmycampus.com"}

    def test_top_up_success_json_shape(self):
        """Stable keys for integrators: ok, balances, currency, transaction id, reference."""
        self.client.force_login(self.user)
        url = reverse("api_v1:finance-wallet-top-up")
        response = self.client.post(
            url,
            data=json.dumps({"amount": "42.50", "reference": "api-contract-ref"}),
            content_type="application/json",
            **self._host(),
        )
        self.assertEqual(response.status_code, 201, msg=response.content)
        body = response.json()
        self.assertIs(body.get("ok"), True)
        self.assertEqual(body.get("wallet_balance"), "42.50")
        self.assertIsInstance(body.get("currency_code"), str)
        self.assertTrue(str(body.get("currency_code")).strip())
        self.assertIsInstance(body.get("transaction_id"), int)
        self.assertEqual(body.get("reference"), "api-contract-ref")
