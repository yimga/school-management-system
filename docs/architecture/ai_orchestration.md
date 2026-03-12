# AI orchestration (internal-first)

All LLM usage goes through a single orchestration layer. **No browser or front-end may call Ollama, vLLM, or any model provider directly.** All product AI traffic goes through the RunMyCampus AI Gateway when `AI_GATEWAY_ENABLED` is True. Scope and phased rollout are tracked only in the **RunMyCampus Open-Source AI Adoption Blueprint** (single plan; no separate backlog file).

## AI Gateway (task-based routing)

- **Entry:** `services.ai_gateway.invoke(task_type, prompt, user_query=..., metadata=..., response_schema=...)` → `(result, meta)`.
- **Task types:** config_explain, setup_recommend, workflow_draft, policy_explain, doc_classify, semantic_search, migration_mapping, admin_copilot, support_suggest, narrative, general_chat.
- **Tiers:** Ollama (lightweight/private), vLLM (structured JSON, throughput), LiteLLM (routing, fallback, premium), rules (fallback). Routing table: `AI_GATEWAY_TASK_TIERS` or defaults in `services/ai_gateway.py`.
- **Structured output:** For workflow_draft, policy_explain, migration_mapping, doc_classify the gateway validates responses via `services.ai_schemas` and returns typed objects or fallback text.
- **Audit:** Every invoke logs task_type, tier, model, latency_ms, tenant_id, school_id, outcome (success/failure/fallback). Data-tier check: premium (LiteLLM/Gemini) is skipped when sensitivity disallows it or the prompt payload contains detected PII.

## Single entry points

| Use case | Entry point | Notes |
|----------|-------------|--------|
| Sync single-turn (copilot, narrative) | `apps.portal.ai_provider.generate_ai_response(...)` | Routes through `services.ai_gateway.invoke("general_chat", ...)` when AI_GATEWAY_ENABLED; returns (text, meta). |
| Productized AI (setup, workflow, policy, doc, search, migration) | `POST /api/ai/setup-assistant/`, `/api/ai/workflow-draft/`, `/api/ai/policy-explain/`, `/api/ai/document-classify/`, `/api/ai/semantic-search/`, `/api/ai/migration-suggest/` | `apps.portal.views_ai_gateway`; permission + audit; gateway only. |
| Admin & Toolset 5A–5I, Wave 2/3 | `POST /api/ai/admin-copilot/`, `/api/ai/theme-recommend/`, `/api/ai/feature-control-explain/`, `/api/ai/report-recommend/`, `/api/ai/design-studio-draft/`, `/api/ai/live-preview-explain/`, `/api/ai/system-config-explain/`, `/api/ai/dashboard-pack-recommend/`, `/api/ai/support-assistant/`, `/api/ai/tenant-maturity/` (GET/POST), `/api/ai/data-quality-assistant/`, `/api/ai/marketplace-recommend/`, `/api/ai/control-plane-intelligence/` | Same pattern: rate limit, RAG where applicable, budget 429, audit, citations where used. |
| Async / bulk | `apps.portal.tasks.generate_ai_response_async` + poll `ai:async_result:{task_id}` | Uses `OllamaInferenceService.infer` and cache. |
| WebSocket chat | `apps.api.consumers` | Calls `OllamaInferenceService.infer` (sync_to_async). |
| Workflow / country suggestions | `apps.portal.ai_provider.get_workflow_clues` / `get_country_dossier_summary` | Delegates to Ollama. |

## Provider order and adapters

