# apps/setup_studio

> The Unified Wizard Engine — every guided setup flow in the platform, defined in
> JSON, driven by one engine, persisted into one row per school.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` FK, not by a Postgres schema)
**Scale:** 2 models · 4 migrations · 39 test modules · ~15.3k LOC

## What this app owns

`setup_studio` answers one question: how does a brand-new school go from an empty
tenant to a working campus without an implementation consultant? It owns the
guided-onboarding checklist and, more importantly, the **Unified Wizard Engine** —
the single runtime behind every wizard on the platform, operator-facing and
tenant-facing alike.

The defining design decision is that **a wizard is data, not code**. Each one is
a JSON file in `apps/setup_studio/wizards/` (37 of them at present) declaring its
steps, branching, validation rules, audience, and dotted-path references to
resolvers. `wizard_engine` loads and validates the whole registry at import time
— schema, resolver importability, audience markers — so a malformed wizard fails
at startup rather than half-way through a school's onboarding. Adding a wizard
means adding a JSON file and a resolver function; it does not mean adding a view,
a URL, a template, or a migration.

The second decision follows from the first: **wizard state needs no schema.**
Every school has exactly one `SetupProgress` row, and all wizard answers live
namespaced under `step_state["wizards"][<wizard_key>]` (see
`wizard_state_resolver`). That is why an app with ~15k LOC and 39 test modules
carries just two models and four migrations, and why shipping a new wizard never
touches the migration rail.

Persistence writers do not own domain tables either. They write through the
tenant `School.settings` JSON (via `wizard_resolvers._write_to_site_settings`,
which `platform_runtime`'s `get_effective_site_settings` reads as overrides on
the global singleton) and integrate best-effort into per-domain services where
those already exist. The wizard never invents a parallel write path to a domain
that already has one.

## Key models

The app declares exactly 2 models — see "What this app owns" for why.

| Model | Table | Purpose |
| --- | --- | --- |
| `SetupProgress` | `setup_studio_setupprogress` | One row per school. Holds `current_step_key`, `completed_keys`, and the `step_state` JSONField that is the entire wizard-state store (`step_state["wizards"][<key>]`). |
| `SetupStepDefinition` | `setup_studio_setupstepdefinition` | Platform-wide master definition of a checklist setup step (key, label, order, group, link). Not per-tenant. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `tenant_wizard_index` / `tenant_wizard` / `tenant_wizard_step` / `tenant_wizard_reset` | Tenant surface at `/school/studio/wizards/` |
| URL | `operator_wizard_index` / `operator_wizard` / `operator_wizard_step` / `operator_wizard_reset` | Operator surface, same engine, different audience |
| URL | `wizard_ai_recommend`, `wizard_step_draft_sync`, `wizard_search_api` | Wizard APIs |
| URL | `wizard_activation_dashboard`, `wizard_cockpit_preset_apply`, `wizard_cache_telemetry` | Operator activation/telemetry surfaces |
| URL | `zero_friction_payload`, `zero_friction_blockers`, `zero_friction_recommended` | Health score, launch blockers, recommended-next APIs |
| Celery | `prune_stale_resumable_wizards` | Clears abandoned resumable wizard state |
| Celery | `refresh_setup_recommendations_for_active_schools` | Refreshes AI setup recommendations |
| Command | `seed_operational_wizard_kernels`, `seed_studio_os` | Seeding |
| Module | `wizard_engine` | Registry, branching, validation orchestration. Public API is documented in its docstring. |
| Module | `wizard_state_resolver` | The `SetupProgress.step_state` wrapper — the only thing that should write wizard state |
| Module | `wizard_validators` | Pure, Django-free validators returning `(is_valid, error_token)` |
| Module | `wizard_ai` | The only AI-touching module in this app (5 public callables) |
| Module | `wizard_gates` | Permission + prerequisite gates; raises `GateBlockedError` |
| Module | `tenant_guard` | `assert_same_school` — cross-tenant setup mutations raise |
| Module | `legacy_view_bridge` | Redirects five migrated legacy wizard views to the engine |
| Module | `sovereignty_kernel` | Seeds jurisdiction/residency from `School.country_code` on an OSS stack (Caddy + Let's Encrypt) |
| Module | `migration_scope` | The canonical migration-domain list + presets, platform-wide for every tenant |

## Before you change this

- **`wizard_ai` is the only place in this app allowed to touch AI, and it must go
  through `services.ai_helpers`** — never `services.ai_gateway` directly. Two
  scanners enforce this at baseline 0: `scan_ai_gateway_boundary.py` platform-wide
  and `scan_wizard_ai_boundary.py` for this app specifically. Every AI helper
  sanitizes context against a sensitive-keyword list (password/token/ssn/email/
  guardian_name/…), runs on a 5-second budget, and **falls back to a
  deterministic rule on any failure**. A wizard must work with AI switched off.
- **Do not add a model to store wizard answers.** `step_state` is the store, and
  `wizard_state_resolver` is its only sanctioned writer. Writing `step_state`
  directly will clobber the `wizards` namespace — `zero_friction.merge_persisted_wizard_state`
  exists precisely because a launch-kernel write once had to be taught to
  preserve it.
- **Free text is capped even when a wizard declares no `max_length`.**
  `DEFAULT_MAX_TEXT_FIELD_LENGTH` (20k, env-tunable via
  `WIZARD_MAX_TEXT_FIELD_LENGTH`) is a backstop, not a default: `step_state` is a
  JSONField, so an unbounded string is a cheap storage-DoS that bloats every
  later read of the row. An explicit `max_length` in the wizard JSON always wins.
- **`wizard_validators` has no Django import and must keep it that way** — that
  is what makes the whole validation layer unit-testable without a database.
  Validators return `(is_valid, error_token)` and never raise, so the engine can
  build a per-field error map.
- **The registry is validated at import.** A new wizard JSON with a bad schema, a
  dotted resolver path that will not import, or a missing audience marker fails
  at module load — deliberately loud, deliberately early.
- **Cross-tenant setup mutations must raise, not filter.**
  `tenant_guard.assert_same_school` throws `SetupStudioTenantScopeError` on a
  mismatch, and writers only ever write to the school handed to them.
- **No hardcoded role strings.** Option lists carry tokens; `wizard_gates` keeps
  its canonical tenant-admin token set behind an explicit
  `role-string-allow` marker because the scanner would otherwise flag it.
- **Amounts are Decimal-only.** Resolvers return strings for money and validate
  through `validate_decimal_range`; there is no float money path here.
- **`legacy_view_bridge` keeps a rollback path on purpose.** Each migrated wizard
  can be disabled per-key via `RMC_WIZARD_ENGINE_OVERRIDES`, and `?legacy=1`
  always renders the legacy view regardless of override state. That escape hatch
  is intentional during a bake-in window — do not remove it while a legacy view
  still exists.
- **`migration_scope` is deliberately un-gated.** Every tenant — past, present,
  future — gets the same canonical domain list and presets from code, with no
  per-school SiteSettings gate. Adding a gate would fragment the Migration Cloud
  contract.
