# PROMPT 2 — Aggressive, intrusive tenant audit + re-architecture (no more break-fixes)

> Paste as a single instruction. This is the "stop patching, fix the structure" mandate. It is grounded in a
> 2026-06-26 architecture map; the 12 targets below are real and tied to files.

## Mission

Audit **everything** about how tenants work — from **conception to configurability** — aggressively and
intrusively, then **re-architect the incoherent parts** so the platform is stable, robust, innovative,
creative and inspiring instead of a stream of break-fixes. Scope: provisioning, configurability, RBAC, the
management/teacher/parent/student/owner experiences, every tool and app, cross-surface consistency,
blueprints, policies, and **how the tenant subdomains and the operator/control-plane section relate**. Where
there is a *better way*, implement it — don't just document it.

Align to the goal: the AWS / Salesforce / Shopify of school management. Premium, luxury, best-in-class.

## Method (this is what makes it NOT a break-fix)

1. **AUDIT-FIRST, evidence-based.** For every claim, cite `path:line`. Do not trust labels or counters that
   could be pinned to 0 by a swallowed exception — verify against the live registry/resolver.
2. **Name the incoherence, then converge it.** Where two systems own one concern (e.g. config in three
   stores), pick ONE source of truth, build a single resolver, and migrate the others behind it.
3. **Lock invariants with CI gates.** Every structural fix ships with a zero-tolerance scanner/verifier so
   the regression can never silently return (this codebase already has ~30 such gates — extend the pattern).
4. **Tenant-wide & lifecycle-safe.** Fixes must hold for past, present and future tenants (data migrations
   + signup path), and must not regress tenant isolation (`scan_tenant_queryset_safety` baseline 0).
5. **Surgical waves, not a big-bang rewrite.** Sequence as independent waves; each wave is green (tests +
   gates) before the next. Show diffs; never `git add -A` (shared tree with a concurrent agent).

## The 12 audit targets (each: investigate → decide SOT/redesign → implement → gate)

1. **Provisioning state coherence.** There is NO single FSM — state is split across `School.settings` (JSON),
   `setup_studio.SetupProgress` (structured), and `schools.SchoolProvisioningEvent` (22-state audit trail).
   Two modules can disagree on "launch-ready". → Define ONE canonical provisioning/lifecycle state contract
   (an explicit enum/FSM), make `launch_ready`/`launch_blockers`/`health_score` derive from it, and back the
   "14-state lifecycle OS" the design hub promises. Files: `apps/schools/models.py:289,934`,
   `apps/setup_studio/models.py:6,32`, `apps/schools/onboarding_service.py`, `apps/lifecycle/`.

2. **Configurability SOT fragmentation.** `RuntimeDefaults` (≈170 first-class typed cols + JSON) vs
   `siteconfig.SiteSettings` (JSON brand_payload) vs `School.settings` (JSON). The `EXACT_FIELD_OWNERS` map +
   `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES` tuple must be hand-synced; drift is silent. → Designate the SOT
   per field class, build one `get_effective_config(school, key)` resolver everyone calls, and add a CI gate
   that fails when a typed column is added without its tuple/owner entry. Files:
   `apps/platform_runtime/runtime_defaults_first_class.py`, `apps/siteconfig/models.py`,
   `apps/siteconfig/config_service.py`, `apps/siteconfig/domain_ownership.py`, `apps/siteconfig/context_processors.py`.

3. **RBAC multi-role composition.** `User.Role` (24 TextChoices) + school-scoped `AccessRole` (permissions are
   GLOBAL) + ad-hoc dual-hat (teacher-hat/parent-hat on one account). A school owner could mint a role with
   permissions they shouldn't grant; no per-school permission ceiling. → Formalize role composition + a
   per-school permission ceiling; one `user.can(action, school)` gate. Files: `apps/accounts/models.py:63,150`,
   `apps/accounts/permissions.py`, `apps/accounts/decorators.py`, `apps/portal/portal_roles.py`,
   `apps/platform_runtime/role_registry.py`. Keep `scan_role_strings` honest.

4. **Operator ↔ tenant boundary + audit trail.** Manager host is middleware-routed, not settings-registered;
   impersonation is session-based with **no persistent "who impersonated whom, when, what changed" log**; any
   SUPERADMIN sees all schools (operator-team scoping is second-class). → Add an operator-action audit ledger
   (append-only, like `migration_cloud` audit), enforce operator-team scoping at the view layer, and harden
   host→urlconf resolution. Files: `config/manager_urls.py`, `config/tenant_urls.py`,
   `apps/schools/control_plane.py`, `apps/schools/super_views_impersonation.py`, `apps/schools/bulk_operator_actions.py`,
   `apps/tenancy/middleware_boundary_guard.py`.

