# Live PSP + settlement readiness checklist

Use this when moving a corridor from **metadata-only** readiness to **verified live**.  
Do **not** treat configuration inside RunMyCampus as proof of PSP approval — provider dashboards and contracts are authoritative.

Cross-reference: **`docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md`**, **`docs/payments/PAYMENT_BLOCKER_CLASSIFICATION.md`**, **`docs/external_dependencies_register.json`**, **`python manage.py check_payment_gateways --mode=metadata`**.

**Current execution note (2026-05-13):** Repo readiness remains complete for metadata checks and webhook rails, but no provider row can move to **`verified_live`** until an operator supplies provider evidence. Minimum evidence package per corridor: merchant approval screenshot/export, staging/prod secret names configured outside Git, webhook secret configured, settlement account confirmation, one supervised live or approved test transaction where policy allows, and payout/settlement confirmation. Keep secrets out of this file.

Legend for each row:

| Column | Meaning |
|--------|---------|
| Merchant account | Business entity approved by PSP |
| Business verification | KYC/KYB complete |
| API keys | Publishable + secret (stored only in deployment secrets) |
| Webhook endpoint | HTTPS URL reachable by PSP |
| Webhook secret | Signing secret from PSP |
| Test txn | Sandbox or small verified capture (policy-dependent) |
| Production ping | Non-destructive live probe where supported |
| Settlement account | Payout bank / MoMo settlement wallet |
| Settlement confirmation | How payout is confirmed (dashboard export / webhook / statement) |
| Chargeback/refund | Owner + PSP workflow documented |
| Reconciliation owner | Named finance role |
| Country/currency | ISO codes served |
| Risk/compliance | PCI scope, MOUs, licensing |

---

## Stripe

| Track | Owner | Notes |
|-------|-------|-------|
| Merchant account created | | Stripe Connect or direct charges per product decision |
| Business verification status | | |
| API keys obtained | | Live **`pk_live_*`**, **`sk_live_*`** — never commit |
| Webhook endpoint configured | | `/finance/payments/webhook/...` per deployment |
| Webhook secret configured | | Signing secret from Stripe Dashboard |
| Test transaction verified | | Stripe test mode before live |
| Production ping verified | | Prefer Stripe API metadata (`balance`/`payment_methods` listing) — **no charge** unless policy allows micro-auth |
| Settlement account configured | | Payout schedule + bank |
| Settlement confirmation method | | Stripe payouts export / webhook |
| Chargeback/refund flow | | Disputes dashboard + internal playbook |
| Reconciliation owner | | |
| Country/currency coverage | | |
| Risk/compliance notes | | PCI SAQ scope if card data touches campus-controlled surfaces |

---

## Paystack

| Track | Owner | Notes |
|-------|-------|-------|
| Merchant account created | | Nigeria / Ghana contexts |
| Business verification status | | |
| API keys obtained | | **`PAYSTACK_SECRET_KEY`** (live) — deployment only |
| Webhook endpoint configured | | Public HTTPS |
| Webhook secret configured | | |
| Test transaction verified | | Paystack test keys |
| Production ping verified | | Metadata-only if Paystack exposes health endpoint; else **`external_required`** until first supervised txn |
| Settlement account configured | | Settlement bank on file |
| Settlement confirmation method | | Paystack settlements export |
| Chargeback/refund flow | | |
| Reconciliation owner | | |
| Country/currency coverage | | NG / GH typical |
| Risk/compliance notes | | |

---

## Flutterwave

| Track | Owner | Notes |
|-------|-------|-------|
| Merchant account created | | Multi-country Africa |
| Business verification status | | |
| API keys obtained | | Live secret key — deployment only |
| Webhook endpoint configured | | |
| Webhook secret configured | | **`FLW_SECRET_HASH`** / verification hash |
| Test transaction verified | | Sandbox |
| Production ping verified | | Often **`external_required`** without supervised live call |
| Settlement account configured | | |
| Settlement confirmation method | | Flutterwave settlements |
| Chargeback/refund flow | | |
| Reconciliation owner | | |
| Country/currency coverage | | |
| Risk/compliance notes | | |

---

## MTN MoMo

| Track | Owner | Notes |
|-------|-------|-------|
| Merchant MoMo collection account | | Hub / aggregator contract |
| Business verification status | | Telco / aggregator KYC |
| API credentials | | **`Integration`** config (`provider`**=`payments`, slug **`mtn_momo`**) |
| Callback URL | | Registered with aggregator |
| Webhook / callback secret | | As required by aggregator |
| Test transaction verified | | Sandbox MSISDN |
| Production ping verified | | Metadata-only in-repo; live USSD/app flows are external proof |
| Settlement account configured | | Settlement to bank / MoMo wallet |
| Settlement confirmation method | | Aggregator settlement reports |
| Chargeback/refund flow | | Telco dispute path |
| Reconciliation owner | | |
| Country/currency coverage | | CM / GH / UG etc. per corridor |
| Risk/compliance notes | | Regulatory caps per country |

---

## Orange Money

| Track | Owner | Notes |
|-------|-------|-------|
| Merchant Orange Money account | | |
| Business verification status | | |
| API credentials | | **`orange_momo`** integration |
| Callback URL | | |
| Webhook secret | | Partner-dependent |
| Test transaction verified | | Sandbox where available |
| Production ping verified | | Usually **`external_required`** without telco proof |
| Settlement account configured | | |
| Settlement confirmation method | | Partner reports |
| Chargeback/refund flow | | |
| Reconciliation owner | | |
| Country/currency coverage | | Francophone corridors |
| Risk/compliance notes | | |

---

## Bank / SEPA / generic CARD rails

| Track | Owner | Notes |
|-------|-------|-------|
| Bank partner / sponsor bank | | |
| Compliance approval | | |
| Settlement account | | IBAN / local rails |
| Production confirmation | | Statements / SWIFT / ACH evidence |
| Chargeback/refund flow | | |
| Reconciliation owner | | |
| Country/currency coverage | | EU / UK / US profiles |
| Risk/compliance notes | | PSD2 / open banking |

---

## Manual fallback (offline receipt)

Not an API PSP — operational discipline required.

| Track | Owner | Notes |
|-------|-------|-------|
| Policy allows manual proof | | **`TenantPaymentPolicy.allow_manual_offline_proof`** |
| Receipt capture UX | | Portal / finance queue |
| Reconciliation workflow | | approve/reject + **`AuditLog`** |
| Audit procedure | | Who may approve |
