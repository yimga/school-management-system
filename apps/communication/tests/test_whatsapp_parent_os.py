"""Wave H (v3.95.0 — 2026-05-26) — WhatsApp Parent OS kernel + webhook tests.

Mock-mode: never hits Meta. The kernel is pure (modulo in-memory rate
buckets); the webhook view is exercised via Django RequestFactory with a
stubbed `WhatsAppIntegration.verify_webhook` / `.send_message`.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.communication.whatsapp_parent_os import (
    InboundMessage,
    RoutingConfig,
    classify_intent_keyword,
    known_intents,
    reset_rate_buckets,
    route_inbound_message,
    template_key_for,
)


class IntentKeywordClassificationTests(SimpleTestCase):
    """Keyword classifier returns the right intent for common parent phrases."""

    def test_fee_balance_simple(self):
        self.assertEqual(classify_intent_keyword("fee"), "fee_balance")
        self.assertEqual(classify_intent_keyword("FEES"), "fee_balance")
        self.assertEqual(classify_intent_keyword("balance"), "fee_balance")

    def test_fee_balance_french(self):
        self.assertEqual(classify_intent_keyword("frais"), "fee_balance")

    def test_fee_balance_portuguese(self):
        self.assertEqual(classify_intent_keyword("mensalidade"), "fee_balance")

    def test_absence_report(self):
        self.assertEqual(classify_intent_keyword("absent"), "absence_report")
        self.assertEqual(classify_intent_keyword("My child is sick today"), "absence_report")
        self.assertEqual(classify_intent_keyword("not coming"), "absence_report")

    def test_report_card(self):
        self.assertEqual(classify_intent_keyword("report"), "report_card")
        self.assertEqual(classify_intent_keyword("bulletin"), "report_card")
        self.assertEqual(classify_intent_keyword("notas"), "report_card")

    def test_homework(self):
        self.assertEqual(classify_intent_keyword("hw"), "homework")
        self.assertEqual(classify_intent_keyword("devoir"), "homework")

    def test_menu(self):
        self.assertEqual(classify_intent_keyword("menu"), "menu")
        self.assertEqual(classify_intent_keyword("hi"), "menu")
        self.assertEqual(classify_intent_keyword("hello"), "menu")

    def test_help(self):
        self.assertEqual(classify_intent_keyword("help"), "help")
        self.assertEqual(classify_intent_keyword("ayuda"), "help")

    def test_human_handoff(self):
        self.assertEqual(classify_intent_keyword("human"), "human")
        self.assertEqual(classify_intent_keyword("speak to a person"), "human")

    def test_stop(self):
        self.assertEqual(classify_intent_keyword("stop"), "stop")
        self.assertEqual(classify_intent_keyword("unsubscribe"), "stop")

    def test_unknown_falls_through(self):
        self.assertEqual(classify_intent_keyword("xkcd random gibberish"), "unknown")
        self.assertEqual(classify_intent_keyword(""), "unknown")
        self.assertEqual(classify_intent_keyword(None), "unknown")  # type: ignore[arg-type]

    def test_punctuation_stripped(self):
        self.assertEqual(classify_intent_keyword("FEES!!!"), "fee_balance")
        self.assertEqual(classify_intent_keyword("help???"), "help")

    def test_substring_does_not_false_match(self):
        # "I afford fees no problem" — single-word lookups use token match
        # so 'afford' won't match the FEE keyword token.
        result = classify_intent_keyword("I afford the trip")
        self.assertEqual(result, "unknown")


class RouteInboundMessageTests(SimpleTestCase):
    """End-to-end kernel routing: inbound → OutboundIntent."""

    def setUp(self):
        reset_rate_buckets()

    def _msg(self, body="", button="", phone="+237600000001", tenant="t1"):
        return InboundMessage(
            from_phone=phone, body=body, tenant_id=tenant, button_payload=button,
        )

    def test_button_payload_wins_over_body(self):
        out = route_inbound_message(self._msg(body="random", button="fee_balance"))
        self.assertEqual(out.intent, "fee_balance")
        self.assertEqual(out.template_key, "parent_os_fee_balance_reply")

    def test_unknown_intent_returns_safe_menu(self):
        out = route_inbound_message(self._msg(body="zzz random"))
        self.assertEqual(out.intent, "unknown")
        self.assertEqual(out.template_key, "parent_os_unknown_intent")
        self.assertIn("MENU", out.body_text)

    def test_human_intent_flags_requires_human(self):
        out = route_inbound_message(self._msg(body="human"))
        self.assertTrue(out.requires_human)
        self.assertEqual(out.intent, "human")

    def test_allowlist_excludes_intent(self):
        # Tenant disabled homework intent — should degrade to unknown.
        cfg = RoutingConfig(allowlist=("fee_balance", "menu", "help", "human", "stop"))
        out = route_inbound_message(self._msg(body="homework"), config=cfg)
        self.assertEqual(out.intent, "unknown")

    def test_rate_limit_triggers_after_quota(self):
        cfg = RoutingConfig(rate_limit_per_hour=2)
        for _ in range(2):
            out = route_inbound_message(self._msg(body="menu"), config=cfg)
            self.assertFalse(out.rate_limited)
        # 3rd in same hour — rate-limited.
        out = route_inbound_message(self._msg(body="menu"), config=cfg)
        self.assertTrue(out.rate_limited)
        self.assertEqual(out.template_key, "parent_os_rate_limited")

    def test_stop_bypasses_rate_limit(self):
        cfg = RoutingConfig(rate_limit_per_hour=1)
        # Burn the quota.
        route_inbound_message(self._msg(body="menu"), config=cfg)
        # STOP must still be honored.
        out = route_inbound_message(self._msg(body="stop"), config=cfg)
        self.assertFalse(out.rate_limited)
        self.assertEqual(out.intent, "stop")

    def test_placeholder_resolver_substitutes_body(self):
        def resolver(_msg, intent):
            if intent == "fee_balance":
                return {"balance": "₦145,000"}
            return {}

        cfg = RoutingConfig(placeholder_resolver=resolver)
        out = route_inbound_message(self._msg(body="fees"), config=cfg)
        self.assertIn("₦145,000", out.body_text)

    def test_placeholder_resolver_exception_is_swallowed(self):
        def broken(_msg, _intent):
            raise RuntimeError("boom")

        cfg = RoutingConfig(placeholder_resolver=broken)
        out = route_inbound_message(self._msg(body="fees"), config=cfg)
        # Falls back to literal template with no substitution.
        self.assertIn("{balance}", out.body_text)


class KnownIntentsAndTemplateKeysTests(SimpleTestCase):
    """Public introspection — registry must stay aligned with kernel logic."""

    def test_known_intents_excludes_unknown(self):
        intents = known_intents()
        self.assertNotIn("unknown", intents)
        # All allowlist intents present.
        for k in ("fee_balance", "absence_report", "report_card", "homework",
                  "menu", "help", "human", "stop"):
            self.assertIn(k, intents)

    def test_template_key_for_unknown_falls_back(self):
        key = template_key_for("nonexistent")
        self.assertEqual(key, "parent_os_unknown_intent")


class MetaWebhookParserTests(SimpleTestCase):
    """The Meta envelope parser handles text / button / interactive correctly."""

    def test_parses_text_message(self):
        from apps.communication.views_whatsapp_webhook import _parse_meta_webhook

        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "237600000001",
                            "id": "wamid.ABC",
                            "type": "text",
                            "text": {"body": "fees"},
                        }],
                    },
                }],
            }],
        }
        out = _parse_meta_webhook(payload)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].from_phone, "237600000001")
        self.assertEqual(out[0].body, "fees")

    def test_parses_interactive_button_reply(self):
        from apps.communication.views_whatsapp_webhook import _parse_meta_webhook

        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "237600000001",
                            "id": "wamid.XYZ",
                            "type": "interactive",
                            "interactive": {
                                "button_reply": {
                                    "id": "fee_balance",
                                    "title": "Check fees",
                                },
                            },
                        }],
                    },
                }],
            }],
        }
        out = _parse_meta_webhook(payload)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].button_payload, "fee_balance")

    def test_ignores_image_messages(self):
        from apps.communication.views_whatsapp_webhook import _parse_meta_webhook

        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "237600000001",
                            "type": "image",
                            "image": {"id": "mediaid"},
                        }],
                    },
                }],
            }],
        }
        out = _parse_meta_webhook(payload)
        self.assertEqual(out, [])

    def test_empty_payload_is_safe(self):
        from apps.communication.views_whatsapp_webhook import _parse_meta_webhook

        self.assertEqual(_parse_meta_webhook({}), [])
        self.assertEqual(_parse_meta_webhook({"entry": []}), [])
        self.assertEqual(_parse_meta_webhook({"entry": [{}]}), [])


class WebhookViewTests(SimpleTestCase):
    """End-to-end webhook view via RequestFactory + stubbed integration."""

    def setUp(self):
        self.rf = RequestFactory()
        reset_rate_buckets()

    def _make_view_request(self, body: bytes):
        req = self.rf.post(
            "/comms/whatsapp/webhook/",
            data=body,
            content_type="application/json",
        )
        return req

    def test_get_handshake_returns_challenge_on_valid_token(self):
        from apps.communication import views_whatsapp_webhook as mod

        req = self.rf.get("/comms/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=t&hub.challenge=42")
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=True):
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"42")

    def test_get_handshake_returns_403_on_invalid_token(self):
        from apps.communication import views_whatsapp_webhook as mod

        req = self.rf.get("/comms/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=bad&hub.challenge=42")
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=False):
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 403)

    def test_post_invalid_signature_returns_403(self):
        from apps.communication import views_whatsapp_webhook as mod

        req = self._make_view_request(b'{"entry":[]}')
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=False):
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 403)

    def test_post_disabled_tenant_acks_without_sending(self):
        from apps.communication import views_whatsapp_webhook as mod

        payload = json.dumps({
            "entry": [{"changes": [{"value": {"messages": [{
                "from": "237600000001", "type": "text", "text": {"body": "fees"},
            }]}}]}],
        }).encode()
        req = self._make_view_request(payload)
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=True), \
             patch.object(mod, "_is_enabled_for_tenant", return_value=False), \
             patch.object(mod.WhatsAppIntegration, "send_message") as send_mock:
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content)["status"], "disabled")
        send_mock.assert_not_called()

    def test_post_enabled_tenant_dispatches_send(self):
        from apps.communication import views_whatsapp_webhook as mod

        payload = json.dumps({
            "entry": [{"changes": [{"value": {"messages": [{
                "from": "237600000001", "type": "text",
                "text": {"body": "fees"},
            }]}}]}],
        }).encode()
        req = self._make_view_request(payload)
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=True), \
             patch.object(mod, "_is_enabled_for_tenant", return_value=True), \
             patch.object(mod.WhatsAppIntegration, "send_message",
                          return_value={"success": True, "message_id": "x"}) as send_mock:
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content)["handled"], 1)
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertEqual(args[0], "237600000001")
        self.assertIn("balance", args[1].lower())

    def test_post_invalid_json_returns_400(self):
        from apps.communication import views_whatsapp_webhook as mod

        req = self._make_view_request(b"not json")
        with patch.object(mod.WhatsAppIntegration, "verify_webhook", return_value=True), \
             patch.object(mod, "_is_enabled_for_tenant", return_value=True):
            resp = mod.whatsapp_webhook(req)
        self.assertEqual(resp.status_code, 400)
