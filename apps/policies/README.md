# apps/policies

> The Policy Decision Point (PDP) plus the tenant blueprint: one place that
> answers "is this subject allowed to do this to this resource?" and one place
> that resolves what a school's effective settings actually are.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` FK,
not by a Postgres schema)
**Scale:** 10 models · 10 migrations · 8 test modules · ~5.9k LOC

## What this app owns

Two related things share this app. The first is the **PDP** — `pdp.py::decide`
is a single entry point that evaluates `PolicyRule` rows against a
(subject, action, resource) triple and returns an effect of `allow`, `deny`, or
`implicit_deny`, plus the rule that matched and a human-readable explanation.
Every call writes a `PolicyDecisionLog` row; the log is the product, not a side
effect. On top of it sit `enforcement.py` (view decorators) and `dlp.py`
(field-level redaction driven by the entity catalog's sensitivity tiers).

The second is the **blueprint / policy resolver** — `resolver.py` merges
platform defaults ⊕ country defaults ⊕ tenant overrides into one effective
policy, and `PolicyBundle` snapshots that merge at a point in time so it can be
rolled back to.

The defining design decision is **how enforcement was turned on without
breaking anything**. The PDP was promoted from advisory to enforce on
2026-07-09, and the mechanism that made that safe is *parity probes*: an
enforced surface passes its OWN canonical RBAC gate as
`parity_probe=<callable(request) -> bool>`, whose verdict lands in the subject
as `subject.rbac_allowed`. The platform-baseline allow-rules seeded by migration
0010 condition on exactly that. So enforcement starts at *exact parity* with
the access each surface already granted, and from that floor the PDP can only
ever **narrow** — a tenant or operator deny rule (default priority 100, ahead of
the priority-500 baselines) binds, and deactivating a baseline rule fail-closes
its surface. The whole design lets a risky global flip start as a no-op.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `PolicyRule` | `policies_policyrule` | The ABAC rule the PDP evaluates: subject/action/resource matchers + conditions + priority |
| `PolicyDecisionLog` | `policies_policydecisionlog` | Append-only log of every PDP decision — written on every `decide()` call |
| `PolicyBundle` | `policies_policybundle` | Snapshot of merged policy (settings + features) for a school at a point in time |
| `TenantBlueprint` | `policies_tenantblueprint` | Points a school at its active `PolicyBundle`; rollback = repoint it |
| `TenantPolicyOverride` | `policies_tenantpolicyoverride` | Tenant-level override for one policy key |
| `ScheduledPolicyOverride` | `policies_scheduledpolicyoverride` | Temporary override active only between `start_at` and `end_at` |
| `CountryProfile` | `policies_countryprofile` | Region/country-level defaults (currency, timezone, grading scale) — the middle layer of the merge |
| `BlueprintPack` | `policies_blueprintpack` | Catalog entry for a blueprint pack: institution archetype + `policy_snapshot` template |
| `BlueprintCompatibilityRule` | `policies_blueprintcompatibilityrule` | Links blueprint packs to compatible policy bundles/constraints |
| `PolicyCompatibilityRule` | `policies_policycompatibilityrule` | Which blueprints/countries a policy bundle applies to |

All 10 declared models are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `pdp` | `decide()` / `allowed()` — the single PDP entry point; documents the rule DSL in its docstring |
| Module | `enforcement` | `pdp_advisory` (logs, never blocks) and `pdp_enforce` (raises `PermissionDenied`) |
| Module | `dlp` | Field-level redaction: null / mask / hash / tokenize per the field's `dlp_redaction_strategy` |
| Module | `resolver` | `get_effective_policy` / `get_tenant_blueprint` — the platform ⊕ country ⊕ tenant merge |
| Module | `blueprint_registry` | The canonical import for blueprint reads + apply/preview |
| Module | `declarative_overrides` | Idempotent loader for an operator-shipped JSON (or YAML, when PyYAML is present) override file |
| Module | `rollback` | Repoints `TenantBlueprint.active_bundle` at a previous bundle |
| Management command | `apply_tenant_overrides` | Applies a declarative override file |
| Management command | `seed_blueprint_policy_packs`, `update_blueprint_bundles` | Blueprint pack seeding / bundle refresh |
| Setting | `POLICY_PDP_ENFORCEMENT_MODE` | `enforce` (deployed default since 2026-07-09) / `advisory` (rollback posture) / `off` |
| Setting | `POLICY_CACHE_TTL` | Optional per-tenant policy caching in the resolver |

No `urls.py` and no Celery tasks — this app is consumed by other apps'
surfaces. `apps.py::ready()` imports `signals` unguarded.

## Before you change this

- **Never read `School.settings` / `School.features` directly.** The resolver's
  module docstring states this as a rule: go through `get_effective_policy`, or
  the platform ⊕ country ⊕ tenant merge silently doesn't happen and a school's
  country defaults and overrides are skipped.
- **`pdp_enforce` must sit INNERMOST on the view stack**, below `@login_required`
  / `@require_school` / the coarse RBAC gates. Put it above them and anonymous
  users get a `PermissionDenied` instead of a login redirect, and the PDP starts
  seeing requests the coarse gates were supposed to reject first.
- **Everything fails closed, deliberately.** A parity probe that raises computes
  `False`, not `True`. An unknown `POLICY_PDP_ENFORCEMENT_MODE` value falls back
  to `advisory`, not `enforce`. `implicit_deny` (no rule matched) is a deny, not
  a default-allow. Do not "helpfully" soften any of these.
- **`is_superuser` is god-mode and bypasses the PDP entirely** — when the subject
  is a platform superuser, `decide` skips rule evaluation altogether (`for rule
  in [] if is_god else ...`) and returns allow. That is intentional so the
  platform superadmin can never be locked out by a tenant's own policy. Note it
  keys on the Django `is_superuser` flag, not on a `SUPERADMIN` role string —
  the two are not the same thing on this platform.
- **Rule priority is ascending-wins and the numbers are load-bearing.** Baseline
  allow-rules seeded by migration 0010 sit at priority 500; tenant/operator deny
  rules default to 100 so they bind ahead of the baseline. Reseeding baselines at
  a lower number would silently make tenant denies unreachable.
- **Deactivating a baseline rule fail-closes its surface.** That is the intended
  kill-switch, but it means a casual "let's disable this rule and see" takes a
  surface offline for everyone. The documented rollback for the whole PDP is
  `POLICY_PDP_ENFORCEMENT_MODE=advisory`, not rule surgery.
- **The `PolicyDecisionLog` truncation caps are derived from the model's own
  `max_length`s** via `_meta.get_field`, precisely so they can never drift from
  the schema. If you widen a column, do not add a second hardcoded cap beside it.
  `decision_reason` is an unbounded `TextField`, so its 5000-char cap is a
  deliberate soft bound on log-row size rather than a column fit.
- **`declarative_overrides` is idempotent by contract** — re-running the same
  file must remain a no-op. YAML support is conditional on PyYAML being
  installed; JSON always works.
