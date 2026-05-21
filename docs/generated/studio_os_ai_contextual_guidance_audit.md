# Studio OS — AI / Contextual Guidance Audit (v3.54.0)

**Generated:** 2026-05-21. AI surfaces in Studio OS as they stand after v3.54.0.

## AI gateway invariants (preserved)

- **All calls route through** `services.ai_helpers` (`scan_ai_gateway_boundary` baseline 0 — preserved).
- **Preserve list untouched** by v3.54.0:
  - `ai/Modelfile`
  - `services/ai_gateway.py`
  - `services/ai_helpers.py`
  - `apps/apicenter/`
  - `apps/schools/super_views_create_school_wizard.py`
- **Tenant PII safety:** school slug → `sha256[:8]` in all logs/payloads/prompts (per batch 1372 R2).
- **Deployment posture:** Cloud-first via LiteLLM on Render; Ollama for offline schools (batch 1370).

## Studio OS AI surfaces

### Studio guidance panel

- **Partial:** [`templates/studio_os/partials/studio_guidance_panel.html`](../../templates/studio_os/partials/studio_guidance_panel.html)
- **Service:** [`apps/studio_os/studio_guidance.py`](../../apps/studio_os/studio_guidance.py)
- **v3.54.0 changes:** upgraded with primary/secondary/preview action structure + blocker pill when guidance returns a blocker. Renders on Overview (when `not current_mode`) AND per-mode bodies (Experience body includes it explicitly).
- **Tenant-safe** + **operator-safe**.

### Persistent co-pilot rail

- **Service:** [`apps/studio_os/copilot_rail_service.py`](../../apps/studio_os/copilot_rail_service.py) (v3.53.1)
- **View:** [`apps/studio_os/views_copilot_rail.py`](../../apps/studio_os/views_copilot_rail.py)
- **Endpoints:** `studio_os:copilot_rail_context` · `studio_os:copilot_rail_insights`
- **JS:** [`static/js/rmc-copilot-rail.js`](../../static/js/rmc-copilot-rail.js) (90s rotation, armed-attribute compliant)
- **v3.54.0 changes:** light edits — host-kind badge + preview microlist
- **Tenant PII safety:** cross-tenant leak rejection in cloud responses (`test_cross_tenant_leak_in_cloud_response_falls_back`); slug hashed
- **Cloud-first** via `services.ai_helpers.invoke_with_request`
- **Fallback chain:** cloud → rules layer → view exception caught (3-tier graceful)

### Command palette

- **Trigger:** `Ctrl+K` (`cmd+k` on macOS)
- **Shell button:** [`shell.html:41`](../../templates/studio_os/shell.html#L41) — `id="studio-command-palette-btn"`
- **Palette div:** [`shell.html:282-289`](../../templates/studio_os/shell.html#L282-L289) — `id="studio-cmd-palette"` with `role="dialog" aria-modal="true" aria-describedby`
- **Registry:** [`apps/siteconfig/command_bar_registry.py`](../../apps/siteconfig/command_bar_registry.py) (v3.53.0, 246 lines, 33 actions, role + tenant scoped, no cross-tenant URL leakage)
- **v3.54.0 changes:** none — preserved as-is.
- **Scope:** filtered per `request.user` role + tenant via registry.

### AI guided assistant card

- **Include:** `{% include "components/ai_guided_assistant_card.html" with assistant_key="studio_os_assistant" ... %}`
- **Shell line:** [`shell.html:55`](../../templates/studio_os/shell.html#L55)
- **Card title (translatable):** "Studio guided assistant"
- **Card hint (translatable):** "Suggests next steps across Studio modes. Apply packages and automations only through existing preview and rollback flows."
- **v3.54.0 changes:** none.

## Examples meeting the bar

- **Bad:** *"Review your automation settings."*
- **Good:** *"This automation cannot be launched because no trigger is active. Go to Studio OS → Automation → Trigger Map and enable one trigger before launch."*
- **Actual v3.54.0 compliance:** `studio_guidance_panel` + per-section preview panes follow the GOOD pattern — they reference concrete next routes (e.g. "Open Theme & colors", "Open Workflow center") AND show the blocker (e.g. "Simulation engine coming online") rather than generic "review your settings."

## DATA DEFAULTER and FEATURE CODESPACE DISCONNECT states

Honest empty states per section:

| Section | Honest empty state |
|---|---|
| Overview | `cockpit_signal_strip` renders `data-state="unknown"` when `overview_signals` value is `None` |
| Experience | Live preview pane renders "Preview unavailable — select a tenant context" when role-preview entries absent |
| Automation | Simulation pane renders "Simulation engine coming online" when no payload |
| Output | Readiness pane renders "Readiness service offline" when service unreachable |
| Launch | Readiness pane renders "Checklist coming online" when timeline/approvals empty |
| Control | Governance pane renders "No governance change staged" when no staged change |
| Studio guidance | Returns honest "No actions queued" when no recommendation |

## What is blocked (v3.55+)

- Live cockpit AI personalization (cloud-first gateway wired; per-section AI guidance hooks deferred)
- Real-time multi-operator collaboration
- Full Render-deployed AI Center posture sweep (operator action)
- Tone-aware AI recommendation prompts for cockpit signal tiles (E1 from v3.52+ exists; not yet wired to `overview_signals`)
