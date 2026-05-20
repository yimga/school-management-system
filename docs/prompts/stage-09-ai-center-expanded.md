# Stage 9 — API Center + AI Center Expanded (19 Phases)

**Pack:** `2026-05-20-orchestrator-v2`  
**Agent:** 9 | **SOT batch:** 1328 | **Pillar:** P4

**Prerequisites:** Stages 1, 4, 8 accepted. Paste global rules + platform clause + **Stage 9 replacement header** from [`00-platform-wide-clause.md`](00-platform-wide-clause.md).

---

## ROLE

You are the RunMyCampus Platform-Wide API Center, AI Center, Knowledge Engine, Automation, Integration, and Governed Ollama Engineer.

## MISSION

Upgrade the API Center into the central command hub for RunMyCampus intelligence, developer experience, automation, integrations, and governed AI assistance.

**This is not a chatbot task.** The AI Center must become first-line support, technical writer, tenant copilot, operator assistant, KB generator, support deflection, and zero-hallucination intelligence layer.

## NON-NEGOTIABLE AI RULES

1. **Zero hallucination** — missing from app ledger → `FEATURE CODESPACE DISCONNECT: This feature does not exist in the active RunMyCampus app ledger.`
2. **Missing context** — not in KB → `DATA DEFAULTER: This specific platform detail is missing from my current knowledge base.`
3. **Audience separation** — operators get architecture; tenants get simple steps + escalation.
4. **No fluff** — facts, steps, tables only.
5. **Permission-filtered** — tenant, role, permissions, route, flags, entitlements.

Extend existing `services/ai/` engine room (batch 1294/1317) — do not duplicate.

---


## PHASE 1 — API Center + AI Center discovery

Inspect: `apps/apicenter/`, `apps/api/`, `apps/automation/`, `apps/orchestration/`, `apps/events/`, `apps/sync_engine/`, `apps/integrations_marketplace/`, `apps/marketplace/`, `apps/observability/`, `apps/feedback/`, `apps/studio_os/`, `apps/migration_cloud/`, `services/`, `config/urls.py`, `config/manager_urls.py`, `config/tenant_urls.py`, AI/Ollama/Celery settings.

**Create:** [`docs/generated/api_ai_center_discovery.json`](../generated/api_ai_center_discovery.json), [`.md`](../generated/api_ai_center_discovery.md)

---

## PHASE 2 — API Center open-and-usable certification

Routes: `/apicenter/`, `/apicenter/docs/`, `/apicenter/keys/`, `/api/schema/`, `/api/schema/ui/`, `/configuration/integrations/`, `/super/developers/` (if present).

Each route: purpose, primary action, auth boundary, scopes, no dummy UI, mobile-safe.

**Create:** [`docs/generated/api_center_open_usable_audit.json`](../generated/api_center_open_usable_audit.json), [`.md`](../generated/api_center_open_usable_audit.md)

**Tests:** `apps.apicenter.tests.test_api_center_open_and_usable`, `apps.platform_runtime.tests.test_integration_center_links`, `apps.api.tests.test_api_schema_ui_contracts`

---

## PHASE 3 — Ollama Modelfile governance

**Create/update:**

- [`ai/Modelfile`](../../ai/Modelfile)
- [`docs/architecture/RUNMYCAMPUS_AI_CENTER.md`](../architecture/RUNMYCAMPUS_AI_CENTER.md)
- [`docs/generated/ai_center_modelfile_audit.json`](../generated/ai_center_modelfile_audit.json)
- [`docs/generated/ai_center_modelfile_audit.md`](../generated/ai_center_modelfile_audit.md)

**Baseline Modelfile** (do NOT claim "studied codebase perfectly" — indexed knowledge only):

