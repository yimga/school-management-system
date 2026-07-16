# apps/siteconfig

> The platform's configuration control centre: what a tenant may switch on, how
> it looks, what it is called, and which region's rules it follows.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` FK where they are per-tenant at all, not by a Postgres schema)
**Scale:** 82 models · 207 migrations · 233 test modules · ~165k LOC

## What this app owns

Siteconfig is the answer to "why does this tenant see *that*?". It owns the
platform-wide registries that every other app reads from but none of them own:
feature toggles, dashboard and workflow packs, brand and theme profiles, region /
country / currency / grading profiles, the marketing CMS, the global support desk,
and the AI gateway's model + prompt registries. It is also the operator cockpit —
most of the `views_*` and `cockpit_*` modules render the manager-host surfaces
that a RunMyCampus operator uses to steer the fleet.

The defining decision here is a **retirement in progress**, and you need to know
about it before you touch anything. Siteconfig was originally the mega-domain
where every configurable value lived. It is being decomposed, and two modules
encode that migration as executable rules rather than prose:

- `domain_ownership.py` maps every legacy settings field name to exactly one
  target owner (`brand_experience`, `policies_rules`, `plans_entitlements`,
  `reports`, `design_studio`, …). It is deliberately import-safe and Django-free
  so scripts can classify a field without booting the framework. Exact-name
  matches beat prefix matches — `notify_intelligence` stays `brand_experience`
  even though the bare `notify_` prefix belongs to `policies_rules`.
