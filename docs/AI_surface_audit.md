# AI Surface Audit

**Purpose:** §2.3 "Audit every AI/copilot/widget/template/JS surface" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Single list of backend and template surfaces that invoke AI; no secrets in browser.

**Status:** DONE — inventory complete.

---

## 1. Backend entry points (all via services.ai_gateway or delegate)

| Surface | Module / path | Notes |
|---------|----------------|-------|
| Gateway invoke | `services.ai_gateway.invoke()` | Single entry; task types in TaskType enum |
| Helpers (platform-wide) | `services.ai_helpers.invoke_task / invoke_json_task / record_feedback` | Graceful degradation, PII inference, prompt-type tagging; all non-migration callers go here first |
| Copilot sync | `apps.portal.ai_provider.generate_ai_response()` | Delegates to gateway |
| Async tasks | `apps.portal.tasks.generate_ai_response_async` | Celery; calls invoke |
| REST gateway | `apps.portal.views_ai_gateway` | api_ai_feedback, domain assistants (`api_interop_assistant`, `api_runtime_config_explain`, `api_observability_assistant`, `api_billing_usage_explain`, `api_trust_compliance_assistant`, `api_studio_os_assistant`), _gateway_response, _log_gateway_audit |
| Copilot views | `apps.portal.views_ai_copilot` | `ai_health` (probe), `ai_copilot_audit_feed` (staff feed), `get_public_ai_provider_status`; no keys in context |
| Bounded-context wrappers | `apps/migration_cloud/ai_bridge.py`, `apps/finance/ai_categorize.py`, `apps/people/ai_dedup.py`, `apps/automation/ai_workflow_suggest.py`, `apps/dashboard/services/insight_anomalies._enrich_with_ai_narrative` | Per-context modules; never import `services.ai_gateway` directly |
| RAG ingest | `apps.siteconfig.management.commands.ingest_policy_documents` (CLI) + `apps.siteconfig.views_console_ai_rag.ingest_policy_docs` (`POST /siteconfig/console/ai/rag/ingest/`, staff-only) | Populates `AIEmbeddingStore`; audited via `AI_RAG_INGEST_TRIGGERED` |
| RAG memory service | `services.ai_memory` | Similarity search backed by `AIEmbeddingStore`; scope filters |
| Embedding provider | `services.embeddings` | Ollama default; OpenAI-compatible alternative |
| Tests | `apps.portal.tests.test_ai_gateway*`, `test_ai_feedback`, `test_ai_copilot_config`, `services.tests.test_ai_memory` | Assert no secret in rendered output; graceful-degradation paths |

---

## 2. Template / JS surfaces

| Surface | Path | Notes |
|---------|------|-------|
| AI copilot UI | `templates/components/ai_copilot.html` | AI_PROVIDER_NAME only; no API keys |
| Guided assistant cards | `templates/components/ai_guided_assistant_card.html` + `static/js/rmc_ai_guided_assistant.js` | POST `/api/ai/*-assistant/` with CSRF; no provider keys in browser |
| JSON API console cards | `templates/components/ai_json_api_card.html` + `static/js/rmc_ai_json_api_card.js` | Arbitrary JSON POST to `/api/ai/*`; CSRF cookie only |
| Control-plane aggregate | `templates/schools/super_ai_gateway_console.html` | Staff JSON consoles for productized endpoints; canonical table in [AI_DOMAIN_ASSISTANT_REGISTRY.md](AI_DOMAIN_ASSISTANT_REGISTRY.md) |
| Context | `apps.siteconfig.context_processors.ai_copilot_settings` | Capability flags only; test_ai_copilot_context |
| AI health pill | `static/js/rmc-ai-health-pill.js` + `aiCopilotStatus` element in `templates/components/ai_copilot.html` | Polls `/api/ai/health/`; sets visible "limited mode" badge when Ollama is down |
| ⌘K command palette → Ask AI | `static/js/rmc-command-palette.js` (Ask-AI fallback, 2026-05-14) | When no items match the user's query, surfaces "Ask AI: <query>" row that opens the copilot prepopulated |
| Anomaly card narrative | `apps.dashboard.services.insight_anomalies._enrich_with_ai_narrative` | One-line model suggestion appended to each anomaly card as `ai_suggestion`; safe on AI-disabled tenants |

---

## 3. Audit and rate limiting

- **Audit:** `services.ai_gateway` logs `ai_gateway_invoke` with tenant_id/school_id/outcome; `log_ai_action` persists to AIActionAuditLog (no prompt/response content).
- **Rate limit:** views_ai_gateway uses _check_rate_limit; feedback via record_feedback.

---

## 4. Completion

- [x] Every AI path goes through gateway or delegate.
- [x] Template/tests prove no provider secret in HTML/JS.
- [x] Audit trail documented in [AI_audit_trail_and_permissions.md](AI_audit_trail_and_permissions.md).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.3.*