```text
FROM llama3.1:8b
PARAMETER temperature 0.0
PARAMETER top_p 0.1
PARAMETER num_ctx 65536

SYSTEM """
You are the RunMyCampus AI Center Core Engine. Governed, permission-filtered platform assistant.

Answer only from indexed RunMyCampus knowledge, route metadata, schema metadata, generated proof artifacts, approved documentation, and permission-filtered tenant context.

If absent from active app ledger:
FEATURE CODESPACE DISCONNECT: This feature does not exist in the active RunMyCampus app ledger.

If not in indexed knowledge base:
DATA DEFAULTER: This specific platform detail is missing from my current knowledge base.

Managers: technical routes, services, audit implications.
Tenants: simple steps, page paths, safe escalation.
Never expose secrets, API keys, tokens, passwords, cross-tenant data.
Never perform destructive actions.
"""
```

---

## PHASE 4 — Platform inventory ingestion pipeline

**Create:** [`scripts/generate_ai_center_inventory.py`](../../scripts/generate_ai_center_inventory.py)

**Outputs:** [`docs/generated/ai_center_platform_inventory.json`](../generated/ai_center_platform_inventory.json), [`.md`](../generated/ai_center_platform_inventory.md)

Inventory: apps, routes, hosts, views, templates, permissions, models, services, proof artifacts, SOT status, flags — **metadata only**, no secrets/PII.

**Tests:** `services.ai.tests.test_ai_center_inventory_redaction` OR `apps.apicenter.tests.test_ai_center_inventory_redaction`

---

## PHASE 5 — RAG / knowledge base indexing contract

**Pluggable:** `services/ai_center/indexing.py` OR `apps/apicenter/ai_center/indexing.py`

Interfaces: `build_platform_index()`, `index_document()`, `search_platform_knowledge()`, `search_by_route()`, `search_by_role()`, `search_by_module()`, `get_feature_evidence()`, `get_missing_context_reason()`

**Create:** [`docs/generated/ai_center_indexing_contract.json`](../generated/ai_center_indexing_contract.json), [`.md`](../generated/ai_center_indexing_contract.md)

---

## PHASE 6 — Permission-filtered AI query service

**File:** `services/ai_center/query_service.py` — `answer_platform_question(user, tenant, role, route_context, question, audience)`

Output: answer, audience, route_context, evidence, missing_context, feature_absent, confidence, safety_flags, audit_id.

Must enforce: FEATURE CODESPACE DISCONNECT, DATA DEFAULTER, cross-tenant block, AI disabled fallback, no secrets in prompt/answer.

---

## PHASE 7 — Ollama client

**File:** `services/ai_center/ollama_client.py`

