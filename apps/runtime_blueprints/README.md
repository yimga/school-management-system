# apps/runtime_blueprints

> The bounded-context ownership surface for the composition layer — blueprints,
> dashboard packs, workflow packs, layouts, and report templates.

**Tenancy:** SHARED (public schema; listed in `SHARED_APPS` at `settings.py:3888`)
**Scale:** 20 proxy models · 1 migration · 1 test module · ~0.5k LOC

## What this app owns

This app owns an *import path*, not a set of tables. It is one of four
bounded-context ownership surfaces in the repo (with `global_registries`,
`plans_entitlements`, and `policies_rules`), and its `models.py` docstring states
the goal exactly: these are "proxy-owner models over the current storage layer so
runtime, dashboard, workflow, and blueprint code can migrate off
`apps.siteconfig.*` without a table move first."

It is the widest of the four — 20 proxies drawn from four concrete modules
(`apps.policies.models`, `apps.siteconfig.models_tooling`,
`apps.siteconfig.models_dashboard`, `apps.siteconfig.models_workflow`) — because
the composition layer is where the platform's "what does this tenant actually
see" question is answered: which blueprint is activated, which dashboard pack and
layout are assigned, which workflow pack is live, which report card style
renders.

The mechanism is a runtime factory, `_proxy_model(legacy_model, app_label=..., doc=...)`,
which builds each class with `type()` and a `Meta` carrying `proxy = True` plus
`app_label = "runtime_blueprints"`. Django registers them as this app's models;
the rows keep living in the originating app's table.
`migrations/0001_proxy_owner_models.py` is `CreateModel(fields=[], options={"proxy": True}, bases=("policies.blueprintcompatibilityrule",))`
and nineteen more like it — it creates **no tables at all**, it only teaches the
migration graph that these proxies exist.

## Key models

**Every model here is a proxy built at import time by `_proxy_model()`.** There
is no hand-written model class in this app and no table of its own. The table
names below belong to the *legacy owners* (`apps.policies` and `apps.siteconfig`),
which is why the `policies_` / `siteconfig_` prefixes survive.

| Concrete owner | Proxy | Table | Purpose |
| --- | --- | --- | --- |
| `apps.policies` | `BlueprintPack` | `policies_blueprintpack` | Blueprint catalog entries |
| `apps.policies` | `BlueprintCompatibilityRule` | `policies_blueprintcompatibilityrule` | Compatibility rules between blueprints |
| `apps.policies` | `TenantBlueprint` | `policies_tenantblueprint` | Tenant blueprint activation (`school` FK) |
| `apps.siteconfig.models_dashboard` | `DashboardPack` | `siteconfig_dashboardpack` | Dashboard packs |
| `apps.siteconfig.models_dashboard` | `DashboardPackAssignment` | `siteconfig_dashboardpackassignment` | Pack → tenant assignment (`school` FK) |
| `apps.siteconfig.models_dashboard` | `DashboardLayout` | `siteconfig_dashboardlayout` | Layout definitions |
| `apps.siteconfig.models_dashboard` | `DashboardTemplate` | `siteconfig_dashboardtemplate` | Dashboard templates |
| `apps.siteconfig.models_dashboard` | `DashboardWidget` | `siteconfig_dashboardwidget` | Widget catalog entries |
| `apps.siteconfig.models_dashboard` | `DashboardUserPreference` | `siteconfig_dashboarduserpreference` | Per-user dashboard preferences |
| `apps.siteconfig.models_dashboard` | `TenantLayoutAssignment` | `siteconfig_tenantlayoutassignment` | Layout → tenant assignment (`school` FK) |
| `apps.siteconfig.models_dashboard` | `SuperAdminDashboardPreference` | `siteconfig_superadmindashboardpreference` | Control-plane dashboard layout state |
| `apps.siteconfig.models_workflow` | `WorkflowPack` | `siteconfig_workflowpack` | Workflow packs |
| `apps.siteconfig.models_workflow` | `WorkflowPackAssignment` | `siteconfig_workflowpackassignment` | Pack → tenant assignment (`school` FK) |
| `apps.siteconfig.models_workflow` | `WorkflowTemplate` | `siteconfig_workflowtemplate` | Workflow templates |
| `apps.siteconfig.models_workflow` | `TenantWorkflow` | `siteconfig_tenantworkflow` | Tenant workflow activation (`school` FK) |
| `apps.siteconfig.models_tooling` | `ReportTemplate` | `siteconfig_reporttemplate` | Reusable report templates |
| `apps.siteconfig.models_tooling` | `OfficialReportTemplate` | `siteconfig_officialreporttemplate` | Official report templates (`school` FK) |
| `apps.siteconfig.models_tooling` | `ReportCardStyle` | `siteconfig_reportcardstyle` | Report card styling assets |
| `apps.siteconfig.models_tooling` | `FormDraft` | `siteconfig_formdraft` | Packageable setup / report form drafts (`school` FK) |
| `apps.siteconfig.models_tooling` | `UserPreference` | `siteconfig_userpreference` | Runtime-facing user preference state |

