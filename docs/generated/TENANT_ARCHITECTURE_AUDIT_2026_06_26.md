# Tenant architecture audit — triage & remediation plan (START of Prompt 2)

**Date:** 2026-06-26 · **Status:** triage / hypotheses-to-confirm (NOT a completed audit).
**Method note:** findings below come from an architecture-map sweep. Treat each as a HYPOTHESIS to confirm
against live code before remediating — a parallel width audit this session was partly STALE (it claimed
`package_rollout.html` still used `.cp-list`; it was already converted to `.cp-grid`). Verify first.

This document starts Prompt 2 (`docs/generated/PROMPT_2_TENANT_DEEP_AUDIT_AND_REARCHITECT.md`): it triages the
12 structural targets, gives each a preliminary verdict, and recommends the wave order by risk × leverage.

## The 12 targets — preliminary verdict

| # | Target | Preliminary verdict | Confirm against | Leverage |
|---|--------|--------------------|-----------------|----------|
| 1 | Provisioning state coherence | **Fragmented** — no FSM enum; state in `School.settings` + `SetupProgress` + `SchoolProvisioningEvent` (22 event types) | `apps/schools/models.py`, `apps/setup_studio/models.py`, `apps/lifecycle/` | HIGH |
| 2 | Config SOT fragmentation | **Fragmented** — `RuntimeDefaults` (≈170 typed + JSON) vs `SiteSettings.brand_payload` vs `School.settings`; owner map hand-synced | `apps/platform_runtime/runtime_defaults_first_class.py`, `apps/siteconfig/config_service.py`, `domain_ownership.py` | HIGH |
| 3 | RBAC multi-role composition | **Risk** — `AccessRole` school-scoped but permissions global; ad-hoc dual-hat; no per-school ceiling | `apps/accounts/models.py`, `permissions.py`, `apps/portal/portal_roles.py` | MED |
| 4 | Operator↔tenant boundary + audit | **Gap** — impersonation session-based, no persistent who-did-what ledger; any SUPERADMIN sees all schools | `apps/schools/control_plane.py`, `super_views_impersonation.py`, `bulk_operator_actions.py` | HIGH |
| 5 | Policy enforcement scatter | **Leak risk** — `apply_policy_rules()` is OPT-IN; 100+ views may skip it | `apps/policies/resolver.py`, `apps/policies_rules/enforcement.py` | HIGH |
| 6 | Blueprint stale-version | **Drift** — version bumps detected, never auto-reconciled; untyped `policy_snapshot` JSON | `apps/policies/models.py`, `blueprint_services.py`, `apps/runtime_blueprints/` | MED |
| 7 | Tenant isolation @ async boundary | **Opt-in** — request path pinned; Celery guards opt-in | `apps/tenancy/celery_boundary.py`, `queryset_boundary.py` | HIGH |
| 8 | Dashboard role dispatch | **Fragile** — no middleware role-gate; per-request sidebar rebuild; silent theme-pack fallback | `templates/portal_base.html`, `apps/siteconfig/context_processors.py`, `portal_sidebar_items.py` | MED |
| 9 | API tenant scoping | **Risk** — serializers must remember `request.user.school`; tokens not school-annotated | `apps/api/`, `config/api_urls.py`, `apps/accounts/auth_backends_*.py` | HIGH |
| 10 | Offline two-rail divergence | **Watch** — SODP + WAL can diverge; conflict resolution unspecified | `apps/platform_runtime/offline_queue.py`, `apps/wal_stream/` | MED |
| 11 | Feature-flag cascade | **Diffuse** — env flag + entitlement + policy + plan, no single arbiter | `apps/platform_runtime/helpers.py`, `apps/plans_entitlements/` | MED |
| 12 | Cross-surface consistency | **Mostly OK** — 5 shells share token grammar; ~30 CI gates already enforce it | the existing gate families | LOW (already guarded) |

## Recommended wave order (risk × leverage)

The platform's strength is its CI-gate culture (~30 zero-tolerance scanners). The right play is the SAME
pattern for these structural concerns: converge to ONE source of truth, then lock it with a new gate.

1. **Wave A — Config SOT (target 2).** Highest leverage: every surface reads config. Designate the SOT per
   field class, expose ONE `get_effective_config(school, key)` resolver, and add a gate that fails when a
   typed `RuntimeDefaults` column is added without its `FIRST_CLASS_FIELD_NAMES` + `EXACT_FIELD_OWNERS` entry.
   Low blast-radius (additive resolver), unblocks everything else.

2. **Wave B — Policy enforcement chokepoint (target 5) + API scoping (target 9).** Both are data-leak risks.
   Make policy + tenant scoping mandatory at a base view/serializer mixin; add a "coverage" gate that flags
   any tenant-data view/serializer not behind it. Directly serves "stable, not break-fix."

3. **Wave C — Provisioning FSM (target 1) + operator audit ledger (target 4).** Define one provisioning
   state enum that `launch_ready`/`blockers`/`health` derive from; add an append-only operator-action ledger
   (mirror the existing `migration_cloud` audit pattern). Powers the "14-state lifecycle OS" the hub promises.

4. **Wave D — Async isolation (7), blueprint reconcile (6), feature-flag arbiter (11), dashboard dispatch (8).**

Each wave: AUDIT-FIRST (confirm the hypothesis), converge to one SOT, implement tenant-wide (data migration +
signup path), ship a new CI gate, keep all existing baselines green. No big-bang.

## Honest scope note

This is the triage. The full audit + remediation is a multi-wave program (Prompt 2 says "implement the top
waves"), best run in a fresh `/clear`'d session per CLAUDE.md. Nothing here is implemented yet — Wave A is the
recommended first concrete step.
