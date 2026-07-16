# apps/billing

> Platform-side commercial billing: what a **tenant owes RunMyCampus** — the
> subscription lifecycle, the platform ledger, entitlements, usage metering, and
> the PSP bridge.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` FK, not by a Postgres schema)
**Scale:** 15 models · 19 migrations · 32 test modules · ~17.6k LOC

## What this app owns

Read the name carefully, because it is the single most common misread in this
repo: `billing` is **not** school fees. Parents paying tuition is `apps.finance`,
a tenant app. `billing` is the *platform's* revenue side — the money a school
owes for using RunMyCampus. Both directions exist, they use different models,
and confusing them produces bugs that move real money.

The app owns five things. **The platform ledger** (`PlatformLedgerEntry`) is the
immutable money record: append-only CHARGE / CREDIT / ADJUSTMENT / WRITE_OFF
lines, one per event, with balance derived from them rather than stored.
**`PlatformInvoice`** is the human-facing numbered document grouping one period's
ledger lines under a gapless `INV-<year>-<seq>` number; the ledger stays the
record of truth beneath it. **The subscription lifecycle FSM**
(`services._advance_subscription_billing`) ages each tenant trial → active →
past_due → suspended on configurable day offsets and restores on payment.
**Entitlements** (`entitlements.can(school, capability)`) are the single gate the
rest of the platform asks "is this tenant allowed this module" — never
`is_feature_enabled` or a raw quota read. **Metering** counts usage dimensions
(db_sessions, storage_bytes, payments, AI tokens) into `UsageMeter`, with
`UsageCap` able to soft-warn or hard-freeze an account.

Around that core sit the world-scale concerns: per-country tax and pricing
policy, a PSP routing/fallback chain, multi-campus and holding-company rollups,
and the dunning + renewal reminder ladders.

## Key models

All 15 declared models are listed.

| Model | Table | Purpose |
| --- | --- | --- |
| `BillingAccount` | `billing_billingaccount` | One tenant's commercial account: status, currency, processor, external customer ref. `parent_account` makes it a child in a group. |
| `TenantSubscription` | `billing_tenantsubscription` | The tenant's plan + billing cycle + period window. The FSM subject. |
| `PlatformLedgerEntry` | `billing_platformledgerentry` | Append-only money line (CHARGE / CREDIT / ADJUSTMENT / WRITE_OFF). Balance is derived from these. |
| `PlatformInvoice` | `billing_platforminvoice` | Numbered per-period document over the ledger lines that share a reference stem. Gapless sequence. |
| `Entitlement` | `billing_entitlement` | Materialized tenant entitlement — the row `entitlements.can()` reads. |
| `UsageMeter` | `billing_usagemeter` | Per-dimension usage for one billing-account period. Unique on (account, metric, period). |
| `UsageCap` | `billing_usagecap` | Per-tenant `soft_warn_at` / `hard_cap` declaration for one dimension. Either may be 0 = no limit. |
| `BillingProcessorSyncEvent` | `billing_billingprocessorsyncevent` | Recorded PSP webhook/sync event — the audit trail behind every processor-driven ledger write. |
| `PlatformBillingProcessorConfig` | `billing_platformbillingprocessorconfig` | Which processor the platform is configured against. |
| `StripePlanPrice` | `billing_stripeplanprice` | Maps a tenant `Plan.slug` to a Stripe Price id for Checkout. Read via `price_map`, never hardcoded in a view. |
| `Quote` | `billing_quote` | Quote for a plan/contract before a subscription exists. |
| `BillingPromotion` | `billing_billingpromotion` | Platform commercial offer template. |
| `SubscriptionGrant` | `billing_subscriptiongrant` | Applied discount, credit, waiver, or sponsorship for one subscription. |
| `CountryBillingProfile` | `billing_countrybillingprofile` | Configurable commercial policy per country/market (incl. tax behavior). |
| `RevenueSharePayout` | `billing_revenuesharepayout` | Revenue-share payout record. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery | `run_platform_billing_lifecycle_task` | The subscription FSM sweep (renewal charge, tax, invoice, dunning aging) |
| Celery | `run_subscription_dunning_reminders_task` | Escalating delinquency ladder off the platform ledger |
| Celery | `run_subscription_renewal_reminders_task` | Pre-renewal notice |
| Celery | `materialize_holding_currency_rollups_task` | Persists per-currency holding-company buckets |
| Celery | `flush_ai_metrics_buckets`, `flush_hot_buffers` | Metering buffer flushes |
| Command | `run_platform_billing_lifecycle`, `run_billing_cron` | Manual lifecycle runs |
| Command | `backfill_platform_invoices` | Issues invoices for pre-existing ledger periods |
| Command | `seed_country_billing_profiles`, `seed_subscription_catalog` | Catalog/policy seeding |
| Command | `aggregate_storage_usage`, `run_revenue_share_payouts`, `send_renewal_reminders`, `import_platform_billing_snapshot` | Periodic operator jobs |
| URL | `create_session` | Embedded-checkout session creation (`urls_embedded_checkout`) |
| Middleware | `middleware_metering.DBSessionMeteringMiddleware` | Counts one `db_sessions` unit per (school, browser session, UTC day) |
| Module | `entitlements` | `can()` / `limits()` / `usage()` — the capability gate for the whole platform |
| Module | `psp_routing` + `psp_adapter_registry` | Ranked PSP candidate chain with fallback |
| Module | `tax_engine` | Pluggable resolver; static `CountryMultiplier.tax_rate` fallback |
| Module | `dunning_reminders`, `renewal_reminders` | Reminder ladders, deduped via `PlatformEventLog` |
| Module | `holding_rollup`, `multi_tier_ledger`, `group_consolidation` | Group/holding aggregation |
| Module | `offboarding`, `remote_cancel` | Cancel the remote subscription before the tenant purge |

`psp_adapter_registry` is explicitly a **preparedness scoreboard**: a row
announces intent, and `adapter_status="live"` is only earned once integration
tests are green. Read the registry, not the row count, before promising a PSP.

## Before you change this

- **A received payment is a CREDIT, not a CHARGE.** This is the app's scar
  tissue. `invoice.paid` / `invoice.payment_succeeded` *settle* the internal
  renewal charge that the lifecycle sweep posts for every tenant, PSP tenants
  included. Recording them as a CHARGE (which is `record_platform_charge`'s
  default) made a received payment **increase** the balance owed — aging paying
  customers to PAST_DUE/SUSPENDED and firing the dunning ladder at people who had
  actually paid. `services.py` now flips these two events to CREDIT explicitly.
  `checkout.session.completed` is deliberately **left as a CHARGE**: it also
  carries marketplace add-on purchases, which have no matching internal charge to
  settle. Test `test_stripe_webhook_invoice_paid_posts_credit_that_settles_renewal`
  pins this. Do not "simplify" the branch.
- **The ledger is append-only and the balance is derived.** Never mutate an entry
  to correct a number — post an ADJUSTMENT or WRITE_OFF. Webhook writes are made
  idempotent by a unique `reference` (`<processor>:<event>:<source_ref>`) checked
  before insert; keep new producers on that pattern.
- **`issue_platform_invoice` is idempotent on `reference_stem` and takes a row
  lock** to assign the sequence. The gapless number is a compliance property —
  concurrent issuance must not reuse a sequence, and re-running the sweep must
  not double-issue.
- **The RLS migration pair (0012/0013) enumerates a fixed table list** written
  before later models landed. `billing_platforminvoice` (0019) and
  `billing_subscriptiongrant` (0014) carry a `school` FK but are **not** in that
  list, so their isolation currently rests on service-layer `school=` scoping
  alone. If you add a school-scoped model here, do not assume RLS covers it.
- **Never gate a feature on anything but `entitlements.can()`.** Direct
  `is_feature_enabled` or quota-table reads from other apps are what this module
  exists to replace.
- **`enforce_cap_actions` suspends but never un-suspends.** A tenant already
  SUSPENDED stays SUSPENDED; auto-unfreeze is a deliberate human action. The
  `evaluate_cap` verdict is a pure read and safe for dashboards.
- **Metering is best-effort by contract, everywhere.** The session middleware,
  the storage hooks, and the AI-token flush all swallow their errors: losing a
  byte count is never worth a 500 on someone's upload. Do not make them raise.
  To bill a new `FileField`, add a line to the tuple in `apps.py::ready()` — or
  call `connect_storage_metering(...)` from your own AppConfig.
- **`holding_rollup` returns per-currency buckets and does no FX.** That is
  honesty, not an omission: each tenant is single-currency, and a faked single
  consolidated number would be a lie. `multi_tier_ledger` does convert, but only
  through an explicit resolver that raises on a cross-currency pair with no
  configured rate. Neither writes to the parent's ledger.
- **Cancel the remote subscription before the purge.** `TenantSubscription` is
  CASCADE-deleted with the School, so once the row is gone the Stripe-side
  subscription keeps billing with no local trace. `offboarding` captures
  `external_subscription_ref` into the purge manifest first. With no configured
  `BILLING_REMOTE_CANCEL_ADAPTER` the cancel is a no-op that records
  `remote_pending` for reconciliation — it never *assumes* cancellation.
- **`regional_pricing` returns the base price unchanged for an unregistered
  country** (multiplier 1, tax 0, USD) so missing data can never silently zero a
  tenant's bill. Keep that default.
