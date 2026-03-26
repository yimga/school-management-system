# RunMyCampus AI Adoption Blueprint — Historical Verification Snapshot

**Status:** Historical verification snapshot only. The live scope, phases, and deliverables for AI adoption are tracked only in the Cursor blueprint plan at `C:\Users\yimga\.cursor\plans\tiered_ai_gateway_and_ollama_7ecaa3c1.plan.md`. This file is evidence-only and must not be used as a second tracker.

## Gateway and routing

| Item | Status | Evidence |
|------|--------|----------|
| Single entry `services.ai_gateway.invoke(task_type, prompt, ...)` | Done | `services/ai_gateway.py` |
| Task types: config_explain, setup_recommend, workflow_draft, policy_explain, doc_classify, semantic_search, migration_*, admin_copilot, support_suggest, narrative, general_chat | Done | `TaskType` enum |
| Tier routing (Ollama, vLLM, LiteLLM, rules) with fallback; `general_chat` = Ollama+rules only | Done | `DEFAULT_TASK_TIERS`, loop in `invoke()` |
| Request metadata: sensitivity_class, latency_target, output_type, allowed_backends | Done | Doc in ai_orchestration.md; filtering and timeout in `invoke()` |
| Budget enforcement: per-tenant daily request cap | Done | `_check_and_consume_budget()`, `AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY`, 429 on exceed |
| Schema validation failure recorded for observability | Done | `schema_validation_failed` in `out_meta`, `_record_metric()` |
| Audit: task_type, tier, model, latency_ms, tenant_id, school_id, outcome | Done | `_audit_log()`; no prompt/response in log payload |
| Data-tier: premium skipped when sensitivity_class high or disallow_external_model | Done | `_data_tier_allows_premium()` |

## Structured output and schemas

| Item | Status | Evidence |
|------|--------|----------|
| workflow_draft, policy_explain, migration_mapping, doc_classify validation | Done | `services/ai_schemas.py`, validators + `extract_json_from_text()` |
| Gateway returns validated objects or safe typed defaults on schema failure | Done | `invoke()` response_schema branch |

## Productized API endpoints

| Endpoint | Status | Notes |
|----------|--------|-------|
| POST /api/ai/setup-assistant/ | Done | RAG default scope, citations, prompt registry, budget 429 |
| POST /api/ai/workflow-draft/ | Done | response_schema workflow_draft, budget 429 |
| POST /api/ai/policy-explain/ | Done | RAG policy/default, citations, budget 429 |
| POST /api/ai/document-classify/ | Done | strip_pii, response_schema doc_classify, budget 429 |
| POST|GET /api/ai/semantic-search/ | Done | RAG + optional summarization, budget 429 |
| POST /api/ai/migration-suggest/ | Done | response_schema migration_mapping, budget 429 |
| POST /api/ai/admin-copilot/ | Done | RAG help/config/default, citations, budget 429 |
| POST /api/ai/theme-recommend/ (5A) | Done | Toolset 5A Theme & Experience |
| POST /api/ai/feature-control-explain/ (5B) | Done | Toolset 5B Feature Control |
| POST /api/ai/report-recommend/ (5C) | Done | Toolset 5C Report Library |
| POST /api/ai/design-studio-draft/ (5E) | Done | Toolset 5E Design Studio |
| POST /api/ai/live-preview-explain/ (5F) | Done | Toolset 5F Live Previews |
| POST /api/ai/system-config-explain/ (5I) | Done | Toolset 5I Configuration Control Center |
| POST /api/ai/dashboard-pack-recommend/ | Done | Wave 2 dashboard/pack recommendations |
| POST /api/ai/support-assistant/ | Done | Wave 2 support assistant, RAG help |
| GET|POST /api/ai/tenant-maturity/ | Done | Wave 2 tenant maturity score + tier |
| POST /api/ai/data-quality-assistant/ | Done | Wave 3 data quality assistant, RAG config/help |
| POST /api/ai/marketplace-recommend/ | Done | Wave 3 marketplace ranking/recommendation |
| POST /api/ai/control-plane-intelligence/ | Done | Wave 3 control-plane intelligence, RAG help/config |

