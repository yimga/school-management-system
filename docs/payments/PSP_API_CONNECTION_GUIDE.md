# PSP API Connection Guide — Step-by-Step

This is the **operator runbook** for connecting each external payment provider to a RunMyCampus deployment. It is the answer to:

> "What do I, the operator with merchant credentials in hand, do to make this corridor verified-live?"

Cross-reference: `docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md`, `docs/payments/PAYMENT_BLOCKER_CLASSIFICATION.md`, `docs/payments/LIVE_PSP_READINESS_CHECKLIST.md`, `docs/external_dependencies_register.json`.

## What stays repo-side, what is external

The repo provides:
- Integration model + per-tenant policy
- Read-only health probe per provider (`check_payment_gateways --mode=production_ping`)
- Ledger plumbing (`MarketplaceMonetizationLedgerEntry`, settlement state machine)
- Webhook receivers + signature verification scaffolding
- Tenant-scoped reconciliation queue + audit log

What the **operator** must do externally:
- Open a merchant account with each provider
- Pass KYC/KYB
- Obtain live API keys
- Register the deployment webhook URL with the provider
- Configure the live secrets in deployment env (never in repo)

The verification command (run from the deploy host, not from a developer laptop):

```bash
python manage.py check_payment_gateways \
    --school=<tenant-slug> \
    --provider=<stripe|paystack|flutterwave|mtn_momo|orange_momo> \
    --mode=production_ping
```

Expected `status` values:
- `ready` → live credentials work, non-charge probe succeeded
- `missing_credentials` → provider rejected the key (rotate / verify merchant live)
- `external_required` → still missing live keys or provider does not expose a non-charge probe
- `degraded` → connectivity / API status issue

---

## 1. Stripe — global card payments

### 1.1 What you need
- A Stripe **business** account (not a personal account)
- Business KYB: registered name, address, EIN/tax ID, beneficial-owner IDs
- A bank account for payouts in your settlement currency

### 1.2 Steps

1. **Sign up / log in:** https://dashboard.stripe.com/register
2. **Activate your account:** complete the *Activate payments* checklist (business profile, statement descriptor, bank account, tax info).
3. **Obtain live keys:** Dashboard → **Developers → API keys** (toggle *Viewing test data* OFF).
   - `Publishable key` → `pk_live_...`
   - `Secret key` → `sk_live_...` (reveal once, store in deployment secrets)
4. **Register the webhook endpoint:** Dashboard → **Developers → Webhooks → Add endpoint**.
   - URL: `https://<your-deployment>/finance/payments/webhook/stripe/`
   - Listen to (minimum): `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`, `charge.dispute.created`, `payout.paid`, `payout.failed`
   - Copy the **signing secret** (`whsec_...`)
5. **Set deployment env vars** (Render dashboard → service → Environment):
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```
6. **Create the Integration row** for the tenant (Django admin → Integrations Marketplace → Integration):
   - `provider=payments`, `slug=stripe`, `enabled=True`
   - `config={"provider_slug": "stripe"}` (secrets stay in env, NOT in config)
7. **Verify (non-charge):**
   ```bash
   python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping
   ```
   Expected: `"status": "ready"`, `"message": "Stripe Balance.retrieve succeeded ..."`
8. **First settled live transaction:** make one tiny supervised charge via the tenant portal, refund it, confirm the webhook fired (Stripe dashboard → Webhook → Recent deliveries). Record evidence path in `external_dependencies_register.json` → `stripe_global_cards.evidence_notes`.

### 1.3 Gotchas
- Stripe test keys (`sk_test_*`) intentionally fail the production ping — that is correct behavior.
- If your business is in a country Stripe does not support directly, use Stripe Atlas or fall back to Paystack/Flutterwave.

---

## 2. Paystack — Ghana / Nigeria cards & bank transfers

### 2.1 What you need
- A Nigerian or Ghanaian registered business
- Business KYC: CAC certificate (NG) or Registrar General (GH), director ID, settlement bank account

### 2.2 Steps

1. **Sign up:** https://dashboard.paystack.com/#/signup
2. **Complete business verification:** Dashboard → **Settings → Business** → upload required documents. Live keys are gated on this passing.
3. **Obtain live keys:** Dashboard → **Settings → API Keys & Webhooks** (toggle to *Live*).
   - `Public key` → `pk_live_...`
   - `Secret key` → `sk_live_...`
4. **Register the webhook URL:** same page.
   - URL: `https://<your-deployment>/finance/payments/webhook/paystack/`
   - Paystack signs webhooks with HMAC-SHA512 of the raw body using your secret key — the receiver verifies this; nothing extra to copy.
