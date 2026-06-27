# TenantRuntime Compilation Pipeline

**Audience:** operators (what `request.tenant_runtime` is, how to read/refresh it,
what a cache-staleness symptom looks like) + engineers (the exact 13-step build
order, the 17 typed context contracts, the two cache tiers and their
invalidation, and how to consume the runtime instead of reaching into
`school.settings`).

**What it is:** the per-request engine that compiles a single, frozen, typed
view of "everything that decides tenant-facing behavior" — identity, registry
(country/currency/grade scales), blueprint, policy bundle, feature flags &
entitlements, branding, workflows, dashboards, integrations/marketplace,
compliance/security, and module configs — into one `TenantRuntime` object and
attaches it as `request.tenant_runtime`.

> **Scope note vs. the precedence doc.** [`runtime_precedence.md`](runtime_precedence.md)
> and [`RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md`](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md)
> document the **7-layer authority order** (who overrides whom). This doc
> documents the **13-step compilation pipeline** that produces the runtime
> object that the precedence order feeds into. They are different things: the
> precedence list is the merge policy; the pipeline is the assembly line. The
> two intersect at exactly one step — feature-flag merging (step 6, see §5).

---

## 1. Entry points

| How it is built | Function | Source |
|---|---|---|
| Per HTTP request (the normal path) | `TenantRuntimeMiddleware.process_request` calls `build_tenant_runtime(tenant_ctx, request=request)` | `apps/platform_runtime/middleware.py:17-23` |
| Outside a request (Celery task / worker) | `build_tenant_runtime_for_tenant(tenant, mode="job")` synthesizes a `TenantContext` then calls the same builder | `apps/platform_runtime/runtime_resolver.py:883-911` |
| Operator inspection (control plane, debug) | `runtime_inspector` re-runs `build_tenant_runtime` and serializes the result | `apps/platform_runtime/runtime_inspector.py:1-21` |

The middleware runs **after** `TenantContextMiddleware` because it reads
`request.tenant_ctx`; if `tenant_ctx` is absent it sets
`request.tenant_runtime = None` and returns (`middleware.py:18-23`). The ordering
is pinned in settings — `TenantContextMiddleware` then `TenantRuntimeMiddleware`
(`config/settings.py:357,360`, and again in the alternate stack at
`config/settings.py:3818,3821`).

---

## 2. The 13-step compilation order

`build_tenant_runtime` runs a fixed, numbered sequence and records each step in a
`compilation_trace` list for the debug section (`runtime_resolver.py:731-880`).
The order is the single source of truth (docstring at
`runtime_resolver.py:5-19`, mirrored at `runtime_resolver.py:739-743`):

| Step | Function (`runtime_resolver.py`) | Produces (contract) | What it reads |
|---|---|---|---|
| 1 | `_step1_route_context` (`:78`) | `RouteContext` | surface (`marketing` / `control_plane` / `tenant_plane`), `is_preview`, `is_sandbox` from `tenant_ctx.policy_overrides` (`:90-99`) |
| 2 | `_step2_tenant_identity` (`:102`) | `TenantIdentity` | `school.id/slug/domain/plan/status/campus_mode/primary_sector` (`:115-128`) |
| 3 | `_step3_registry_context` (`:131`) | `RegistryContext` | `apps.registries` models: country, currency, education levels/system types, institution/document/fee types, grade-scale families — **cached 5 min** (`:131-249`) |
| 4 | `_step4_blueprint` (`:252`) | `BlueprintContext` | `school.tenant_blueprint.applied_pack` (`:254-273`) |
| 5 | `_step5_policy_bundle` (`:283`) | `PolicyContext` | typed sections sliced out of the merged `policy` dict (`:288-302`) |
| 6 | `_step6_flags_entitlements` (`:305`) | `FlagsContext`, `EntitlementsContext` | merges policy `features` + tenant flags + sandbox overlay; entitlements from policy or `plan.modules` (`:318-355`) |
| 7 | `_step7_branding` (`:358`) | `BrandingContext` | `resolve_brand_profile(school, site)`, falling back to raw `school` color/logo fields (`:364-410`) |
| 8 | `_step8_workflows` (`:413`) | `WorkflowsContext` | `WorkflowPackAssignment` + legacy `workflow_resolver.for_action` for `admissions/fee_approval/grade_publish/grade_approval` (`:418-462`) |
| 9 | `_step9_dashboards` (`:465`) | `DashboardsContext` | `DashboardPackAssignment` + legacy `dashboard_resolver.for_role` for `admin/teacher/parent/finance/admissions` (`:471-513`) |
| 10 | `_step10_integrations_marketplace` (`:594`) → `_step10_marketplace` (`:516`) | `IntegrationsContext`, `MarketplaceContext` | `ServiceIntegration` (payment/messaging providers) + active `AppInstallation` (installed apps, granted scopes, widget/workflow/adapter registries) (`:516-632`) |
| 11 | `_step11_compliance_security` (`:635`) | `ComplianceContext`, `SecurityContext` | policy `compliance`/`hr_staff` section + the request actor (id/role/impersonation) (`:636-671`) |
| 12 | `_step12_module_configs` (`:674`) | `ModuleConfigContext` | composes admissions/gradebook/finance from registry + policy + workflows + dashboards already built above (`:683-728`) |
| 13 | freeze (debug) | `RuntimeDebug` + assembled `TenantRuntime` | builds `RuntimeDebug` (version, applied overrides, `compilation_trace`, timestamp) and the immutable `TenantRuntime` (`:825-864`) |