`models.py` also imports several non-model helpers alongside the proxies —
`ThemeLayout`, `ReportCardStyleQuerySet`, `get_report_card_style_for_student`,
`get_dashboard_widget_metadata`, and `SUPER_DASHBOARD_DEFAULT_SECTION_ORDER` —
so callers can reach the whole tooling/dashboard surface through this one import
path rather than reaching back into siteconfig.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Migration | `0001_proxy_owner_models` | Proxy registration only — zero tables |
| Admin | `admin.py` | Proxy-owner admin registrations |
| Tests | `test_runtime_blueprints_smoke` | A `SimpleTestCase` asserting `import apps.runtime_blueprints` succeeds — which, for an app whose whole job is being importable without a circular import, is the load-bearing assertion |
| URLs / Celery / commands | none | This app has no `urls.py`, no tasks, and no management commands |

## Before you change this

- **Editing a proxy's fields is not possible here, and that is the whole point.**
  A proxy model cannot add or alter a column. A new field on `DashboardWidget`
  goes on the concrete model in `apps.siteconfig.models_dashboard`, with the
  migration in *that* app. A `makemigrations` run proposing a real field change
  under `runtime_blueprints` means something has gone wrong — these proxies are
  supposed to be `fields=[]` forever.
- **This app is in `SHARED_APPS` because `apps.reports` needs it.** The settings
  comment at `settings.py:3888` is explicit: "Proxy-owner for `DashboardWidget`;
  required by reports." It is not listed for its own sake — dropping it breaks
  reports under schema-per-tenant.
- **These proxies are SHARED even though several of the underlying rows carry a
  `school` FK.** `TenantBlueprint`, `DashboardPackAssignment`,
  `TenantLayoutAssignment`, `WorkflowPackAssignment`, `TenantWorkflow`,
  `OfficialReportTemplate`, and `FormDraft` all live in the public schema and are
  scoped by an explicit `school` reference — *not* by a Postgres schema. Every
  query against them needs a `school=` filter, and the repo's
  `scan_tenant_queryset_safety.py` gate (baseline 0) enforces exactly that. A
  proxy inherits the concrete model's isolation obligations; it does not soften
  them.
- **The imports reach into siteconfig *submodules* on purpose.** `models.py`
  imports from `apps.siteconfig.models_tooling` / `models_dashboard` /
  `models_workflow`, never from `apps.siteconfig.models`. The in-file comment
  gives the reason: "Import from siteconfig submodules to avoid circular import
  via `siteconfig.models`." Rewriting these to the convenient top-level import
  re-introduces the cycle — and the smoke test above is what will catch you.
- **Three names are surfaced by two different bounded-context apps, and they are
  not the same class.** `BlueprintPack`, `BlueprintCompatibilityRule`, and
  `TenantBlueprint` are exposed both here (as *proxies*, `app_label="runtime_blueprints"`)
  and by `apps.policies_rules` (as plain *re-exports* — literally the concrete
  `apps.policies` class object). They share a table, so queries agree, but the
  class identity does not: `runtime_blueprints.TenantBlueprint` is a subclass of
  the concrete model, so `isinstance(rb_obj, policies.TenantBlueprint)` is `True`
  while the reverse is `False`, and Django gives a proxy model its **own
  `ContentType` row** — so anything keyed on ContentType (generic FKs,
  permissions, audit rows) will disagree depending on which import path created
  the object. Pick one import path per call site and stay on it.
