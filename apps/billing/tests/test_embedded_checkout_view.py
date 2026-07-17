"""Wave P-C+E (v3.95.1 — 2026-05-26) — Embedded checkout HTTP view tests."""

from __future__ import annotations

import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.billing.embedded_checkout_psp_dispatcher import (
    _is_dispatchable,
    make_dispatcher,
)
from apps.billing.views_embedded_checkout import (
    _parse_payload,
    create_embedded_checkout_session,
)


def _make_request(body: dict):
    rf = RequestFactory()
    return rf.post(
        "/billing/embedded-checkout/session/",
        data=json.dumps(body).encode("utf-8"),
        content_type="application/json",
    )


class PayloadParserTests(SimpleTestCase):

    def test_valid_payload_parses(self):
        body = json.dumps({
            "tenant_id": "t1",
            "parent_email": "p@e.com",
            "parent_phone": "+237600000001",
            "line_items": [{
                "sku": "TUITION", "description": "Term 1",
                "amount_minor": 100000, "currency": "NGN", "quantity": 1,
            }],
            "purpose": "tuition_fee",
        }).encode("utf-8")
        req, err = _parse_payload(body)
        self.assertEqual(err, "")
        self.assertIsNotNone(req)
        self.assertEqual(req.tenant_id, "t1")
        self.assertEqual(len(req.line_items), 1)

    def test_invalid_json_returns_error(self):
        req, err = _parse_payload(b"not json")
        self.assertIsNone(req)
        self.assertIn("invalid JSON", err)

    def test_non_dict_returns_error(self):
        req, err = _parse_payload(b"[1,2,3]")
        self.assertIsNone(req)
        self.assertIn("must be an object", err)

    def test_missing_line_items_returns_error(self):
        body = json.dumps({"tenant_id": "t1"}).encode()
        req, err = _parse_payload(body)
        self.assertIsNone(req)
        self.assertIn("line_items", err)

    def test_empty_line_items_returns_error(self):
        body = json.dumps({"line_items": []}).encode()
        req, err = _parse_payload(body)
        self.assertIsNone(req)

    def test_line_item_non_object_returns_error(self):
        body = json.dumps({"line_items": ["not an object"]}).encode()
        req, err = _parse_payload(body)
        self.assertIsNone(req)
        self.assertIn("every line item", err)


class PSPDispatcherTests(SimpleTestCase):

    def test_unknown_processor_not_dispatchable(self):
        ok, reason = _is_dispatchable("fake-psp")
        self.assertFalse(ok)
        self.assertIn("not in registry", reason)

    def test_known_processor_dispatchable(self):
        # Stripe is in the seeded registry.
        ok, _reason = _is_dispatchable("stripe")
        self.assertTrue(ok)

    def test_dispatcher_returns_dev_url_when_psp_not_live(self):
        from apps.billing.embedded_checkout import (
            CheckoutLineItem, CheckoutSessionRequest,
        )
        req = CheckoutSessionRequest(
            tenant_id="t1", parent_email="p@e.com", parent_phone="",
            line_items=(CheckoutLineItem(
                sku="X", description="", amount_minor=1000, currency="USD",
            ),),
        )
        dispatcher = make_dispatcher(force_dev_mode=True)
        result = dispatcher("stripe", req, "rmc_ck_abc", 1000)
        self.assertTrue(result["ok"])
        self.assertIn("mode=dev", result["hosted_url"])

    def test_dispatcher_unknown_processor_returns_error(self):
        from apps.billing.embedded_checkout import (
            CheckoutLineItem, CheckoutSessionRequest,
        )
        req = CheckoutSessionRequest(
            tenant_id="t1", parent_email="p@e.com", parent_phone="",
            line_items=(CheckoutLineItem(
                sku="X", description="", amount_minor=1000, currency="USD",
            ),),
        )
        dispatcher = make_dispatcher()
        result = dispatcher("fake-psp", req, "rmc_ck_abc", 1000)
        self.assertFalse(result["ok"])
        self.assertIn("not in registry", result["error"])


class CreateSessionViewTests(SimpleTestCase):

    @override_settings(EMBEDDED_CHECKOUT_DEV_MODE=True)
    def test_valid_post_returns_ok(self):
        """A well-formed payload parses into a session of the right shape.

        Dev mode is pinned on because this asserts the REQUEST contract (the
        400 / 422 / 200 trio in this class), not settlement: no PSP adapter is
        live, so with dev mode off the same payload correctly returns 422 --
        the checkout is refused rather than faking success. That fail-closed
        contract is covered by
        ``test_embedded_checkout_never_fakes_success.py``.
        """
        req = _make_request({
            "tenant_id": "t1",
            "parent_email": "parent@example.com",
            "parent_phone": "",
            "line_items": [{
                "sku": "TUITION", "description": "Term 1",
                "amount_minor": 100000, "currency": "USD", "quantity": 1,
            }],
            "purpose": "tuition_fee",
        })
        resp = create_embedded_checkout_session(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body["ok"])
        self.assertTrue(body["session_id"].startswith("rmc_ck_"))
        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["total_minor"], 100000)

    def test_invalid_json_returns_400(self):
        from django.test import RequestFactory
        req = RequestFactory().post(
            "/billing/embedded-checkout/session/",
            data=b"not json",
            content_type="application/json",
        )
        resp = create_embedded_checkout_session(req)
        self.assertEqual(resp.status_code, 400)

    def test_validation_failure_returns_422(self):
        req = _make_request({
            "tenant_id": "",  # missing
            "parent_email": "parent@example.com",
            "line_items": [{
                "sku": "X", "description": "", "amount_minor": 100,
                "currency": "USD", "quantity": 1,
            }],
        })
        resp = create_embedded_checkout_session(req)
        self.assertEqual(resp.status_code, 422)
        body = json.loads(resp.content)
        self.assertFalse(body["ok"])
        self.assertIn("tenant_id", body["error"])
