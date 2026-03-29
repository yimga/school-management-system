# Threat model sketch: AI, webhooks, uploads, exports

**Purpose:** Lightweight, actionable threat notes for security reviews and control design. Not a formal STRIDE write-up; extend in your org’s template.

## AI (assist + tools)

| Threat | Mitigation direction |
|--------|---------------------|
| Prompt injection leading to tool abuse or data exfil | Versioned prompts/models; canary; no silent promote for tool/data-access changes; constrained tool allowlists; RAG on **canonical docs**, not unconstrained DB. |
| PII in model context | Redact/limit retrieval; eval harness for leakage (CI where feasible). |
| Operator vs tenant confusion | AI features respect same host/school boundaries as the rest of the app. |

### Implemented controls in this repo (behavior map)

| Control | Where | Notes |
|--------|--------|--------|
| Single ingress; no browser-to-provider | `services/ai_gateway.py` `invoke()` | All model traffic is intended to go through the gateway (see module docstring). |
| Prompt-injection phrase block (pre-provider) | `_PROMPT_INJECTION_MARKERS`, `_looks_like_prompt_injection` | Returns `(None, meta)` with `prompt_injection_blocked: true`; no tier calls. Tests: `services/tests/test_ai_gateway.py`. |
| **LiteLLM** (premium / third-party) gated on data tier | `_data_tier_allows_premium`, `metadata` | Skips `litellm` when `sensitivity_class == "high"`, `disallow_external_model` is true, or `strip_pii_for_inference` detects change in prompt/user_query (`services/inference.py`). Error bucket `data_tier_disallowed`. Tests: same module (`test_invoke_blocks_premium_*`). |
| **RAG retrieval tenant boundary** | `AIMemoryService.search_similar` in `services/ai_memory.py` | With `school_id` set, queryset is `(school_id = tenant) OR (school_id IS NULL)` — **other tenants' scoped rows must never rank in**. Shared **global** rows use `school_id` null. **CI:** `services/tests/test_ai_memory.py` (`RagRetrievalEvalTests`). **Product:** tenant HTTP handlers must pass `school_id` from `request.school` (`apps/portal/views_ai_gateway._school_id`); `school_id=None` skips school filter (operator / no-tenant contexts only). |
| Task tier defaults (e.g. general chat: Ollama + rules only) | `DEFAULT_TASK_TIERS`, `AI_GATEWAY_TASK_TIERS` | `GENERAL_CHAT` has no cloud tier by default; overrides are operator-controlled. |
| Structured output validation + safe defaults | `services/ai_schemas.py`, `_safe_schema_default` | Invalid JSON or schema violations yield typed empty defaults and `schema_validation_failed` in meta. |
| Per-tenant daily budget | `AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY`, `_check_and_consume_budget` | Returns `budget_exceeded` meta; audit path records outcome. |
| Audit / metrics fields | `_audit_log`, `_record_metric` | `task_type`, `request_id`, `tenant_id` / `school_id` when provided in metadata. |
| Blueprint / wiring gate | `scripts/verify_ai_blueprint_completion.py` | Fails CI if gateway, prompts, key docs, or embeddings router drift from required shapes. |

### No parallel stacks & inference ops (operator contract)

**No parallel stacks:** Product features must not add a second browser-reachable or view-layer LLM client that bypasses `services/ai_gateway.py` `invoke()`. New tasks, tiers, and structured outputs extend the gateway and `apps/portal/views_ai_gateway.py`—not ad-hoc SDK calls scattered across apps.

**Inference ops (env + settings, not duplicate codepaths):**