- **Gateway first:** When AI_GATEWAY_ENABLED, `generate_ai_response` uses `invoke("general_chat", ...)` which applies task-tier routing (Ollama → vLLM → LiteLLM → Gemini → rules).
- **Preference (legacy path):** `AI_PROVIDER_PREFERENCE` (e.g. `ollama,gemini,rules`). Default: `ollama`, then `rules`.
- **Ollama:** `services.inference.OllamaInferenceService` (region, dossier, cache, fallback, PII stripping). Used by gateway and ai_provider.
- **vLLM:** `services.ai_gateway._call_vllm` (OpenAI-compatible completions; optional `response_format: json_object`). Set `VLLM_ENDPOINT`, `VLLM_MODEL`.
- **LiteLLM:** `services.ai_gateway._call_litellm` (proxy URL). Set `LITELLM_PROXY_URL`, `LITELLM_MODEL`.
- **Gemini:** `apps.portal.ai_provider._call_gemini` (REST). Key from env; gateway may route general_chat to gemini when allowed.
- **Rules fallback:** When no live provider returns, `_rules_fallback`; no external call.

## Prompts, RAG, audit

- **Prompts:** Owned in code (ai_provider, inference). No tenant identifiers or internal IDs are appended to prompts sent to external providers (`metadata` is not added to prompt text).
- **Prompt discipline:** Productized AI endpoints resolve prompt templates through `apps.siteconfig.prompt_registry` so prompt owner, review status, expected output shape, and backend policy stay governable in one place.
- **RAG:** When RAG is used, source data must come from internal APIs or DB; no raw PII in context sent to external LLMs. `strip_pii_for_inference` in services.inference used for Ollama path.
- **Audit:** Logging and `metadata` returned from `generate_ai_response` are for observability only; extend to structured audit (e.g. event or log line per request) as needed.
- **Evaluation:** Add evaluation harness (e.g. golden set, safety checks) behind the same entry points; no separate provider calls for evals.

## Audit result (no direct provider usage outside facade)

- **portal/views_ai_copilot:** Uses `generate_ai_response` only.
- **communication/narrative_feedback:** Uses `generate_ai_response` only.
- **portal/tasks:** Uses `OllamaInferenceService.infer` (internal); async path does not call Gemini directly.
- **api/consumers:** Uses `OllamaInferenceService.infer` only.
- **portal/ai_provider:** Contains the only Gemini call (`_call_gemini`) and Ollama delegation (`_call_ollama` → OllamaInferenceService).

No `openai`, `anthropic`, or `google.generativeai` SDK imports in app code; Gemini is invoked via REST in ai_provider.

## Embeddings and semantic search

- **Router:** `services.embeddings.get_embedding_provider()` returns Ollama or OpenAI-compatible provider per `AI_EMBEDDING_BACKEND`.
- **Retrieval guardrails:** `AIMemoryService.search_similar(...)` includes tenant scoping, global fallback for shared knowledge, and metadata-based role/staff visibility filtering for indexed content.
- **Storage:** `services.ai_memory.AIMemoryService` uses the router for `store`; `get_embedding_for_text()` for query embedding. Index: policies, blueprints, docs, config (per blueprint).

### Retrieval indexing (ingestion)

Ingest the following into the embedding store (scoped by tenant where applicable) via the management command **`index_ai_knowledge`** (`apps.siteconfig.management.commands.index_ai_knowledge`):

| Source | Scope | Notes |
|--------|--------|------|
| Policy bundles | `policy` | PolicyBundle name, description, migration_notes, section keys; school_id when set |
| Blueprint packs | `blueprint` | BlueprintPack name, description, category, family, policy_snapshot keys |
| Workflow packs | `workflow` | WorkflowPack name, description, code, family |
| Report templates | `report` | ReportTemplate name, description |
| Static help/config | `help`, `config` | Setup Studio, Control Plane, workflows, policies short blurbs |

Run: `python manage.py index_ai_knowledge` (optionally `--scope policy`, `--school-id <uuid>`, `--dry-run`). Use after catalog changes or on a schedule. RAG for setup_assistant, policy_explain, and admin_copilot uses these scopes.

## Data-tier matrix and per-feature data boundary

