# Payment environment contract

Deployment configures **names only** here — **never** paste live secrets into the repo or logs.

## Global

| Concern | Behavior |
|---------|----------|
| Secret storage | Deployment secret manager / env injection |
| Logging | Structured logs **must not** print raw API keys, webhook secrets, or auth headers |
| Webhooks | HTTPS TLS 1.2+; verify signatures per PSP |
| Health command | **`python manage.py check_payment_gateways --school=<slug> --provider=<optional> --mode=metadata`** — **no money movement**, **no secret values printed** |

## Mode matrix

| Mode | Meaning |
|------|---------|
| metadata | Structural checks only (integration row, config keys present, rails from regional profile). Default for CI and operators. |
| production_ping | Optional: non-charge live probe when PSP supports it and deployment policy allows it (Stripe Balance.retrieve only today). |

Without **`verified_live`** external evidence, production_ping stays **`external_required`** in documentation and tooling.

---

## Stripe

| Variable | Purpose | Test vs prod |
|----------|---------|--------------|
| `STRIPE_PUBLISHABLE_KEY` | Client-side tokenization | `pk_test_*` / `pk_live_*` |
| `STRIPE_SECRET_KEY` | Server API | `sk_test_*` / `sk_live_*` |
| `STRIPE_WEBHOOK_SECRET` | Signature verification | Whsec test / live |

Webhook URL pattern (deployment-specific): **`https://<tenant-or-app-host>/finance/payments/webhook/<processor>/`** — exact path must match **`apps/billing`** / **`apps.finance`** webhook routes.

**Health:** Integration slug **`stripe`** or `config.provider_slug` **`stripe`**. Missing integration → **`external_required`**. Empty config hints → **`missing_credentials`**.

---

## Paystack

| Variable | Purpose |
|----------|---------|
| `PAYSTACK_SECRET_KEY` | REST API |
| `PAYSTACK_PUBLIC_KEY` | Client reference |

Webhook signing secret per Paystack dashboard — store as integration config key (e.g. **`webhook_secret`**) — **never log**.

---

## Flutterwave

| Variable | Purpose |
|----------|---------|
| `FLUTTERWAVE_SECRET_KEY` | REST API |
| `FLUTTERWAVE_PUBLIC_KEY` | Client reference |
| `FLW_SECRET_HASH` | Callback verification |

---

## MTN MoMo / Orange Money

Typically **`Integration`** rows (`integrations_marketplace.Integration`) with `provider='payments'` and slug **`mtn_momo`** / **`orange_momo`** (aliases **`mtn`**, **`orange`**).

Expected config keys (names only — values secret):

- `base_url`
- `api_key` or partner-specific token fields
- `callback_url`
- Optional `webhook_secret`

---

## Fallback behavior

| Condition | Runtime posture |
|-----------|-----------------|
| No integration row | **`external_required`** for PSP-specific check |
| Integration row but empty credential hints | **`missing_credentials`** |
| CARD/BANK rail without PSP | **`external_required`** (catalog-driven) |
| Manual fallback disabled | Manual rail **`missing_credentials`** |

See **`apps/finance/payment_gateway_health.py`** for canonical status strings.
