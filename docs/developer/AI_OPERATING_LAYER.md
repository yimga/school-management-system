# AI operating layer (RunMyCampus)

Operational intelligence builds on the North Star assistant pattern: **drafts only**, **human approval** before any real action, **audit metadata** on assistant calls, **structured** recommendation objects for UI.

## Platform gates

| Control | Effect |
|--------|--------|
| `RUNMYCAMPUS_AI_ENABLED=1` | Allows LLM-backed drafts when tenant policy does not block. |
| `RUNMYCAMPUS_AI_ALLOW_EXTERNAL=1` | Permits non-local backends **only if** the tenant also opts in (see below). |

## Tenant policy (`School.settings["ai_policy"]`)

JSON on the school record, e.g.:

```json
{
  "tenant_ai_enabled": true,
  "allow_external_providers": false,
  "allow_external_student_pii": false
}
```

- **`tenant_ai_enabled: false`** — Disables AI for this tenant even when the platform env is on.
- **`allow_external_providers: true`** — Required (with `RUNMYCAMPUS_AI_ALLOW_EXTERNAL`) to use external/paid providers; default is local / rules first.
- **`allow_external_student_pii: true`** — Required to allow high-sensitivity student identifiers on external routes; default is **no** PII off-box.

## Use case keys (draft API `kind`)

| `kind` | Role |
|--------|------|
| `config_copilot` | CCC / settings — checklist from **key names** only (no values). |
| `report_comment` | Reports — short commentary from term/subject **cues**, not roster data. |
| `policy_assistant` | Policies — `context.excerpt` + optional `context.topic`. |
| `workflow_builder` | Automation — high-level steps, **no execution**. |
| `support_knowledge` | Support — topic-only internal hints. |
| `school_insights`, `next_actions`, `parent_message`, `report_summary` | Existing North Star flows. |

## Recommendations registry

`apps/platform_runtime/ai_recommendation_registry.py` lists generators such as `school_health`, `onboarding_next_action`, `workflow_hygiene`, `anomaly_risk`. All entries set **`approval_required: true`**.

## UI hooks

- **Governance banner** and **operational use case** buttons: `templates/siteconfig/partials/north_star_ai_assistant_strip.html` (`data-rmc-ai-governance-banner`, `data-rmc-ai-operational-actions`).
- **Dashboard / backend strip**: `templates/accounts/ai_system_layer_strip.html` includes **anomaly nudge** when `rmc_ai_anomaly_nudge` is present (from `ai_operating_layer_context`).
- **Context**: `apps.platform_runtime.context_processors.ai_operating_layer_context` exposes `rmc_ai_governance` and `rmc_ai_anomaly_nudge`.

## Code map

- `apps/platform_runtime/ai_governance.py` — tenant + env resolution.
- `apps/platform_runtime/ai_providers.py` — `get_ai_runtime_config`, `run_ai_prompt` (PII / backend flags).
- `apps/platform_runtime/ai_assistant_service.py` — draft helpers + audit logging.
- `apps/platform_runtime/ai_system_layer.py` — structured recommendations.
- `apps/platform_runtime/ai_workflow_bridge.py` — approval handoff payload (no side effects).
