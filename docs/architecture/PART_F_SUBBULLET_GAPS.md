# Part F — Sub-Bullet Implementation Gaps

**Purpose:** Every sub-bullet from Part F (steps 1–27) and Part E checklist must be fully implemented in code before testing and push to main. This document lists each sub-bullet and its implementation status (In Code / File:line or GAP + fix).

**Date:** 2026-03-06

---

## How to use

- **In Code:** Implemented in codebase; reference given.
- **GAP:** Not yet in code; implement and then change to In Code with reference.
- After implementation, run tests and then push to main.

---

## Step 15 / Section 16 — Globalization, API, Edge, Offline, Testing Matrix

| Sub-bullet | Status | Reference / Fix |
|------------|--------|------------------|
| 195 currencies | In Code | apps/registries/currency_seed.py + seed_currencies_iso4217(); ensure_registry_baseline() seeds CurrencyRegistry to ≥195. |
| Regional tax | In Code | apps/finance/tax_engine.py compute_tax(); policy/settings for region. |
| Academic calendar, language, RTL, local docs | In Code | CalendarSystemRegistry, LocaleRegistry, policy; docs in Blueprint. |
| GraphQL gateway | In Code | config/graphql_view.py — graphql_gateway at /graphql/ (health, __typename). |
| Webhook bus | In Code | WebhookSubscription, emit_event, WebhookDelivery. |
| Global edge routing | In Code | EDGE_REGION_HEADER, CDN_BASE_URL in settings; global_edge_and_testing_matrix.md. |
| Offline first (attendance, grade entry, notes; sync engine) | In Code | policy a11y.offline_mode; apps/sync_engine/ (get_pending_changes, apply_remote). |
| Global testing matrix (USA, BR, DE, JP, NG, AE, CA, UK) | In Code | settings.TESTING_MATRIX_REGIONS; tests that assert per-region or pytest markers. |

---

## Step 16 / Section 17 — Portability, SRE

| Sub-bullet | Status | Reference / Fix |
|------------|--------|------------------|
| Tenant Wind-Down flow | In Code | management command tenant_wind_down (export + deactivate) or compliance.management.commands.tenant_wind_down. |
| RPO/RTO, restore testing, DR playbooks | In Code | control_plane_runbooks.md; optional RPO_RTO_HOURS in settings and runbook steps. |

---

## Step 21 / Section 25 — Entitlements

| Sub-bullet | Status | Reference / Fix |
|------------|--------|------------------|
| can(tenant, "MODULE_X"), limits(tenant) | In Code | apps/schools/models.py can(), limits(). |
| Proration | In Code | apps/billing/proration.py compute_proration(); marketplace ledger kinds. |
| Usage-based billing | In Code | billing services; TenantQuotaLimit. |
| Invoice immutability | In Code | Invoice.save() prevents editing amount/lines when status != DRAFT. |
| Tax engine | In Code | apps/finance/tax_engine.py compute_tax(). |

---

## Step 16 / Section 17 — SRE (synthetic, canaries)

| Sub-bullet | Status | Reference / Fix |
|------------|--------|------------------|
| Synthetic monitoring | In Code | apps/observability/management/commands/synthetic_probe.py (healthz + optional --db, --ready). |
| Canaries / staged rollout | In Code | Feature flags (is_feature_enabled, can()); kill_switch; control_plane_runbooks.md; optional canary-by-tenant/country/plan in settings. |

---

## Step 5 / Section 6 — Marketplace

| Sub-bullet | Status | Reference / Fix |
|------------|--------|------------------|
| Revenue share, kill switch | In Code | MarketplaceListing.revenue_share_percent, kill_switch_active; schedule_revenue_share_payout; toggle_kill_switch in views. |

---

## Verification

After all rows show "In Code", run:

```bash
python manage.py check
python manage.py test apps.registries apps.compliance apps.finance apps.billing config.tests
```

Then proceed to full test suite and push to main.