5. **Set deployment env vars:**
   ```
   PAYSTACK_SECRET_KEY=sk_live_...
   PAYSTACK_PUBLIC_KEY=pk_live_...
   ```
6. **Create the Integration row:**
   - `provider=payments`, `slug=paystack`, `enabled=True`
   - `config={"provider_slug": "paystack", "callback_url": "https://<your-deployment>/finance/payments/callback/paystack/"}`
7. **Verify (non-charge):**
   ```bash
   python manage.py check_payment_gateways --school=<slug> --provider=paystack --mode=production_ping
   ```
   The repo probes `GET https://api.paystack.co/transaction/totals?perPage=1` — read-only, no money moves.
   Expected: `"status": "ready"`.
8. **First settled live transaction:** charge a small amount via the tenant portal, refund it, confirm webhook delivery in Paystack → **Webhooks → Logs**. Record evidence path.

### 2.3 Gotchas
- Settlement to a Nigerian bank requires CBN-approved banks; settlement timing is T+1 by default.
- Currency mismatch (e.g. NGN merchant collecting USD) requires Paystack approval — open a support ticket.

---

## 3. Flutterwave — Africa multi-country fallback

### 3.1 What you need
- A registered business in any Flutterwave-supported country
- Business KYC: registration certificate, director ID, settlement bank account
- A clear list of corridors you intend to collect in (NG / GH / KE / UG / TZ / RW / CM / etc.)

### 3.2 Steps

1. **Sign up:** https://dashboard.flutterwave.com/signup
2. **Complete verification:** Dashboard → **Compliance** → submit business + director documents. Live mode unlocks after approval.
3. **Obtain live keys:** Dashboard → **Settings → API** (toggle *Live*).
   - `Public Key` → `FLWPUBK-...-X`
   - `Secret Key` → `FLWSECK-...-X`
   - `Encryption Key` → `...`
   - `Secret Hash` → set this yourself; it is what Flutterwave includes in the `verif-hash` header on webhook calls.
4. **Register the webhook URL:** Dashboard → **Settings → Webhooks**.
   - URL: `https://<your-deployment>/finance/payments/webhook/flutterwave/`
   - Set the *Secret hash* to a strong random string and store the same value in `FLW_SECRET_HASH`.
5. **Set deployment env vars:**
   ```
   FLUTTERWAVE_SECRET_KEY=FLWSECK-...-X
   FLUTTERWAVE_PUBLIC_KEY=FLWPUBK-...-X
   FLW_SECRET_HASH=<the strong random string>
   ```
6. **Create the Integration row:**
   - `provider=payments`, `slug=flutterwave`, `enabled=True`
   - `config={"provider_slug": "flutterwave", "callback_url": "https://<your-deployment>/finance/payments/callback/flutterwave/"}`
7. **Verify (non-charge):**
   ```bash
   python manage.py check_payment_gateways --school=<slug> --provider=flutterwave --mode=production_ping
   ```
   The repo probes `GET https://api.flutterwave.com/v3/balances` — read-only.
   Expected: `"status": "ready"`.
8. **First settled live transaction:** charge a small amount, refund, verify webhook in **Settings → Webhooks → History**. Record evidence path.

### 3.3 Gotchas
- Flutterwave secret keys ending in `-TEST` are sandbox; the repo intentionally rejects them at the production-ping gate.
- Corridor enablement is not automatic — you may need to email `merchant@flutterwavego.com` to turn on a specific country.

---

## 4. MTN Mobile Money (MTN MoMo)

There is **no published non-charge probe** for MoMo. Verification is by supervised live transaction. The repo enforces this honestly: production_ping returns `external_required`.

### 4.1 What you need
- An aggregator contract (Hub2, Yas, MFS Africa, or direct MTN partnership) — direct MTN Open API does not return live merchant credentials in most countries.
- A merchant short code with the telco
- Settlement bank or MoMo wallet

### 4.2 Steps

1. **Choose an aggregator** (recommended for speed):
   - https://hub2.io/ — multi-corridor, single API
   - https://www.mfsafrica.com/ — pan-Africa
   - https://yas.co/ — francophone-strong
2. **Sign the merchant agreement** with the aggregator. Provide:
   - Business registration
   - Tax ID
   - Settlement bank details
   - Use-case description (school fee collection)
3. **Receive credentials** (typically by email from the aggregator):
   - `API_USER`, `API_KEY`, `SUBSCRIPTION_KEY`, `BASE_URL` (sandbox vs prod URLs differ)
