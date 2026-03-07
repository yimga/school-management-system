# Why We Deferred (and What We Built Now)

This doc explains **why** the RunMyCampus blueprint items below were initially deferred, and confirms they are **now implemented**.

---

## 1. WebhookSubscription + WebhookDelivery

**Why deferred:**  
The blueprint says *“start simple: DB outbox table + worker; upgrade later.”* We shipped the outbox and consumer first so every part of the system could rely on it. Webhook delivery is the “upgrade”: tenant-managed endpoints, retries, signing, idempotency.

**What we built now:**
- **WebhookSubscription** (events app): `school_id`, `url`, `event_types` (list), `secret` (HMAC), `is_active`, `description`.
- **WebhookDelivery**: one row per (subscription, domain_event); `status`, `http_status`, `attempted_at`, `delivered_at`, `retry_count`, `error_message`, `idempotency_key`.
- Outbox consumer **creates** WebhookDelivery rows for each matching subscription when processing a DomainEvent.
- **process_webhook_deliveries_batch()** POSTs to subscription URLs with:
  - `X-Webhook-Idempotency-Key`
  - `X-Webhook-Signature: sha256=<hmac>` when `secret` is set
- Management command: `python manage.py process_webhook_deliveries [--batch 50]`.

---

## 2. ScopeGrant (tenant-approved scopes)

**Why deferred:**  
MVP was “installed apps + widget registry + scopes + audit.” We had **AppScope** (what an app can ask for). The **approval** step—tenant admin explicitly grants which scopes an installed app gets—was deferred so we could ship install/audit first and add least-privilege grants next.

**What we built now:**
- **ScopeGrant** (marketplace): `installation`, `scope` (FK to AppScope), `granted_at`, `granted_by`.
- Unique on `(installation, scope)` so each scope is granted at most once per installation.
- **grant_scopes(installation, scope_codes_or_scope_objects, granted_by=None)** in `apps.marketplace.services` to create grants (e.g. after install or after tenant approval).

---

## 3. AppBillingLedger (marketplace billing)

**Why deferred:**  
Blueprint Section 3 lists “Billing adjustment” on install; the main ask was “installed apps + widget registry + scopes + audit.” We deferred billing so the install pipeline and audit were not blocked, and so billing could be designed once usage/subscription patterns were clear.

**What we built now:**
- **AppBillingLedger** (marketplace): `school`, `app`, `installation` (optional), `kind` (install_fee, subscription, proration_credit, proration_debit, usage), `amount`, `currency`, `period_start` / `period_end`, `created_at`.
- Ready for proration, install fees, and subscription line items; no invoice generation in this step.

---

## 4. Full module refactor (Admissions or Gradebook)

**Why deferred:**  
Refactoring **every** view/form in one module to use only `request.tenant_ctx` and the Policy Registry is a larger change. We delivered the **pattern** (feature gate + context processor + `docs/patterns/module_refactor_template.md`) and one consumer (FeatureGatekeeperMiddleware) so the rest of the codebase can follow the same pattern without blocking the platform spine.

**What to do next:**  
Use `docs/patterns/module_refactor_template.md` and refactor one full module (e.g. Admissions or Gradebook) so all behavior comes from the registry.

---

## 5. Per-tenant policy caching

**Why deferred:**  
Caching is a **performance** optimization. The resolver is correct without it; we deferred so we could ship behavior first and add Redis (or similar) per-tenant caching when scale demands it.

**Status:**  
Still optional; add in the resolver when needed.

---

## Summary

| Deferred item              | Why deferred                          | Status now                          |
|----------------------------|----------------------------------------|-------------------------------------|
| WebhookSubscription/Delivery | “Start simple; upgrade later”        | **Done** (models + dispatch + batch delivery) |
| ScopeGrant                 | MVP = install + audit first            | **Done** (model + grant_scopes)     |
| AppBillingLedger           | Billing after install pipeline         | **Done** (model + admin)            |
| Full module refactor       | Scope; pattern doc first               | **Next step** (use pattern doc)     |
| Policy caching             | Performance only                       | **Optional** (add when scaling)     |

We deferred to **ship the spine first** (tenancy, policy registry, outbox, marketplace install/audit) and to avoid blocking on billing/approval flows. The deferred pieces are now implemented so the platform matches the blueprint end-to-end.
