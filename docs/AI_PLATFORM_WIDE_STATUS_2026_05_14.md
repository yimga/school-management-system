# AI Platform-Wide Status — 2026-05-14

**Purpose.** This document is the single source of truth for every AI
surface on the platform: where it lives in the codebase, what it does,
how it is gated, and what governance applies. When in doubt about
"is the AI for X wired?", check here first; it is regenerated as part
of each AI-touching wave.

**Last verified:** 2026-05-14 (wave `sms-v2.10.0-ai-surfaces-closeout`).

---

## 1. Architecture — one gateway, many surfaces

Every AI call on the platform routes through one gateway:

```
caller (view / task / lander / template)
   ↓
services/ai_helpers.py            ← non-migration callers go here first
   ↓
services/ai_gateway.py            ← TaskType-routed dispatch
   ↓
tier policy: ollama → vllm → litellm → anthropic → rules
   ↓
audit + metric (AIActionAuditLog + AIGatewayMetric)
```

Rules of the road:

- **Never reach `services/ai_gateway.invoke()` from app code.** Use the
  bounded-context wrapper (`apps/<context>/ai_*.py`) which calls
  `services/ai_helpers.invoke_task` / `invoke_json_task`. Direct gateway
  calls bypass PII inference and prompt-type tagging, breaking the
  AIGatewayMetric rollup.
- **Every helper returns `None` on failure.** AI is enhancement, never
  required-path. Callers must have a deterministic fallback.
- **No secrets in the browser.** All AI configuration is server-side;
  the front-end gets capability flags only (see
  [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md)).

---

## 2. Service layer — files and responsibilities

| File | Responsibility |
|---|---|
| [services/ai_gateway.py](../services/ai_gateway.py) | Universal task router. 21 `TaskType` enums. Default tier policy. Prompt-injection detector. Audit + metric. |
| [services/ai_helpers.py](../services/ai_helpers.py) | Platform-wide wrapper. Graceful degradation, PII inference, prompt-type tagging, `record_feedback`. |
| [services/ai_schemas.py](../services/ai_schemas.py) | JSON-schema validation for structured outputs (mapping, design studio, doc classify, etc.). |
| [services/ai_memory.py](../services/ai_memory.py) | RAG memory abstraction on top of `AIEmbeddingStore`. Similarity search, scope filters. |
| [services/embeddings.py](../services/embeddings.py) | Pluggable embedding provider (Ollama default; OpenAI-compatible alternative). |
| [services/ai_permissions.py](../services/ai_permissions.py) | Per-role / per-task / per-tenant permission resolver. |
| [apps/platform_runtime/ai_governance.py](../apps/platform_runtime/ai_governance.py) | Effective AI enablement: env × tenant policy × content sensitivity. |
| [apps/platform_runtime/ai_providers.py](../apps/platform_runtime/ai_providers.py) | Provider protocol + runtime config + Ollama stub. |
| [apps/siteconfig/models_ai.py](../apps/siteconfig/models_ai.py) | `RegionalAIConfig`, `AIModelRegistry`, `AIEmbeddingStore`, `AIPromptRegistry`, `AIGatewayMetric`. |
| [apps/siteconfig/ai_assistants.py](../apps/siteconfig/ai_assistants.py) | Unified assistant registry (9 named assistants, permission-gated). |
| [apps/portal/views_ai_gateway.py](../apps/portal/views_ai_gateway.py) | All 27 `/api/ai/*` endpoints. Rate limiting, permission checks, audit, embedding retrieval. |
| [apps/portal/views_ai_copilot.py](../apps/portal/views_ai_copilot.py) | Copilot chat, health probe (`/api/ai/health/`), audit feed (`/api/ai-copilot/audit/`). |

---

## 3. Bounded-context AI surfaces

Each bounded context that consumes AI has a single, dedicated wrapper
module. Cross-context imports are forbidden by the bounded-context
linter (`scripts/lint_bounded_context_imports.py --strict`).

