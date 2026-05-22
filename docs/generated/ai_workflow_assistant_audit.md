# AI Workflow Assistant Audit (Phase 8)

_Generated 2026-05-22T17:30:51Z_

Code-truth audit of every AI-touching surface in the platform: which apps route through services.ai_helpers (canonical), which have allowlisted direct gateway access, where the rules-based copilot rail lives, and the gap list for route-aware / evidence-citing / tenant-safe AI guidance.

## Summary

- **apps_importing_services_ai_helpers**: `13`
- **files_importing_services_ai_helpers**: `22`
- **allowlisted_direct_gateway_callers**: `5`
- **direct_gateway_boundary_violations_outside_allowlist**: `20`
- **copilot_rail_service_present**: `True`
- **ai_workflow_bridge_present_at_platform_runtime**: `True`
- **workflow_registry_workflows_with_ai_context_key**: `2`
- **workflow_registry_workflows_total**: `16`

## AI surfaces inventory

### Apps routing through canonical `services.ai_helpers` (22 files)

- `apps/analytics/management/commands/ai_narrate_risk_digest.py`
- `apps/analytics/tests/test_ai_surfaces.py`
- `apps/analytics/tests/test_wave9_language_pgvector.py`
- `apps/api/consumers.py`
- `apps/api/learning_institution_api.py`
- `apps/automation/ai_workflow_suggest.py`
- `apps/communication/narrative_feedback.py`
- `apps/dashboard/services/insight_anomalies.py`
- `apps/finance/ai_categorize.py`
- `apps/migration_cloud/tests/test_ai_helpers.py`
- `apps/observability/ai_copilot_service.py`
- `apps/observability/management/commands/digest_friction.py`
- `apps/people/ai_dedup.py`
- `apps/platform_runtime/workflow_registry.py`
- `apps/portal/ai_provider.py`
- `apps/portal/tasks.py`
- `apps/portal/views_ai_copilot.py`
- `apps/portal/views_ai_gateway.py`
- `apps/siteconfig/tenant_studio_day1.py`
- `apps/siteconfig/views_onboarding_coach.py`
- `apps/studio_os/copilot_rail_service.py`
- `apps/studio_os/views_copilot_rail.py`

### Allowlisted direct gateway callers (5 files)

- `apps/portal/ai_provider.py`
- `apps/portal/views_ai_gateway.py`
- `apps/migration_cloud/ai_bridge.py`
- `apps/platform_runtime/ai_providers.py`
- `apps/siteconfig/management/commands/aggregate_ai_metrics.py`

### Direct gateway boundary violations outside allowlist: **20**

- `apps/api/consumers.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/api/tests/test_ai_chat_consumer_gateway.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/marketplace/management/commands/seed_capability_registry.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/migration_cloud/views.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/platform_runtime/tests/test_ai_assistant.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/platform_runtime/tests/test_ai_deployment_posture.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/platform_runtime/tests/test_ai_system_layer.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/platform_runtime/tests/test_learning_institution_beyond.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tasks.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tests/test_ai_gateway.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tests/test_ai_provider.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tests/test_ai_provider_support_suggest.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tests/test_guided_assistant_rules_fallback.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/portal/tests/test_support_request_flow.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/siteconfig/tenant_studio_day1.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/siteconfig/tests/test_ai_center.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/siteconfig/tests/test_ai_center_integration.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/siteconfig/tests/test_onboarding_coach_api.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/studio_os/copilot_rail_service.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)
- `apps/studio_os/views_copilot_rail.py` — VIOLATION (would trip `scan_ai_gateway_boundary.py`)

## Boundary invariants to preserve

- App code in apps/ MUST route AI through services.ai_helpers (invoke_with_request, normalize_gateway_metadata, record_feedback)
- Direct services.ai_gateway imports outside the 5-file allowlist are forbidden — enforced by scripts/scan_ai_gateway_boundary.py baseline 0
- AI calls must pass tenant_id (or hashed equivalent) to the gateway — never cross-tenant
- DATA DEFAULTER posture: when context absent, return a safe default action — never fabricate
- FEATURE CODESPACE DISCONNECT: when feature absent, return service_online=False so UI renders 'unknown' chip not '0'
- No destructive intents auto-execute; return confirmation-required action with reversible=false instead

## AI workflow assistant contract

**Input context required:**
- Workflow object (key, route, audience, current step) from workflow_registry
- request.user.role (resolved via apps.platform_runtime.role_registry)
- request.tenant + request.public_host_kind
- Readiness / blocker state for the current step

**Output shape:** `{label, url, evidence_id, blocker_reason?, workflow_key}`

**Tenant isolation:** tenant_id ALWAYS passed to gateway; AI responses never reference other tenants' data

**Evidence citation:** Every action returned MUST carry evidence_id when based on tenant data, OR workflow_key when based on registry

## Gaps

### `workflows_with_ai_help_available_tag_but_no_related_ai_context_key` (2 entries)

  `support-help-hub`, `teacher-enter-marks`

### `workflows_with_related_ai_context_key_but_no_ai_help_available_tag` (1 entries)

  `studio-os-experience`

### `apps_with_views_but_no_ai_helpers_import_candidates_for_wiring` (6 entries)

  `academics`, `compliance`, `evals`, `feedback`, `integrations_marketplace`, `reports`

## Phase 11 tests to write

- `apps.apicenter.tests.test_ai_workflow_assistant — bridge respects evidence-id contract`
- `apps.platform_runtime.tests.test_workflow_ai_guidance_contracts — tenant-isolation + role-aware contract`

## Phase 4 AI-wiring plan

| Target | Change |
|---|---|
| `apps/studio_os/copilot_rail_service.py` | Bind 'cloud-first' path to workflow_registry.get_workflow(key).related_ai_context_key when route resolves to a registered workflow |
| `apps/platform_runtime/ai_workflow_bridge.py` | Pass workflow context into invoke_with_request; receive {label, url, evidence_id, workflow_key} structured action |
| `templates/components/workflow_next_action.html` | Phase 4 wires AI-suggested next-action when {{ action.evidence_id }} present, else falls back to registry default |

## Honest deferrals

- End-to-end test of AI tenant isolation under live gateway — Phase 12 (browser QA or live smoke)
- Edge profile (Ollama) parity for workflow-aware AI guidance — services/ai_deployment_posture.py already maps profiles; per-workflow context still needs operator opt-in
- AI feedback loop wiring from record_feedback() back to workflow scorecard (Phase 10) — observability work, not Phase 8

**Verdict:** `PHASE_8_AI_AUDIT_READY`
