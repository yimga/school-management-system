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
4. **Retire/relabel genuine orphans/stubs** found in the self-healing audit:
   `governance/turbo/agentic_self_healing_matrix.py` (0 prod callers, no AI) and the northstar
   self-heal dev tool — retire or relabel (like the `offline_conflict_kernel` retirement). Low risk,
   high honesty.

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
4. Retire/relabel the genuine orphans (agentic_self_healing_matrix, northstar) — honesty win.
5. Phases 2–3 (self-healing + fleet-health aggregation) — approval-gated per phase.
