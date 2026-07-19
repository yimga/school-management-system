# PSP Sandbox Readiness Runbook

> Document: `docs/PSP_SANDBOX_RUNBOOK.md`
> Status: #26 / #6 repo-max gate — adapter code + scaffold present; live charge tests are EXTERNAL

## Overview

RunMyCampus routes tenant fee-collection through a typed payment rail adapter
registry (`apps/billing/psp_adapter_registry.py`). Each PSP has an adapter
status lifecycle: `planned` → `in_progress` → `live`.

This runbook documents the exact environment variables needed to drive sandbox
(test-mode) integrations for each PSP, how CI would prove them, and what
remains EXTERNAL (live production charge with real money).

---

## Rail Architecture

```
PaymentRailAdapter (Protocol)
  ├── ManualFallbackRail  (always-on, no secrets needed)
  ├── Paystack adapter    (in_progress — sandbox scaffold)
  ├── Flutterwave adapter (in_progress — sandbox scaffold)
  ├── MTN MoMo adapter    (in_progress — sandbox scaffold)
  ├── Razorpay adapter    (in_progress — sandbox scaffold)
  ├── Mercado Pago adapter(in_progress — sandbox scaffold)
  ├── dLocal adapter      (in_progress — sandbox scaffold)
  ├── M-Pesa Daraja       (in_progress — STK Push fail-closed gateway)
  └── ... (planned: Adyen, PayPal)
```

All adapters implement:
- `authorize(intent: PaymentIntent) -> PaymentResult`
- `verify_webhook_signature(payload, signature_header) -> bool`

The protocol is **fail-closed**: if no enabled rail matches the tenant's
currency, `PaymentRailUnavailableError` is raised. The `ManualFallbackRail`
accepts any currency as the backstop.

---

## Sandbox Environment Variables (≥3 live rails)

### 1. Paystack (Africa — NGN, GHS, ZAR, KES)

```env
PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PAYSTACK_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PAYSTACK_BASE_URL=https://api.paystack.co
PAYSTACK_SANDBOX_MODE=true
```

**Sandbox test endpoint:** `POST /transaction/initialize` with test card `4084 0840 8408 4081`
**Webhook test:** Paystack dashboard → Webhooks → Send test event

### 2. Flutterwave (Africa — NGN, GHS, KES, UGX, ZAR, XAF)

```env
FLUTTERWAVE_SECRET_KEY=FLWSECK_TEST-xxxxxxxxxxxxxxxxxxxx-X
FLUTTERWAVE_PUBLIC_KEY=FLWPUBK_TEST-xxxxxxxxxxxxxxxxxxxx-X
FLUTTERWAVE_ENCRYPTION_KEY=FLWSECK_TESTxxxxxxxxxxxxxx
FLUTTERWAVE_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxx
FLUTTERWAVE_BASE_URL=https://api.flutterwave.com/v3
FLUTTERWAVE_SANDBOX_MODE=true
```

**Sandbox test endpoint:** `POST /payments` with test card `5531 8866 5214 2950`
**Webhook test:** FLW dashboard → Settings → Webhooks → Test

### 3. Razorpay (APAC — INR)

```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_BASE_URL=https://api.razorpay.com/v1
RAZORPAY_SANDBOX_MODE=true
```

**Sandbox test endpoint:** `POST /orders` → `POST /payments/create/json`
**Webhook test:** Razorpay dashboard → Webhooks → Test Webhook

### 4. MTN MoMo (Africa — XAF, GHS, UGX)

```env
MTN_MOMO_SUBSCRIPTION_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MTN_MOMO_API_USER=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MTN_MOMO_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MTN_MOMO_ENVIRONMENT=sandbox
MTN_MOMO_BASE_URL=https://sandbox.momodeveloper.mtn.com
MTN_MOMO_CALLBACK_URL=https://your-ngrok.ngrok-free.app/webhooks/mtn-momo/
MTN_MOMO_SANDBOX_MODE=true
```

**Sandbox test endpoint:** `POST /collection/v1_0/requesttopay`
**Webhook test:** Callback on sandbox `requesttopay` with MSISDN `46733123450`

### 5. Mercado Pago (Americas — ARS, BRL, MXN, CLP, COP, PEN, UYU)

```env
MERCADO_PAGO_ACCESS_TOKEN=TEST-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
MERCADO_PAGO_PUBLIC_KEY=TEST-xxxxxxxxxxxx-xxxx-xxxx
MERCADO_PAGO_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MERCADO_PAGO_BASE_URL=https://api.mercadopago.com
MERCADO_PAGO_SANDBOX_MODE=true
```