- **Data-tier matrix:** Which data may be sent to which inference tier.
  - **Internal-only (Ollama / vLLM on-prem):** Any tenant data, PII (after stripping if configured), policies, config, workflow definitions, support context.
  - **Premium / external (LiteLLM, Gemini):** Only non-PII, non–tenant-identifying content. Do not send: raw student/parent names, IDs, grades, invoices, or tenant-specific policy text that could re-identify. Allowed: anonymized summaries, public docs, generic workflow templates, migration field names (no row data).
- **Enforcement:** Gateway uses `metadata.sensitivity_class` and `metadata.disallow_external_model`. When `sensitivity_class == "high"` or `disallow_external_model` is set, premium tiers are skipped. Per-feature boundaries below are enforced in the productized views (what is included in the prompt and what is retrieved from RAG).

| Feature | Allowed tenant data | External routing | Retrieval required | Structured output | Retention (prompts/responses) |
|--------|----------------------|------------------|---------------------|-------------------|-------------------------------|
| Setup assistant | Config names, non-PII setup docs | No (internal first) | Yes (setup/help scope) | No | Audit log metadata only; no full prompt/response |
| Workflow draft | Description only; no student names | Optional (vLLM/LiteLLM) | Optional | Yes (workflow_draft) | Audit metadata only |
| Policy explain | Policy text + RAG policy chunks | No for PII policies | Yes (policy scope) | Yes (policy_explain) | Audit metadata only |
| Document classify | Stripped PII text only | Optional | No | Yes (doc_classify) | Audit metadata only |
| Semantic search | Query only; results from internal store | No | Yes (scope-based) | No | Audit metadata only |
| Migration suggest | Field names/schemas only; no row data | Optional | No | Yes (migration_mapping) | Audit metadata only |
| Admin copilot | Help/config docs, non-PII | No | Yes (help/config scope) | No | Audit metadata only |
| General chat / narrative | Stripped or no PII | Per tenant config | Optional | No | Per data retention policy |

## Request metadata (gateway contract)

Callers may pass the following in `metadata` to influence routing and behaviour (all optional):

- **sensitivity_class** (`"low"` \| `"medium"` \| `"high"`): When `"high"`, premium (LiteLLM/Gemini) is disabled for this request.
- **latency_target** (int, seconds): Hint for timeout; gateway caps provider timeout to this value when set (e.g. 5–90).
- **output_type** (`"text"` \| `"json"`): Informational; can be used to prefer JSON-capable backends (e.g. vLLM with `response_format: json_object`).
- **allowed_backends** (list of str): If set, only these tiers are tried (e.g. `["ollama", "rules"]` for internal-only). Order is respected; must be subset of configured tiers.

These are documented in `services.ai_gateway.invoke` and applied in routing/tier selection and timeout.

## Observability and review loops

- **Persisted metrics:** `AIGatewayMetric` aggregates request volume, latency, failure rate, schema-validation failures, `cost_class`, `review_count`, `accepted_count`, and `manual_correction_count`.
- **Metric sources:** `services.ai_gateway.invoke(...)` writes request buckets; `services.ai_gateway.record_feedback(...)` writes review-loop buckets; `python manage.py aggregate_ai_metrics` materializes both into the table.
- **Feedback capture:** Product UIs can POST `/api/ai/feedback/` with `task_type`, `tier`, `request_id`, `request_date`, `accepted`, and `manual_correction` so operator acceptance rate and manual correction rate are queryable instead of inferred.
- **Operator surfaces:** Platform admin exposes prompt registry, embedding store, and AI gateway metrics so prompt approval, indexed knowledge, and AI quality signals are visible from the control plane.

## References

- `apps/portal/ai_provider.py`
- `services/ai_gateway.py`, `services/ai_schemas.py`, `services/embeddings.py`
- `services/inference.py`
- `docs/architecture/ai_tiered_ollama.md` (north-star stack; this plan is the single blueprint)
- `docs/architecture/SERVICE_CATALOG.md` (Zone B AI adapter)