After step 13 the runtime is "treated as immutable for the request"
(`contracts.py:262-263`). The trace list ends with `"13:freeze"`
(`runtime_resolver.py:837`).

### Policy resolution (the input to steps 5/6/11)

If no `policy` is passed in, the builder calls
`get_effective_policy(school, user=user)` (`runtime_resolver.py:754-766`,
defined at `apps/policies/policy_registry.py:18`); failure logs a warning and
falls back to an **empty** policy `{}` so the build never raises
(`runtime_resolver.py:760-768`).

### Failure posture (why a partial deploy still renders)

Every step that touches the DB or an optional app is wrapped in a typed
`try/except` that logs and returns an **empty** context rather than raising — e.g.
registries (`runtime_resolver.py:227-232`), blueprint (`:274-279`), workflows
(`:456-461`), dashboards (`:507-512`), marketplace (`:578-583`), integrations
(`:619-624`). A missing optional app or an un-migrated registry degrades that one
section to empty; it does not 500 the request.

---

## 3. The 17 typed contexts (the contract surface)

All section contexts are frozen dataclasses; `TenantRuntime` itself is a (mutable
during build, then treated-immutable) dataclass. Definitions in
`apps/platform_runtime/contracts.py`:

`TenantIdentity` (`:35`), `RouteContext` (`:51`), `RegistryContext` (`:63`),
`BlueprintContext` (`:82`), `PolicyContext` (`:96`), `BrandingContext` (`:112`),
`FlagsContext` (`:127`), `EntitlementsContext` (`:137`), `WorkflowsContext`
(`:150`), `DashboardsContext` (`:159`), `IntegrationsContext` (`:167`),
`MarketplaceContext` (`:180`), `ComplianceContext` (`:192`), `LocaleContext`
(`:204`), `SecurityContext` (`:216`), `ModuleConfigContext` (`:227`),
`RuntimeDebug` (`:239`), and the aggregate `TenantRuntime` (`:255`).

### `TenantRuntime` accessors engineers should use

`TenantRuntime` exposes properties and resolver methods so callers never re-walk
the chain (`contracts.py:294-352`):

- `is_tenant`, `school_id`, `schema_name` — proxy `tenant_ctx` (`:294-304`).
- `workflow_for(action_slug)` — resolve a workflow def (`:306-315`).
- `get_approval_workflow(workflow_key)` — approval roles/approvers, with a safe
  empty default when there is no school (`:317-338`).
- `dashboard_for(role=..., user=..., **kwargs)` — resolve a role dashboard
  (`:340-351`).

Use these, and the typed sections (`runtime.modules.finance["currency"]`,
`runtime.branding.colors`, `runtime.flags.flags[...]`), instead of reading
`school.settings` / `school.features` directly — that is the whole point of the
pipeline (`contracts.py:269-270`).

---

## 4. Caching — two tiers

### Tier A: request-scope (build once per request)

`build_tenant_runtime` checks a request-attribute cache before doing any work and
stores the result after (`runtime_resolver.py:747-752, 866-867`). The cache is a
plain dict hung off the request under `_platform_runtime_request_cache`, keyed by
`rt:<tenant_id|school_id>:<school_id>` (`apps/platform_runtime/cache.py:13,42-56`).
So multiple consumers in the same request share one build.

### Tier B: per-tenant Django cache (stable segments, 5-min TTL)

- The registry segment (step 3) is cached in the Django cache backend under
  `platform_runtime:registry_context:<country>` for `REGISTRY_CONTEXT_CACHE_TTL`
  = 300s (`runtime_resolver.py:32,138-141,248`).
- A general helper `get_tenant_cached_segment(school_id, segment, loader)` caches
  any stable segment under `platform_runtime:tenant:<school_id>:<segment>` with
  `RUNTIME_TENANT_CACHE_TTL` (default 300s, overridable via settings)
  (`cache.py:61-95`). TTL `<= 0` disables caching and always calls the loader
  (`cache.py:84-85`).

### Invalidation (operator-relevant)