Settings: `AI_GATEWAY_ENABLED`, `AI_GATEWAY_PROVIDER=ollama`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL=ai-center-master`, `AI_CENTER_LOG_PROMPTS=False`, `AI_CENTER_MAX_CONTEXT_DOCS`, `AI_CENTER_TIMEOUT_SECONDS`

Circuit breaker; no prompt logging by default.

---

## PHASE 8 — KB / FAQ generation engine

**File:** `services/ai_center/kb_generator.py`

Functions: `generate_kb_article_from_route`, `generate_kb_article_from_code_change`, `generate_faqs_for_module`, `generate_tenant_guide`, `generate_operator_runbook`, `generate_release_note_from_feature`, `propose_help_topics_from_errors`, `propose_faqs_from_feedback`

**Draft by default** — human review before tenant-visible publish.

Routes: `/super/ai-center/kb-drafts/`, `/super/ai-center/generate-kb/`, `/super/ai-center/faq-candidates/`

---

## PHASE 9 — Contextual in-app micro-insights

`get_contextual_tip(user, tenant, route, module, current_state)` — UI marker `data-ai-contextual-insight`

Surfaces: Migration Cloud, setup, billing, feedback, API Center, Studio OS, configuration, marketplace, offline sync.

---

## PHASE 10 — Behavioral friction analysis

**File:** `services/ai_center/friction_analysis.py`

**Create:** [`docs/generated/ai_center_friction_analysis.json`](../generated/ai_center_friction_analysis.json), [`.md`](../generated/ai_center_friction_analysis.md)

Route: `/super/ai-center/friction/`

---

## PHASE 11 — AI Center UI

Routes: `/super/ai-center/`, `/inventory/`, `/kb-drafts/`, `/friction/`, `/settings/`, `/query/`; tenant `/school/help/ai/` (feature-flagged)

Apple-class; health pill; offline banner; no dummy buttons.

Integrate existing: `templates/siteconfig/partials/ai_center_body.html`, `static/js/rmc-ai-health-pill.js`, `verify_ai_engine_room.py`.

---

## PHASE 12 — API payload contracts

[`docs/architecture/RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md`](../architecture/RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md)

[`docs/generated/ai_center_api_contracts.json`](../generated/ai_center_api_contracts.json), [`.md`](../generated/ai_center_api_contracts.md)

---

## PHASE 13 — Audit / observability / safety

Events: `ai_query_submitted`, `ai_answer_generated`, `ai_missing_context`, `ai_feature_absent`, `ai_kb_draft_created`, `ai_kb_draft_published`, `ai_contextual_tip_generated`, `ai_friction_topic_detected`, `ai_gateway_error`, `ai_gateway_disabled_fallback`

**Create:** [`docs/generated/ai_center_audit_observability.json`](../generated/ai_center_audit_observability.json), [`.md`](../generated/ai_center_audit_observability.md)

---

## PHASE 14 — Security tests (required list)

```text
apps.apicenter.tests.test_ai_center_security
apps.apicenter.tests.test_ai_center_permission_filtering
apps.apicenter.tests.test_ai_center_kb_generation
apps.apicenter.tests.test_ai_center_contextual_insights
apps.apicenter.tests.test_ai_center_friction_analysis
apps.apicenter.tests.test_ai_center_ollama_client
apps.apicenter.tests.test_ai_center_api_contracts
```

Must prove: no cross-tenant context; no secrets; disabled fallback; FEATURE/DATA fallbacks; KB drafts need evidence; tenant KB not auto-published.

---

## PHASE 15 — Browser QA

`tests/e2e/ai-center.spec.js` — super AI center, apicenter, integrations, school help AI.

---

## PHASE 16 — Generated proof bundle

- `api_automation_integration_certification.json/md`
- `ai_automation_api_engine_room_certification.json/md`
- `ai_center_platform_inventory.json/md`
- `ai_center_friction_analysis.json/md`
- `ai_center_audit_observability.json/md`
- `api_ai_center_discovery.json/md`
- `api_center_open_usable_audit.json/md`
- `ai_center_modelfile_audit.json/md`
- `ai_center_indexing_contract.json/md`
- `ai_center_api_contracts.json/md`

---

## PHASE 17 — Tests

```bash
python manage.py test apps.apicenter.tests apps.api.tests apps.automation.tests apps.events.tests apps.feedback.tests apps.marketplace.tests apps.observability.tests --settings=config.settings --noinput --keepdb
python scripts/run_sqlite_memory_tests.py apicenter,ai
```

---

## PHASE 18 — Verifiers

Standard stack + **`python scripts/verify_ai_engine_room.py`** → PASS

---

## PHASE 19 — SOT / log

**Verdict:** `API CENTER + AI CENTER READY — REPO SCOPE`

Caveats: live Ollama = EXTERNAL unless `verify_ollama_live.py` run on host; RAG freshness = last index run.

---

## FINAL REPORT (Stage 9 — A through U)

| Section | Topic |
|---------|-------|
| A | API/AI discovery |
| B | API Center open-and-usable |
| C | Modelfile governance |
| D | Inventory pipeline |
| E | RAG/indexing contract |
| F | Permission-filtered query service |
| G | Ollama client |
| H | KB/FAQ generation |
| I | Contextual micro-insights |
| J | Friction analysis |
| K | AI Center UI |
| L | API payload contracts |
| M | Audit/observability |
| N | Security tests |
| O | Browser QA |
| P | Generated proof |
| Q | Tests |
| R | Verifiers |
| S | SOT/log |
| T | Remaining gaps |
| U | Verdict: FAILURE / API CENTER + AI CENTER PARTIAL / API CENTER + AI CENTER READY — REPO SCOPE |

---

## APPENDIX A — Existing engine room (extend, do not fork)

Batch **1294** shipped `services/ai/` engine room. Before building parallel systems, wire AI Center phases to:

| Module | Path |
|--------|------|
| Gateway | `services/ai/gateway.py` via `services/ai_helpers.py` |
| Prompts | `services/ai/prompts.py` |
| Knowledge | `services/ai/knowledge.py` |
| Command bar | `services/ai/command_bar.py`, `apps/portal/views_command_bar.py` |
| Product assistants | `services/ai/product_assistants.py` |
| Portal views | `apps/portal/views_ai_gateway.py`, `apps/siteconfig/views_ai_center.py` |
| UI partial | `templates/siteconfig/partials/ai_center_body.html` |
| Gate | `scripts/verify_ai_engine_room.py` |

App code under `apps/` must route AI through `services/ai_helpers` — not `services.ai_gateway` directly (`scan_ai_gateway_boundary.py` baseline 0).

---

## APPENDIX B — Settings contract (env via os.environ.get only)

| Setting | Purpose |
|---------|---------|
| `AI_GATEWAY_ENABLED` | Master switch |
| `AI_ALLOW_RULES_FALLBACK` | Offline/rules tier when Ollama down |
| `AI_GATEWAY_PROVIDER` | `ollama` when live |
| `OLLAMA_BASE_URL` | Default `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | e.g. `ai-center-master` from Modelfile |
| `AI_CENTER_LOG_PROMPTS` | Default False |
| `AI_CENTER_MAX_CONTEXT_DOCS` | RAG slice limit |
| `AI_CENTER_TIMEOUT_SECONDS` | Request timeout |
| `AI_ENGINE_ROOM_SUPPORT` | Engine room feature flag |
| `ENABLE_AI_KNOWLEDGE_INDEX_BEAT` | Celery index beat |
| `ENABLE_OLLAMA_MODEL_SYNC_BEAT` | Weekly model sync |

