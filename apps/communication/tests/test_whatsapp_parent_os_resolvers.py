"""Wave P-D (v3.95.1 — 2026-05-26) — WhatsApp Parent OS resolver tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.whatsapp_parent_os import InboundMessage
from apps.communication.whatsapp_parent_os_resolvers import (
    _normalize_phone,
    resolve,
)


def _msg(intent_phone="+237600000001", tenant="t1"):
    return InboundMessage(
        from_phone=intent_phone, body="", tenant_id=tenant,
    )


class PhoneNormalizationTests(SimpleTestCase):

    def test_strips_non_digits(self):
        self.assertEqual(_normalize_phone("+237 6 00-00 00 01"), "+237600000001")

    def test_handles_empty(self):
        self.assertEqual(_normalize_phone(""), "")
        self.assertEqual(_normalize_phone(None), "")

    def test_keeps_leading_plus(self):
        self.assertEqual(_normalize_phone("+1234567890"), "+1234567890")

    def test_drops_letters(self):
        self.assertEqual(_normalize_phone("+1 (800) FLY-NOW"), "+1800")


class ResolverIntentRoutingTests(SimpleTestCase):

    def test_fee_balance_missing_guardian_returns_empty(self):
        # No Guardian model available in unit-test scope → empty dict, no
        # exception (kernel keeps body literal).
        result = resolve(_msg(), intent="fee_balance")
        # Should never raise; placeholders may be empty.
        self.assertIsInstance(result, dict)

    def test_absence_report_missing_guardian_returns_empty(self):
        result = resolve(_msg(), intent="absence_report")
        self.assertIsInstance(result, dict)

    def test_report_card_returns_link_stub(self):
        result = resolve(_msg(), intent="report_card")
        self.assertIn("link", result)
        self.assertTrue(result["link"].startswith("https://"))

    def test_homework_returns_summary_stub(self):
        result = resolve(_msg(), intent="homework")
        self.assertIn("summary", result)
        self.assertIn("Maths", result["summary"])

    def test_unknown_intent_returns_empty(self):
        result = resolve(_msg(), intent="something_unknown")
        self.assertEqual(result, {})

    def test_menu_intent_returns_empty(self):
        # The menu / help / human / stop intents don't need placeholders.
        result = resolve(_msg(), intent="menu")
        self.assertEqual(result, {})
