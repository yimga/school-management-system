"""Tests for the region-aware payment + messaging rails SOT."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_channel_rails import (
    messaging_channels_for_country,
    payment_rails_for_country,
)


class PaymentRailsTests(SimpleTestCase):
    def test_kenya_puts_mpesa_first(self):
        rails = payment_rails_for_country("KE")
        self.assertEqual(rails[0]["id"], "mpesa")
        self.assertEqual(rails[0]["kind"], "mobile_money")

    def test_nigeria_surfaces_mobile_money_paystack_first(self):
        rails = payment_rails_for_country("NG")
        self.assertEqual(rails[0]["kind"], "mobile_money")
        ids = [r["id"] for r in rails]
        self.assertIn("paystack", ids)

    def test_unknown_country_returns_card_and_bank(self):
        rails = payment_rails_for_country("ZZ")
        kinds = {r["kind"] for r in rails}
        ids = {r["id"] for r in rails}
        self.assertEqual(ids, {"card", "bank"})
        self.assertEqual(kinds, {"card", "bank"})
        # No mobile-money rail should be invented for an unknown market.
        self.assertNotIn("mobile_money", kinds)

    def test_case_insensitive(self):
        self.assertEqual(
            [r["id"] for r in payment_rails_for_country("ke")],
            [r["id"] for r in payment_rails_for_country("KE")],
        )
        self.assertEqual(
            [r["id"] for r in payment_rails_for_country("  ng  ")],
            [r["id"] for r in payment_rails_for_country("NG")],
        )

    def test_every_payment_entry_has_non_empty_id_and_label(self):
        for cc in ("KE", "NG", "GH", "IN", "BR", "US", "ZZ", ""):
            for rail in payment_rails_for_country(cc):
                self.assertTrue(rail["id"], f"empty id for {cc}: {rail}")
                self.assertTrue(rail["label"], f"empty label for {cc}: {rail}")
                self.assertIn(rail["kind"], {"mobile_money", "card", "bank", "wallet"})

    def test_no_duplicate_rail_ids(self):
        for cc in ("KE", "NG", "GH", "IN", "BR", "US"):
            ids = [r["id"] for r in payment_rails_for_country(cc)]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate rail for {cc}")


class MessagingChannelsTests(SimpleTestCase):
    def test_nigeria_and_kenya_put_whatsapp_first(self):
        for cc in ("NG", "KE"):
            channels = messaging_channels_for_country(cc)
            self.assertEqual(channels[0]["id"], "whatsapp", cc)

    def test_whatsapp_markets_always_include_sms_and_email(self):
        for cc in ("NG", "KE", "GH", "IN", "BR", "ZA"):
            ids = {c["id"] for c in messaging_channels_for_country(cc)}
            self.assertIn("sms", ids, cc)
            self.assertIn("email", ids, cc)

    def test_non_whatsapp_market_leads_with_email_or_inapp(self):
        channels = messaging_channels_for_country("US")
        self.assertIn(channels[0]["id"], {"email", "inapp"})
        # SMS + email still present everywhere.
        ids = {c["id"] for c in channels}
        self.assertIn("sms", ids)
        self.assertIn("email", ids)

    def test_case_insensitive(self):
        self.assertEqual(
            [c["id"] for c in messaging_channels_for_country("ng")],
            [c["id"] for c in messaging_channels_for_country("NG")],
        )

    def test_every_channel_entry_has_non_empty_id_label_note(self):
        for cc in ("NG", "KE", "US", "ZZ", ""):
            for ch in messaging_channels_for_country(cc):
                self.assertTrue(ch["id"], f"empty id for {cc}: {ch}")
                self.assertTrue(ch["label"], f"empty label for {cc}: {ch}")
                self.assertTrue(ch["note"], f"empty note for {cc}: {ch}")