All endpoints: login_required, CSRF, rate limit, audit, budget 429 when applicable.

## Citations and RAG

| Item | Status | Evidence |
|------|--------|----------|
| setup_assistant returns citations (id, scope, metadata) | Done | `views_ai_gateway.api_setup_assistant` |
| policy_explain returns citations | Done | `api_policy_explain` |
| admin_copilot returns citations | Done | `api_admin_copilot` |

## Prompt registry and prompt classes

| Item | Status | Evidence |
|------|--------|----------|
| AIPromptRegistry model (prompt_key, prompt_class, owner, purpose, template_body, allowed_data_sources, expected_output_shape, model_backend_policy, is_active, review_status) | Done | `apps/siteconfig/models.py` |
| AIPromptClass constants (setup, workflow, policy, migration, document, support, marketplace, design_experience, analytics, admin) | Done | `apps/siteconfig/models.py` |
| get_prompt_template(key, context) with DB + BUILTIN_PROMPTS fallback | Done | `apps/siteconfig/prompt_registry.py` |
| Views use prompt registry where applicable | Done | setup_assistant, policy_explain, admin_copilot, theme, feature_control, report, design_studio, system_config, support_suggest |

## Observability and quality

| Item | Status | Evidence |
|------|--------|----------|
| AIGatewayMetric model (date, tenant_id, task_type, tier, request_count, total_latency_ms, failure_count, schema_validation_failures) | Done | `apps/siteconfig/models.py` |
| Cache bucket recording in _audit_log (_record_metric) | Done | `services/ai_gateway.py` |
| aggregate_ai_metrics management command | Done | `apps/siteconfig/management/commands/aggregate_ai_metrics.py` |
| Tenant-safe logs: no prompt/response in audit new_values | Done | `_redact_audit_meta()` in views_ai_gateway |

## Data-tier and data-boundary docs

| Item | Status | Evidence |
|------|--------|----------|
| Data-tier matrix (internal vs premium) | Done | ai_orchestration.md |
| Per-feature data boundary table | Done | ai_orchestration.md |
| Request metadata documented | Done | ai_orchestration.md |

## Retrieval indexing

| Item | Status | Evidence |
|------|--------|----------|
| index_ai_knowledge management command | Done | `apps/siteconfig/management/commands/index_ai_knowledge.py` |
| Sources: policy bundles, blueprint packs, workflow packs, report templates, static help/config | Done | Command scopes: policy, blueprint, workflow, report, help, config |
| Doc in ai_orchestration.md | Done | Retrieval indexing section |

## Open WebUI

| Item | Status | Evidence |
|------|--------|----------|
| Deployment steps in ai_tiered_ollama.md | Done | "Deploying Open WebUI" section |
| OPEN_WEBUI_URL setting | Done | config/settings.py |
| Control Plane link when OPEN_WEBUI_URL set | Done | backend_dashboard.html + context in views.py |

## UI wiring

| Item | Status | Evidence |
|------|--------|----------|
| Setup Studio: "Explain" and "Suggest workflow" buttons | Done | guided_onboarding.html, JS to /api/ai/setup-assistant/ and /api/ai/workflow-draft/ |
| CSRF and result display | Done | getCsrf(), showResult(), fetch POST |

## Wiring (provider, WebSocket, tasks)

| Item | Status | Evidence |
|------|--------|----------|
| ai_provider.generate_ai_response uses gateway when AI_GATEWAY_ENABLED | Done | ai_provider.py |
| AIChatConsumer uses gateway | Done | api/consumers.py |
| generate_ai_response_async uses invoke("narrative", ...) | Done | portal/tasks.py |
| get_workflow_clues / suggest_support_ticket use gateway when enabled | Done | ai_provider.py |

## Tests

| Item | Status | Evidence |
|------|--------|----------|
| Task tiers, invoke (ollama + rules fallback), schema validators, extract_json | Done | apps/portal/tests/test_ai_gateway.py |
| allowed_backends, budget_exceeded | Done | Same file |

---

**Verification:** Run `python manage.py test apps.portal.tests.test_ai_gateway -v 2`. All items above are implemented at expert level (production logic, no TODOs or stubs).
