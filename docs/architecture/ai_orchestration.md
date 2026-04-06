# AI orchestration (internal-first)

All LLM usage goes through a single orchestration layer. **No browser or front-end may call Ollama, vLLM, or any model provider directly.** All product AI traffic goes through the RunMyCampus AI Gateway when `AI_GATEWAY_ENABLED` is True. Scope and phased rollout are tracked only in the **RunMyCampus Open-Source AI Adoption Blueprint** (single plan; no separate backlog file).

## AI Gateway (task-based routing)

- **Entry:** `services.ai_gateway.invoke(task_type, prompt, user_query=..., metadata=..., response_schema=...)` → `(result, meta)`.
- **Task types:** config_explain, setup_recommend, workflow_draft, policy_explain, doc_classify, semantic_search, migration_mapping (plus migration_fingerprint, migration_parity), admin_copilot, support_suggest, narrative, general_chat, and domain-guided tasks: interop_assistant, runtime_config_explain, observability_assistant, billing_usage_explain, trust_compliance_assistant, studio_os_assistant (see `TaskType` in `services/ai_gateway.py`).
- **Tiers:** **Defaults:** Ollama then rules for every task (`DEFAULT_TASK_TIERS` in `services/ai_gateway.py`). **Optional:** vLLM / LiteLLM only when added per task via Django `AI_GATEWAY_TASK_TIERS` (merge override).
- **Structured output:** For workflow_draft, policy_explain, migration_mapping, doc_classify the gateway validates responses via `services.ai_schemas` and returns typed objects or fallback text.
- **Audit:** Every invoke logs task_type, tier, model, latency_ms, tenant_id, school_id, outcome (success/failure/fallback). Data-tier check: premium (**LiteLLM** only) is skipped when sensitivity disallows it or the prompt payload contains detected PII. **`general_chat` uses Ollama + rules only** (no Google Gemini or other cloud LLM in that path).

## Single entry points

| Use case | Entry point | Notes |
|----------|-------------|--------|
| Sync single-turn (copilot, narrative) | `apps.portal.ai_provider.generate_ai_response(...)` | Routes through `services.ai_gateway.invoke("general_chat", ...)` when AI_GATEWAY_ENABLED; returns (text, meta). |
| Productized AI (setup, workflow, policy, doc, search, migration) | `POST /api/ai/setup-assistant/`, `/api/ai/workflow-draft/`, `/api/ai/policy-explain/`, `/api/ai/document-classify/`, `/api/ai/semantic-search/`, `/api/ai/migration-suggest/` | `apps.portal.views_ai_gateway`; permission + audit; gateway only. |
| Admin & Toolset 5A–5I, Wave 2/3 | `POST /api/ai/admin-copilot/`, `/api/ai/theme-recommend/`, `/api/ai/feature-control-explain/`, `/api/ai/report-recommend/`, `/api/ai/design-studio-draft/`, `/api/ai/live-preview-explain/`, `/api/ai/system-config-explain/`, `/api/ai/dashboard-pack-recommend/`, `/api/ai/support-assistant/`, `/api/ai/tenant-maturity/` (GET/POST), `/api/ai/data-quality-assistant/`, `/api/ai/marketplace-recommend/`, `/api/ai/control-plane-intelligence/` | Same pattern: rate limit, RAG where applicable, budget 429, audit, citations where used. |
| Async / bulk | `apps.portal.tasks.generate_ai_response_async` + poll `ai:async_result:{task_id}` | Celery → `services.ai_gateway.invoke("narrative", ...)`; result in cache. |
| WebSocket chat | `apps.api.consumers.AIChatConsumer` | `sync_to_async` → `services.ai_gateway.invoke("general_chat", ...)` (same gateway as HTTP). |
| Workflow / country suggestions | `apps.portal.ai_provider.get_workflow_clues` / `get_country_dossier_summary` | Delegates to Ollama. |

## Provider order and adapters

