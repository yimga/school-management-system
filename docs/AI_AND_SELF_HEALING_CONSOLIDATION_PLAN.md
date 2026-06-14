# AI & Self-Healing Consolidation Plan

Date: 2026-06-10
Status: plan (the hub destination is built + landed on main; the relocations below are scoped, not yet executed)
Owner ask: "consolidate everything related to AI so things are not all over the place on our
dashboards — do the same for everything else."

---

## 0. What already exists (do not rebuild)

- **Destination hub:** `apps/platform_runtime/views_health_autopilot.py` →
  `templates/platform_runtime/health_autopilot_console.html`, staff route `self-healing/`
  (`platform_runtime:health_autopilot_console`). It already renders the **canonical generative-AI
  surface inventory** (`ai_providers.describe_ai_assistant_surfaces()`) + the self-healing engine
  (live shadow proposals, policies, catalog, remediation log). Cross-linked from the platform-health
  console. **Landed on origin/main** (commit `d009e5a0`, in the history of `e0a1f693d`).
- **Canonical AI inventory SOT:** `apps/platform_runtime/ai_providers.py::describe_ai_assistant_surfaces()`
  — 8 generative surfaces, all gated through `run_ai_prompt` → `invoke_service_layer_ai`.

The hub IS the consolidation destination. The work below is **relocation/labelling**, not new systems.

---

## 1. AI surface inventory (ground truth from the audit)

| Surface | Module | Real generative AI? | Wired | Notes |
|---|---|---|---|---|
| AI gateway facade | `services/ai_helpers.invoke_with_request` | yes (Ollama→LiteLLM→rules) | yes | the spine |
| Provider facade (platform_runtime) | `apps/platform_runtime/ai_providers.run_ai_prompt` | yes | yes | allowlisted; off by default |
| Assist dock actions | `apps/assist_dock/ai_actions.py` | yes | yes | page copilot |
| Studio OS rail insights | `apps/studio_os/copilot_rail_service.py` | yes (rules fallback) | yes | |
| Migration AI bridge | `apps/migration_cloud/ai_bridge.py` | yes (per-school, off by default) | yes | classify-with-fallback |
| System-level suggestions | `apps/platform_runtime/ai_system_layer.py` | yes (optional LLM) | yes | no auto-action |
| **Health autopilot AI classifier** | `apps/platform_runtime/health_autopilot.py` | yes (classify-onto-catalog only) | dormant | NEW this wave |
| Manager copilot rail feed | `apps/observability/ai_copilot_service.py` | **NO — rules/DB metrics** | yes (cockpit_context) | role-named ("feeds the rail"); reports gateway reachability |
| Policy "copilot" | `apps/governance/turbo/ai_policy_copilot.py` | **NO — regex over matrix** | yes (governance view) | **already self-documents** it makes no LLM call |

### Stub assessment (important)
The two modules flagged "dishonest AI" in the one-line audit are **less dishonest than implied**:
- `ai_policy_copilot.py` — its own docstring says *"no LLM call is needed because the matrix already
  encodes the answers… says so honestly instead of hallucinating."* Only the module **name** says "ai".
- `ai_copilot_service.py` — a **role-named metrics feed** that populates the operator copilot *rail*
  from DB counts and reports whether the real gateway is reachable. It does not claim inference.

**Recommendation: do NOT rename these modules.** A rename touches `cockpit_context`, governance
views/urls, two test files, `__all__`, and risks the `verify_ai_copilot_rbac_coverage` gate — high
regression surface for marginal honesty gain, especially with a live peer in the tree. Instead:
- **(done)** the hub now honestly states these are rules-based, not generative AI.
- **(optional, low-risk)** add a one-line docstring note to each module clarifying the name is
  historical/role-based, not an inference claim. No code/caller changes.

---

## 2. Nav entry for the hub (make it findable)

Operator **consoles** (e.g. `platform-health`) are surfaced via the **operator tools edge-tray**, not
the main sidebar (`apps/schools/control_plane_nav.py`). So the hub's nav entry belongs in the tray:

- File: `templates/partials/rmc_operator_tools_page_data.html` — the `"operator"` group array
  (currently `["platform-health", "open-incidents", "security-posture", …]`). Add an `"intelligence"`
  (or `"self-healing"`) chip id, and define its url/label the same way `platform-health` is defined.
