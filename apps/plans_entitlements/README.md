# apps/plans_entitlements

> The bounded-context ownership surface for the commercial layer — plans,
> add-ons, subscriptions, entitlements, usage meters, and the platform ledger.

**Tenancy:** SHARED (public schema — but read the tenancy note below; in
schema-per-tenant mode this app is not installed at all)
**Scale:** 11 proxy models · 2 migrations · 2 test modules · ~0.3k LOC

## What this app owns

This app owns an *import path*, not a set of tables. It is one of four
bounded-context ownership surfaces in the repo (with `global_registries`,
`runtime_blueprints`, and `policies_rules`), and its `models.py` docstring is
precise about the intent: these proxy-owner models "let billing and entitlement
code target the new domain app now while keeping the current tables intact."

The domain it fronts is the money-adjacent one: what a school is *entitled* to
(`Entitlement`, materialized per tenant), what it *bought* (`Plan`, `PlanAddon`,
`TenantSubscription`, `Quote`), what it *used* (`UsageMeter`), what the platform
*earned* (`PlatformLedgerEntry`, `RevenueSharePayout`), and how price varies by
region (`CountryMultiplier`).

The mechanism is a runtime factory, `_proxy_model(legacy_model, app_label=..., doc=...)`,
which builds each class with `type()` and a `Meta` carrying `proxy = True` plus
`app_label = "plans_entitlements"`. Django registers them as this app's models;
the rows keep living in `apps.billing` and `apps.siteconfig` tables. Both
migrations are `CreateModel(fields=[], options={"proxy": True}, bases=("billing.entitlement",))`-shaped
— they create **no tables at all**, they only teach the migration graph that
these proxies exist.

## Key models

**Every model here is a proxy built at import time by `_proxy_model()`.** There
is no hand-written model class in this app and no table of its own. The table
names below belong to the *legacy owners* — eight to `apps.billing`, three to
`apps.siteconfig.models_platform_catalog` — which is why the `billing_` /
`siteconfig_` prefixes survive.

| Concrete owner | Proxy | Table | Purpose |
| --- | --- | --- | --- |
| `apps.billing` | `BillingAccount` | `billing_billingaccount` | Billing accounts (`school` FK) |
| `apps.billing` | `TenantSubscription` | `billing_tenantsubscription` | Tenant subscription state (`school` FK) |
| `apps.billing` | `Entitlement` | `billing_entitlement` | Materialized tenant entitlements (`school` FK) |
| `apps.billing` | `UsageMeter` | `billing_usagemeter` | Usage metering (`school` FK) |
| `apps.billing` | `Quote` | `billing_quote` | Commercial quote state (`school` FK) |
| `apps.billing` | `PlatformLedgerEntry` | `billing_platformledgerentry` | Platform commercial ledger events (`school` FK) |
| `apps.billing` | `RevenueSharePayout` | `billing_revenuesharepayout` | Revenue-share payouts |
| `apps.billing` | `BillingProcessorSyncEvent` | `billing_billingprocessorsyncevent` | Payment-processor sync events (`school` FK) |
| `apps.siteconfig.models_platform_catalog` | `Plan` | `siteconfig_plan` | Plan definitions |
| `apps.siteconfig.models_platform_catalog` | `PlanAddon` | `siteconfig_planaddon` | Add-on definitions |
| `apps.siteconfig.models_platform_catalog` | `CountryMultiplier` | `siteconfig_countrymultiplier` | Regional price multipliers |

All eleven are listed in `models.py`'s `__all__`.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Migration | `0001_proxy_owner_models` | 10 proxies; depends on `billing.0004` and `siteconfig.0147` |
| Migration | `0002_entitlement_proxy` | Adds the `Entitlement` proxy separately — it depends on `billing.0008_entitlement`, which did not exist when `0001` was written |
| Admin | `admin.py` | Proxy-owner admin registrations |
| Tests | `test_edos_plans_entitlements_kernel`, `test_global_local_gap_closure_batch_1488` | Auto-generated `SimpleTestCase` scaffolds asserting audit artifacts under `docs/generated/` and this contract path exist. They assert the app *directory* is present — they do not exercise the proxies |
| URLs / Celery / commands | none | This app has no `urls.py`, no tasks, and no management commands |

## Before you change this

- **In the production tenancy mode, this app is not installed.** It appears in
  the top-level `INSTALLED_APPS` (`settings.py:312`) but it is **absent from both
  `SHARED_APPS` and `TENANT_APPS`** — the lists that replace `INSTALLED_APPS`
  wholesale when `USE_DJANGO_TENANTS` is on (the default for PostgreSQL,
  `settings.py:3854-3946`). Its sibling surfaces `runtime_blueprints` and
  `global_registries` *were* added to `SHARED_APPS`, each with a comment naming
  the app that forced it ("required by reports", "required by compliance"); no
  such consumer exists for this one. So: these proxies resolve under RLS/SQLite
  and vanish under schema-per-tenant. **Do not write production code that imports
  a model from here** without first adding the app to `SHARED_APPS` — a green
  test suite on SQLite proves nothing about the deployed topology.
- **The `Tenancy: SHARED` line above is the settings-truth answer** (this app is
  not in `TENANT_APPS`, so its rows would live in the public schema), and it is
  what the README gate checks. It is not a claim that the app is active in that
  mode — see the bullet above.
- **Editing a proxy's fields is not possible here, and that is the whole point.**
  A proxy model cannot add or alter a column. A new field on `Entitlement` goes on
  the concrete model in `apps.billing`, with the migration in *that* app. A
  `makemigrations` run proposing a real field change under `plans_entitlements`
  means something has gone wrong — these proxies are supposed to be `fields=[]`
  forever.
- **`0002` exists because migration dependencies are real even when tables are
  not.** A proxy still needs its base model to exist in the migration *state*, so
  `Entitlement` could not join `0001` (which pins `billing.0004`) and needed its
  own migration pinning `billing.0008_entitlement`. Adding a proxy for a newer
  billing model means a new migration here, not an edit to `0001`.
- **These are money tables; the platform's financial gates still apply through
  the proxy.** `scan_money_float.py` is a zero-tolerance gate over `apps/billing/`
  and friends — `float()` on a Decimal amount silently corrupts ledger sums.
  Reaching a `billing_platformledgerentry` row through a `plans_entitlements`
  proxy does not exempt the calling code from Decimal discipline.
- **Eight of the eleven carry a `school` FK and live in the public schema.**
  They are scoped by an explicit `school` reference, not by a Postgres schema, so
  every query needs a `school=` filter — enforced by `scan_tenant_queryset_safety.py`
  (baseline 0). A proxy inherits the concrete model's isolation obligations; it
  does not soften them.
- **The test modules here are scaffolds, not coverage.** Both are auto-generated
  and assert that files exist on disk. Do not read a green run as evidence the
  proxies resolve — under schema-per-tenant they would not even be registered.