- `sitesettings_slim_contract.py` states the post-Phase-B invariant: the
  `SiteSettings` singleton is allowed exactly three physical columns (`id`,
  `maintenance_mode`, `updated_at`). Everything else that still *reads* like a
  settings attribute is virtual, resolved by `SiteSettings.__getattr__` out of
  `platform_runtime.RuntimeDefaults` (typed first-class columns win over the JSON
  payload, matching the resolver's merge order).

So: this app is large, but a lot of its surface is a *registry* or a *cockpit
view*, not domain logic. New tenant behaviour generally does not belong here.

## Key models

82 models across `models.py` + the `models_*` splits (`models_ai`,
`models_dashboard`, `models_workflow`, `models_marketing`, `models_support`,
`models_feature_controls`, `models_platform_catalog`, …). This table is the
subset that matters most; it is deliberately not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `SiteSettings` | `siteconfig_sitesettings` | The slim singleton. Three real columns; every other attribute is virtual via `__getattr__` → `RuntimeDefaults`. Do not add a column (see below). |
| `FeatureToggleDefinition` | `siteconfig_featuretoggledefinition` | Registry of every configurable toggle: key, scope, default. |
| `FeatureToggleState` | `siteconfig_featuretogglestate` | Effective toggle value. `school`-scoped row beats a `school=NULL` global row beats the definition default (`feature_toggles.resolve_toggle`). |
| `BrandProfile` | `siteconfig_brandprofile` | Canonical tenant brand hub — the model all runtime tenant branding should resolve through. |
| `BrandSettings` | `siteconfig_brandsettings` | Explicit per-tenant branding (logo, colours, custom CSS). |
| `DashboardTemplate` | `siteconfig_dashboardtemplate` | Master dashboard template, public/control schema. |
| `TenantLayoutAssignment` | `siteconfig_tenantlayoutassignment` | Per-school, per-role assignment of a `DashboardTemplate`. Public schema, scoped by `school`. |
| `DashboardPack` / `DashboardPackAssignment` | `siteconfig_dashboardpack(assignment)` | Reusable dashboard packs (School Admin Executive, Teacher Command Center) and their per-school, per-role assignment. |
| `WorkflowTemplate` / `TenantWorkflow` | `siteconfig_workflowtemplate`, `siteconfig_tenantworkflow` | Master workflow definition (trigger / conditions / actions as JSON) and its per-school activation. |
| `SchoolAutomationWorkflow` | `siteconfig_schoolautomationworkflow` | School-authored no-code automation from the visual builder. Lives in the public schema with a `school` FK. |
| `WorkflowRunLog` / `SchoolWorkflowExecutionLog` | `siteconfig_workflowrunlog`, `siteconfig_schoolworkflowexecutionlog` | Per-run audit for the workflow engine and for the async/retryable school automations. |
| `CustomNuance` / `PendingNuance` | `siteconfig_customnuance`, `siteconfig_pendingnuance` | JSON-Logic rules evaluated at a named hook point by `nuance_engine` — the tenant extensibility escape hatch, with review staging. |
| `GradingScaleConfig` | `siteconfig_gradingscaleconfig` | Per-region grading scale definitions. |
| `RegionConfig` / `Province` / `CountryMultiplier` | `siteconfig_regionconfig`, `_province`, `_countrymultiplier` | The geo/regional spine: region records, subdivisions, and per-country pricing multipliers. |
| `AIModelRegistry` / `RegionalAIConfig` / `AIPromptRegistry` | `siteconfig_aimodelregistry`, `_regionalaiconfig`, `_aipromptregistry` | Which model version runs per region/hardware, the per-region Ollama endpoint, and the prompt registry (owner, purpose, allowed data sources). |
| `GlobalSupportTicket` | `siteconfig_globalsupportticket` | Support ticket raised from any tenant, deliberately stored in the public/shared schema so operators see one queue. |
| `ImpersonationLog` | `siteconfig_impersonationlog` | Audit log for super-admin tenant impersonation. |
| `PlatformPulseSnapshot` | `siteconfig_platformpulsesnapshot` | One row per `metric_key` per UTC date — the operator pulse series. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `domain_ownership` | SOT for "which bounded context owns this settings field". Import-safe, no Django. |
| Module | `sitesettings_slim_contract` | The three-column invariant, checked against both the ORM fields and the live DB columns. |
| Module | `config_service` | Application-facing config facade — typed per-domain objects (`BrandConfig`, `FinanceConfig`, `SecurityConfig`, …) over the merged resolver. |
| Module | `feature_toggles` | `resolve_toggle(key, school=, fallback=)`, the 4-step priority resolver. |
| Module | `nuance_engine` | JSON-Logic-only tenant rules with a whitelisted context per hook point and a 50 ms timeout. |
| Module | `workflow_engine` | Condition evaluation + action execution + run logging for the workflow/automation models. |
| Module | `db_router` | `TenantDatabaseRouter` (tenant DB alias + read-replica split + the data-residency border lock) and `PreviewDatabaseRouter`. |
| Celery | `execute_school_workflow_async`, `retry_school_workflow_execution_async` | School automation execution + retry. |
| Celery | `emergency_broadcast_fanout` | `BroadcastCampaign` fan-out over WebSocket/Redis pub-sub. |
| Celery | `snapshot_platform_pulse_daily`, `calculate_monthly_revenue_stats` | Operator metric snapshots. |
| Celery | `check_regional_ollama_health`, `sync_regional_models_for_cluster`, `global_ai_upgrade_run`, `index_ai_knowledge_beat`, `ai_quality_scorecard_beat` | Sovereign/regional AI fleet upkeep. |
| Celery | `verify_custom_domain_task`, `sweep_pending_custom_domains_task` | Custom-domain verification (paired with `apps/schools` domain records). |
| Celery | `support_sla_breach_sweep`, `deliver_support_ticket_http_webhook` | Global support desk SLA + webhook fan-out. |
| Command | `seed_global_data`, `seed_country_profiles`, `seed_global_regions`, `seed_global_brand_registry`, `bootstrap_platform_catalog` | The seed family that populates the registries. Read one before writing another. |
| Command | `export_config` / `import_config`, `export_ui_config` / `import_ui_config` | Config portability between environments. |
| Command | `verify_region_coverage`, `verify_terminology_cascade`, `validate_regions`, `verify_all_migrations_applied` | Registry-integrity checks. |
| URLs | `apps/siteconfig/urls.py` | Mostly operator/manager-host surfaces (`cockpit_*`, `ai_center`, `ai_governance`, `billing_*`, `compliance_export_*`) plus tenant studio/theme pages. Many are host-split — see below. |

## Before you change this

- **Do not add a column to `SiteSettings`.** The slim contract allows exactly
  `id`, `maintenance_mode`, `updated_at`, and it is enforced two ways:
  `scripts/verify_phase_b_execution.py` pre-deploy plus a belt-and-suspenders
  check against the *physical* columns on the live connection (so a half-applied
  migration or hand-rolled DDL is caught too). A new configurable value goes in
  `platform_runtime.RuntimeDefaults` and flows down the cascade documented in
  `CLAUDE.md`; `SiteSettings.__getattr__` will surface it for free.
- **New config does not belong in siteconfig by default.** `domain_ownership.py`
  exists because this app was a mega-domain and is being retired as one. If you
  are adding a field, first ask `EXACT_FIELD_OWNERS` / `classify_site_settings_field`
  which bounded context owns it. Exact-name matches beat prefix matches — this is
  deliberate and commented in the source.
- **Read config through a facade, not the raw namespace.** One key →
  `platform_runtime.config_resolver.get_effective_config(school, key)`; a whole
  domain → `siteconfig.config_service`. They are complementary layers, not rivals.
  `scan_config_resolver_fragmentation.py` is a zero-baseline CI gate: a new raw
  `get_effective_site_settings` grab outside the SOT modules fails the build.
- **`db_router.py` carries a real reentrancy hazard.** The residency check does
  ORM work itself (region resolution reads, a violation writes an audit row), and
  each of those re-enters `db_for_read`/`db_for_write` — unbounded recursion
  without the thread-local `_residency_guard`. The same module also duplicates the
  enforcement flag read (`_residency_enforce_flag`) import-free on purpose: the
  fail-closed arm must be able to answer "is enforcement on?" even when the
  compliance import it is handling the failure of is the thing that broke. Under
  `DATA_RESIDENCY_ENFORCE`, broken plumbing **denies** rather than skipping.
- **`nuance_engine` is JSON-Logic only, never raw code**, the context is scrubbed
  to a per-hook whitelist in `HOOK_REGISTRY`, and evaluation is timeout-bounded at
  50 ms. Adding a hook means adding its allowed keys — do not widen a hook to pass
  a whole model through, and do not add an eval path.
- **Toggle precedence is school → global → definition default → caller fallback**,
  and expiry is part of it (`expires_at` null-or-future). A toggle whose
  definition row is missing or inactive resolves straight to the caller's
  fallback — it does not raise. Do not reorder this in a caller.
- **This app renders on more than one host.** Cockpit/`super` views serve the
  manager host, tenant studio/theme pages serve tenant subdomains, and marketing
  CMS content serves the public host. A hardcoded `{% url 'super:…' %}` in a
  template that also renders on a tenant host is a live 500 — that exact class of
  bug shipped before. Resolve host-varying URLs in the view or guard on
  `public_host_kind`; `verify_cross_host_template_reverse.py` gates it.
- **`apps.py::ready()` swallows import failures by design** for the `models_*`
  splits and signal wiring (it logs and continues). That means a typo in a model
  split degrades to a *missing model*, not a loud crash. If a model or a signal
  seems not to exist at runtime, check the startup log before assuming the code
  is not there.
- **App code must not import `services.ai_gateway` directly.** Route AI through
  `services/ai_helpers.py`. `aggregate_ai_metrics` is one of the few allowlisted
  infrastructure exceptions, and `scan_ai_gateway_boundary.py` enforces the rest
  at baseline 0.
