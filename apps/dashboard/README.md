# apps/dashboard

> The decision-surface layer: what each role sees first, which action it is
> pushed toward, and the registries that keep every dashboard in the platform
> honest about being one.

**Tenancy:** SHARED (public schema; this app stores nothing, so tenancy is a
routing fact, not a storage one)
**Scale:** 0 models · 0 migrations · 13 test modules · ~6.8k LOC

## What this app owns

Dashboard owns *decisions about dashboards*, not dashboards themselves. No view
here renders a page and no model here stores a row. It is a library of pure
builders and canonical registries that the real surfaces — the backend
dashboard, the control plane, the portal role landings — import to answer four
questions consistently: which home configuration applies to this role, which
KPIs belong in its strip, which single action is primary, and what a
brand-new tenant with no data should be told instead.

The defining design decision is that **the registries are the source of truth
and CI enforces them**. `phase7_dashboard_templates.PHASE7_DASHBOARD_TEMPLATES`
is a literal tuple naming every full-page dashboard template on the platform;
`phase8_declarations.PHASE8_DECLARATIONS` must be keyed identically to it (tests
enforce the match), and every template extending `control_plane_base.html` must
either appear in the Phase 7 tuple or be explicitly listed in
`control_plane_hub_scan.EXEMPT_CONTROL_PLANE_TEMPLATES`. That closure is what
makes a "dashboard" a declared thing with a stated job-to-be-done, a main
question, and a primary action — rather than whatever a developer happened to
put on a page. `dashboard_density_check` adds the clutter contract on top: a
template above the card threshold must fold its secondary density behind
`<details class="de-secondary-collapsible">`.

The second decision is a **pure-core / request-aware-shell split**, and it is
why this app is so testable for its size. `zero_state_for_role` is a pure
`role -> payload | None` function; `build_first_run_zero_state` is the
request-aware wrapper that gates and resolves URLs around it. The same shape
recurs across `role_home_engine`, `north_star_guidance`, and
`decision_surface_context`.

## Key models

**None — this app declares no Django models and ships no migrations.** That is
deliberate. Everything here is a pure builder or a canonical registry over
templates and roles; the state these surfaces read belongs to the apps that own
it. In particular, if you are looking for where a dashboard preference or a
completed first-run tour is persisted, it is `DashboardUserPreference` in
`apps/siteconfig/models_dashboard.py` — not here.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `role_home_engine` | SOT for role-native home config: destinations, next-best actions, KPI selection |
| Module | `action_registry` | SOT for primary / chip / grid / quick-link / command-palette actions per dashboard — prevents duplicate CTAs |
| Module | `phase7_dashboard_templates` | The canonical tuple of full-page dashboard templates |
| Module | `phase8_declarations` | One structured declaration (type, JTBD, main question, main action) per Phase 7 template |
| Module | `control_plane_hub_scan` | Registry-closure scan over templates extending `control_plane_base.html` |
| Module | `dashboard_density_check` | Phase 8 clutter contract (card-count threshold + collapsible marker) |
| Module | `first_run_zero_state` | Per-role "here's your next step" card for a not-yet-launched tenant |
| Module | `north_star_guidance`, `recommendation_service` | Role-native recommended next steps |
| Module | `decision_surface_context` | Maps role-home data onto `decision_engine_surface.html` |
| Module | `admin_context` | Shared context builder for the Unfold admin dashboard |
| Context processors | `first_run_zero_state`, `first_run_tour` | Globally wired; return `{}` on every non-applicable request |

No URLs (`no urls.py`), no Celery tasks, no management commands. External
verifiers consume this app's registries:
`scripts/verify_control_plane_hub_registry_drift.py` and
`scripts/verify_phase7_dashboard_markers.py` both import from it.

## Before you change this

- **The app label is `rms_dashboard`, not `dashboard`.** `apps.py` sets it
  explicitly. Any `get_model("dashboard", ...)`, `ContentType` lookup, or
  cross-app reference using the directory name will fail at runtime — and
  `verify_get_model_integrity` only catches the literal call shapes. The
  directory is `apps/dashboard/`; the registry key is `rms_dashboard`.
- **`PHASE7_DASHBOARD_TEMPLATES` and `PHASE8_DECLARATIONS` must stay key-aligned.**
  Tests assert it. Adding a full-page dashboard means adding it to the Phase 7
  tuple *and* writing its Phase 8 declaration — or the density and marker gates
  go red. A new control-plane template that is neither registered nor exempt
  fails `verify_control_plane_hub_registry_drift`.
- **The context processors run on every single request.** They are written so the
  non-applicable path costs a couple of `getattr`s and returns `{}`. Do not add
  a DB query to the ungated path — this is platform-wide hot code.
- **Everything first-run is fail-soft on purpose.** Any error inside
  `build_first_run_zero_state` yields `None`, so a populated tenant or a
  transient failure never shows a stale "get started" card to a school that has
  been running for a year. Do not "improve" that by letting the exception
  propagate; a wrong welcome card is worse than no card.
- **Use `_safe_reverse`, not bare `reverse`.** `recommendation_service` wraps
  reverse in `NoReverseMatch` handling with a `"#"` fallback, because these
  builders run across host-split urlconfs where a name valid on one host does
  not resolve on another. A bare `reverse` here is a 500 waiting for the wrong
  host.
- **Keep the pure core pure.** The builders' whole value is that they are
  unit-testable with no request and no DB — which is what 13 test modules over a
  model-less app buys. If a builder needs request state, add a thin request-aware
  wrapper beside it (the `zero_state_for_role` / `build_first_run_zero_state`
  pattern) rather than threading `request` into the pure function.
- `dashboard_density_check`'s card threshold is **empirically tuned**, not
  arbitrary — parent/teacher surfaces sit just below it and control-plane
  billing/backend sit above. Moving it re-classifies real pages.
