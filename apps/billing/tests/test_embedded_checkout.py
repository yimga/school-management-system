"""Wave I (v3.95.0 — 2026-05-26) — Embedded Checkout kernel tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.billing.embedded_checkout import (
    CheckoutLineItem,
    CheckoutSessionRequest,
    allowed_purposes,
    candidate_processors,
    create_session,
    format_amount_for_display,
    session_currency,
    total_minor,
    validate_request,
)


class ValidationTests(SimpleTestCase):

    def _req(self, **kw):
        defaults = dict(
            tenant_id="t1",
            parent_email="parent@example.com",
            parent_phone="+237600000001",
            line_items=(CheckoutLineItem(
                sku="TUITION_T1", description="Term 1 Tuition",
                amount_minor=14500000, currency="NGN",
            ),),
            purpose="tuition_fee",
        )
        defaults.update(kw)
        return CheckoutSessionRequest(**defaults)

    def test_valid_request_passes(self):
        self.assertEqual(validate_request(self._req()), "")

    def test_missing_tenant_id_fails(self):
        self.assertIn("tenant_id", validate_request(self._req(tenant_id="")))

    def test_missing_parent_contact_fails(self):
        err = validate_request(self._req(parent_email="", parent_phone=""))
        self.assertIn("parent contact", err)

    def test_empty_line_items_fails(self):
        self.assertIn("line item", validate_request(self._req(line_items=())))

    def test_invalid_purpose_fails(self):
        self.assertIn("purpose", validate_request(self._req(purpose="malware")))

    def test_invalid_currency_fails(self):
        bad = CheckoutLineItem(sku="X", description="", amount_minor=1, currency="ZZZZ", quantity=1)
        self.assertIn("ISO currency", validate_request(self._req(line_items=(bad,))))

    def test_mixed_currencies_fail(self):
        items = (
            CheckoutLineItem(sku="A", description="", amount_minor=100, currency="NGN"),
            CheckoutLineItem(sku="B", description="", amount_minor=100, currency="USD"),
        )
        self.assertIn("currency", validate_request(self._req(line_items=items)))

    def test_zero_amount_fails(self):
        bad = CheckoutLineItem(sku="X", description="", amount_minor=0, currency="NGN", quantity=1)
        self.assertIn("non-positive amount", validate_request(self._req(line_items=(bad,))))

    def test_zero_quantity_fails(self):
        bad = CheckoutLineItem(sku="X", description="", amount_minor=100, currency="NGN", quantity=0)
        self.assertIn("non-positive quantity", validate_request(self._req(line_items=(bad,))))


class CurrencyAndTotalsTests(SimpleTestCase):

    def test_total_minor_sums_quantity(self):
        req = CheckoutSessionRequest(
            tenant_id="t1", parent_email="p@e.com", parent_phone="",
            line_items=(
                CheckoutLineItem(sku="A", description="", amount_minor=5000, currency="NGN", quantity=2),
                CheckoutLineItem(sku="B", description="", amount_minor=1000, currency="NGN", quantity=3),
            ),
        )
        self.assertEqual(total_minor(req), 5000 * 2 + 1000 * 3)
        self.assertEqual(session_currency(req), "NGN")


class ProcessorSelectionTests(SimpleTestCase):

    def _req(self, currency, preferred=""):
        return CheckoutSessionRequest(
            tenant_id="t1", parent_email="p@e.com", parent_phone="",
            line_items=(CheckoutLineItem(
                sku="X", description="", amount_minor=10000, currency=currency,
            ),),
            preferred_processor=preferred,
        )

    def test_ngn_prefers_paystack(self):
        self.assertEqual(candidate_processors(self._req("NGN"))[0], "paystack")

    def test_kes_prefers_flutterwave(self):
        self.assertEqual(candidate_processors(self._req("KES"))[0], "flutterwave")

    def test_inr_prefers_razorpay(self):
        self.assertEqual(candidate_processors(self._req("INR"))[0], "razorpay")

    def test_xaf_prefers_flutterwave_then_momo_then_orange(self):
        cps = candidate_processors(self._req("XAF"))
        self.assertEqual(cps[0], "flutterwave")
        self.assertIn("mtn_momo", cps)
        self.assertIn("orange_money", cps)

    def test_usd_prefers_stripe(self):
        self.assertEqual(candidate_processors(self._req("USD")), ("stripe",))

    def test_unknown_currency_falls_back_to_stripe(self):
        # ISK isn't in our map.
        self.assertEqual(candidate_processors(self._req("ISK")), ("stripe",))

    def test_preferred_processor_overrides_currency_default(self):
        self.assertEqual(
            candidate_processors(self._req("NGN", preferred="stripe")),
            ("stripe",),
        )


class CreateSessionTests(SimpleTestCase):

    def _req(self, **kw):
        defaults = dict(
            tenant_id="t1",
            parent_email="parent@example.com",
            parent_phone="+237600000001",
            line_items=(CheckoutLineItem(
                sku="TUITION_T1", description="Term 1 Tuition",
                amount_minor=14500000, currency="NGN",
            ),),
            purpose="tuition_fee",
        )
        defaults.update(kw)
        return CheckoutSessionRequest(**defaults)

    def test_create_session_without_dispatcher_returns_ready_shape(self):
        result = create_session(self._req())
        self.assertTrue(result.ok)
        self.assertTrue(result.session_id.startswith("rmc_ck_"))
        self.assertEqual(result.processor, "paystack")  # NGN top candidate
        self.assertEqual(result.total_minor, 14500000)
        self.assertEqual(result.currency, "NGN")
        self.assertFalse(result.metadata.get("dispatched"))

    def test_create_session_invalid_returns_error(self):
        result = create_session(self._req(line_items=()))
        self.assertFalse(result.ok)
        self.assertIn("line item", result.error)

    def test_create_session_dispatcher_success(self):
        captured = {}

        def disp(processor, req, session_id, total):
            captured["processor"] = processor
            captured["session_id"] = session_id
            captured["total"] = total
            return {"ok": True, "hosted_url": f"https://psp.example/{session_id}",
                    "metadata": {"checkout_intent_id": "abc123"}}

        result = create_session(self._req(), psp_dispatcher=disp)
        self.assertTrue(result.ok)
        self.assertEqual(captured["processor"], "paystack")
        self.assertEqual(captured["total"], 14500000)
        self.assertTrue(result.hosted_url.startswith("https://psp.example/"))
        self.assertTrue(result.metadata.get("dispatched"))
        self.assertEqual(result.metadata.get("checkout_intent_id"), "abc123")

    def test_create_session_dispatcher_failure_tries_next(self):
        attempts = []

        def disp(processor, _req, _sid, _total):
            attempts.append(processor)
            if processor == "paystack":
                return {"ok": False, "error": "paystack down"}
            return {"ok": True, "hosted_url": "https://fw.example/ok"}

        # NGN candidates = (paystack, flutterwave, stripe)
        result = create_session(self._req(), psp_dispatcher=disp)
        self.assertTrue(result.ok)
        self.assertEqual(attempts, ["paystack", "flutterwave"])
        self.assertEqual(result.processor, "flutterwave")

    def test_create_session_dispatcher_exception_is_swallowed(self):
        attempts = []

        def disp(processor, _req, _sid, _total):
            attempts.append(processor)
            if processor == "paystack":
                raise RuntimeError("network exploded")
            return {"ok": True, "hosted_url": "https://x"}

        result = create_session(self._req(), psp_dispatcher=disp)
        self.assertTrue(result.ok)
        self.assertEqual(result.processor, "flutterwave")
        self.assertEqual(len(attempts), 2)

    def test_create_session_all_processors_fail(self):
        def disp(_processor, _req, _sid, _total):
            return {"ok": False, "error": "down"}

        result = create_session(self._req(), psp_dispatcher=disp)
        self.assertFalse(result.ok)
        self.assertIn("down", result.error)


class DisplayFormatTests(SimpleTestCase):

    def test_two_decimal_currency(self):
        self.assertEqual(format_amount_for_display(14500000, "NGN"), "145,000.00 NGN")
        self.assertEqual(format_amount_for_display(9999, "USD"), "99.99 USD")

    def test_zero_decimal_currency(self):
        self.assertEqual(format_amount_for_display(15000, "JPY"), "15,000 JPY")
        self.assertEqual(format_amount_for_display(50000, "XAF"), "50,000 XAF")

    def test_allowed_purposes_includes_core(self):
        purposes = allowed_purposes()
        for p in ("tuition_fee", "transport_fee", "exam_fee", "donation"):
            self.assertIn(p, purposes)
