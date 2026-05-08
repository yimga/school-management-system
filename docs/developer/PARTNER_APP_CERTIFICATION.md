# RunMyCampus Partner App Certification

**SOT batch 1216** — Linux + Shopify pillar push.
**Audience:** third-party developer who wants to publish a paid or free app for RunMyCampus tenants.
**Promise:** five honest stages from sandbox to listed-and-installable. No surprises, no fake gates.

---

## 1. Why this exists

The Linux pillar requires a stable extension surface. The Shopify pillar requires a populated catalog with real third-party developers. This document defines the contract between RunMyCampus and a partner who builds an app on our SDK.

We have:
- 22+ first-party apps already seeded (`apps/marketplace/management/commands/seed_marketplace_apps.py`).
- Python SDK (`sdk/runmycampus/`) and JavaScript SDK (`sdk/js/runmycampus-client.mjs`).
- OAuth client_credentials flow via `apicenter`.
- Sandbox docs (`docs/developer/SANDBOX_QUICKSTART.md`).
- Marketplace governance (`apps/platform_runtime/app_catalog_governance.py`).
- Settlement truth phase map (`apps/marketplace/settlement_truth.py`).

What we don't yet have: **third-party developers**. This document is the on-ramp.

---

## 2. The five stages

### Stage 1 — Sandbox

**Outcome:** developer has a sandbox tenant, an OAuth client, and a working "hello world" app.

1. Sign up at `developer.runmycampus.com` (sandbox provisioning view: `developer_sandbox`).
2. Provision a sandbox tenant via `DeveloperApplication`.
3. Issue OAuth client_credentials (apicenter).
4. Build against the SDK using the sandbox quickstart.
5. Hit the sandbox API: read tenants, read installable apps, simulate an install.

**SLA:** sandbox is provisioned within 1 business day.
**Cost:** free.

### Stage 2 — App authoring

**Outcome:** developer has a working `MarketplaceApp` model in their developer org with a manifest.

1. Author the app's manifest with explicit scopes: see `manifest.scopes` in the seed file.
2. Declare wedge_ids the app contributes to (1–45 catalog wedges).
3. Implement webhooks if the app reacts to platform events.
4. Implement uninstall posture (always non-destructive by default).
5. Run preview + impact tests in the sandbox.

**SLA:** none — developer pace.

### Stage 3 — Sandbox certification

**Outcome:** RunMyCampus has tested the app in our sandbox and confirmed:

1. Tenant isolation is honored (no cross-tenant queries).
2. Permission scopes match manifest declarations (no privilege escalation).
3. Webhook subscribers handle retries + DLQ + signature verification.
4. Uninstall is non-destructive (snapshot-restorable).
5. Settlement truth is honest (no `settlement_completed = true` without real proof).
6. Data residency posture is declared.
7. Apple-class UX axe pass on any UI surface the app exposes.
8. SDK version compatibility declared.

**Verifiers we run:** `audit_tenant_isolation`, `audit_post_surface`, `verify_test_module_contract`, `audit_route_surface`, `audit_security_surface`, plus a partner-app-specific permission probe.

**SLA:** 5 business days from submission.
**Cost:** free.

### Stage 4 — Marketplace listing

**Outcome:** the app is discoverable in `/super/apps/` (platform-side) and `/school/apps/` (tenant-side).

1. RunMyCampus creates the `PublisherOrganization` row for the partner.
2. `MarketplaceApp` and `MarketplaceListing` rows created with `is_active = True` and `state = "approved"`.
3. SKU registry contract (`marketplace_sku_registry.MARKETPLACE_SKU_CONTRACTS`) is updated.
4. Compatibility matrix (`AppVersionCompat`) is populated.
5. Pricing model declared: free / paid / enterprise. Paid SKUs require either:
   - PSP credentials live (Stripe/Paystack/Flutterwave/MoMo/Orange/SEPA) — external, currently `credentials_needed`, OR
   - Manual fallback enforcement (tenant operator accepts manual settlement responsibility).

**SLA:** within 2 business days of stage-3 pass.

### Stage 5 — First paid install

**Outcome:** a paying tenant installs the partner app and the install is settled.

1. Tenant browses catalog, selects app.
2. `assert_paid_install_billing_ready_or_raise` checks PSP / billing readiness.
3. Tenant approves install impact and scopes.
4. `MarketplaceMonetizationLedgerEntry` row written with `idempotency_key`.
5. Webhook subscribers fire `marketplace_install_succeeded`.
6. Settlement truth phase map updates as the PSP confirms processing.
7. Partner sees the install in their developer console.

**Honest constraint:** stage 5 requires a live PSP merchant credential set. Until then, installs can complete in sandbox / manual-fallback mode but cannot mark `settlement_completed = true`.

---

## 3. Revenue share model

Default split (until contractually negotiated):

| SKU type | Partner share | RunMyCampus share | Notes |
|---|---|---|---|
| Free app | 100% | 0% | No revenue events |
| Paid app — flat fee | 80% | 20% | Standard partner |
| Paid app — usage metered | 80% of usage units | 20% | Usage events recorded in `monetization_ledger_ops` |
| Enterprise app | Negotiated | Negotiated | Always custom MSA |

Settlement is monthly, paid through the partner's bank of record once `settlement_completed = true` is verified by the PSP truth path. We never simulate settlement.

---

## 4. Decommissioning

A partner can decommission an app at any time:

1. Set `is_active = False` on the `MarketplaceApp` (kill switch).
2. Existing tenant installs continue to work but no new installs are allowed.
3. After 90 days, RunMyCampus orphans the app and runs governed uninstall on remaining tenants with full notice.
4. Final ledger settlement is run.

RunMyCampus can also decommission an app if security or compliance issues arise. We will:
- Notify the partner at least 14 days in advance for non-critical issues.
- Immediately for critical issues, with a public AuditLog row.

---

## 5. The Linux argument

Why partner with us specifically?

1. **Honest ecosystem.** No claims we don't back. No fake settlement. No silent permissions grants.
2. **Stable extension surface.** Manifest contract is versioned (`AppVersionCompat`). Breaking changes ship as new major versions of the SDK with migration paths.
3. **Multi-tenant by default.** Every app gets multi-tenant isolation primitives free.
4. **Multi-corridor payments.** When PSP credentials are live, your app earns in any of 7 regional corridors automatically.
5. **Offline-first.** Your app inherits offline capture + conflict UI primitives.
6. **Developer-first SDK.** OAuth client_credentials, sandbox tenants, webhook infra, replay queues — none of which you have to build.

---

## 6. Apply

Email `developers@runmycampus.com` (external alias) with:
- Company name + region of incorporation
- App slug (kebab-case, ≤ 80 chars)
- One-paragraph app description
- Wedge_ids the app touches
- Scopes the app requires
- Pricing model

We respond within 1 business day.

---

## 7. Honest carve-outs

This document does NOT promise:

- Distribution to specific schools (we don't sell access to tenants).
- Featured placement (we don't pay-to-play).
- Indemnity for partner-side data loss (each side carries its own DPA).
- Support for a partner whose app has an open SEV-1 caused by partner code.
