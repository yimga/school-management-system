"""Stripe Connect settings bridge tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.models import School
from apps.schools.stripe_connect_settings import (
    get_stripe_connect_payload,
    is_stripe_connected,
    merge_stripe_account_object,
    set_stripe_connect_payload,
)


class StripeConnectSettingsTests(SimpleTestCase):
    def test_default_payload_empty(self):
        school = School(name="T", slug="t", subdomain="t")
        payload = get_stripe_connect_payload(school)
        self.assertEqual(payload["account_id"], "")
        self.assertEqual(payload["onboarding_status"], "pending")
        self.assertFalse(is_stripe_connected(school))

    def test_merge_account_object_complete(self):
        school = School(name="T", slug="t", subdomain="t", settings={})
        merge_stripe_account_object(
            school,
            {
                "id": "acct_test123",
                "type": "express",
                "charges_enabled": True,
                "payouts_enabled": True,
                "details_submitted": True,
            },
        )
        payload = get_stripe_connect_payload(school)
        self.assertEqual(payload["account_id"], "acct_test123")
        self.assertEqual(payload["onboarding_status"], "complete")
        self.assertTrue(is_stripe_connected(school))

    def test_set_payload_preserves_account_id(self):
        school = School(name="T", slug="t", subdomain="t", settings={})
        set_stripe_connect_payload(school, {"account_id": "acct_keep"})
        set_stripe_connect_payload(school, {"charges_enabled": True})
        self.assertEqual(get_stripe_connect_payload(school)["account_id"], "acct_keep")