Document every new setting in `.env.example` with operator comments.

---

## APPENDIX C — Honest deferrals (do not fake closed)

| Item | Classification |
|------|----------------|
| Live Ollama inference on production host | EXTERNAL — `verify_ollama_live.py` |
| Render LIVE SHA parity | EXTERNAL — GAP-EXT-001 |
| Live PSP settlement | EXTERNAL |
| SOC2/PCI certificates | EXTERNAL |
| Auto-publish tenant KB without human review | FORBIDDEN |
| Destructive AI actions (delete, pay, impersonate) | FORBIDDEN |
| Full codebase in prompt without inventory | FORBIDDEN |

---

## APPENDIX D — Cross-links to SOT batches (context)

- **1317** — Support pipeline + KB embeddings + SSE
- **1294** — AI engine room tiers 1–5
- **1247–1249** — AI Center UX, offline vs Ollama
- **1298** — Platform chromatic compliance (AI Center tables)

When closing Stage 9, reference which batches your work extends in SOT draft line.

---

## APPENDIX E — Service worker / static deploy checklist

If Stage 9 ships new CSS/JS for AI Center:

1. Bump `static/js/service-worker.js` `CACHE_VERSION` to `sms-vX.Y.Z-<slug>-YYYY-MM-DD`
2. Wire scripts in all four dashboard shells if shell-level
3. Record wave in `docs/CSS_RETIREMENT_DOCKET.md`
4. Run `verify_service_worker_version.py --check-monotonic`

---

## APPENDIX F — Phase 14 security test matrix (expanded)