4. **Register the callback URL** with the aggregator:
   - URL: `https://<your-deployment>/finance/payments/callback/mtn_momo/`
5. **Create the Integration row**:
   - `provider=payments`, `slug=mtn_momo`, `enabled=True`
   - `config = {"provider_slug": "mtn_momo", "base_url": "<aggregator prod base url>", "callback_url": "https://<your-deployment>/finance/payments/callback/mtn_momo/"}`
   - Secret credentials go to deployment env vars (names depend on aggregator); never store in `config`.
6. **Verify (metadata only, by design):**
   ```bash
   python manage.py check_payment_gateways --school=<slug> --provider=mtn_momo --mode=metadata
   ```
   Expected: `"status": "ready"` (metadata) — meaning the integration row + callback URL are present.
7. **Supervised live transaction:** push a sandbox MSISDN payment first, then a small live one. Capture the aggregator settlement report and store its path in `mtn_momo.evidence_notes`.

### 4.3 Gotchas
- MTN MoMo has hard regulatory caps (often ≤ 500 USD/transaction depending on country); larger fee amounts must be split.
- USSD-initiated payments can take up to 60 s to confirm; the receiver must be idempotent.

---

## 5. Orange Money

Same posture as MTN MoMo: no non-charge probe, supervised live transaction is the only honest proof.

### 5.1 What you need
- Orange Money merchant profile (per-country)
- Partner PSP contract (Orange direct API requires telco onboarding; aggregators are usually faster)

### 5.2 Steps

1. **Choose a partner**:
   - https://hub2.io/ — supports Orange Money in CI, SN, ML, BF, CM
   - https://yas.co/ — francophone Africa specialist
2. **Sign merchant agreement** + KYC.
3. **Receive credentials** from partner.
4. **Register callback URL**: `https://<your-deployment>/finance/payments/callback/orange_momo/`
5. **Create the Integration row**:
   - `provider=payments`, `slug=orange_momo`, `enabled=True`
   - `config = {"provider_slug": "orange_momo", "base_url": "<partner prod base url>", "callback_url": "https://<your-deployment>/finance/payments/callback/orange_momo/"}`
6. **Verify metadata** (same command as MoMo, with `--provider=orange_momo`).
7. **Supervised live transaction** + evidence capture.

---

## 6. Bank / SEPA / generic CARD rails

These are bank-onboarding flows, not API integrations.

- **Sponsor bank agreement** (US/UK/EU): contact a sponsor bank or use a BaaS provider (Modern Treasury, Synctera, ClearBank).
- **SEPA**: requires a creditor identifier (CI), not just a normal IBAN. Most schools use a PSP that abstracts this (Stripe SEPA, GoCardless).
- **CARD direct (no PSP)**: requires PCI-DSS Level 1 audit; not recommended.

The repo classifies these as `external_required` until a PSP partnership lands. There is intentionally no non-charge probe — the proof is bank statements / SWIFT / SEPA file evidence.

---

## 7. Manual fallback (offline receipt)

Not an API connection — operational discipline.

1. Set `TenantPaymentPolicy.allow_manual_offline_proof = True`.
2. Define an internal approval matrix (who can approve a manual receipt — typically: bursar + school head).
3. Use the receipt-capture UX in the portal; reconciliations land in the finance queue with audit log entries.
4. Reconcile against bank statements weekly.

This rail is always available even without any PSP — useful in early pilots while merchant accounts are pending.

---

## 8. Evidence recording (every corridor)

After any of the above goes live, update `docs/external_dependencies_register.json`:

```json
{
  "id": "stripe_global_cards",
  "status": "verified_live",
  "evidence_notes": "<dashboard URL or path to webhook delivery log + first settled txn ID>",
  "verified_live_date": "<ISO date>",
  "verified_by": "<operator name>"
}
```

Then run:

```bash
python scripts/generate_external_dependencies_register.py
```

This regenerates `docs/generated/external_dependencies_register.{json,md}`. The five-pillar certification doc (`docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md`) reads from this register.

---

## 9. What this guide does NOT cover

- **PCI / SOC 2 audit packs.** External auditor engagement (3–6 months). See `docs/compliance/`.
- **Country-specific data residency.** Legal opinion required per corridor (`docs/external_dependencies_register.json` → `data_localization_placeholder`).
- **Sponsor bank onboarding.** Commercial negotiation outside the repo.
- **Render / DNS / TLS provisioning.** Operator-managed infrastructure (`docs/deployment/RENDER_DEPLOYMENT_RUNBOOK.md`).

These remain honestly external on the live/ecosystem axis — no amount of repo work can move them.