**Sandbox test endpoint:** `POST /v1/payments` with test card `5031 7557 3453 0604`
**Webhook test:** MercadoPago dashboard → Webhooks → Configure + test

### 6. M-Pesa Daraja (East Africa — KES, TZS, UGX)

```env
MPESA_CONSUMER_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MPESA_CONSUMER_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MPESA_SHORTCODE=174379
MPESA_PASSKEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MPESA_CALLBACK_URL=https://your-host.example/webhooks/mpesa/
MPESA_BASE_URL=https://sandbox.safaricom.co.ke
MPESA_SANDBOX_MODE=true
```

**Gateway module:** `apps/finance/gateways/mpesa_daraja.py` (`MpesaDarajaGateway`)
**Sandbox test endpoint:** `POST /mpesa/stkpush/v1/processrequest` after OAuth
**Webhook test:** STK callback `Body.stkCallback.ResultCode=0`

---

## Fail-Closed HTTP Contract

Every adapter MUST:
1. **Default to sandbox mode** when `*_SANDBOX_MODE=true` or when the secret key
   contains `test`/`TEST`/`sandbox`.
2. **Refuse to authorize** if the secret key is empty/placeholder — raise
   `PaymentRailUnavailableError`, never silently succeed.
3. **Validate webhook signatures** using `hmac.compare_digest` (constant-time).
   Return `False` on any mismatch or missing secret — never silently pass.
4. **Log but never expose** secret material in error messages or audit trails.

---

## How CI Would Prove Sandbox Readiness

```yaml
# Hypothetical CI job (secrets stored in GitHub Secrets)
jobs:
  psp-sandbox-smoke:
    runs-on: ubuntu-latest
    env:
      PAYSTACK_SECRET_KEY: ${{ secrets.PAYSTACK_TEST_KEY }}
      FLUTTERWAVE_SECRET_KEY: ${{ secrets.FLW_TEST_KEY }}
      RAZORPAY_KEY_ID: ${{ secrets.RZP_TEST_KEY_ID }}
      RAZORPAY_KEY_SECRET: ${{ secrets.RZP_TEST_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/verify_psp_sandbox_readiness.py --json
      - run: python manage.py test apps.finance.tests_psp_sandbox --no-input
```

The `verify_psp_sandbox_readiness.py` script PASSES when:
- Adapter code exists (registry row + Protocol implementation)
- Runbook exists with env vars documented
- Fail-closed HTTP behaviour is verifiable from code structure

It reports `EXTERNAL_LIVE_CHARGE_REQUIRED` when:
- Live secrets are absent (cannot make real sandbox API calls)
- PSP partner approval is pending (MTN MoMo aggregator approval)
- OAuth token exchange not yet performed (Mercado Pago)

---

## What Remains EXTERNAL

| Item | Why | Resolution path |
|------|-----|-----------------|
| Live sandbox API calls | Requires real test-mode credentials provisioned by each PSP | Operator provisions secrets in vault; CI reads from GitHub Secrets |
| MTN MoMo aggregator approval | Business contract, not code | Complete MoMo developer portal onboarding |
| Orange Money partner onboarding | Partner program signup | Contact Orange developer relations |
| M-Pesa Daraja certification | Safaricom developer approval | Submit app for review on Daraja portal |
| Production charge verification | Real money movement | Blocked until PSP contract + UAT signoff |

---

## Adapter Status Summary

| PSP | Status | Region | Currencies | Sandbox secrets needed |
|-----|--------|--------|------------|----------------------|
| Paystack | in_progress | Africa | NGN,GHS,ZAR,KES | 3 env vars |
| Flutterwave | in_progress | Africa | NGN,GHS,KES,UGX,ZAR,XAF | 4 env vars |
| MTN MoMo | in_progress | Africa | XAF,GHS,UGX | 4 env vars |
| Razorpay | in_progress | APAC | INR | 3 env vars |
| Mercado Pago | in_progress | Americas | ARS,BRL,MXN,CLP,COP,PEN,UYU | 3 env vars |
| dLocal | in_progress | Americas | USD,BRL,MXN,INR | 3 env vars |
| M-Pesa Daraja | planned | Africa | KES | 4 env vars |
| Orange Money | in_progress | Africa | XAF,XOF | 3 env vars |
| Adyen | planned | EMEA | EUR,GBP,USD | 4 env vars |
| PayPal | planned | Global | USD,EUR,GBP | 3 env vars |
| Stripe | in_progress | Global | USD,EUR,GBP,NGN | 2 env vars |