| Test case | Expected |
|-----------|----------|
| Tenant A user asks about Tenant B school | Blocked / empty context |
| Tenant user asks for `/super/` route internals | FEATURE CODESPACE DISCONNECT or audience filter |
| Question references nonexistent app | FEATURE CODESPACE DISCONNECT |
| Indexed docs empty for topic | DATA DEFAULTER |
| `AI_GATEWAY_ENABLED=0` | Rules/disabled message; no HTTP to Ollama |
| Prompt contains API key in user message | Redacted; not logged |
| KB draft without evidence IDs | Rejected |
| Auto-publish tenant article | Blocked — draft only |
| Manager query from tenant host | Audience still tenant-safe unless operator role |
| `verify_ai_engine_room` regression | PASS after changes |

---

## APPENDIX G — Generated artifact path checklist (copy for report H)

```text
docs/generated/api_ai_center_discovery.json
docs/generated/api_ai_center_discovery.md
docs/generated/api_center_open_usable_audit.json
docs/generated/api_center_open_usable_audit.md
docs/generated/ai_center_modelfile_audit.json
docs/generated/ai_center_modelfile_audit.md
docs/generated/ai_center_platform_inventory.json
docs/generated/ai_center_platform_inventory.md
docs/generated/ai_center_indexing_contract.json
docs/generated/ai_center_indexing_contract.md
docs/generated/ai_center_friction_analysis.json
docs/generated/ai_center_friction_analysis.md
docs/generated/ai_center_audit_observability.json
docs/generated/ai_center_audit_observability.md
docs/generated/ai_center_api_contracts.json
docs/generated/ai_center_api_contracts.md
docs/generated/api_automation_integration_certification.json
docs/generated/api_automation_integration_certification.md
docs/generated/ai_automation_api_engine_room_certification.json
docs/generated/ai_automation_api_engine_room_certification.md
docs/architecture/RUNMYCAMPUS_AI_CENTER.md
docs/architecture/RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md
ai/Modelfile
scripts/generate_ai_center_inventory.py
```

---

## APPENDIX H — Ambition guardrails (Stage 9)

**Do not:** claim sub-millisecond AI; bypass webhook retry queues; let AI run migrations; store source SIS credentials in AI context; mark vendor live connectors production_ready without tests.

**Do:** keep ambition aggressive; produce measurable proof; extend `verify_ai_engine_room.py` if new surfaces added; run `audit_template_render_safety.py` after template changes.

---

## REPORT BACK TO ORCHESTRATOR

Paste this block at the end of every worker session (max 40 lines body + verdict):

```text
STAGE: <N>
AGENT: <id>
GIT_SHA: <short>
SOT_BATCH_DRAFT: <131X if proposing>

A — Discovery: <what was inspected>
B — Gaps found: <count + top 3>
C — Fixes made: <summary>
D — Security/tenant: <PASS|FAIL + note>
E — UI/UX: <PASS|N/A + note>
F — Tests: <commands + OK/FAIL counts>
G — Verifiers: <list + PASS/FAIL>
H — Artifacts: <docs/generated/*.json paths>
I — SOT draft: <one-line verdict string only — Moderator commits>
J — Remaining gaps: <honest partials + EXTERNAL>
K — Files changed: <count + top paths>
L — Verdict: FAILURE | PARTIAL | READY — FOCUSED REPO SCOPE | READY — REPO SCOPE

RERUN_REQUIRED: yes|no
BLOCKERS: <none|list>
```

Moderator updates [`docs/generated/orchestrator_execution_matrix.json`](../generated/orchestrator_execution_matrix.json) after accepting a stage.

---

## GEAR-UP V3 — ESCALATION LAYER (mandatory)

Read [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md).

## GEAR-UP V3 — PLATFORM ESCALATION (all agents)

**Pack:** `2026-05-20-orchestrator-v3` — supersedes v2 execution bar. **100% means 100%** for repo-contained work; EXTERNAL must be labeled, never faked.

### Cross-cutting quality bar (every stage)

