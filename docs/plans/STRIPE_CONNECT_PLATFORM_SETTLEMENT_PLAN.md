# Stripe Connect platform settlement — execution plan

**Status:** **IN PROGRESS (Lane 1 repo-scope shipping; Lane 2 operator evidence pending)**
**Plan owner:** RunMyCampus platform billing
**Created:** 2026-05-23
**Target SW range:** `sms-v3.71.1` → `sms-v3.72.x`
**Batch IDs:** **1413** (program) → **1414** Phase 1 scaffold → **1415** Phase 2 Connect onboarding → **1416** Phase 3 production default
**GEOS lane:** Step 5 — PSP settlement (`docs/generated/geos_lane2_operator_checklist.md`)
**Handoff-ready for:** Claude Code, Codex, Cursor — single build contract; do not spawn parallel payment strategy docs

**Canonical cross-links (extend, do not replace):**

- [`docs/payments/LIVE_PSP_READINESS_CHECKLIST.md`](../payments/LIVE_PSP_READINESS_CHECKLIST.md)
- [`docs/payments/PSP_API_CONNECTION_GUIDE.md`](../payments/PSP_API_CONNECTION_GUIDE.md)
- [`docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md`](../payments/PAYMENT_ENVIRONMENT_CONTRACT.md)
- [`docs/external_dependencies_register.json`](../external_dependencies_register.json)
- [`var/evidence/geos-99/README.md`](../../var/evidence/geos-99/README.md)
- Existing code: `apps/billing/processors.py::StripeConnectProcessor`, `apps/finance/gateways/stripe.py`, `apps/siteconfig/views_billing_stripe.py`

---

## 0 — Executive summary

RunMyCampus long-term money flow is **Stripe Connect**: each school is a connected account (merchant of record for tuition); the platform may take an application fee. Direct `sk_live_` on Render validates the rail first; Connect runs on the **same platform Stripe account**, not a separate signup.

**Stripe onboarding (operator, once):** select all three products:

| Stripe onboarding option | Select | RunMyCampus use |
|---|---|---|
| Non-recurring payments | **Yes** | Parent term invoices / one-off fees |
| Recurring payments | **Yes** | Schools pay RunMyCampus SaaS subscriptions |
| Build a platform or marketplace | **Yes** | Schools as connected accounts; platform fee / marketplace |

**Platform description for Connect review:**

> RunMyCampus is education software. Schools (connected accounts) collect tuition and fees from parents. The platform provides invoicing and payment technology and may charge a software or processing fee. Schools are the merchants of record for tuition; we are the platform facilitator.

**Connect account type:** **Express** (default) — Stripe-hosted KYC; school gets Express dashboard; lowest compliance burden on the platform. Standard only if a school insists on full Stripe dashboard; Custom only if counsel requires maximum control.

---

## 1 — Phase map (execution order is mandatory)

### Phase 1 — Platform account live (GEOS step 5 — do first)

**Goal:** Prove keys, webhooks, and ledger on the platform account before any school Connect KYC.

| # | Operator task | Repo / evidence |
|---|---|---|
| 1 | Finish Stripe platform KYB; select all three onboarding products | — |
| 2 | Set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` on Render | `config/settings_registry.py` |
| 3 | Register webhook `https://<deployment>/finance/payments/webhook/stripe/` | `apps/finance/views_payments.py` |
| 4 | Add platform billing processor row (`PlatformBillingProcessorConfig` code=`stripe`) | Django admin |
| 5 | One supervised pilot invoice charge + refund | `var/evidence/geos-99/psp/stripe/phase1_platform_charge_*.json` |
| 6 | Non-charge ping | `python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping` |

**Lane 1 deliverables (batch 1414):**

- Evidence scaffold under `var/evidence/geos-99/psp/stripe/`
- `scripts/verify_stripe_platform_settlement_scaffold.py` → **STRIPE_PLATFORM_SETTLEMENT_SCAFFOLD_PASS**
- PSP guide §1 Connect preamble + Phase 1 checklist
- External register rows: `stripe_global_cards`, `stripe_connect_platform`