- **Gateway first:** When AI_GATEWAY_ENABLED, `generate_ai_response` uses `invoke("general_chat", ...)` with tiers **`["ollama", "rules"]`** only (policy-aligned with internal chat).
- **Preference (status UI):** `AI_PROVIDER_PREFERENCE` defaults to `ollama,rules`. Tokens such as `gemini` are **ignored** if present in env (legacy cleanup).
- **Ollama:** `services.inference.OllamaInferenceService` (region, dossier, cache, fallback, PII stripping). Used by gateway and `apps.portal.ai_provider` for delegation. Set `OLLAMA_ENDPOINT`, `OLLAMA_MODEL`. Operations: [OLLAMA_OPERATIONS_AND_UPDATES.md](../OLLAMA_OPERATIONS_AND_UPDATES.md).
- **vLLM:** `services.ai_gateway._call_vllm` (OpenAI-compatible completions; optional `response_format: json_object`). Set `VLLM_ENDPOINT`, `VLLM_MODEL`.
- **LiteLLM:** `services.ai_gateway._call_litellm` (proxy URL). Set `LITELLM_PROXY_URL`, `LITELLM_MODEL`. Only runs for tasks that include `litellm` after an `AI_GATEWAY_TASK_TIERS` override — **not** in default `DEFAULT_TASK_TIERS`.
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
- **portal/tasks:** Uses `OllamaInferenceService.infer` (internal).
- **api/consumers:** Uses gateway / inference paths only (no direct browser provider calls).
- **portal/ai_provider:** Ollama status + `generate_ai_response` → gateway; **no** Google Generative Language API.

No `openai`, `anthropic`, or `google.generativeai` SDK imports in app code for copilot chat; cloud premium is optional **LiteLLM proxy** only where a task tier lists it.

## Embeddings and semantic search

- **Router:** `services.embeddings.get_embedding_provider()` returns Ollama or OpenAI-compatible provider per `AI_EMBEDDING_BACKEND`.
- **Retrieval guardrails:** `AIMemoryService.search_similar(...)` includes tenant scoping, global fallback for shared knowledge, metadata-based role/staff visibility filtering, and for **`policy`** scope a **tenant-first ranking boost** when `school_id` is set (school-specific policy bundles rank above global rows at equal embedding similarity). Product HTTP RAG entrypoints now use `global_only=True` when `request.school` is missing, so non-tenant requests see only platform-global rows instead of an unscoped cross-tenant sweep.
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

### Scheduled RAG indexing (Celery beat, opt-in)

When `ENABLE_AI_KNOWLEDGE_INDEX_BEAT=1` in the environment that runs **Celery beat and workers**, `config.settings.CELERY_BEAT_SCHEDULE` registers **`siteconfig.index_ai_knowledge_beat`** on a **daily** interval (same pattern as other opt-in beats). The task runs `python manage.py index_ai_knowledge` via `call_command`. **Requirements:** embedding provider must work from the worker host (`AI_EMBEDDING_*`). If embeddings are unavailable, the management command exits early (no crash). Disable the env flag to turn the schedule off.

### AI quality scorecard loop (review metrics)

- `POST /api/ai/feedback/` captures review-loop signals (`accepted`, `manual_correction`) for task+tier.
- `python manage.py aggregate_ai_metrics` upserts request + review buckets into `AIGatewayMetric`.
- `python manage.py ai_quality_scorecard --days 7` prints task-level rates (`acceptance_rate`, `manual_correction_rate`, `schema_fail_rate`, `failure_rate`) for operator review.
- Optional weekly beat: `ENABLE_AI_QUALITY_SCORECARD_BEAT=1` runs `siteconfig.ai_quality_scorecard_beat` (aggregate + scorecard).

### Migration playbooks (data plane, not LLM)

`apps.automation.playbook_executor.execute_playbook` runs migration profiles in order. **Semantics:** **`FAILED`** stops the sequence on the first failed step (no automatic step retries — operators re-run a profile or playbook after fixing data). **`PARTIAL`** means at least one step completed with errors while the run continued; overall playbook status stays **`PARTIAL`** if any step was partial.

