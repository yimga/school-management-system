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


class PaymentRailsLocalizationTests(SimpleTestCase):
    def test_default_lang_is_english(self):
        default = payment_rails_for_country("US")
        explicit = payment_rails_for_country("US", lang="en")
        self.assertEqual(default, explicit)
        ids = {r["id"]: r["label"] for r in explicit}
        self.assertEqual(ids["card"], "Card")

    def test_french_translates_generic_labels_not_brands(self):
        # US: only generic Card + ACH (ACH is a brand/scheme name, untranslated).
        us_fr = payment_rails_for_country("US", lang="fr")
        labels = {r["id"]: r["label"] for r in us_fr}
        self.assertEqual(labels["card"], "Carte")
        self.assertEqual(labels["ach"], "ACH")  # brand name unchanged
        # KE: M-Pesa brand name must stay verbatim in any language.
        ke_fr = payment_rails_for_country("KE", lang="fr")
        ke_labels = {r["id"]: r["label"] for r in ke_fr}
        self.assertEqual(ke_labels["mpesa"], "M-Pesa")

    def test_arabic_card_label_is_arabic(self):
        ar = payment_rails_for_country("ZZ", lang="ar")
        labels = {r["id"]: r["label"] for r in ar}
        self.assertNotEqual(labels["card"], "Card")
        self.assertTrue(
            any("؀" <= ch <= "ۿ" for ch in labels["card"]),
            "Arabic Card label must contain Arabic-script characters",
        )
        self.assertNotEqual(labels["bank"], "Bank transfer")

    def test_unknown_lang_falls_back_to_english(self):
        en = payment_rails_for_country("US", lang="en")
        zz = payment_rails_for_country("US", lang="zz")
        self.assertEqual(en, zz)

    def test_regional_variant_resolves_to_base_lang(self):
        pt = payment_rails_for_country("BR", lang="pt")
        pt_br = payment_rails_for_country("BR", lang="pt-BR")
        self.assertEqual(pt, pt_br)

    def test_order_and_ids_unchanged_by_language(self):
        for cc in ("KE", "NG", "US", "BR"):
            en_ids = [r["id"] for r in payment_rails_for_country(cc, lang="en")]
            fr_ids = [r["id"] for r in payment_rails_for_country(cc, lang="fr")]
            self.assertEqual(en_ids, fr_ids, cc)


class MessagingChannelsLocalizationTests(SimpleTestCase):
    def test_default_lang_is_english(self):
        default = messaging_channels_for_country("NG")
        explicit = messaging_channels_for_country("NG", lang="en")
        self.assertEqual(default, explicit)

    def test_french_translates_notes_and_inapp_label_not_brands(self):
        en = messaging_channels_for_country("NG", lang="en")
        fr = messaging_channels_for_country("NG", lang="fr")
        self.assertEqual(
            [c["id"] for c in en], [c["id"] for c in fr]
        )
        by_id_en = {c["id"]: c for c in en}
        by_id_fr = {c["id"]: c for c in fr}
        # Brand labels stay verbatim.
        self.assertEqual(by_id_fr["whatsapp"]["label"], "WhatsApp")
        self.assertEqual(by_id_fr["sms"]["label"], "SMS")
        self.assertEqual(by_id_fr["email"]["label"], "Email")
        # In-app label + notes are translated.
        self.assertNotEqual(by_id_en["inapp"]["label"], by_id_fr["inapp"]["label"])
        self.assertNotEqual(by_id_en["whatsapp"]["note"], by_id_fr["whatsapp"]["note"])

    def test_arabic_returns_proper_arabic_notes(self):
        ar = messaging_channels_for_country("NG", lang="ar")
        by_id = {c["id"]: c for c in ar}
        self.assertTrue(
            any("؀" <= ch <= "ۿ" for ch in by_id["whatsapp"]["note"]),
            "Arabic note must contain Arabic-script characters",
        )

    def test_unknown_lang_falls_back_to_english(self):
        en = messaging_channels_for_country("US", lang="en")
        zz = messaging_channels_for_country("US", lang="zz")
        self.assertEqual(en, zz)
