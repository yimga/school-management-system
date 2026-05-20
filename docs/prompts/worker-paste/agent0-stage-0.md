# WORKER PASTE — Agent0 (Stage 0)

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

# Stage 0 — Current-State Validation

**Pack:** `2026-05-20-orchestrator-v5`  
**Prerequisites:** [`00-global-execution-rules.md`](00-global-execution-rules.md), [`00-platform-wide-clause.md`](00-platform-wide-clause.md), [`00-moderator-addendum.md`](00-moderator-addendum.md), [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md), [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md), [`00-gear-up-v5-transformational.md`](00-gear-up-v5-transformational.md)

**Also run:** [`phase-0-p0-deploy-gate.md`](phase-0-p0-deploy-gate.md) status folded into readiness JSON.

---

## ROLE

You are the RunMyCampus Current-State Validation and Execution Planner.

## MISSION

Inspect the current repo before any aggressive refactor. Determine exactly what exists, what is missing, what is stale, what is already fixed, and what must be protected before Stage 1 starts.

---

## PLATFORM-WIDE CLAUSE

Apply the full clause from [`00-platform-wide-clause.md`](00-platform-wide-clause.md).

---

## TASKS

### 1. Inspect current repo state

```bash
git branch --show-current
git status --short
git diff --stat
git diff --check
git rev-parse --short HEAD
```

### 2. Inspect SOT and proof artifacts

Read:

- [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (latest §11.4 batch)
- [`docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md)
- [`docs/generated/system_closure_map.json`](../generated/system_closure_map.json)
- [`docs/generated/category_scope_review.json`](../generated/category_scope_review.json)
- [`docs/generated/external_dependencies_register.json`](../generated/external_dependencies_register.json)
- [`docs/generated/route_surface_audit.json`](../generated/route_surface_audit.json)
- [`docs/generated/security_surface_audit.json`](../generated/security_surface_audit.json)
- [`docs/generated/tenant_isolation_audit.json`](../generated/tenant_isolation_audit.json)
- [`docs/generated/architecture_certification_scorecard.json`](../generated/architecture_certification_scorecard.json)
- [`docs/generated/orchestrator_gap_burndown.json`](../generated/orchestrator_gap_burndown.json)

### 3. Confirm latest status

Record: latest SOT batch, repo verdict, external blockers, Render/live status, migration-cloud status, security exception status, Phase 0 deploy status.

### 4. Build execution map

Create/update:

- [`docs/generated/aggressive_stage_execution_readiness.json`](../generated/aggressive_stage_execution_readiness.json)
- [`docs/generated/aggressive_stage_execution_readiness.md`](../generated/aggressive_stage_execution_readiness.md)
- [`docs/generated/orchestrator_execution_matrix.json`](../generated/orchestrator_execution_matrix.json)
- [`docs/generated/orchestrator_gap_burndown.json`](../generated/orchestrator_gap_burndown.json)

For each stage 0–10: existing files, tests, artifacts, gaps, risk, scope, blockers. Include **seven-pillar** status and **phase0_deploy** block.

### 5. Run baseline gates (Stage 0 stack — no luxury UI yet)

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
python scripts/verify_migration_files_tracked.py
python scripts/verify_ai_engine_room.py
python scripts/verify_five_pillar_platform_completion.py
python scripts/verify_six_pillar_global_dominance.py
```

### 6. Product code policy

Do **not** change product code unless a baseline gate is broken and must be fixed before Stage 1 (e.g. duplicate SOT batch id).

## ACCEPTANCE

- Execution map covers all stages 0–10 + Phase 0 + seven pillars
- All baseline verifiers run with PASS/FAIL recorded
- Verdict is exactly one of:
  - **READY FOR STAGE 1**
  - **NOT READY FOR STAGE 1**

## PILLAR

**P6** DevOps readiness included in JSON.

---

## GEAR-UP V3 — ESCALATION LAYER (mandatory)

Read [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md), [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md), and [`00-gear-up-v5-transformational.md`](00-gear-up-v5-transformational.md).

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





---

## SOT VERDICT (return exactly one)

`READY FOR STAGE 1 | NOT READY FOR STAGE 1`

---

## STANDARD FINAL REPORT

Use A–L from global rules. Include `REPORT BACK TO ORCHESTRATOR` footer.


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

# Phase 0 — P0 Deploy Gate

**Owners:** Moderator + Agent 0 (fixes may delegate to Agent 1)  
**Blocks:** LIVE deploy claims until `phase0_deploy: READY` in readiness JSON

---

## MISSION

Close Render predeploy blockers before the nine-agent wave claims production readiness.

---

## STAGED DELIVERABLES

| File | Role |
|------|------|
| [`apps/automation/migrations/0018_workflow_trigger_offline_action.py`](../../apps/automation/migrations/0018_workflow_trigger_offline_action.py) | Shipped migration |
| [`apps/analytics/management/commands/bootstrap_at_risk_registry.py`](../../apps/analytics/management/commands/bootstrap_at_risk_registry.py) | Tenant-aware predeploy bootstrap |
| [`.gitignore`](../../.gitignore) | `!**/migrations/*Conflict*.py` |
| [`scripts/verify_migration_files_tracked.py`](../../scripts/verify_migration_files_tracked.py) | CI guard |
| [`scripts/release/render_predeploy.sh`](../../scripts/release/render_predeploy.sh) | Predeploy orchestrator |

---

## KNOWN FIX

`BootstrapRegistryTests.test_skips_unknown_operator` — explicit `--operator-username` missing must return `None` (no superuser fallback) in `_resolve_operator`.

---

## VALIDATION

```bash
python scripts/verify_migration_files_tracked.py
python manage.py test apps.analytics.tests.test_operator_commands.BootstrapRegistryTests --settings=config.settings --noinput
# After user-approved commit/push only:
bash scripts/release/render_predeploy.sh
```

Expect: `migrate_schemas` → `verify_all_migrations_applied` → `bootstrap_at_risk_registry` (no ProgrammingError)

---

## ACCEPTANCE CHECKLIST (100%)

- [ ] All migration files tracked — `verify_migration_files_tracked.py` PASS
- [ ] `BootstrapRegistryTests` 5/5 green
- [ ] `render_predeploy.sh` green OR honest `BLOCKED_EXTERNAL` with log in readiness JSON
- [ ] Recorded in `aggressive_stage_execution_readiness.json` as `phase0_deploy: READY|BLOCKED`

---

## SOT

Moderator records Phase 0 in §11.4 batch **1319** scope (with Stage 0) after checklist green.


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


### Phase 0 V5
- Journey manifest + nav ledger generated before Stage 1 agents start.


---

# PILLAR PASTE BUNDLE (this agent)

## Prompt 6 — Cloud DevOps & Platform Reliability (P6)

**Agents:** 0, 1, Moderator

**Paste:** [`scripts/release/render_predeploy.sh`](../../scripts/release/render_predeploy.sh), [`docs/DEPLOY_PIPELINE_RUNBOOK.md`](../DEPLOY_PIPELINE_RUNBOOK.md), [`architectural-boundaries.yml`](../../.github/workflows/architectural-boundaries.yml), `verify_migration_files_tracked.py`

**Note:** Render bash predeploy — K8s sections N/A unless Dockerfile exists.

---