1. **Zero-click contract** — every list/table/wizard: primary action, next-best action, empty state with CTA, no dead `href="#"` / `javascript:void(0)`.
2. **Page fold discipline** — long pages: `data-rmc-page-fold-nav="required"`, numbered pagination on catalogs (`data-rmc-scroll-policy="paginate"`); run `python scripts/verify_page_fold_standards.py` when templates change.
3. **Interaction integrity** — run `python scripts/verify_interaction_integrity_contract.py` on touched portal/control-plane templates.
4. **Observability** — security/tenant/AI/finance events emit structured logs or metrics via `apps/observability/metrics.py` (no PII in labels).
5. **Before/after proof** — each certification JSON must include `v3_delta` with: `findings_before`, `findings_after`, `tests_added`, `verifiers_green`.
6. **Competitor parity row** — one honest table vs PowerSchool / Blackbaud / Veracross / FACTS / generic SIS (what we match, what is EXTERNAL).
7. **No hardcoding** — route through 7-layer configurability; no new inline hex in templates (token/CSS only).
8. **Second-pass challenge** — after implementation, re-read your artifacts as a hostile reviewer; document what you would break.

### V3 verifier additions (run when in scope)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/verify_platform_chromatic_compliance.py
```

North Star target: **75/75 ELITE** (not 71/75) before Stage 10 can claim READY.


## GEAR-UP V4 — CATEGORY-DEFINING BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v4` — supersedes v3. Compete with PowerSchool + Blackbaud + Veracross + Shopify-grade ops UX.

### Non-negotiables (repo-contained)

1. **All gaps CLOSED** — every OPEN row in `orchestrator_gap_burndown.json` fixed or reclassified with proof.
2. **All verifiers GREEN** — standard stack + v3/v4 additions; zero new baseline regressions.
3. **Security** — `audit_security_surface.py`, `audit_tenant_isolation.py`, `scan_tenant_queryset_safety --compare` (0), `pip_audit` or documented CVE allowlist in `security_exception_register.json`.
4. **Hygiene** — `ruff check apps services scripts --select F401,F841,E711` on touched paths; no dead imports; no duplicate helper modules.
5. **Redundancy** — grep for parallel implementations; consolidate into canonical module (document in artifact `v4_deduplication_log.json`).
6. **Live Ollama** — operator permission granted: run `ollama serve`, `ollama pull llama3.1:8b`, `ollama create ai-center-master -f ai/Modelfile`, `python scripts/verify_ollama_live.py --strict --invoke`; artifact `docs/generated/ollama_live_proof.json`.
7. **Render LIVE** — ask user for `RENDER_API_KEY` + service ID only when needed; until then `render_parity` stays EXTERNAL with honest checklist in cert JSON.
8. **North Star** — `run_northstar_audit.py` → **75/75 DOMINANT** (hard gate).
9. **Competitive matrix** — each stage cert JSON adds `v4_competitive_wins[]` (3+ measurable wins vs named SIS).

### V4 verifier bundle (run all applicable)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/run_northstar_audit.py
python scripts/verify_ollama_live.py --strict --invoke
python scripts/verify_ai_engine_room.py
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/scan_money_float.py --compare
python scripts/scan_tenant_queryset_safety.py --compare
python scripts/scan_pii_logging_smell.py --compare
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

Add to certification JSON:

```json
"v4": {
  "prompt_pack_version": "2026-05-20-orchestrator-v4",
  "gaps_closed": [],
  "verifiers_all_green": true,
  "hygiene_ruff_exit": 0,
  "security_audit_exit": 0,
  "competitive_wins": []
}
```


### Stage 9 V4
- **Live Ollama required:** `verify_ollama_live.py --strict --invoke` PASS.
- `ollama_live_proof.json` with model, latency_ms, FEATURE/DATA fallback sample outputs.
- Phases 20–24 from v3 + vector KB tenant isolation test.
- No duplicate `services/ai` vs `services/ai_center` gateways.