### Phase 2 — Connect enabled (batch 1415)

**Goal:** One pilot school completes Express onboarding; payout lands on connected account.

| # | Operator / Stripe Dashboard | Repo |
|---|---|---|
| 1 | Connect → Get started (Express) on platform account | — |
| 2 | Register Connect redirect URLs for tenant host | `siteconfig:billing_stripe_connect` return/refresh |
| 3 | Pilot school admin opens `/siteconfig/billing-stripe/` → Connect | `apps/siteconfig/views_billing_stripe_connect.py` |
| 4 | School completes Stripe-hosted onboarding | Stripe AccountLink |
| 5 | First tuition payment with destination / connected account | Finance gateway + metadata |
| 6 | Evidence: webhook + payout export | `var/evidence/geos-99/psp/stripe/phase2_connect_pilot_*.json` |

**Lane 1 deliverables:**

- `apps/schools/stripe_connect_settings.py` — `School.settings["stripe_connect"]` bridge
- `apps/billing/stripe_connect_onboarding.py` — Account.create + AccountLink.create (stdlib HTTP, same pattern as `stripe_checkout.py`)
- Tenant routes: `/siteconfig/billing-stripe/`, `/siteconfig/billing-stripe/connect/`, `/siteconfig/billing-stripe/return/`
- `StripeConnectProcessor.normalize` handles `account.updated` sync hook
- Tests: `apps/siteconfig/tests/test_billing_stripe_connect.py`, `apps/schools/tests/test_stripe_connect_settings.py`
- Verifier extended: Connect routes + settings module present

**Processor metadata contract** (`PlatformBillingProcessorConfig.metadata`):

```json
{
  "secret_key": "<from env at runtime — never commit>",
  "connect_enabled": true,
  "connect_account_type": "express",
  "application_fee_percent": "2.5"
}
```

**Tenant storage** (`School.settings["stripe_connect"]`):

```json
{
  "account_id": "acct_…",
  "account_type": "express",
  "charges_enabled": true,
  "payouts_enabled": true,
  "details_submitted": true,
  "onboarding_status": "complete",
  "connected_at": "2026-05-23T12:00:00Z"
}
```

### Phase 3 — Production default (batch 1416)

**Goal:** New schools get Connect onboarding in School Studio / billing setup; Africa corridors use Paystack / Flutterwave / MoMo alongside Connect where Stripe is supported.

| # | Deliverable |
|---|---|
| 1 | Link from Plan & entitlements → Stripe Connect page |
| 2 | Studio infrastructure optional fold for Connect status (follow-up) |
| 3 | Finance `StripeGateway.initiate` reads connected `account_id` when present |
| 4 | Marketplace Wave E+ unblocks after Connect + counsel docket |
| 5 | Register `stripe_connect_platform` → **verified_live** only with Phase 2 evidence |

---

## 2 — Money flow (Connect)

```
Parent pays tuition
    → Charge on school's Connected Account (or destination charge via platform)
    → Payout to school's bank
    → Platform application fee → RunMyCampus balance
```

SaaS subscription (school → platform) stays on platform Checkout (`views_billing_stripe.py`) — separate from tuition Connect charges.

---

## 3 — Webhook events (minimum)

**Platform direct (Phase 1):** `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`, `charge.dispute.created`, `payout.paid`, `payout.failed`, `checkout.session.completed`, `customer.subscription.*`, `invoice.*`

**Connect (Phase 2+):** `account.updated`, `account.application.deauthorized`, `transfer.created`, `payout.paid` (connected account context)

Same signing secret on the platform webhook endpoint unless Stripe Dashboard requires a Connect-specific endpoint (document in operator runbook when encountered).

---

## 4 — Definition of done

### Lane 1 (repo)

- [ ] Plan file is canonical (this document)
- [ ] Phase 1 evidence scaffold + verifier green
- [ ] Phase 2 Connect onboarding routes resolve; mocked HTTP tests pass
- [ ] SOT §11.4 batches 1413–1416 recorded after validation
- [ ] `docs/external_dependencies_register.json` updated
- [ ] Service worker bumped on static/template wave

