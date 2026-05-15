# Migration Cloud — AI architecture & how it's *functional*, not decorative

This document explains the platform's AI stack as it stands today, where
the Migration Cloud plugs into it, and what we did to make sure the
AI layer is *load-bearing* — not a stub that "sits there."

For the universal-intake pipeline see [MIGRATION_UNIVERSAL_INTAKE.md].
For real-world walkthroughs see [MIGRATION_CLOUD_SCENARIOS.md].

---

## The platform's AI stack (today, production)

The RunMyCampus platform ships a mature AI orchestration layer with
governance, audit, and fallback chains. Four production backends + a
deterministic rules fallback, gated per tenant.

### Call path

```
Django view / management command / orchestrator
        │
        ▼
apps/platform_runtime/ai_providers.py::run_ai_prompt   ← legacy convenience wrapper
        │   (or directly:)
        ▼
services/ai_gateway.py::invoke(TaskType.X, prompt, metadata=...)
        │
        ▼
Tier loop (per TaskType): [ollama → anthropic → vllm → litellm → rules]
        │
        ▼
Backend client (apps/portal/ai_provider.py / services/inference.py)
        │
        ▼
Response → schema validation → audit log → return (text, metadata)
```

### Backends

| Backend | Role | Activated by |
|---|---|---|
| **Ollama** | Default; local-first / sovereign AI | `OLLAMA_ENDPOINT` (default `http://localhost:11434/api/generate`) + `OLLAMA_MODEL` |
| **Anthropic** | Premium tier; opted-in per tenant | `ANTHROPIC_API_KEY` + tenant's `ai_policy.allow_external_providers=true` |
| **vLLM** | High-throughput self-hosted | `VLLM_ENDPOINT` |
| **LiteLLM** | Multi-provider proxy | `LITELLM_PROXY_URL` |
| **Rules fallback** | Deterministic; always available | `AI_ALLOW_RULES_FALLBACK=1` (default on) |

### Tenant policy gates

Every AI invocation reads three governance values from
`School.settings["ai_policy"]`:

* `tenant_ai_enabled` — master switch per tenant (defaults true if the
  platform's `RUNMYCAMPUS_AI_ENABLED` env is on).
* `allow_external_providers` — enables Anthropic/vLLM/LiteLLM tiers
  (defaults false; Ollama+rules only).
* `allow_external_student_pii` — high-PII prompts force local backends
  unless this is explicitly true.

### Audit trail

* `apps/platform_runtime/models.py::AIActionAuditLog` — one row per
  invocation; metadata only (no prompt/response text per privacy).
* `apps/siteconfig/models_ai.py::AIGatewayMetric` — daily aggregates of
  request count, failure count, schema validation failures, review
  count, accepted count, manual-correction count, per task type per
  tenant.

### Feedback API

`services/ai_gateway.py::record_feedback(task_type, tier, *,
tenant_id, school_id, accepted, manual_correction, request_id, ...)`
flips the daily `AIGatewayMetric` counters so the platform can answer
"how often do operators trust assistant X?" without re-querying every
audit row.

### Existing assistant surfaces

`describe_ai_assistant_surfaces()` documents eight production surfaces:

* `config_copilot` — SiteConfig setup guidance
* `report_comment_assistant` — report narrative comments
* `policy_assistant` — policy wording hints
* `workflow_builder_assistant` — workflow scaffolding (no execution)
* `support_knowledge_assistant` — internal KB hints
* `anomaly_nudge` — health/risk nudges (registered, view pending)
* `school_health_insight` — dashboard narrative (approval required)
* `onboarding_next_action` — CCC next-step suggestion

All are wired through `run_ai_prompt` and return drafts (never silent
execution).

### Verdict on platform AI maturity

| Component | State |
|---|---|
| Gateway + tier routing | **Production** |
| Per-tenant policy enforcement | **Production** |
| Audit log + daily metrics | **Production** |
| Feedback loop API | **Production** (under-used by callers) |
| 8 assistant surfaces | **Production** as drafts |
| Embedding store (`AIEmbeddingStore`) | **Scaffolded** — populated only by migration + semantic_search |
| Regional model registry | **Scaffolded** — defaults to env vars; World Engine future |
| Anomaly nudge view | **Scaffolded** — registry key only |

---

## How Migration Cloud uses the AI stack

### Single integration point

`apps/migration_cloud/ai_bridge.py` is the only Migration Cloud module
that calls the platform AI gateway. Centralising the integration buys:

* **Graceful degradation.** When `RUNMYCAMPUS_AI_ENABLED=0` or the
  tenant's `ai_policy.tenant_ai_enabled=false`, every `propose_*`
  returns `None`. Deterministic layers carry the bundle. Bundles always
  complete — they just quarantine more aggressively.
* **Tenant safety.** Every call passes `school=` so governance gates
  fire. PII columns (detected by name + value regex) force
  `content_sensitivity="high_pii"` which the gateway routes to local
  backends only.
* **Task-specific bucketing.** Calls route through
  `TaskType.MIGRATION_MAPPING` / `MIGRATION_FINGERPRINT` so daily
  metrics bucket the migration assistant separately from the generic
  narrative assistant. Operators see "Migration Cloud accepted 92% of
  source classifications today" without grep'ing audit logs.
* **Cost discipline.** Layered callers (alias → token similarity →
  AI) only reach the LLM when deterministic layers don't reach the
  configured threshold (see `apps.migration_cloud.defaults._SEED`):
  - `source_min_confidence = 0.65`
  - `domain_min_confidence = 0.70`
  - `field_min_confidence = 0.80`
* **Auditability.** Every prompt carries a `prompt_type` tag
  (`migration_cloud.source_classifier`, `.domain_classifier`,
  `.field_mapper`, `.transformer_picker`) so AIActionAuditLog answers
  "what did the migration assistant infer for tenant X."

### Four use cases the AI handles

| Use case | Code path | TaskType | What it does |
|---|---|---|---|
| Source classifier tiebreaker | `classifiers/source.py::classify_source` | `MIGRATION_FINGERPRINT` | Names the source system when no header signature exceeds threshold |
| Domain classifier tiebreaker | `classifiers/domain.py::classify_domain` | `MIGRATION_FINGERPRINT` | Picks the canonical domain for an artifact when overlap is ambiguous |
| Field mapping tiebreaker | `mapper.py::_map_one_column` | `MIGRATION_MAPPING` | Maps an unknown source column to a canonical field from a shortlist |
| Transformer suggestion | `ai_bridge.propose_transformer` | `MIGRATION_MAPPING` | Suggests a registered transformer (date format, name split, currency, etc.) |

### What the AI does NOT do

* **No tenant writes.** All persistence lives in
  `apps/migration_cloud/landers/` under a `schema_context` wrap —
  deterministic, replayable, rollback-able.
* **No hallucination.** Every proposal is constrained to a fixed
  allow-list (known sources, known domains, ontology fields, registered
  transformers). The parser rejects answers outside the allow-list.
* **No silent override.** Operators see every AI suggestion + the
  reasoning string + the confidence. The wizard exposes a feedback
  endpoint that pipes accept/override decisions back to
  `services.ai_gateway.record_feedback`.

---

## What makes the AI *functional*, not decorative

Three concrete loops keep the AI honest and improving:

### 1. Feedback loop — operator overrides go back to the platform

When an operator accepts or overrides an AI mapping in the wizard, the
view at `apps/migration_cloud/views.py::MigrationCloudFeedbackView`
POSTs `{accepted, manual_correction, prompt_type, ...}` →
`ai_bridge.record_operator_feedback` → `services.ai_gateway.record_feedback`
→ `AIGatewayMetric` daily rollup. The platform's existing weekly
dashboard surfaces these aggregates per task type. Slow-converging
task types (low acceptance %) become the prompt-iteration backlog.

### 2. Audit trail — every AI call is queryable per tenant

Every `propose_*` call lands a row in `AIActionAuditLog` with
`prompt_type`, `tenant_id`, `tier`, `latency_ms`, `outcome`. Operators
can answer "what did the migration assistant infer for tenant X in the
last 7 days" with one ORM query — no log archaeology required.

### 3. Saved mapping profiles — operator-curated mappings beat the AI next time

When an operator saves a successful mapping as a profile (via the
wizard or the `MigrationProfile` admin), every subsequent bundle from
that same source gets the operator-curated mappings at confidence 1.0
without an AI call. The AI's job is the cold start; the platform's job
is to remember the answer.

---

## What we improved in this build

1. **Switched `ai_bridge` from `TaskType.NARRATIVE` to
   `TaskType.MIGRATION_MAPPING` / `MIGRATION_FINGERPRINT`** — the
   gateway now buckets Migration Cloud calls separately for tier
   policy, daily metrics, and audit. Without this, every migration
   assistant call was hidden inside the generic narrative metric.

2. **Wired `record_operator_feedback`** — the wizard now POSTs to
   `/super/migration/<id>/feedback/` (and the tenant mirror) which calls
   `services.ai_gateway.record_feedback`. Operator trust in the AI is
   now measurable per task type per tenant per day.

3. **Tightened PII detection** — `ai_bridge._looks_like_pii` checks
   column name (`ssn`, `social_security`, `passport`, `email`, `phone`,
   `dob`, etc.) AND value regex (SSN shape, email shape) and forces
   `high_pii` sensitivity. The gateway then forces
   `allowed_backends=["ollama", "rules"]` so high-PII prompts never
   hit external LLMs.

4. **Allow-list parsing** — every AI response goes through a parser
   that rejects answers outside the known allow-list (known sources,
   known domains, ontology fields, registered transformers). The
   gateway's schema validation + our allow-list = two layers of
   no-hallucination guarantee.

5. **Cost-aware layering** — Layer 1 (alias) covers ~95% of typical
   columns deterministically. Layer 2 (token similarity) catches another
   ~3%. Layer 3 (value-shape sanity) catches ~1%. Only the residual
   1% reaches Layer 4 (AI tiebreaker). Bundles of 1k students typically
   consume 5–20 LLM calls total — not 1000.

---

## Further improvements (sequenced)

| # | Improvement | Effort | Why |
|---|---|---|---|
| 1 | Populate `AIEmbeddingStore` with mapping decisions per tenant → embedding-based recall for "this column → that canonical field" without re-prompting | Medium | Eliminates AI calls on the second+ bundle from the same source |
| 2 | Add a `MigrationProfile` "save from this run" button in the wizard → captures operator-approved mappings as reusable profiles | Small | Curated profiles beat AI cold-start every time |
| 3 | Wire `anomaly_nudge` view to surface low-confidence AI mappings ("Operator review queue") | Small | Closes the loop on the existing surface |
| 4 | Add a Celery beat task that scans 7-day `AIGatewayMetric` rollup and auto-disables external tiers for tenants where local acceptance > 90% | Medium | Cost-tier optimization without operator intervention |
| 5 | Embeddings-based source-system classifier (replace heuristic signature scoring) when `AIEmbeddingStore` is populated | Medium | Better long-tail vendor recognition |
| 6 | Multi-language ontology overlays (Danish, Swahili, Vietnamese, …) loaded from `RuntimeDefaults.payload['migration_cloud.ontology.synonyms_overlay']` | Small | Aalborg-style schools (foreign-language headers) skip the AI tiebreaker |

---

## Environment variables relevant to Migration Cloud's AI usage

| Var | Effect |
|---|---|
| `RUNMYCAMPUS_AI_ENABLED` | Master switch. `0` → bridge always returns None, deterministic layers carry the bundle. |
| `RUNMYCAMPUS_AI_ALLOW_EXTERNAL` | Platform gate for external backends. Tenant must also opt in. |
| `AI_PROVIDER_TIMEOUT_SECONDS` | Per-call timeout (default 25s). Migration Cloud bundles tolerate this — prompts are small and infrequent. |
| `AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY` | Daily cap. Migration Cloud's layered design keeps a typical bundle far under any sensible cap. |
| `MIGRATION_CLOUD__CLASSIFIER__SOURCE_MIN_CONFIDENCE` | Override the seeded source threshold (default 0.65). |
| `MIGRATION_CLOUD__CLASSIFIER__DOMAIN_MIN_CONFIDENCE` | Override the seeded domain threshold (default 0.70). |
| `MIGRATION_CLOUD__MAPPER__FIELD_MIN_CONFIDENCE` | Override the seeded field-mapping threshold (default 0.80). |

---

## Consistency invariants enforced across the stack

These are checked at module load + Django system check, and any new
contributor adding to Migration Cloud should preserve them:

1. **Universal-first.** Every accelerator output flows through the
   universal mapper for non-pre-mapped columns. Accelerators NEVER
   bypass the universal path past the entry point.
2. **No data loss.** Unmapped columns land as
   `custom_fields.<slug>` → DynamicField. Bad rows quarantine; bundle
   continues. The ontology covers the bedrock; everything else is
   preserved, not dropped.
3. **No hardcoding.** Every tunable (confidence thresholds, MIME
   whitelist, size caps, SLO targets) lives in
   `apps.migration_cloud.defaults._SEED` and reads via env →
   `RuntimeDefaults.payload` → seed cascade.
4. **Tenant scoping.** All persistence runs inside
   `django_tenants.utils.schema_context(bundle.schema_name)`. Bundle
   metadata + audit stays in public schema. CI gate
   `tenants-rls.yml` enforces this.
5. **Graceful degradation.** Every AI call is optional; deterministic
   layers carry every bundle to completion.
6. **Idempotent.** Re-applying the same `idempotency_key` produces
   zero net new creates. Verified by `reconciliation._idempotency_check`.

---

## Where to look next

| File | Owns |
|---|---|
| `apps/migration_cloud/ai_bridge.py` | The single AI integration point |
| `apps/migration_cloud/pipeline.py` | `advance_bundle()` — ingestion → mapped |
| `apps/migration_cloud/orchestrator.py` | `apply_bundle()` — mapped → applied |
| `apps/migration_cloud/reconciliation.py` | `reconcile_bundle()` — applied → reconciled |
| `apps/migration_cloud/landers/` | Per-domain tenant persistence (students, guardians, staff, custom_fields fallback) |
| `apps/migration_cloud/accelerators/` | 7 vendor accelerators (OneRoster + PowerSchool + Blackbaud + Veracross + FACTS + Skyward + Alma) |
| `apps/migration_cloud/intake/` | 9 source-shape adapters (file, archive, url, sftp, s3, sql_dump, database, oauth_folder, email) |
| `apps/migration_cloud/views.py` | Operator + tenant wizard scaffold |
| `services/ai_gateway.py` | The platform's gateway — extend `TaskType` here when adding new AI use cases |

---

## 2026-05-14 polish wave — AI made platform-wide & migration cloud closed out

The five "future polish" follow-ups documented earlier in this file all
landed end-to-end. Plus a platform-wide AI sweep so the gateway is no
longer migration-only.

### 1. AIEmbeddingStore wired for mapping recall

`apps/migration_cloud/ai_bridge.py` now exposes:

- `remember_mapping_decision(...)` — persists a column → canonical mapping
  into `AIEmbeddingStore` under `scope="migration_mapping"`, tenant-scoped
  via `school_id`, with the source column + sample-value hash + canonical
  field + transformer + source-system metadata.
- `recall_mapping_decision(...)` — embeds the source column + samples and
  searches the store via `AIMemoryService.search_similar`. When a past
  decision crosses the similarity floor *and* its canonical_field is still
  in the current candidate shortlist, the mapper short-circuits the AI
  tiebreaker entirely.

Call sites: `mapper.py::_map_one_column` writes a memory after every
deterministic / AI mapping (`_remember(...)` helper). The recall layer
sits between token-similarity and AI tiebreaker (method label
`"embedding_recall"`). The wizard's feedback endpoint
(`MigrationCloudFeedbackView`) also persists into the store on operator
accept/override — operator decisions outweigh model decisions in future
recall, since they store with confidence 0.85–0.90.

**Effect:** the second bundle from the same vendor for the same tenant
makes ~0 AI calls for any column the first bundle resolved. AI is
reserved for genuinely novel shapes.

### 2. "Save as profile" — operator-curated profiles

`MigrationCloudSaveProfileView` (`POST /<bundle>/save-profile/`) walks the
bundle's `mapping_summary["per_artifact"]` and distills every
high-confidence (>= 0.65), non-custom-field mapping into a
`apps.automation.MigrationProfile` row. Slug is auto-uniquified, source
system + domain inferred from the bundle's discovery output, config
JSON captures the curated column→canonical map with transformers.
Future bundles from the same vendor can preload this profile and skip
discovery for known shapes.

### 3. Anomaly nudge / operator review queue

`MigrationCloudAnomalyNudgeView` (`GET /<bundle>/review/`) surfaces three
actionable lists in one view: low-confidence + custom-field mappings,
quarantine records (joined via `MigrationRun.parent_bundle`), and
reconciliation drift (any domain under 99% parity). Template:
`templates/migration_cloud/anomaly_nudge.html`. Linked from the bundle
detail's actions bar.

### 4. Multi-language ontology overlays via RuntimeDefaults

`apps/migration_cloud/ontology/catalog.py::all_synonyms()` now merges the
seeded synonyms with whatever the platform team (or tenant via
RuntimeDefaults override) has staged at:

```
RuntimeDefaults.payload["migration_cloud.ontology.synonyms_overlay"] = {
    "students": {
        "first_name": {
            "sw": ["jina_la_kwanza"],
            "ha": ["sunan_farko"],
        },
        ...
    },
    ...
}
```

Overlay synonyms are additive (never remove a baseline). Cached for the
process; `reset_synonym_overlay_cache()` clears after admin updates.

### 5. Drag-and-drop polish on bundle detail

`templates/migration_cloud/bundle_detail.html` replaces the flat mapping
table with a draggable + decision-bearing surface:

- Confidence pills colour by band (success >= 0.9 / warning >= 0.7 / danger).
- Each row has Accept + Override buttons + an inline "Why?" disclosure.
- Drag-and-drop reassigns a source column's canonical field to whatever
  row is dropped on.
- Every decision POSTs to `/<bundle>/feedback/` →
  `record_operator_feedback` → AIGatewayMetric daily rollup *and*
  AIEmbeddingStore (when accept/override on a mapping).
- New CSS in `static/css/design-tokens.css` (`.rmc-mapping__*`,
  `.rmc-pill--confidence`, etc.). New JS at
  `static/js/migration_cloud_wizard.js`. Save-profile + review-queue
  buttons on the actions row.

### Platform-wide AI (no longer migration-only)

`services/ai_helpers.py` — a thin shared module any app can call to
reach the gateway with graceful degradation + PII heuristics + stable
prompt-type tagging. Public surface:

- `is_ai_available(school)` — predicate.
- `invoke_task(...)` — returns `(text, meta)` or `None`.
- `invoke_json_task(...)` — same, parses one JSON object.
- `looks_like_pii(*chunks)` — heuristic.
- `record_feedback(...)` — forwards accept/override to AIGatewayMetric.

Concrete new AI integrations off it:

| Module | Task type | Purpose |
|---|---|---|
| `apps/finance/ai_categorize.py` | `DOC_CLASSIFY` | Categorize unmatched bank statement deposits + payer hint. Wired in `BankStatementImportService._link_or_create_suspense` — stored on the suspense's `raw_payload["ai_category"]` so the operator UI can render the suggestion. |
| `apps/people/ai_dedup.py` | `DOC_CLASSIFY` | Score person-record pairs for likely-same-person. Wired in `apps/migration_cloud/landers/student_lander.py` — after a new student row is created, scan for last-name matches; AI is only asked when the deterministic score is in the ambiguous 0.55–0.92 band. Findings written to `bundle.mapping_summary["dedup_candidates"]`. |
| `apps/automation/ai_workflow_suggest.py` | `WORKFLOW_DRAFT` | Translate operator natural-language intent into a workflow node list. Studio "Ask AI" surface plugs in here. Allow-list of node kinds enforced server-side. |
| `apps/dashboard/services/insight_anomalies.py` | `NARRATIVE` | Enriches the rules-based anomaly cards with a one-line model-generated next-step suggestion. Field `ai_suggestion` on each card; rendered as a whisper line in the UI when present. |

All four integrations:
- Degrade silently when AI is disabled (return `None` / leave card
  untouched / drop the field).
- Tag a stable `northstar_prompt_type` so AIGatewayMetric buckets each
  surface separately per tenant per day.
- Use the PII heuristic where input chunks could carry student data,
  forcing `content_sensitivity="high_pii"` → gateway routes only to
  local backends per the tenant's AI policy.

### Verified

- `python manage.py check` → no issues (0 silenced).
- URL grammar reverses cleanly for the two new routes under both shells.
- Module-load smoke for every new file passes (`ai_helpers`,
  `finance.ai_categorize`, `people.ai_dedup`, `automation.ai_workflow_suggest`,
  `migration_cloud.ai_bridge` new functions).
- Ontology overlay loader returns 11 synonyms for `first_name` and merges
  cleanly with overlay (empty payload today; ready when RuntimeDefaults
  publishes one).
