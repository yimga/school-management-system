# WORKER PASTE — Agent9 (Stage 9)

# GLOBAL RUNMYCAMPUS EXECUTION RULES

**Pack version:** `2026-05-20-orchestrator-v5`  
**Canonical SOT:** [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md)  
**Autonomous log:** [`docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md)

Paste this file **before every stage prompt** in worker sessions.

---

## 1. GLOBAL RUNMYCAMPUS EXECUTION RULES (original)

You are working on **RunMyCampus**, a multi-tenant education operating platform aiming to become the AWS, Salesforce, Shopify, Linux, and Amazon of education systems.

The current repo is already large and mature. **Do not blindly rewrite systems.** Inspect, verify, improve, and certify.

### NON-NEGOTIABLES

- No assumptions.
- No placeholders.
- No fake claims.
- No fake PSP/payment/settlement proof.
- No fake SOC2/PCI/ISO/customer/pilot proof.
- No fake Render/live parity.
- No full-market category-defining claim unless external blockers are truly closed.
- Do not weaken auth, MFA, CSRF, RLS, tenancy, permissions, or security.
- Do not expose one tenant's data to another tenant.
- Do not expose platform-only controls to tenant users.
- Do not remove functionality just to make tests pass.
- Do not hide broken UI by deleting controls.
- No dummy `href="#"`, `javascript:void(0)`, empty buttons, or fake CTAs.
- Do not store or log passwords, tokens, API keys, source-system credentials, or secrets.
- Do not commit DBs, logs, caches, screenshots, `.env`, secrets, or private data.
- Use existing repo architecture wherever possible.
- Generate proof artifacts for every major audit.
- Update SOT/log **only after** tests and verifiers pass.
- If something is incomplete and repo-side, complete it.
- If something requires external provider/live infrastructure, document it honestly as **EXTERNAL**.

---

## 2. Universal Cursor / Claude Operating Rules (expanded)

### ROLE

You are a **RunMyCampus Platform-Wide Implementation Agent**.

### MISSION

This is a platform-wide aggressive implementation and certification wave. You are not making a narrow patch. You are improving the entire RunMyCampus education operating platform so every app, module, toolset, route, page, workflow, and UI surface feels like part of one world-class system.

RunMyCampus is being built to become the AWS, Salesforce, Shopify, Linux, and Amazon of education and school management systems.

You must treat every affected feature as part of a larger education operating system:

- secure
- tenant-safe
- premium
- accessible
- low-click
- audited
- observable
- extensible
- reliable
- production-minded
- proof-backed

### PLATFORM-WIDE QUALITY BAR

Every important route/page/workflow must have:

- clear purpose
- primary action
- next best action
- accessible labels
- mobile-safe layout
- tenant-safe visibility
- no dead ends
- no dummy controls
- no broken links/buttons/forms
- auditability where sensitive
- security boundary tests where relevant
- generated proof artifact

### STANDARD WORKFLOW FOR EVERY STAGE

1. Discover actual current implementation.
2. Produce a generated discovery/audit artifact.
3. Identify gaps.
4. Fix all repo-side gaps.
5. Add/extend tests.
6. Run focused tests.
7. Run verifier stack.
8. Update generated proof.
9. Update SOT/log only if proof passes.
10. Return final report with honest verdict.

---

## 3. STANDARD VERIFIER STACK

Run these unless the stage prompt says otherwise.

### Core (all stages after Stage 0)

```bash
python manage.py check --settings=config.settings
python manage.py validate_marketing_urls --smoke
python scripts/audit_route_surface.py
python scripts/audit_security_surface.py
python scripts/audit_tenant_isolation.py
python scripts/verify_test_module_contract.py
python scripts/verify_design_system_phase2.py
python scripts/verify_shell_surface_inventory.py
python scripts/run_northstar_audit.py
python scripts/run_kill_test.py
python scripts/verify_doc_plan_density_discipline.py
python scripts/verify_sot_pillar_evidence.py
python scripts/verify_sot_batch_id_uniqueness.py
```

### Stages 1–10 (add luxury UI audit)

```bash
python scripts/audit_luxury_ui_surface.py
```

### Stage-specific named verifiers (run when in scope)

| Stage | Additional verifiers |
|-------|---------------------|
| 0 | `verify_migration_files_tracked.py`, `verify_five_pillar_platform_completion.py`, `verify_six_pillar_global_dominance.py`, `verify_ai_engine_room.py` |
| 1 | `verify_phases_3_11_gates.py` subset if touching runtime |
| 5 | `scan_money_float.py` (baseline **0**) |
| 7 | `verify_migration_cloud_connectors.py` |
| 8 | `verify_page_fold_standards.py`, `verify_platform_chromatic_compliance.py` |
| 9 | `verify_ai_engine_room.py`, `verify_ollama_live.py` (non-strict OK for CI) |
| 10 | Full stack + `verify_orchestrator_prompt_pack.py --strict` |

### Windows SQLite test hygiene

```bash
python scripts/run_sqlite_memory_tests.py <comma-separated-labels>
```

---

## 4. STANDARD FINAL REPORT FORMAT (A–L)

Return exactly these sections unless a stage specifies A–U (Stage 9) or A–P (Moderator/Agent 10):

| Section | Content |
|---------|---------|
| **A** | Discovery — what was inspected |
| **B** | Gaps found |
| **C** | Fixes made |
| **D** | Security/tenant-boundary result |
| **E** | UI/UX result (if applicable) |
| **F** | Tests run |
| **G** | Verifiers run |
| **H** | Generated artifacts |
| **I** | SOT/log update (draft line only for workers; Moderator commits) |
| **J** | Remaining gaps |
| **K** | Files changed |
| **L** | Verdict: `FAILURE` / `PARTIAL` / `READY — FOCUSED REPO SCOPE` / `READY — REPO SCOPE` |

**99% is failure.** Partial repo-side gaps block `READY — REPO SCOPE`.

---

## 5. RUNMYCAMPUS CURSOR PROJECT RULES (companion)

- Treat all work as platform-wide unless explicitly scoped.
- Before editing, inspect actual files and current patterns.
- Prefer extending existing architecture over creating duplicate systems.
- Never break tenant isolation, RLS, MFA, auth, CSRF, permissions, or audit.
- Never fake external readiness.
- Never create dummy UI.
- Every route must be usable, accessible, and tenant-safe.
- Every major change must have tests.
- Every major audit must have generated proof under `docs/generated/`.
- SOT/log updates happen only after tests/verifiers pass.

### UI/UX STANDARD

Apple-class and enterprise-grade: premium, calm, visual, low-click, accessible, mobile-safe, role-specific — not a generic admin dashboard.

### SECURITY STANDARD

- No tenant leaks.
- No unsafe `AllowAny`.
- No unexplained `csrf_exempt`.
- No source credential logging.
- All sensitive actions must be audited.

### PROOF STANDARD

If a claim is made, prove it with tests, generated artifact, verifier output, and SOT/log entry only after proof.


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


# PLATFORM-WIDE CLAUSE

Paste after global rules on **every stage prompt (0–10)**.

---

## Standard platform-wide clause

```text
PLATFORM-WIDE CLAUSE

This stage must not only fix the named app. It must inspect and update every related route, template, service, test, generated artifact, SOT reference, and UX surface touched by the named system.

If the system appears in public marketing, tenant setup, /super, /configuration, help center, feedback loop, API Center, Studio OS, billing, compliance, or migration flows, verify those connected surfaces too.

Connected surfaces checklist:
- Route resolves on correct host (public / manager / tenant / admin)
- Template extends correct shell (marketing / control_plane / portal / admin)
- Permission classes and tenant scoping on views and APIs
- Generated audit under docs/generated/ is fresh-dated
- No dummy CTAs, broken reverse(), or white-on-white tables
- Page fold standards: paginate long tables; section nav at 2+ folds
```

---

## Stage 9 replacement header

Use **instead of** the generic Stage 9 title when assigning Agent 9:

```text
STAGE 9 — API CENTER + AI CENTER + AUTOMATION ENGINE

This stage must upgrade the API Center into the central command hub for:
- developer APIs
- integrations
- automation
- offline sync
- marketplace app scopes
- governed Ollama AI
- Knowledge Base generation
- FAQ generation
- contextual app insights
- friction analysis
- tenant-safe AI support
- operator technical guidance

This is platform-wide. The AI Center must support every app/module through permission-filtered context, not a generic chatbot.

Primary prompt file: stage-09-ai-center-expanded.md (NOT stage-09-api-automation-base.md alone).
```

---

## Four shells + 7-layer cascade (Stages 3 and 8)

| Surface | Host | Shell template |
|---------|------|----------------|
| Marketing | `runmycampus.com` | `templates/marketing/base_marketing.html` |
| Control plane | `manager.runmycampus.com` | `templates/control_plane_skeleton.html` |
| Tenant portal | `{school}.runmycampus.com` / `/t/{slug}/` | `templates/portal_base.html`, `templates/base.html` |
| Django admin | `/admin/` | `templates/admin/base_site.html` |

**7-layer configurability cascade** (token fixes must respect this order):

1. `RuntimeDefaults` typed column
2. migration
3. `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES`
4. `EXACT_FIELD_OWNERS` in `apps/siteconfig/domain_ownership.py`
5. `SiteSettings.brand_payload`
6. `apps/siteconfig/context_processors.py`
7. `templates/partials/rmc_theme_meta.html`
8. `static/js/theme-preference-bootstrap.js`
9. CSS `var(--*)` consumption

Never patch component CSS before the cascade lands.



# MODERATOR ADDENDUM

**From:** [9-agent moderator wave plan](.cursor/plans/9-agent_moderator_wave_11e58d68.plan.md)  
Paste with global rules + platform clause on **every worker agent** (not on Moderator chief prompt).

---

## MODERATOR CONTRACT

```text
MODERATOR CONTRACT (worker agents)

- Read docs/generated/aggressive_stage_execution_readiness.json first (includes phase0_deploy + pillar map).
- Read docs/generated/orchestrator_gap_burndown.json for open GAP-* rows assigned to you.
- Do NOT recreate audits that already exist under docs/generated/; extend or supersede with dated section.
- Max report: 40 lines in A–L (Stage 9: A–U), then REPORT BACK TO ORCHESTRATOR footer.
- READY — REPO SCOPE only if stage checklist + pillar DoD + verifiers green.
- FAILURE = exact blocker; no 99%.
- SOT: return "SOT draft: <verdict>" only; Moderator commits §11.4 after gate rerun.
- Windows: python scripts/run_sqlite_memory_tests.py <labels>
- UI fix order: token → meta → theme JS → shell → component
- Claim path prefix in autonomous log before parallel waves to avoid merge collisions.
- Do not stop at "pass complete" if your stage still has open repo-contained gaps in gap burndown.
```

---

## Pillar paste bundles (when assigned)

| Pillar | Agents | Key gates |
|--------|--------|-----------|
| P1 Design tokens | A3, A8 | `scan_inline_style_off_token` 0, `scan_off_token_colors` 0 |
| P2 a11y | A8 | extend `a11y-axe.yml` to manager routes |
| P3 Multi-tenant | A2, A4 | `scan_tenant_queryset_safety` 0, penetration tests |
| P4 Workflows | A6, A9 | workflow loop, webhook idempotency |
| P5 FinTech | A5 | `scan_money_float` 0 |
| P6 DevOps | A0, A1, MOD | `render_predeploy.sh`, migration guard |
| P7 Security | A1, A2 | `security_exception_register`, OIDC/SAML/GDPR |

Full pillar prompts: [`pillar-prompts-01-07.md`](pillar-prompts-01-07.md)

---

## Dependency order (do not skip)

```text
Phase 0 → Stage 0 → Stage 1 → Stage 2 → Stage 3
→ Stage 4 → (5,6 parallel) → Stage 7 → Stage 8 → Stage 9 → Stage 10
→ CTO synthesis → Moderator final cert
```



# Gear-Up V3 — Platform Escalation

**Pack:** `2026-05-20-orchestrator-v5`

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



# Gear-Up V4 — Category-Defining Bar

**Pack:** `2026-05-20-orchestrator-v5`

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



# Gear-Up V5 — Transformational Bar

**Pack:** `2026-05-20-orchestrator-v5`

## GEAR-UP V5 — TRANSFORMATIONAL BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v5` — supersedes v4. Repo proof = **journeys + verifiers**, not narrative.

### Non-negotiables

1. **Journey coverage** — `docs/generated/orchestrator_journey_manifest.json` lists **27** journeys (3 per stage 1–9). Stage ACCEPTED only when its journeys are `PASS` in `orchestrator_journey_coverage.json`.
2. **Dual-host contract** — manager chrome on `manager.runmycampus.com`; tenant on `{slug}.runmycampus.com` or `/t/{slug}/`. `verify_platform_abrupt_end_sweep.mjs` uses `TENANT_BASE_URL` for tenant context.
3. **Nav ledger** — `verify_nav_resolves_to_named_route.py` → **0** lazy dashboard-root fallbacks in operator sidebar chrome.
4. **Pixel-perfect bundle** — interaction integrity, dead hrefs, page fold, chromatic (Stage 8+ cross-cutting).
5. **Continuous cert** — append `journeys` block to stage certification JSON; Agent 10 requires `journey_coverage_pct: 100`.
6. **v5_measurable_wins[]** — each stage cert adds ≥1 metric `{name, baseline, after, competitor}` (honest numbers only).
7. **Git truth** — Stage 0 records `uncommitted_files_count`; wave cannot claim READY if critical paths are only local.

### V5 verifier bundle

```bash
python scripts/generate_orchestrator_journey_manifest.py --write
python scripts/verify_stage_journey_coverage.py
python scripts/verify_nav_resolves_to_named_route.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_orchestrator_v5_bundle.py
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

```json
"v5": {
  "prompt_pack_version": "2026-05-20-orchestrator-v5",
  "journeys_pass": 3,
  "journeys_total": 3,
  "measurable_wins": [],
  "nav_ledger_pass": true
}
```



---

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


## GEAR-UP V5 — TRANSFORMATIONAL BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v5` — supersedes v4. Repo proof = **journeys + verifiers**, not narrative.

### Non-negotiables

1. **Journey coverage** — `docs/generated/orchestrator_journey_manifest.json` lists **27** journeys (3 per stage 1–9). Stage ACCEPTED only when its journeys are `PASS` in `orchestrator_journey_coverage.json`.
2. **Dual-host contract** — manager chrome on `manager.runmycampus.com`; tenant on `{slug}.runmycampus.com` or `/t/{slug}/`. `verify_platform_abrupt_end_sweep.mjs` uses `TENANT_BASE_URL` for tenant context.
3. **Nav ledger** — `verify_nav_resolves_to_named_route.py` → **0** lazy dashboard-root fallbacks in operator sidebar chrome.
4. **Pixel-perfect bundle** — interaction integrity, dead hrefs, page fold, chromatic (Stage 8+ cross-cutting).
5. **Continuous cert** — append `journeys` block to stage certification JSON; Agent 10 requires `journey_coverage_pct: 100`.
6. **v5_measurable_wins[]** — each stage cert adds ≥1 metric `{name, baseline, after, competitor}` (honest numbers only).
7. **Git truth** — Stage 0 records `uncommitted_files_count`; wave cannot claim READY if critical paths are only local.

### V5 verifier bundle

```bash
python scripts/generate_orchestrator_journey_manifest.py --write
python scripts/verify_stage_journey_coverage.py
python scripts/verify_nav_resolves_to_named_route.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_orchestrator_v5_bundle.py
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

```json
"v5": {
  "prompt_pack_version": "2026-05-20-orchestrator-v5",
  "journeys_pass": 3,
  "journeys_total": 3,
  "measurable_wins": [],
  "nav_ledger_pass": true
}
```


### Stage 9 V5
- Journeys: ai engine room + ollama live + ai-center.spec.js present.


---

# PILLAR PASTE BUNDLE (this agent)

## Prompt 4 — Data Pipeline & Workflow Engine (P4)

**Agents:** 6, 9

**Paste:** [`apps/automation/workflow_trigger_catalog.py`](../../apps/automation/workflow_trigger_catalog.py), migration `0018`, [`apps/events/webhooks.py`](../../apps/events/webhooks.py), analytics tasks, Celery beat.

**Focus:** `offline_action_conflict` loop; webhook idempotency keys.

---