### Lane 2 (operator — not claimed until evidence exists)

- [ ] `stripe_global_cards` → **verified_live** (Phase 1 charge + refund JSON path)
- [ ] `stripe_connect_platform` → **verified_live** (Phase 2 pilot school payout path)
- [ ] `verify_greatest_education_os_matrix.py --write` composite improves honestly

---

## 5 — BUILD AGENT PROMPT (handoff — execute 100% repo scope)

Copy everything below to the build agent. **Do not stop at plan-only output.**

```
You are the RunMyCampus Stripe Connect settlement build agent.

READ FIRST (mandatory, no parallel strategy docs):
- docs/plans/STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md
- docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11.4 batches 1413–1416
- docs/payments/PSP_API_CONNECTION_GUIDE.md
- apps/billing/processors.py (StripeConnectProcessor)
- apps/billing/stripe_checkout.py (HTTP pattern)
- apps/siteconfig/views_billing_stripe.py (tenant billing entry)

MISSION: Ship Lane 1 repo-complete for Phases 1–3 scaffolding. Lane 2 (live Stripe KYB, keys, pilot charge) is operator-only — scaffold evidence paths, never fabricate verified_live.

PHASE 1 (batch 1414):
- var/evidence/geos-99/psp/stripe/README.md + phase1/phase2 evidence JSON templates
- scripts/verify_stripe_platform_settlement_scaffold.py → STRIPE_PLATFORM_SETTLEMENT_SCAFFOLD_PASS
- Extend PSP_API_CONNECTION_GUIDE.md with Connect phases + Express onboarding URLs

PHASE 2 (batch 1415):
- apps/schools/stripe_connect_settings.py (get/set payload, is_stripe_connected, merge from Stripe account object)
- apps/billing/stripe_connect_onboarding.py (create_express_account, create_account_link, fetch_account, platform_connect_config from processor metadata)
- apps/siteconfig/views_billing_stripe_connect.py + templates/siteconfig/billing_stripe_connect.html
- siteconfig/urls.py: billing-stripe/, billing-stripe/connect/, billing-stripe/return/
- Extend StripeConnectProcessor.normalize for account.updated → stripe_connect_sync snapshots
- apps/billing/services.py or webhook apply hook: persist sync to School.settings when school_id in metadata
- Tests with mocked urllib (no live Stripe)

PHASE 3 (batch 1416):
- Link from billing_plan_readonly_body.html to billing_stripe_connect
- apps/finance/gateways/stripe.py: when school has stripe_connect.account_id + charges_enabled, include in initiate raw_response
- Update external_dependencies_register.json (stripe_connect_platform row)
- Update SOT §11.4 + RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md AFTER green verifiers
- Bump static/js/service-worker.js CACHE_VERSION monotonically
- Wire verify_stripe_platform_settlement_scaffold.py into scripts/verify_phases_3_11_gates.py

PROOF (all must pass before claiming done):
  python scripts/verify_stripe_platform_settlement_scaffold.py
  python manage.py test apps.siteconfig.tests.test_billing_stripe_connect apps.schools.tests.test_stripe_connect_settings --noinput
  python scripts/verify_geos_lane2_scaffold.py

HARD RULES:
- No secrets in repo; keys only via env / processor metadata at runtime
- Match existing stripe_checkout urllib form-post pattern — no new Stripe SDK dependency
- Tenant isolation: school_id from request.school only; webhook metadata must match
- Smallest diff; no new parallel payment roadmap markdown
- Do NOT set external_dependencies_register status to verified_live without evidence file path

When Lane 1 is green, stop only if a true external blocker remains (operator has not supplied Stripe keys). Otherwise continue through Phase 3 repo items in the same run.
```

---

## 6 — Honest deferrals (Lane 2 / counsel)

- Live Stripe KYB approval and `sk_live_*` provisioning
- First production charge + refund evidence
- Pilot school Connect KYC completion
- Marketplace template monetization flip (`RMC_TEMPLATE_MONETIZATION_ENABLED`) — still counsel-pending per `docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md`
- Paystack / Flutterwave / MoMo corridors — parallel register rows, not replaced by Connect