| Context | Wrapper | Surface | Status |
|---|---|---|---|
| Migration Cloud | [apps/migration_cloud/ai_bridge.py](../apps/migration_cloud/ai_bridge.py) | Source classifier, domain classifier, layered field mapper, auto-transformers | ✅ Wired |
| Finance | [apps/finance/ai_categorize.py](../apps/finance/ai_categorize.py) | Bank statement unmatched-entry categorization | ✅ Wired |
| People | [apps/people/ai_dedup.py](../apps/people/ai_dedup.py) | Duplicate person record proposal (weighted score + AI tiebreak) | ✅ Wired |
| Automation | [apps/automation/ai_workflow_suggest.py](../apps/automation/ai_workflow_suggest.py) | Workflow studio "Ask AI" — intent to validated node list | ✅ Wired |
| Dashboard | [apps/dashboard/services/insight_anomalies.py](../apps/dashboard/services/insight_anomalies.py) `_enrich_with_ai_narrative` | One-line LLM next-step suggestion on each anomaly card | ✅ Wired |
| Analytics ML | [apps/analytics/ml/](../apps/analytics/ml/) (train_at_risk.py, synthetic_at_risk_dataset.py) | Sklearn at-risk classifier; joblib artifact at `AT_RISK_MODEL_PATH` | ✅ Wired |
| Policy / handbook RAG | `ingest_policy_documents` mgmt command + `views_console_ai_rag.py` admin endpoint | Bulk ingest tenant handbook → AIEmbeddingStore; queried via `semantic_search` and `policy_explain` endpoints | ✅ Wired |

---

## 4. The 27 `/api/ai/*` endpoints

All in [apps/portal/views_ai_gateway.py](../apps/portal/views_ai_gateway.py).
Each is rate-limited, permission-gated, and audited. See
[AI_DOMAIN_ASSISTANT_REGISTRY.md](AI_DOMAIN_ASSISTANT_REGISTRY.md) for
the per-endpoint detail.

| # | Endpoint | TaskType | Caller surface |
|---|---|---|---|
| 1 | `/api/ai/setup-assistant/` | `CONFIG_EXPLAIN` | First-run setup wizard |
| 2 | `/api/ai/workflow-draft/` | `WORKFLOW_DRAFT` | Workflow studio "Ask AI" |
| 3 | `/api/ai/policy-explain/` | `POLICY_EXPLAIN` | Handbook / policy reader |
| 4 | `/api/ai/document-classify/` | `DOC_CLASSIFY` | Document upload pipeline |
| 5 | `/api/ai/semantic-search/` | `SEMANTIC_SEARCH` | Global KB search |
| 6 | `/api/ai/migration-suggest/` | `MIGRATION_MAPPING` | Migration Cloud mapper |
| 7 | `/api/ai/admin-copilot/` | `ADMIN_COPILOT` | Backend admin sidebar copilot |
| 8 | `/api/ai/theme-recommend/` | `SETUP_RECOMMEND` | Design Studio theme picker |
| 9 | `/api/ai/feature-control-explain/` | `CONFIG_EXPLAIN` | Feature flag console |
| 10 | `/api/ai/report-recommend/` | `SETUP_RECOMMEND` | Report studio template picker |
| 11 | `/api/ai/design-studio-draft/` | `DESIGN_STUDIO` | Design Studio canvas drafts |
| 12 | `/api/ai/live-preview-explain/` | `CONFIG_EXPLAIN` | Live preview overlay |
| 13 | `/api/ai/system-config-explain/` | `RUNTIME_CONFIG_EXPLAIN` | System settings overlay |
| 14 | `/api/ai/dashboard-pack-recommend/` | `SETUP_RECOMMEND` | Dashboard pack picker |
| 15 | `/api/ai/support-assistant/` | `SUPPORT_SUGGEST` | Support inbox triage |
| 16 | `/api/ai/tenant-maturity/` | `NARRATIVE` | Tenant readiness card |
| 17 | `/api/ai/data-quality-assistant/` | `NARRATIVE` | Data quality remediation |
| 18 | `/api/ai/marketplace-recommend/` | `SETUP_RECOMMEND` | App-marketplace recommendations |
| 19 | `/api/ai/control-plane-intelligence/` | `ADMIN_COPILOT` | Control plane operator copilot |
| 20 | `/api/ai/interop-assistant/` | `INTEROP_ASSISTANT` | Integration setup helper |
| 21 | `/api/ai/runtime-config-explain/` | `RUNTIME_CONFIG_EXPLAIN` | RuntimeDefaults explainer |
| 22 | `/api/ai/observability-assistant/` | `OBSERVABILITY_ASSISTANT` | Observability narrative |
| 23 | `/api/ai/billing-usage-explain/` | `BILLING_USAGE_EXPLAIN` | Billing usage card |
| 24 | `/api/ai/trust-compliance-assistant/` | `TRUST_COMPLIANCE_ASSISTANT` | SOC 2 / compliance explainer (local-only) |
| 25 | `/api/ai/studio-os-assistant/` | `STUDIO_OS_ASSISTANT` | Studio OS shell copilot |
| 26 | `/api/ai/feedback/` | (feedback sink) | Accept / edit / dismiss capture |
| 27 | `/api/ai/health/` | (probe) | Live health probe (cached 60s) |