Before execution, a **preflight confidence score** is computed from payload quality signals:

- `required_field_coverage`
- `duplicate_risk`
- `rollback_readiness`
- `quarantine_risk`

If score is below `MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE` (default `70`), execution is blocked unless `override_reason` is explicitly provided by operator flow.

Each `execute_playbook` call writes one **`AutomationExecutionLog`** row (`task_name=automation.playbook.execute`) with step summaries for audit (`failed_steps`, `partial_steps`, per-step `quarantine_count`) plus `preflight_confidence_score`, threshold, signal breakdown, and override metadata.

**Quarantine:** `MigrationQuarantineRecord.migration_run` links rows to `MigrationRun` (`related_name=quarantine_records`). Platform admin lists quarantine counts on runs; the staff **Automation outcomes** console (`automation:outcomes_console`) shows **`quarantine_record_count`** per recent run.

## Data-tier matrix and per-feature data boundary

- **Data-tier matrix:** Which data may be sent to which inference tier.
  - **Internal-only (Ollama / vLLM on-prem):** Any tenant data, PII (after stripping if configured), policies, config, workflow definitions, support context.
  - **Premium / external (LiteLLM proxy only):** Only non-PII, non–tenant-identifying content. Do not send: raw student/parent names, IDs, grades, invoices, or tenant-specific policy text that could re-identify. Allowed: anonymized summaries, public docs, generic workflow templates, migration field names (no row data).
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

- **sensitivity_class** (`"low"` \| `"medium"` \| `"high"`): When `"high"`, premium (**LiteLLM**) is disabled for this request.
- **latency_target** (int, seconds): Hint for timeout; gateway caps provider timeout to this value when set (e.g. 5–90).
- **output_type** (`"text"` \| `"json"`): Informational; can be used to prefer JSON-capable backends (e.g. vLLM with `response_format: json_object`).
- **allowed_backends** (list of str): If set, only these tiers are tried (e.g. `["ollama", "rules"]` for internal-only). Order is respected; must be subset of configured tiers. If the intersection is empty, the gateway returns unavailable instead of widening back to the default tier list.

These are documented in `services.ai_gateway.invoke` and applied in routing/tier selection and timeout.

## Observability and review loops

- **Persisted metrics:** `AIGatewayMetric` aggregates request volume, latency, failure rate, schema-validation failures, `cost_class`, `review_count`, `accepted_count`, and `manual_correction_count`.
- **Metric sources:** `services.ai_gateway.invoke(...)` writes request buckets; `services.ai_gateway.record_feedback(...)` writes review-loop buckets; `python manage.py aggregate_ai_metrics` materializes both into the table.
- **Feedback capture:** Product UIs can POST `/api/ai/feedback/` with `task_type`, `tier`, `request_id`, `request_date`, `accepted`, and `manual_correction` so operator acceptance rate and manual correction rate are queryable instead of inferred.
- **Operator surfaces:** Platform admin exposes prompt registry, embedding store, and AI gateway metrics so prompt approval, indexed knowledge, and AI quality signals are visible from the control plane. **In-product API consoles** (guided + JSON cards and `super:ai_gateway_console`) are documented in the **In-browser operator surfaces** section above and in [AI_DOMAIN_ASSISTANT_REGISTRY.md](../AI_DOMAIN_ASSISTANT_REGISTRY.md).

## References

- [OLLAMA_OPERATIONS_AND_UPDATES.md](../OLLAMA_OPERATIONS_AND_UPDATES.md) (self-hosted Ollama upgrades and verification)
- `apps/portal/ai_provider.py`
- `services/ai_gateway.py`, `services/ai_schemas.py`, `services/embeddings.py`
- `services/inference.py`
- `docs/AI_DOMAIN_ASSISTANT_REGISTRY.md` (HTTP AI endpoints + UI embedding inventory)
- `docs/architecture/ai_tiered_ollama.md` (north-star stack; this plan is the single blueprint)
- `docs/architecture/SERVICE_CATALOG.md` (Zone B AI adapter)