5. **Policy enforcement scatter.** `apps/policies/resolver.py::get_effective_policy` merges correctly, but
   field-level RLS (`apps/policies_rules/enforcement.py::apply_policy_rules`) is OPT-IN — 100+ views/serializers
   may forget it and leak data. → Make policy enforcement mandatory at a chokepoint (a base view/serializer
   mixin or middleware), add a "policy-coverage" gate that flags tenant-data views not behind the gate, and a
   dry-run "policy impact preview". Files: `apps/policies/resolver.py`, `apps/policies_rules/enforcement.py`,
   `apps/policies/models.py`.

6. **Blueprint stale-version drift.** Applying a `BlueprintPack` snapshots `policy_snapshot` into a
   `PolicyBundle`; pack version bumps are detected but NEVER auto-applied — schools drift from intended policy
   forever; no pack-dependency model. → Add an update/reconcile path (operator-approved bulk re-apply with
   diff preview) + a typed schema for `policy_snapshot` (no more untyped JSON). Files:
   `apps/policies/models.py:149`, `apps/policies/blueprint_services.py`, `apps/runtime_blueprints/`.

7. **Tenant isolation at the async boundary.** Request path is pinned (`TenantBoundaryCoreGuardMiddleware`),
   but Celery tasks rely on opt-in `celery_boundary.py` guards. → Make tenant-pinning mandatory for tasks that
   touch tenant-scoped models; extend `scan_tenant_queryset_safety` coverage to task modules. Files:
   `apps/tenancy/celery_boundary.py`, `apps/tenancy/queryset_boundary.py`, `apps/tenancy/boundary_core_guard.py`.

8. **Dashboard role dispatch.** No middleware role-gate — a misconfigured view can render the wrong shell for a
   role; the portal sidebar rebuilds per request (no cache); theme-pack fallback is silent. → Add a role→shell
   contract + per-request sidebar cache + explicit theme-pack fallback. Files: `templates/portal_base.html`,
   `apps/siteconfig/context_processors.py`, `apps/siteconfig/portal_sidebar_items.py`, `apps/portal/views_*.py`.

9. **API tenant scoping.** Shared `config/api_urls.py`; serializers must remember to filter by
   `request.user.school`; tokens are user-level, not school-annotated. → Enforce tenant scoping at a base
   serializer/permission layer; annotate tokens with school. Files: `apps/api/`, `config/api_urls.py`,
   `apps/accounts/auth_backends_*.py`.

10. **Offline two-rail divergence.** SODP (`platform_runtime/offline_queue.py`) and WAL (`wal_stream/`) can
    diverge; conflict resolution for stale offline writes is unspecified. → Specify conflict resolution
    (remote-wins/merge) per capability; keep `verify_offline_capability_implementation` at 0.
    Files: `apps/platform_runtime/offline_queue.py`, `apps/wal_stream/`, `docs/OFFLINE_TWO_RAIL_ARCHITECTURE.md`.

11. **Feature-flag cascade.** A feature can be toggled by env flag, entitlement, policy AND plan with no
    central arbiter. → One `feature_enabled(school, key)` arbiter with a defined precedence. Files:
    `apps/platform_runtime/helpers.py`, `apps/plans_entitlements/`, `apps/policies/resolver.py`.

12. **Consistency across surfaces.** Confirm the 5 shells (`portal_base`, `control_plane_skeleton`, `base`,
    `admin/base_site`, `marketing`) share the token system, grammar and chrome; flag any surface that forked.
    Use the existing gate families (reference-integrity, theme-locked, undefined-css, role-string, locale-display)
    as the consistency yardstick and close any drift.

## Deliverables

1. `docs/generated/TENANT_ARCHITECTURE_AUDIT_<date>.html` (or `.md`) — findings per target with `path:line`
   evidence, a verdict (coherent / fragmented / leaking), and the chosen SOT/redesign.
2. A sequenced remediation plan: independent waves, each with its own tests + a new CI gate that locks the
   invariant. Recommend the order by risk × leverage (config SOT, provisioning FSM, policy chokepoint, and
   operator audit trail are the highest-leverage).
3. Implement the top waves end-to-end (don't stop at the doc) — tested, gated, tenant-wide, green.

## Guardrails

- No break-fixes: prefer a structural fix + an invariant gate over a one-off patch.
- No hardcoding; route through the cascade. No `git add -A`. Don't touch peer-uncommitted files.
- Keep all reference-integrity + tenant-isolation gates at their baselines. Bump SW on CSS/JS waves.
- Surface scope before sweeping: name the breadth and the strategic subset first.