| Knob | Where | Purpose |
|------|--------|---------|
| `AI_GATEWAY_ENABLED` | `config/settings.py` | Kill switch for in-product gateway traffic. |
| `AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY` | `config/settings.py` | Per-tenant daily cap (0 = off). |
| `AI_GATEWAY_TASK_TIERS` / vLLM & LiteLLM envs | `config/settings.py` (see comments) | Task-tier routing; `VLLM_*`, `LITELLM_*` only when tiers enable them. |
| Data-class / premium gating | `services/inference.py` | Works with gateway metadata (`strip_pii_for_inference`, sensitivity) before premium/third-party tiers. |
| Embeddings | `AI_EMBEDDING_BACKEND`, `AI_EMBEDDING_*` | `services/embeddings.py` router (Ollama vs OpenAI-compatible). |
| Optional beats | `ENABLE_OLLAMA_MODEL_SYNC_BEAT`, `ENABLE_AI_KNOWLEDGE_INDEX_BEAT`, `ENABLE_AI_QUALITY_SCORECARD_BEAT` | Background indexing / model sync—still use gateway + memory services, not parallel inference stacks. |

RAG, playbook automation, and beats are summarized under the **AI RAG, migration playbook…** slice in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (section 11.4). Indexing uses policy-scoped tenant ranking (`services/ai_memory.py`, `siteconfig` beats)—not raw unconstrained DB dumps into the model.

## Webhooks

| Threat | Mitigation direction |
|--------|---------------------|
| Forged callbacks | Shared secret / signature verification; idempotency; replay windows. |
| SSRF via callback URLs | Allowlist destinations; block internal ranges in outbound fetches. |
| Inbound integration abuse | **Platform marketplace integration webhook** (`POST /api/integrations/v1/platform-webhook`): raw-body HMAC with header `X-RunMyCampus-Integration-Signature: sha256=<hex>` using effective **`webhook_signing_secret`** (`RuntimeDefaults` / `SiteSettings` merge via `get_effective_site_settings`); **503** if unset; **401** if signature invalid; append **`PlatformIntegrationWebhookEvent`** row (verified flag + body hash + client IP) for audit. |

**AI adjacency:** Treat LLM tool callbacks and third-party “agent” webhooks like other signed ingress: same tenant/host boundaries as the rest of the app; no unconstrained tool URLs; secrets are first-class on `RuntimeDefaults` where applicable (see marketplace credential train **0029**–**0034**).

## Uploads

| Threat | Mitigation direction |
|--------|---------------------|
| Malware / polyglots | MIME sniff limits; AV scanning where required; size quotas. |
| Path traversal / storage abuse | Randomized object keys; no user-controlled paths; per-tenant quotas. |

## Exports

| Threat | Mitigation direction |
|--------|---------------------|
| Bulk exfiltration by compromised account | Role checks; rate limits; audit logs; optional approval for large exports. |
| Cross-tenant export | Schema / `school_id` enforcement in queries; tests for tenant isolation on export paths. |

## Cross-cutting

- **Structured alerts** on impersonation start/end, role changes, export jobs, webhook verification failures.
- **CI:** dependency/CVE (e.g. `pip-audit` in `.github/workflows/smoke.yml`), plus targeted security tests for host/school boundaries.
- **Gilead / naming corpus:** `scripts/lint_gilead_residue.py` (runtime-visible strings) and `scripts/verify_gilead_full_tree_classification.py` (docs + migrations buckets). When you add migrations or marketing copy, update [GILEAD_REFERENCE_CLASSIFICATION.md](GILEAD_REFERENCE_CLASSIFICATION.md) if classifier rules change.
- **SQL / CSRF / AllowAny:** allowlists under `scripts/allowlists/` with `last_reviewed`; `scripts/verify_security_allowlists.py` + `scripts/verify_security_allowlist_density.py` (run after changing exempt paths or expected counts). Phase 8 ledger: `scripts/build_phase8_security_ledger.py --write` then `--check`.
- **Doc / plan density:** single strategy file remains [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md); `scripts/verify_doc_plan_density_discipline.py` guards against parallel master plans—extend SOT and [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) instead of new roadmaps.
- **Trust center UI ↔ docs:** `templates/schools/super_trust_center.html` and `templates/accounts/security_trust_hub.html` embed stable anchors to [NORTH_STAR_TRUST_AND_OPS.md](NORTH_STAR_TRUST_AND_OPS.md) and this threat sketch; `scripts/verify_phase9_security_trust_conformance.py` checks template tokens + these files on disk.

See [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md) for operator/tenant routing and impersonation.