- Resolve the chip URL to `platform_runtime:health_autopilot_console` (server-side `{% url %}`), and
  gate it on staff like the other operator chips.
- Verify with `scripts/verify_nav_resolves_to_named_route.py` and the render-safety scanner before/after.

Risk: the tray + `rmc-operator-tools-tray.js` chip-url resolution must be matched exactly (the chip
"Messages dead button" incident shows the tray has handler-vs-url-fallback subtleties). Do this as a
**dedicated small commit** with a browser smoke of the tray, not bundled.

Alternative (lighter): the hub is **already cross-linked** from the platform-health console — that is a
working discovery path today; the tray chip is the polish.

---

## 3. "Everything else" — consolidation candidates (phased, approval-gated)

Each is a relocation INTO a hub, not a rewrite. Order by value/risk:

1. **AI dashboards → Intelligence hub.** The generative surfaces (assist dock, studio rail, migration
   AI, system suggestions) already share `ai_providers`/`ai_helpers`; consolidation = surface their
   *status + entry links* in the hub's AI section (read-only), NOT moving their UIs. Low risk.
2. **Self-healing/remediation → hub.** `platform_health`, `workflow_autopilot`, `circuit_breaker`,
   `events/remediation_ops` status surfaced in one operator console. Medium (read-only aggregation).
3. **Health/observability widgets → one operator health surface.** `customer_health`,
   `tenant_operational_health`, `installation_health`, `registry_health` are scattered detection
   widgets; a single operator "Fleet Health" surface (the tenant-health API already exists). Medium.
4. **Relabel (do NOT retire) the misleadingly-named modules.** Correction after closer
   inspection — these are NOT dead code, so unlike the `offline_conflict_kernel` retirement they
   must NOT be deleted:
   - `governance/turbo/agentic_self_healing_matrix.py` is `TURBO_CONTRACTS[0]` in
     `apps/governance/turbo/__init__.py` (1 of 15 phase-6 contract deliverables) **and has a
     dedicated CI gate** (`scripts/verify_matrix_freshness.py` points `CONTRACT_MODULE` at it).
     Deleting it would break that gate + the contract registry. It is tracked scaffolding (a JSON
     approval queue, no AI yet), not an orphan. Honest action: a docstring note that "agentic" is
     aspirational/not-yet-AI-backed — no deletion, no caller changes.
   - `scripts/northstar_self_heal*` is read by the founder dashboard (`super_views_founder_dashboard`)
     — also not an orphan. Leave as honest dev/CI tooling.
   The only genuinely-retired self-healing orphan was `offline_conflict_kernel` (done 2026-06-10,
   separate wave). There are no further safe deletions in this cluster.

**Method for each phase:** inventory the scattered surfaces → build/extend the single hub section
(read-only links + status first) → only then consider physically moving widgets → run the nav,
render-safety, undefined-css gates → commit per phase, peer-isolated.

**Explicitly out of scope without sign-off:** a platform-wide template sweep that relocates every
widget across 40+ dashboard templates in one pass. That is the high-risk "do everything" interpretation
the codebase's own rules say to scope before sweeping.

---

## 4. Sequencing recommendation

1. ✅ Hub built + AI inventory consolidated + honest generative-vs-rules labelling (landed/this wave).
2. Tray nav chip for the hub (dedicated small commit + browser smoke).
3. Phase 1 above (AI status/links in hub) — read-only, low risk.
4. Relabel (never retire) the misleadingly-named modules — see §3.4 — honesty win.
5. Phases 2–3 (self-healing + fleet-health aggregation) — approval-gated per phase.

---

## 5. Per-dashboard AI surface inventory (verified 2026-06-10)

Every AI-related surface, where it renders, its route, whether it actually calls a model, and a
per-surface recommendation. Templates/routes below were confirmed present in the tree; a few
specifics flagged "(unverified)" still need a manual look. **No code changes were made for this
inventory — it is the approval-gate input for any relocation.**

