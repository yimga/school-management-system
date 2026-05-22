# Cockpit AI flow (v3.58, 2026-05-22)

The Studio OS / control-plane co-pilot rail surfaces AI-powered insights and
suggested actions without ever choosing a backend client-side. The rail's job
is to **render whatever the server decided** — picking the backend is a
deployment-posture decision that lives on the server.

## Three backend tiers

The cockpit can be served by any of three tiers. They are mutually exclusive —
a given environment is in exactly one posture at any time.

| Posture | Where it runs | When picked | Pill copy | Pill color |
|---|---|---|---|---|
| `live_cloud` | LiteLLM gateway → OpenRouter / Anthropic / OpenAI | `RMC_DEPLOYMENT_PROFILE=online` AND `LITELLM_*` env present | "Live · cloud AI" | indigo |
| `live_local` | Ollama on the appliance | `RMC_DEPLOYMENT_PROFILE=edge` (offline appliance) | "Live · local AI" | emerald |
| `guided`     | Rules engine (`apps/studio_os/copilot_rail_service.py`) | Cloud unreachable + Ollama not configured | "Guided mode" | amber |
| `unavailable`| —                                                   | All three failed | "AI unavailable" | rose |

The picker lives in `services/ai_deployment_posture.py` (introduced in v3.52.14).
See `docs/AI_DEPLOYMENT_POSTURE.md` for the full deployment matrix.

## Data flow

```
[browser]                                    [Django app]                          [AI tier]
  rail mounted                                                                       
       │                                                                             
       │ GET /studio/copilot/rail/context/?mode=…                                    
       ├──────────────────────────────────────────► views_copilot_rail.RailContextView
       │                                                  │                          
       │                                                  ├ services/ai_helpers.invoke_with_request()
       │                                                  │      │                   
       │                                                  │      │ posture=live_cloud
       │                                                  │      ├──────────────────► LiteLLM → cloud LLM
       │                                                  │      │                   
       │                                                  │      │ posture=live_local
       │                                                  │      ├──────────────────► Ollama (http://localhost:11434)
       │                                                  │      │                   
       │                                                  │      │ posture=guided
       │                                                  │      └──────────────────► copilot_rail_service.rules_layer
       │                                                  │                          
       │ ◄────────────────────────────────────────────────┤ {snapshot, insights[], quick_actions[]}
       │                                                                             
       │  static/js/rmc-copilot-rail.js renders into the rail:                       
       │     - insights list (3 cards, source attributed)                            
       │     - posture pill flips color/copy                                         
       │     - quick-actions list                                                    
       │                                                                             
       │  static/js/_pages/rmc-copilot-rail.js handles UX:                           
       │     - expand/collapse via [data-rmc-copilot-toggle]                         
       │     - Cmd/Ctrl+K focuses the input                                          
       │     - the 3 collapsed icons route to tabs: chat / actions / threads         
       │     - suggestion click autofills the textarea                               
       │     - operator notebook drag + recent-10 + minimize                         
```

## Failure-mode contract

1. **Network failure on the rail context fetch**: the posture pill flips to
   `unavailable`. The server-rendered fallback (`cockpit.ai_copilot_rail`
   defaults from `apps/siteconfig/cockpit_manager_200x.py`) stays in place so
   the rail never strands a blank skeleton.

2. **Cloud reachable but LLM returns nothing**: server falls back to rules
   layer transparently; the response's `posture_mode` shifts to `guided` and
   the pill amber-pulses.

3. **Ollama offline appliance**: when the appliance loses internet AND Ollama
   itself is down, the rail enters `unavailable` until Ollama is restored.
   No data leaves the appliance.

4. **Operator-supplied data**: the notebook's recent-notes panel stays
   client-side in localStorage by design. A note only leaves the device when
   the operator hits Save and `cockpit.operator_notebook.save_url` is
   configured. Empty `save_url` → local-only.

## Privacy posture summary

| Surface | Hits LLM? | Persists where |
|---|---|---|
| Insight cards | ✓ (cloud or local) | server side per-operator |
| Quick actions | ✗ (rules) | none |
| Suggestion chips | ✗ (server-precomputed) | none |
| Chat input | ✓ (when sent) | server side per-operator |
| Operator notebook | ✗ by default | localStorage; server if save_url set |

## Where to extend

- **New insight source**: add a generator to
  `apps/studio_os/copilot_rail_service.py::generate_insights()` and tag each
  emitted insight with `source="cloud"|"local"|"rules"`. The rail renders the
  `source` badge automatically.
- **New quick action**: register in
  `apps/studio_os/action_registry.py` with the appropriate `surface`/`role`
  filters; the rail picks it up via the registry.
- **New rail tab**: add a `<button data-rmc-copilot-tab="…">` in
  `templates/partials/cockpit/_ai_copilot_rail.html` and a corresponding
  `data-rmc-copilot-pane` block. The CSS in
  `static/css/rmc-cp-200x.css` already routes via
  `[data-rmc-copilot-active-tab]`.
