# Embedded Checkout — Tenant Integration Guide

**Wave I + Wave P-C/E · v3.95.1 · 2026-05-26**

The Embedded Checkout primitive lets a school accept parent fee payments through a single platform endpoint that auto-routes to the right PSP (Stripe / Paystack / Flutterwave / Razorpay / MTN MoMo / Orange Money) based on currency.

## Endpoint

```
POST /billing/embedded-checkout/session/
Content-Type: application/json
```

## Request body

```json
{
  "tenant_id": "greenwich-park",
  "parent_email": "parent@example.com",
  "parent_phone": "+237600000001",
  "line_items": [
    {"sku": "TUITION_T1", "description": "Term 1 Tuition", "amount_minor": 14500000, "currency": "NGN", "quantity": 1}
  ],
  "purpose": "tuition_fee",
  "student_reference": "STU-00042",
  "locale": "en",
  "success_url": "https://yourschool.com/payment-ok",
  "cancel_url": "https://yourschool.com/payment-cancel",
  "preferred_processor": ""
}
```

`amount_minor` is in the smallest unit of the currency (NGN kobo, USD cents, JPY yen). `preferred_processor` is optional — when empty, the platform picks the most-local PSP for the currency.

## Response (200 OK)

```json
{
  "ok": true,
  "session_id": "rmc_ck_abc123def456",
  "hosted_url": "https://checkout.stripe.com/...",
  "processor": "paystack",
  "currency": "NGN",
  "total_minor": 14500000,
  "metadata": {"dispatched": true}
}
```

## Currency → processor routing

| Currency | Candidates (most-local first) |
|---|---|
| NGN | paystack, flutterwave, stripe |
| GHS | paystack, flutterwave |
| KES / UGX / TZS / RWF | flutterwave, mtn_momo |
| XAF / XOF | flutterwave, orange_money, mtn_momo |
| ZAR | stripe, flutterwave |
| INR | razorpay, stripe |
| USD / GBP / EUR / AUD / NZD / BRL / MXN / others | stripe |

If the first candidate fails, the dispatcher tries the next. The full list lives in [apps/billing/embedded_checkout.py:_CURRENCY_TO_PREFERRED_PROCESSORS](beta/school-management-system/apps/billing/embedded_checkout.py).

## Modes

- **Dev mode** (default in v3.95.1) — returns a placeholder `hosted_url` with `?mode=dev`. Real settlement requires the PSP's `adapter_status="live"` in [apps/billing/psp_adapter_registry.py](beta/school-management-system/apps/billing/psp_adapter_registry.py) PLUS valid credentials in the tenant's `PlatformBillingProcessorConfig` row.
- **Live mode** — engages when a per-PSP live creator is implemented (currently Stripe has scaffolding; Wave P-E+1 ships the remaining 5).

## Error handling

| HTTP | Condition |
|---|---|
| 400 | Invalid JSON, missing line items, malformed line item |
| 403 | `tenant_id` in body doesn't match the request's resolved School |
| 422 | All processor candidates failed (`error` describes the chain) |
| 200 OK | Success with `ok: false` if validation fails before dispatch |

## Boundaries preserved

- **No direct PSP SDK imports** in the kernel — every vendor call routes through `psp_adapter_registry.get_psp` + per-PSP creator functions in `apps/billing/`.
- **CSRF-exempt + POST-only** at the view layer. CSRF is replaced by the `tenant_id` cross-check against the request's resolved School.

## Tests

[apps/billing/tests/test_embedded_checkout.py](beta/school-management-system/apps/billing/tests/test_embedded_checkout.py) — 26 unit tests covering validation, currency routing, dispatcher fallthrough, and display formatting.