| # | Surface | Module | Renders on (template / dashboard) | Route | Type | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Manager copilot rail | `observability/ai_copilot_service.py` | `partials/cockpit/_ai_copilot_rail.html` (manager control-plane, via `cockpit_context`) | ambient (manager) | **RULES** (ticket / AI-review / KB-gap counts; no model) | **RELABEL-ONLY** — name says "AI copilot" but it's a metrics feed. Clarify label/docstring; do NOT move. No model call to consolidate. |
| 2 | Studio OS copilot rail | `studio_os/copilot_rail_service.py` + `views_copilot_rail.py` | `studio_os/partials/cockpit_copilot_rail.html` (studio_os + tenant) | `studio_os:copilot_rail_{context,insights,send,send_stream}` | **GENERATIVE** (`invoke_with_request`, rules fallback) | **KEEP / LINK-INTO-HUB** — primary unified generative assistant. Hub *links* to it, doesn't absorb it. Low risk. |
| 3 | Assist dock AI actions | `assist_dock/ai_actions.py` | assist dock panel (client-rendered) | `assist_dock:ai_actions`, `assist_dock:ai_invoke` | **GENERATIVE** (summarize/explain/draft/translate) | **LEAVE — ambient.** Page-aware, belongs everywhere. Registry-decoupled. |
| 4 | School health insight | `platform_runtime/ai_system_layer.py` | `accounts/ai_system_layer_strip.html` (tenant `backend_dashboard`) | ambient (dashboard ctx) | **GENERATIVE** (rules fallback) | **RELOCATION CANDIDATE** (moderate blast radius) — could move to a tenant intelligence section. Approval-gated. |
| 5 | Onboarding next action | `platform_runtime/ai_system_layer.py` | `accounts/ai_system_layer_strip.html` | ambient (dashboard ctx) | **GENERATIVE** (rules fallback) | **RELOCATION CANDIDATE** — same strip as #4; move together or leave. |
| 6 | Anomaly risk nudge | `platform_runtime/ai_system_layer.py` (via `platform_runtime/context_processors.py`) | `accounts/ai_system_layer_strip.html` | ambient (ctx processor) | **GENERATIVE** | **LINK-INTO-HUB** — candidate to flow through the self-healing hub instead of every dashboard. Low risk. |
| 7 | Migration AI bridge | `migration_cloud/ai_bridge.py` | internal (intake classification) — not a standalone widget | internal API | **GENERATIVE** (per-school, off by default) | **LEAVE — internal pipeline**, not a dashboard widget. |
| 8 | Policy "copilot" | `governance/turbo/ai_policy_copilot.py` | governance policy page (sidecar/modal) (template unverified) | governance view (route name unverified) | **RULES** (regex over matrix; self-documents "no LLM") | **RELABEL-ONLY** — rename UI label to "Policy matrix lookup". CI-gated contract (§3.4) — never delete. |
| 9 | Portal AI gateway (legacy) | `portal/ai_provider.py` + `portal/views_ai_stream.py` + `ai_chrome_config.py` | portal floating copilot | `portal:ai_stream` (+ `ai_line_intents`) | **GENERATIVE** | **DEPRECATE-CANDIDATE** — reportedly superseded by the studio rail (#2). Verify parity + grep hardcoded URL refs BEFORE any removal. Approval-gated. |
| 10 | Intelligence & Self-Healing hub | `platform_runtime/views_health_autopilot.py` | `platform_runtime/health_autopilot_console.html` | `platform_runtime:health_autopilot_console` (`self-healing/`) | **FACADE** (reads `describe_ai_assistant_surfaces`; no inference) | **THE HUB / EXPAND** — already the authoritative operator AI map. Phase-1 work lands here. |
| 11 | Risk digest narrator | `analytics/management/commands/ai_narrate_risk_digest.py` | background (digest emails) | mgmt command | **GENERATIVE** (async) | **LEAVE** — not a dashboard widget. |

Flagged for manual confirmation: portal `ai_help` / `ai_assistant_panel` permission gates (separate visible widget?); `brand_experience/template_ai_recommender.py` (internal vs visible?); an API WebSocket AI chat consumer (UI render location not found in Python).

### Recommended ordered execution (each its own commit, approval-gated)
1. ✅ **DONE (2026-06-10, commit `690b12039`) — Relabel-only (zero behavior change):** #1 manager rail
   insight-feed module (`ai_copilot_service.py` docstring: stated plainly it is a rules-based metrics
   feed, not inference; the rail's generative chat is studio_os) + #8 policy lookup (`ai_governance_body.html`:
   "Policy copilot" → "Policy matrix lookup", copy clarifies no model call). No behavior change.
2. ✅ **DONE (2026-06-10, commit `b2716acee`) — Link-into-hub (read-only, hub-only):** added a
   "Where to find generative AI" launcher to the self-healing hub linking #2 studio rail
   (`studio_os:shell`) + AI governance page (`siteconfig:ai_governance`), with #3 assist-dock and
   #9 portal gateway listed as ambient (no standalone page). Routes reversed defensively
   (`_safe_reverse`); ambient surfaces never get a fabricated link. 26/26 tests, gates 0, no SW bump.
3. ✅ **DONE (2026-06-10, commit `3ee11281b`) — Anomaly nudge (#6) in hub (ADDITIVE, reframed):** the
   original "remove the nudge from every dashboard" framing was a UX regression (an anomaly *risk*
   nudge earns its place by being proactive), so instead the hub now shows a **read-only cross-tenant
   view** of `ai_system_layer.generate_anomaly_risk_nudge` while the ambient per-dashboard nudge stays.
   Bounded by `_MAX_NUDGE_SCHOOLS=12` so it never fans out into unbounded model calls when AI is on
   (healthy tenants short-circuit before any model call); cap disclosed in the UI. Hub-only.
4. ✅ **DONE (2026-06-10, commit `f2ac4f1de`) — premise corrected + canonical call made & implemented:**
   The literal task ("relocate the two dashboard-strip insights #4 + #5 into one tenant intelligence section")
   is **ALREADY DONE**: `templates/accounts/ai_system_layer_strip.html` already merges #4 (school health),
   #5 (onboarding next action) AND #6 (anomaly nudge) into ONE `<section>` ("Intelligence suggestions
   (draft)"), it is included **exactly once** (`backend_dashboard.html:195`), and both are wired
   (`accounts/views.py:2773` health, `:2776` onboarding; nudge via `context_processors.py:142`). The
   heading is already honest ("Rules-based when AI is disabled; approve before acting") — renaming it would
   *reduce* precision, so it was left alone.
   **The REAL scatter** (different from the menu's premise) is that the AI strip **duplicates richer
   non-AI widgets on the same page**: onboarding renders in ~4 places in `section-readiness`
   (`first_login_checklist_card` ln190, `school_onboarding_card` ln194, AI strip #5 ln195,
   `backend_command_center_setup_strip` ln196) + the "Finish setup essentials" attention card (ln179);
   anomalies in 3 (attention cards ln153-187, `insight-anomalies` widget ln269-307, AI strip #6); health
   in 3 (`admin_health` ln73, `operational_health_strip` ln79, AI strip #4). De-duplicating that means
   **deleting/merging widgets** + a **product decision** on which surface is canonical (and whether the
   genuinely-AI strip is the one to keep or drop), on a page that **cannot be browser-verified locally**
   (tenant `backend_dashboard` 500s on this box from migration-DB lag).
   **CANONICAL CALL (owner-delegated) + IMPLEMENTED:** health stays canonical in `operational_health_strip`,
   anomalies in the `insight-anomalies` widget, onboarding in `school_onboarding_card`. The AI strip is
   **KEPT as the single AI home but now renders only when the school's AI assistant is enabled**
   (`rmc_ai_layer_enabled` from `ai_operating_layer_context` → `get_ai_runtime_config(school).enabled`);
   in rules-only mode its rows just restate the richer widgets, so it's hidden then (AI-off tenants — the
   default — lose nothing). Heading → "AI suggestions (draft)" + honest subtitle. Single include site,
   `manage.py check` clean, render-safety 0, if/endif balanced, trivially reversible. **STILL NEEDS
   post-deploy browser smoke** on the tenant dashboard. *(superseded line below was the pre-decision note.)*
   Deferred pending owner sign-off on
   the canonical-surface decision + a commitment to post-deploy browser smoke. NOT safe to do blind.
5. **Portal legacy gateway (#9) deprecation:** only after confirming studio-rail parity; grep-audit URL refs first. Highest risk; separate sign-off.

Items 1–3 are landed on local main (commits above). Item 4 was investigated and found **already satisfied
as literally specified** (no churn manufactured); its real follow-on (dashboard de-duplication) is a
product decision + browser-verification job, not a code task I can do blind. Item 5 needs studio-rail
parity confirmation + URL-ref grep audit first.
