# apps/studio_os

> The unified Studio workspace — one shell over five modes (Experience,
> Automation, Output, Launch, Control) plus the canvas-first Experience builder
> and its proof-before-publish gate.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 1 model · 4 migrations · 48 test modules · ~14.5k LOC

## What this app owns

Studio OS is the workbench a school administrator uses to configure their campus.
It owns the **shell**, not the settings: the five-mode navigation, the embed and
preview contract, the co-pilot rail, deep links, and the command surfaces. The
actual configuration lives where it always lived — `siteconfig` owns the theme
form, `automation` owns workflows, `marketplace` owns packs. Studio's job is to
present all of it as one workspace, which is why an app of ~14.5k LOC and 48 test
modules declares exactly one model.

Two decisions define the app.

**One preview path.** `services.STUDIO_MODE_EMBED_TARGETS` maps each mode to a
single `(reverse_name, query_param)` pair, and `get_studio_preview_url()` is the
only sanctioned way to build an embed URL. Ad-hoc embed URLs are how preview
behavior drifts per surface. `embed_render` renders body-only documents (tokens +
bootstrap + one body partial, no portal or control-plane chrome) for in-canvas
frames.

**Never invent surface.** The rule runs through the whole app. The canvas-first
Experience builder anchors every editable inspector row to a real form widget
already rendered in the canvas (`#id_<field>`), and every field a region declares
must be a member of `siteconfig.forms.THEME_EXPERIENCE_FIELD_NAMES` — the
publish-guarded theme source of truth, enforced by `validate_region_catalog` and
tests. Softer product-derived rows render read-only, never as fake-editable
inputs. `copilot_rail_service` pulls quick actions from the universal command-bar
registry as pure passthrough and never fabricates a URL. `school_infrastructure`
exposes preview, validation, and honest capability flags while apply/rollback
stays platform-governed.

The one model exists because of the third surface: the `#rollout`
proof-before-publish gate needed a durable, auditable record of who approved
which region against which draft — something a session store cannot provide.

## Key models

The app declares exactly 1 model. Studio OS was deliberately model-less (views +
services only) until the rollout gate forced the exception.

| Model | Table | Purpose |
| --- | --- | --- |
| `ExperienceRegionApproval` | `studio_os_experienceregionapproval` | One row per `(school, region_key)`. Records who approved an Experience region and pins it to `draft_fingerprint` — a sha256[:16] over the region's live theme values — so the approval self-invalidates once the draft drifts. |

## Surfaces

49 named URL routes, all under the `studio_os` namespace, grouped by mode:

| Group | Representative names |
| --- | --- |
| Experience | `experience`, `experience_dashboard_visual_packs`, `experience_theme_tokens`, `experience_portal_shell_layouts`, `experience_packs`, `experience_compare`, `experience_recommendations`, `experience_approve_region` |
| Automation | `automation_visual_builder`, `automation_natural_language_workflow`, `automation_simulation_engine`, `automation_dependency_graph`, `automation_conflict_detection`, `automation_staged_activation`, `automation_replay_rollback`, `automation_workflow_health` |
| Control | `control`, `control_impact`, `audit`, `ai_cleanup`, `approval_hub` |
| Co-pilot | `copilot_rail_context`, `copilot_rail_insights`, `copilot_rail_send`, `copilot_rail_send_stream` |
| Shell | `global_search`, `import_hub` |

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | Preview/publish/rollback/activity; `STUDIO_MODE_EMBED_TARGETS` is the embed-URL source of truth |
| Module | `experience_regions` | The six-region catalog + scoped inspector model; pure data, no Django import at load |
| Module | `experience_rollout` | Fingerprint + approval gate; `compute_region_fingerprint` |
| Module | `deep_links` | Resolves links across tenant/manager hosts where a namespace exists on only one |
| Module | `embed_render` | Body-only renders for in-canvas frames |
| Module | `navigation` | Control governance rail + manager focus sidebar |
| Module | `copilot_rail_service` | Context snapshot, insights pulse, quick actions |
| Module | `copilot_registry_insights` | Operator-only bridge to the feature-gap + backlog registries |
| Module | `school_infrastructure` | Blueprint registry + pack catalog read from disk |
| Module | `studio_guidance` | In-context Q&A content for the shell |

This app ships **no Celery tasks and no management commands**. (`seed_studio_os`
lives in `apps/setup_studio`.)

## Before you change this

- **`studio_os` is in TENANT_APPS and its RLS is asserted by its own migrations
  0003 + 0004 — for a specific reason.** Migration 0002 already enabled RLS and
  created the tenant policy, but under a non-convention filename.
  `scan_rls_force_coverage` looks for `*_enable_rls_postgresql` +
  `*_rls_policy_default_deny`, so it could not see studio_os as covered and
  baselined the table; worse, the catch-all `schools.0048_force_rls_on_all_enabled_tables`
  depends only on each app's `*_rls_policy_default_deny` migration, so with
  studio_os absent from its dependency list 0048 could run **before** this table
  was enabled and leave it un-FORCEd. Without FORCE, the table owner — the role
  Django runs as — bypasses the policy entirely. 0003 re-asserts ENABLE and adds
  FORCE explicitly on studio_os's own graph; 0004 re-asserts the identical
  default-deny policy under the convention name. Both are idempotent. **Do not
  rename or collapse them** — the convention filename is the interface.
- **Approvals go stale by design.** `draft_fingerprint` pins an approval to the
  exact theme values it was granted against. Any drift invalidates it and it can
  no longer satisfy the publish gate. That is the feature.
- **The rollout gate defaults to advisory and fails open.**
  `STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT` is `advisory` unless set to `enforce`,
  and any internal error fails open. Publish must never wedge on the gate's own
  bug. Approvals fall back to a session store when no tenant school is in context
  (operator preview) or a DB write errors — an approval is never silently lost.
- **Every region field must exist in `THEME_EXPERIENCE_FIELD_NAMES`.** This is
  the invariant `validate_region_catalog` and its tests enforce. The builder must
  not create a parallel write path around the publish-guarded theme form.
- **`experience_regions` deliberately imports no Django at module load.** The
  field allowlist is validated lazily so importing the catalog is side-effect-free
  and safe to reference at URL/registry scan time. Keep it plain data + pure
  helpers.
- **Build embed URLs through `get_studio_preview_url(mode)`.** That is the point
  of `STUDIO_MODE_EMBED_TARGETS`.
- **Cross-host links are not `reverse()`.** Namespaces exist on only one host
  (tenant vs. manager), so `deep_links` resolves path suffixes against
  `STUDIO_APPROVAL_HUB_TENANT_BASE_URL` / `MANAGER_PLATFORM_BASE_URL`.
  `navigation` also drops `super:` / `admin:` rail items unless
  `request.public_host_kind == "manager"`. A plain `reverse()` on a cross-host
  name raises `NoReverseMatch` and 500s the page.
- **`copilot_rail_service` never logs a raw tenant slug** — only the sha256[:8]
  prefix — and routes AI through `services.ai_helpers`, never `services.ai_gateway`.
  When the gateway returns `None` it falls back to deterministic rules insights so
  the panel never goes blank; each insight carries a `source` tag for provenance.
- **`copilot_registry_insights` is cheap by construction and must stay that way.**
  It counts `FeatureRow.status` without per-row proof resolution, reads only the
  **cached** backlog snapshot (it never runs gate scripts or pytest in a request —
  no cache means no backlog item, rather than a slow eval), returns `[]` for
  non-staff, and never raises.
- **`school_infrastructure` reads pack manifests from disk to avoid importing
  `apps.marketplace`** — that is tenant-safe discovery, not a convenience.