Plus three implicit premium-tier tasks not exposed as their own endpoint
(invoked from inside backend tasks): `RISK_EXPLAIN`, `TEACHER_COMMS_DRAFT`,
`REPORT_CARD_COMMENT`.

---

## 5. Governance — three controls in series

Every call is gated by all three. If any returns "disabled" the call
short-circuits to the deterministic fallback.

1. **Platform.** Env `RUNMYCAMPUS_AI_ENABLED`. If unset, AI off everywhere.
2. **Tenant.** `School.settings["ai_policy"]` JSON:
   - `tenant_ai_enabled` (bool, default true)
   - `allow_external_providers` (bool, default false — local-only)
   - `allow_external_student_pii` (bool, default false)
3. **Content.** Helper detects `high_pii` from inputs and forces
   local-only backends, regardless of tenant choice.

Resolution lives in
[apps/platform_runtime/ai_governance.py](../apps/platform_runtime/ai_governance.py).

---

## 6. Audit + metric — what we log

| Sink | Granularity | Retention |
|---|---|---|
| `AIActionAuditLog` | Per request (action, user, task_type, tier, outcome, latency_ms, request_id) | Per audit policy |
| `AIGatewayMetric` | Daily rollup (date, tenant, task_type, tier, cost_class, request_count, latency_sum, failure_count, schema_validation_failures, review_count, accepted_count, manual_correction_count) | Permanent |
| Django cache | Real-time (`ai:metrics:{date}:{tenant}:{task}:{tier}:{cost_class}`) | 3 days |

**No prompt content, no response text, no user query is persisted to
audit.** `_redact_audit_meta` strips them in
[apps/portal/views_ai_gateway.py](../apps/portal/views_ai_gateway.py).

---

## 7. Safety controls

- **Prompt-injection regex.** `services/ai_gateway.py` blocks
  "ignore previous instructions", "jailbreak", "override safety",
  "reveal system prompt", and ~15 similar patterns.
- **PII inference.** `services/ai_helpers.looks_like_pii` checks
  column names and sample values; matches force `content_sensitivity="high_pii"`.
- **High-PII routing.** Any `high_pii` call ignores tenant
  `allow_external_providers` and uses local backends only.
- **Permission gating.** Every endpoint resolves
  `get_ai_permission_for_user()`; 403 if denied.
- **Structured output validation.** `services/ai_schemas.py` enforces
  JSON schema for 10 task types; schema_validation_failures roll up
  to `AIGatewayMetric` for review.
- **Rate limiting.** Per-user, per-window in
  `views_ai_copilot.py` (`RATE_LIMIT_PER_MIN`, `RATE_LIMIT_WINDOW`).

---

## 8. Health probe

`GET /api/ai/health/` (wired in `config/urls.py`, `config/tenant_urls.py`,
`config/manager_urls.py`, `config/public_urls.py`):