`invalidate_tenant_runtime_cache(school_id)` deletes the known per-tenant
segments (`registry`, `blueprint`, `policy`, `branding`, `workflows`,
`dashboards`, `marketplace`) — call it after any change to those
(`cache.py:98-120`). The convenience wrapper
`invalidate_policy_and_runtime_caches(school)` also clears the policies-app
cache, then the runtime cache (`cache.py:123-133`). **Operator symptom:** a
policy/blueprint/branding change that "doesn't show up" for up to ~5 minutes is
the Tier-B TTL; forcing it requires an invalidation call (or waiting out the
TTL).

---

## 5. The one intersection with the 7-layer precedence: feature flags

Step 6 is where the compilation pipeline calls into the precedence engine.
`_step6_flags_entitlements` merges three flag sources in precedence order
(lowest first, higher wins on conflict) via
`merge_feature_flags_by_runtime_precedence` (`runtime_resolver.py:318-338`;
function at `apps/platform_runtime/precedence.py:82-111`):

1. policy `features` (already merged platform→region→tenant policy bundle),
2. `TenantContext.feature_flags` (per-request tenant overlay),
3. sandbox/preview overlay from `policy_overrides["feature_flags"]` /
   `["sandbox_feature_flags"]` — applied **only** when `route.is_sandbox` or
   `route.is_preview` (`runtime_resolver.py:321-329`).

The precedence module is the authority list itself: `PRECEDENCE_ORDER`
(`precedence.py:13-21`), aliases (`:23-34`), `precedence_rank` (`:56-58`),
`merge_by_precedence` (`:72-79`), and `merge_feature_flags_by_runtime_precedence`
(`:82-111`). The ordered keys are `platform_default → registry_default →
blueprint_default → policy_bundle → entitlement_gate → tenant_override →
sandbox_override` (`precedence.py:13-21`).

---

## 6. Who consumes `request.tenant_runtime`

~36 references across the codebase read `request.tenant_runtime` (e.g.
`apps/evals/runtime_helpers.py`, `apps/finance/runtime_helpers.py`,
`apps/portal/runtime_helpers.py`, `apps/reports/services.py`,
`apps/siteconfig/config_service.py`, `apps/api/entity_api.py`). The per-app
`runtime_helpers.py` modules are the intended adapter layer — call those, or the
`TenantRuntime` accessors in §3, rather than re-deriving behavior from the
school record.

The runtime is **not** injected by a template context processor. The processors
in `apps/platform_runtime/context_processors.py` expose adjacent strips
(shell contract, offline sync bar, AI layer, action hub, etc.) but the runtime
itself reaches templates through views that read `request.tenant_runtime`.

---

## 7. Operator runbook

| Need | Do this |
|---|---|
| See a tenant's effective blueprint / policies / entitlements / overrides | Use the runtime inspector (control-plane operator tooling, Phase 9) — `apps/platform_runtime/runtime_inspector.py:1-4`. It re-runs `build_tenant_runtime` and serializes blueprint/policy/entitlement/marketplace snapshots. |
| A config change isn't visible | It is almost always the Tier-B 5-min TTL (§4). Call `invalidate_policy_and_runtime_caches(school)` (`cache.py:123`) or wait out the TTL. |
| A section is mysteriously empty | That section's optional app/registry is missing or un-migrated; the step degraded to empty by design (§2 "Failure posture"). Check the warning logs the step emits. |
| Confirm build order didn't change | `RuntimeDebug.compilation_trace` lists every step `1:route … 13:freeze` (`runtime_resolver.py:770-837`). |

---

## 8. Tests (regression anchors)

- `apps/platform_runtime/tests/test_precedence.py` — precedence ordering /
  merge behavior.
- `apps/platform_runtime/tests/test_runtime_contract.py` — the `TenantRuntime`
  contract surface.
- `apps/platform_runtime/tests/test_core_runtime_integrity.py`,
  `test_web_runtime.py`, `test_runtime_by_blueprint_family.py`,
  `test_entitlement_policy_runtime.py` — runtime build / blueprint / entitlement
  coverage.
- `test_batch953_runtime_resolution_trace_log.py` — the `compilation_trace`
  log line.

---

## 9. Quick reference (paths)

- Builder + steps: `apps/platform_runtime/runtime_resolver.py`
  (`build_tenant_runtime:731`, `build_tenant_runtime_for_tenant:883`,
  `_step1`…`_step12` at `:78,102,131,252,283,305,358,413,465,516,594,635,674`).
- Contracts: `apps/platform_runtime/contracts.py` (17 dataclasses, `TenantRuntime:255`).
- Precedence engine: `apps/platform_runtime/precedence.py`.
- Caches + invalidation: `apps/platform_runtime/cache.py`.
- Middleware: `apps/platform_runtime/middleware.py`; wired at
  `config/settings.py:357-360`.
- Inspector: `apps/platform_runtime/runtime_inspector.py`.
- Related docs: [`runtime_precedence.md`](runtime_precedence.md),
  [`RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md`](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md),
  [`runtime_resolvers_and_contracts.md`](runtime_resolvers_and_contracts.md).
