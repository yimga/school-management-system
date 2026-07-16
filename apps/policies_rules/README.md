# apps/policies_rules

> A domain import path for the policy layer — grading, attendance, and billing
> rules — re-exported from where they currently live.

**Tenancy:** SHARED (public schema — but read the tenancy note below; in
schema-per-tenant mode this app is not installed at all)
**Scale:** 0 models · 0 migrations · 1 test module · ~54 LOC across 4 files

## What this app owns

It owns eleven names and nothing else. This is the smallest app in the repo and
the most honest about it: `apps/policies_rules/` contains an `apps.py`, a
`models.py` of pure `from … import …` lines, and a smoke test. There is no
`migrations/` directory, no `admin.py`, no `urls.py`, no services.

It is one of four bounded-context ownership surfaces (with `global_registries`,
`runtime_blueprints`, and `plans_entitlements`) staged so that domain code can
name a policy concept without importing `apps.siteconfig` or `apps.policies`
directly. The `models.py` docstring says exactly what it is and what it is for:
"These state-compatible re-exports give new code a domain import path while the
database ownership migration is still in progress."

**The distinction that matters is that this app re-exports where its three
siblings proxy.** The other three build new classes at import time with a
`_proxy_model()` factory, which gives them a distinct `app_label`, a distinct
`ContentType`, and a migration to register the proxy. This one simply binds
existing class objects to a new module path. `policies_rules.PolicyBundle` **is**
`policies.PolicyBundle` — the same object, identical under `is`. That is why the
app has zero models of its own and zero migrations: from Django's point of view,
nothing new was declared. It is the cheapest possible version of the
bounded-context move, and it costs a `makemigrations` run exactly nothing.

## Key models

**None — this app declares no Django models and ships no migrations.** It does
not even have a `migrations/` directory, and that is correct rather than an
omission: a module of re-exports declares nothing for Django to migrate.

The eleven names in `models.py`'s `__all__` are the concrete classes of two other
apps, reachable through this path unchanged:

| Re-exported from | Names |
| --- | --- |
| `apps.policies.models` | `BlueprintPack`, `BlueprintCompatibilityRule`, `TenantBlueprint`, `PolicyBundle`, `PolicyCompatibilityRule`, `ScheduledPolicyOverride`, `TenantPolicyOverride`, `CountryProfile` |
| `apps.siteconfig.models_feature_controls` | `FeatureToggleDefinition`, `FeatureToggleState`, `TourStep` |

Their tables, migrations, fields, and isolation rules all belong to
`apps.policies` and `apps.siteconfig`. If you are looking for a
`policies_rules_*` table, none exists.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `models` | The eleven re-exports and their `__all__` |
| AppConfig | `PoliciesRulesConfig` | `verbose_name = "Policies & Rules (grading, attendance, billing)"` — the clearest statement in the app of the domain it is staking out |
| Tests | `test_policies_rules_smoke` | A `SimpleTestCase` asserting `import apps.policies_rules` succeeds. For an app whose entire product is an importable name path, that is the load-bearing assertion |
| URLs / Celery / commands / admin | none | None of these exist here |

## Before you change this

- **In the production tenancy mode, this app is not installed.** It appears in
  the top-level `INSTALLED_APPS` (`settings.py:311`) but it is **absent from both
  `SHARED_APPS` and `TENANT_APPS`** — the lists that replace `INSTALLED_APPS`
  wholesale when `USE_DJANGO_TENANTS` is on (the default for PostgreSQL,
  `settings.py:3854-3946`). Its siblings `runtime_blueprints` and
  `global_registries` were each added to `SHARED_APPS` with a comment naming the
  consumer that forced it; no such consumer exists for this one. Because these
  are plain re-exports, importing `apps.policies_rules.models` still *works* in
  that mode — Python does not care whether the app is installed, and the
  underlying `apps.policies` classes are registered regardless. That makes the
  breakage quiet rather than loud, which is worse. Add the app to `SHARED_APPS`
  before relying on it as an app.
- **The `Tenancy: SHARED` line above is the settings-truth answer** (this app is
  not in `TENANT_APPS`) and is what the README gate checks. It is not a claim
  that the app is active in schema-per-tenant mode — see above.
- **Adding a model here is a much bigger decision than it looks.** The moment you
  declare a real model in this `models.py`, this app needs a `migrations/`
  directory, an entry in `SHARED_APPS` or `TENANT_APPS`, and a tenancy answer for
  the new table. Today it needs none of those. Keep new state in `apps.policies`
  and re-export it, unless you are deliberately starting the table-ownership move
  the docstring anticipates.
- **Three of these names collide with `runtime_blueprints` proxies, and the two
  are not interchangeable.** `BlueprintPack`, `BlueprintCompatibilityRule`, and
  `TenantBlueprint` are also surfaced by `apps.runtime_blueprints` — there as
  proxy subclasses with their own `app_label` and their own `ContentType` row.
  The versions here are the concrete `apps.policies` classes themselves. They
  share a table, so queries agree; `isinstance` and ContentType-keyed lookups
  (generic FKs, permissions, audit rows) do not. Pick one import path per call
  site and stay on it.
- **Do not "upgrade" these re-exports into proxies to match the siblings.** The
  re-export is what keeps this app at zero models, zero migrations, and zero
  ContentType rows. Proxying would buy a distinct `app_label` and cost all three.