```json
{
  "success": true,
  "reachable": true,
  "provider": "ollama",
  "latency_ms": 47,
  "fallback_active": false,
  "degraded": false,
  "checked_at": "2026-05-14T15:00:00Z",
  "preference": ["ollama", "vllm", "litellm", "anthropic", "rules"],
  "rules_fallback_enabled": true
}
```

Cached 60s server-side. Drives the floating copilot's "limited mode"
badge ([static/js/rmc-ai-health-pill.js](../static/js/rmc-ai-health-pill.js)).

---

## 9. Command palette ⌘K integration

The platform-wide ⌘K palette
([static/js/rmc-command-palette.js](../static/js/rmc-command-palette.js))
has three AI hooks:

1. **"Open AI Copilot" item.** Dispatches `rmc:cmdk:open-ai`, which
   clicks `#aiCopilotTrigger`.
2. **"Ask AI: <query>" fallback** (added 2026-05-14). When no items
   match the user's typed query, the palette shows an "Ask AI"
   row that opens the copilot prepopulated with the query. Avoids the
   dead-end "No matches" state.
3. **AI-related navigation items.** Per-shell `rmc-cmdk-data` JSON
   exposes "Workflow Studio", "Design Studio", "Migration Cloud",
   "Insights" so users jump straight to the AI-bearing pages.

---

## 10. Operator workflows

| I want to… | Do this |
|---|---|
| Bulk-ingest a tenant's handbook into RAG | `python manage.py ingest_policy_documents --school <uuid> --path /path/to/policies` — or from the console: **Settings → AI → Ingest policy docs** |
| Dry-run an ingest | Add `--dry-run` |
| See real-time AI usage | Query `AIGatewayMetric` for today |
| Disable AI for a tenant | Set `school.settings["ai_policy"]["tenant_ai_enabled"] = False` |
| Restrict tenant to local-only | Set `school.settings["ai_policy"]["allow_external_providers"] = False` |
| Add a new TaskType | (1) Append to `TaskType` enum in `services/ai_gateway.py`. (2) Set tier policy in `DEFAULT_TASK_TIERS`. (3) Add schema in `services/ai_schemas.py` if structured. (4) Add caller via `services/ai_helpers.invoke_task`. (5) Expose endpoint in `apps/portal/views_ai_gateway.py` if user-facing. (6) Document here. |
| Check provider health | `curl /api/ai/health/` |
| Re-train the at-risk model | `python apps/analytics/ml/train_at_risk.py` (synthetic) or with `--csv path/to/real.csv` |

---

## 11. What is *not* yet implemented

These are tracked, deliberately out-of-scope for the current wave, or
external dependencies:

| Gap | Owner | Why deferred |
|---|---|---|
| Regional Ollama hot-swap (RegionalAIConfig live failover) | Platform | Model + registry exist; production smoke-test needs a second region |
| LoRA adapter training pipeline | ML | At-risk classifier (sklearn) is the only ML model today; LoRA needs custom-tenant data volume that no tenant has produced yet |
| Voice / speech AI surfaces | Future | No 2026 commitment |
| Image generation in-product | Marketing pipeline only | See [AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md](AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md); in-product image gen has no current use case |
| Acceptance-rate dashboard from `AIGatewayMetric` | Observability | Data is captured; the analyst surface is a separate wave |

---

## 12. Related SOTs

- [AI_DOMAIN_ASSISTANT_REGISTRY.md](AI_DOMAIN_ASSISTANT_REGISTRY.md) — per-endpoint reference
- [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md) — capability-flag contract
- [AI_surface_audit.md](AI_surface_audit.md) — surface-by-surface §2.3 compliance audit
- [AI_audit_trail_and_permissions.md](AI_audit_trail_and_permissions.md) — audit + permissions
- [AI_MODEL_LIFECYCLE.md](AI_MODEL_LIFECYCLE.md) — sovereign-stack model sync
- [AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md](AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md) — marketing AI media
- [ML_AT_RISK_TRAINING.md](ML_AT_RISK_TRAINING.md) — at-risk model training pipeline
- [MIGRATION_CLOUD_AI.md](MIGRATION_CLOUD_AI.md) — Migration Cloud AI architecture
- [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md) — security threat model
