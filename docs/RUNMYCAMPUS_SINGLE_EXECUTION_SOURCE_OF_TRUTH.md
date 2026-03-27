# RunMyCampus — single execution source of truth

**What this file is:** The only place for **execution strategy, program status, and “what’s left.”** Completion states: `DONE` | `PARTIAL` | `NOT DONE` | `DEPRECATED/REPLACED` | `BLOCKED`. No fake completion. **§12 engineering gate (9.5/10)** and **Wave 8 / Phase I.5 structural bar (11/10)** are **MET** in-repo; **12/10+ market** and **15/10** tiers are **continuous** (not single checkboxes).

**Policy (read once):** Everything in this plan is **non-negotiable** unless **BLOCKED** with owner/reason or **external-only** ([SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) OPEN). Legacy docs that say *optional* mean **required** per [PLAN_POLICY.md](PLAN_POLICY.md). **Depth and polish** ship as **§11.4 slices** (scoped, tested, logged)—not as “stuck PARTIAL” on gates that are already MET.

**Agents:** Before work, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md). Autonomous log: [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md). Full audit narrative: [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md). Stock-take: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6.

**Platform boundary:** [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md). Threats: [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md).

---

## At a glance

| Question | Answer |
|----------|--------|
| **Where is status?** | **§0** (scores), **§11.4** (what’s left + release), **§12** (engineering gate). |
| **What must pass before merge/release?** | `bash scripts/pre_deploy_gate.sh`; record `docs/generated/pre_deploy_gate_run.txt` per [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). |
| **Where is granular file/route work?** | [docs/phase_checklists/](phase_checklists/), [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md). |
| **External / org work (certifications, vendors)?** | [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) — not duplicate open rows here. |

### Documentation map

| Role | File |
|------|------|
| **Canonical execution + status** | **This file** |
| **§0.1.5 external OPEN queue** | [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) |
| **§0.1.5 verification commands** | [SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md](SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md) |
| **Evidence / waves** | [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md), [runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md) |
| **Session log (non-authoritative)** | [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md) |
| **Per-phase checklists** | [docs/phase_checklists/](phase_checklists/) |
| **Template inline styles gate** | `python scripts/report_template_inline_styles.py` → 0 non-exempt flagged blocks |

**Rule:** Other `SOT_*.md` and phase indexes are **subordinate**—no second execution plan. Extend **this file** + external backlog for OPEN; do not spawn parallel “master plans.”

### How to read checkboxes

- **`[x]`** = Done and verified for current scope.
- **`[ ]`** = Required unless superseded by §0.1.5 external-only rule.
- **§6 / §5.x depth:** Many rows are **[x]** at **repo behavioral** bar; **further product depth** = §11.4 slices (not fake `[x]` for unbuilt scope).

---

# 0. Current truth

## Truth statement

RunMyCampus is a **multi-tenant platform**. **§12** and **Wave 8 / Phase I.5** structural bars are **MET** with recorded sign-off. Market leadership vs incumbents is **continuous** (benchmark §0.2)—not one git milestone.

## Current platform state

Global-first product: region/currency/language via `RegionConfig` and school settings—not a single-country app.

## Methodology

Historical **7.3/10** static audit is **superseded** for status. **In-repo** bar = gates in §12 + scripts in CI. **Per production tag:** staging + Phase H / BR-13 + release QA.

## Current score (authoritative)

| Tier | Status |
|------|--------|
| **§12 engineering gate (9.5/10)** | **MET** — §12 checklist + `pre_deploy_gate` |
| **11/10 structural north-star (repo)** | **MET** — Wave 8 internal closure + Phase I.5 + pillar evidence |
| **12/10+ / 15/10** | Continuous product / evidence—not claimed here without §0.2 proof |

## Structural signals (refresh when needed)

Order-of-magnitude repo scale and lint counts: re-run `scripts/lint_raw_sql_usage.py`, `lint_gilead_residue.py`, `generate_platform_inventory.py`, and tree counts when refreshing; do not treat static numbers as gate truth. For **tenant gravity** (SiteSettings, non-migration `cursor.execute`, product `print`, scoped Gilead), prefer **`scoped_gravity_counts`** inside `docs/generated/platform_inventory.json` over gross `baseline_counts`.

### Premium maturity blockers (honest)

| Theme | Status | Next execution hooks |
|-------|--------|----------------------|
| Shell triad (`/admin`, `/super`, `/studio`) | **PARTIAL** | [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md), `verify_shell_architecture_matrix.py`, `verify_phases_3_11_gates.py` |
| `siteconfig` decomposition | **PARTIAL** | [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md), `verify_siteconfig_decomposition_depth.py`, §11.4 Phase B |
| Gilead residue (full tree) | **PARTIAL** | `lint_gilead_residue.py`, `verify_gilead_full_tree_classification.py`; corpus in docs/migrations—[GILEAD_REFERENCE_CLASSIFICATION.md](GILEAD_REFERENCE_CLASSIFICATION.md) |
| Raw SQL / endpoints | **PARTIAL** | `lint_raw_sql_usage`, `lint_allow_any_usage`, `lint_csrf_exempt_usage`, `build_phase8_security_ledger.py --check` |
| AI / provider scatter | **PARTIAL** | `verify_ai_blueprint_completion.py`, gateway + [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md) |
| Doc / plan density | **PARTIAL** | `verify_doc_plan_density_discipline.py`, **this file** + log A–F; no new master plans |

### Structural remediation stack (P0–P6)

Ordered program that maps the six maturity themes into **§11.4 slices** (each slice: scope → implement → tests → log A–F in [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md)). **Do not** ship decisions from gross totals alone: `docs/generated/platform_inventory.json` now includes **`scoped_gravity_counts`** (product-signal tallies); pair with `python scripts/report_premium_maturity_signals.py --json` for decorator-level CSRF and non-migration SQL.

| Priority | Theme | Objective | Primary hooks | Done means |
|----------|-------|-----------|---------------|------------|
| **P0** | Security / public surface | No unreviewed raw SQL, CSRF exemptions, or broad AllowAny | `lint_raw_sql_usage.py`, `lint_csrf_exempt_usage.py`, `lint_allow_any_usage.py`, `build_phase8_security_ledger.py --check`, `report_premium_maturity_signals.py --strict` | Lints green; ledgers current; allowlist entries have owner metadata |
| **P1** | Gilead residue | No customer-visible demo naming / drift | `lint_gilead_residue.py`, `verify_gilead_full_tree_classification.py`, [GILEAD_REFERENCE_CLASSIFICATION.md](GILEAD_REFERENCE_CLASSIFICATION.md) | Lint green; **`gilead_line_hits_…`** in inventory trending down |
| **P2** | SiteSettings gravity | Runtime-first + physical decomposition; fewer live references | [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md), `lint_tenant_settings.py`, `verify_siteconfig_decomposition_depth.py`, Phase B batches, RuntimeDefaults | **`site_settings_refs_apps_py_excl_migrations_tests`** down; owners cover fields |
| **P3** | Admin gravity | High-value operator flows live in **control-plane** UX; Django admin is escape hatch | Product routes in `siteconfig` / `schools` super views / Studio hubs; thin `ModelAdmin` where possible; [phase_04_control_plane.md](phase_checklists/phase_04_control_plane.md) | Top journeys no longer **only** `/admin/…` |
| **P4** | Shell unification | One navigational language across `/super/`, `/studio/`, admin bridges | [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md), `verify_shell_architecture_matrix.py` | Matrix verification **PASS**; duplicates removed per matrix |
| **P5** | Repo sprawl | Doc density and tree governance | `verify_doc_plan_density_discipline.py`, subtractive cleanup, `generate_platform_inventory.py --check` | No new overlapping master plans; inventory committed |
| **P6** | Tooling vs product hygiene | `print()` stays out of **apps** product paths | `lint_no_print_in_apps.py` (gates); scripts may use `print` | **`print_calls_apps_py_excl_migrations_tests_management`** stays at zero |

**Execution order:** **P0 → P1** are **merge-bar hygiene** (already enforced in `pre_deploy_gate.sh` where wired). **P2–P4** are **multi-slice architecture** (siteconfig, admin, shell). **P5–P6** are **continuous governance**.

### Cursor 12-phase map (index only—detail in phase_checklists)

| Phase | Theme | Checklist |
|-------|--------|-----------|
| 1 | Authenticated shell | [phase_01_authenticated_shell.md](phase_checklists/phase_01_authenticated_shell.md) |
| 2 | Design system | [phase_02_design_system_tokens.md](phase_checklists/phase_02_design_system_tokens.md) |
| 3 | Navigation / archetypes | [phase_03_navigation_command_archetypes.md](phase_checklists/phase_03_navigation_command_archetypes.md) |
| 4 | Control plane UX | [phase_04_control_plane.md](phase_checklists/phase_04_control_plane.md) |
| 5 | Studio OS | [phase_05_studio_os.md](phase_checklists/phase_05_studio_os.md) |
| 6 | Siteconfig / SiteSettings | [phase_06_siteconfig_sitesettings.md](phase_checklists/phase_06_siteconfig_sitesettings.md) |
| 7 | Runtime-first | [phase_07_runtime_first.md](phase_checklists/phase_07_runtime_first.md) |
| 8 | Dashboards / role homes | [phase_08_dashboards_role_homes.md](phase_checklists/phase_08_dashboards_role_homes.md) |
| 9 | Security / trust | [phase_09_security_trust.md](phase_checklists/phase_09_security_trust.md) |
| 10 | Marketplace / migration | [phase_10_marketplace_packs_migration.md](phase_checklists/phase_10_marketplace_packs_migration.md) |
| 11 | Marketing front | [phase_11_marketing_front.md](phase_checklists/phase_11_marketing_front.md) |
| 12 | Gilead + docs discipline | [phase_12_gilead_docs_discipline.md](phase_checklists/phase_12_gilead_docs_discipline.md) |

### Autonomous prompts vs this file

Literal “every line / zero csrf_exempt / minimal clicks everywhere” **≠** §12 closure. **Closure** = §12 + `pre_deploy_gate` + defined script/registry gates. Unbounded English goals → **§11.4** slices with tests and log entries.

### §11.4 execution rule

Ship work as: **scope slice → implement → validate → log (A–F) → update §11.4**. Operational reliability (`pre_deploy_gate`, stable `DJANGO_TEST_DB_FILE`) is mandatory infrastructure.

## ZIP phases 1, 3, 5 — **COMPLETE**

| Phase | Goal | Verify |
|-------|------|--------|
| **1** Shell + nav unification | One control-plane language; matrix | [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md); `pytest apps/schools/tests/test_primary_control_plane_nav.py` |
| **3** Operator UX | Outcome-first CCC + Control Studio | `pytest apps/siteconfig/tests/test_control_outcome_center.py`; [phase_04](phase_checklists/phase_04_control_plane.md) |
| **5** SiteSettings behavioral gate | Runtime-first; tenant lint | `verify_phase_5_siteconfig.py`; `lint_tenant_settings` |

**Phase 2 (design system):** `scripts/verify_design_system_phase2.py` + [DESIGN_SYSTEM_PHASE2.md](DESIGN_SYSTEM_PHASE2.md). **Phase B (physical schema):** [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md)—does not reopen ZIP Phase 5 DONE rows.

## External benchmark reality (one paragraph)

Incumbents (Infinite Campus, Blackbaud, PowerSchool, Shopify-style extensibility, etc.) set the **comparison bar**. RunMyCampus wins on lower-click setup, runtime/metadata rigor, pack ecosystem, migration, role-native UX, and trust posture—**evidenced per release**, not by narrative alone.

## Six historical audit themes (superseded as open “spine” risks)

| Theme | Closed in repo by |
|-------|-------------------|
| siteconfig / SiteSettings | §12 + lint + runtime-first |
| Runtime as law | `test_runtime_contract`, precedence docs |
| Studio OS fragmentation | Five hubs + §4 |
| Security / trust | Lints + `public_endpoint_audit` + SECURITY_REVIEW_LOG |
| Gilead (live surfaces) | Migration 0155 + `lint_gilead_residue` |
| Docs truth | DOCS_TRUTH_AUDIT + this file as authority |

---

# 0.1 Vision: one-stop-shop ecosystem

**North star:** One ecosystem for education—identity, SIS, learning, finance, advancement, comms, reporting, operations—so schools can run on **one** platform. **Benchmarks** (Shopify-like extensibility, Google-like cohesion, etc.) express **direction**, not checkbox substitutes for §12.

**In practice:** Packs, marketplace, blueprints, workflows, registries, Setup/Launch Studio, and runtime resolution implement “everything at every level” **incrementally**. **Detail and historical narrative:** [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).

---

# 0.1.5 Prioritized execution (waves — summary)

**Repo closure:** Wave 8 **internal** items = **CLOSED** on repository evidence ([SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) internal table). **Organizational / vendor / certification / infinite depth** = **OPEN** only in that backlog—**not** duplicate `[ ]` rows here.

| Wave | Focus |
|------|--------|
| 1–2 | Risk, internal API consistency |
| 3–4 | Open-source spine, one-stop depth |
| 5–6 | Migration north star, paper → digital |
| 7 | Forward-looking / 100-year lens |
| 8 | Experience, performance, trust, ecosystem, global, innovation, support (N1–N29 themes) |

**Verification:** `python scripts/verify_sot_pillar_evidence.py` (and commands in SOT_0155_SECTION_0_1_5_QUEUE_STATUS). **Runbooks:** [runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md).

**N23 (inclusive terminology & imagery):** [N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md](N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md), [CONTENT_AND_TERMINOLOGY_GOVERNANCE.md](CONTENT_AND_TERMINOLOGY_GOVERNANCE.md).

---

# 0.2 Competitive obliteration roadmap

**Wedges 1–6 (Phase I)** are **Implemented** in code; **world-class depth** continues in product increments ([WEDGE_WORLD_CLASS_IMPLEMENTATION.md](WEDGE_WORLD_CLASS_IMPLEMENTATION.md), [RUNMYCAMPUS_45_WEDGE_SCORECARD.md](RUNMYCAMPUS_45_WEDGE_SCORECARD.md)).

## 0.2.1 Full wedge set (names + scope)

Geography, education systems, learning styles, institution types—**non-negotiable over time**, delivered via packs, regions, and runtime. **Per-wedge GTM matrix:** [RUNMYCAMPUS_45_WEDGE_SCORECARD.md](RUNMYCAMPUS_45_WEDGE_SCORECARD.md) (extends this section; does not replace codebase validation).

### 0.2.1.2 Wedge implementation status (Phase I)

**Phase I checklist** (wedges 1–6): all items **[x]** — see **§11 Phase I** below for the compact checklist. Evidence tables (education_dna, OneRoster, LTI, REGIONAL_POLICY_PACKS, advancement models, HE catalog, etc.) remain in code and wedge docs; **do not** duplicate full prose here.

### 0.2.1.3 Innovation / gap ledger

**MET / gaps / BLOCKED** per wedge: [RUNMYCAMPUS_45_WEDGE_SCORECARD.md](RUNMYCAMPUS_45_WEDGE_SCORECARD.md), [BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md](BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md).

### 0.2.1.4–0.2.1.6 BR, super-premium, phased execution

**Buyer readiness and tier-1 ledger:** captured in north-star and wedge docs cited above; execution still maps to **§11.4** slices. **Scoring honesty:** BR-13 and manual passes are **release** gates; automation proves **repo** bar.

## 0.2.2 Granular tenant configuration

**No two schools the same:** runtime + packs + policies + entitlements + region—**non-negotiable**; depth = §5 / §11.4.

---

# 0.3 Foundation prerequisites

## Pillars (summary)

| # | Pillar |
|---|--------|
| 1 | Architecture — bounded contexts, clear platform vs tenant |
| 2 | Ecosystem — marketplace, packs, extensibility |
| 3 | Security & compliance |
| 4 | Integration / trust / API |
| 5 | Internal platform APIs |
| 6 | Premium UI/UX |
| 7 | i18n, control plane, migration, honest docs |

### 0.3.1 Codebase evidence registry

Prove pillars with tests/scripts — run `python scripts/verify_sot_pillar_evidence.py` and gate tests cited in [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md).

### 0.3.2 Competitor map (beyond-reach reference)

[BEYOND_REACH_IMPROVEMENTS.md](BEYOND_REACH_IMPROVEMENTS.md), [BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md](BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md) — not duplicate execution plans.

### 0.3.3 Mandatory beyond-reach queue

Sequenced work that does not fit a single checkbox — execute as **§11.4** slices with evidence; external blockers → [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md).

---

# 0.4 Competitive intelligence

**Method:** Web-sourced and user-reported claims (see audit plan for citations). **Priorities (non-negotiable over time):**

- **Emulate / surpass:** one system of record; integrations that work; role-native UX; support as product; curriculum/region as packs; advancement in one graph.
- **Avoid:** slowness, security incidents, migration disasters, cluttered UX, opaque outages, legacy navigation debt.
- **Gaps to close:** trust center & compliance; migration safety; performance targets; LMS/SSO depth; UK/international packs; advancement CRM depth.

**Long-form competitor notes** (K–12, UK MIS, LMS, HE, etc.) live in the **enterprise audit** and research files—**not** duplicated here.

---

# 0.5 Leveraging internal AI

**Gateway:** `services.ai_gateway` only—no browser provider keys. **Task types and surfaces:** [AI_DOMAIN_ASSISTANT_REGISTRY.md](AI_DOMAIN_ASSISTANT_REGISTRY.md), [architecture/ai_orchestration.md](architecture/ai_orchestration.md). **Rule:** extend prompts/RAG/endpoints before inventing parallel AI stacks; track work here + backlog. **Open-source inference defaults** (Ollama + rules for chat; optional self-hosted vLLM/LiteLLM only where configured) and **ops** for pulls / image digests: [OLLAMA_OPERATIONS_AND_UPDATES.md](OLLAMA_OPERATIONS_AND_UPDATES.md).

---

# 1. Master operating principles

1. **Runtime is the law** — tenant behavior via resolvers, not raw `SiteSettings` in tenant apps.
2. **Metadata first-class** — catalog, lineage, packs.
3. **Packs are products** — validate, preview, apply, rollback.
4. **Configuration outcome-driven** — CCC / Control Studio patterns.
5. **Low-click, role-native** — palette, role-home, one action model.
6. **Security boring** — classified exemptions, audits, webhooks signed.
7. **Delete aggressively** — legacy paths removed per [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md).

## 1.8 Decision architecture & continuous improvement

**Decision architecture (seven questions):** who, what question, what state, next action, confidence, wrong-path, fallback — template [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md); meta-layer [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md).

**After gates are green:** keep tightening §1.1–1.7 (runtime, metadata, packs, outcomes, low-click, security, legacy removal); track in **§11.4** and BACKLOG — same as prior SOT §1.8 compliance table.

---

# 2. Red-alert workstreams

### 2.1 SiteSettings / siteconfig dismantling

- [x] **ZIP Phase 5 + Phase B migration program** — [site_settings_usage_inventory.md](site_settings_usage_inventory.md), [domain_ownership.md](domain_ownership.md).
### 2.2 Gilead residue purge

- [x] Live surfaces clean; full corpus = §11.4 / docs hygiene.

### 2.3 AI / provider secret hardening

- [x] Gateway + `lint_secret_exposure`.

### 2.4 Public endpoint and raw SQL hardening

- [x] Allowlists + CI lints.

---

# 3. Architecture transformation

- **3.1** Bounded contexts — enforced via imports + docs.
- **3.2** Runtime-first — `get_effective_site_settings`, inspector, contract tests.
- **3.2.1–3.2.5** Phases 7–11 (dashboards, security, marketplace, marketing, Gilead/docs) — **MET** at repo gate; continuous depth = §11.4.

## 3.3 Metadata-first completion

Lineage API/UI, pack provenance, governance — **MET (repo baseline)**; automatic lineage on every new surface = §11.4 cadence. See [metadata_lineage_approach.md](metadata_lineage_approach.md).

---

# 4. Studio OS

| § | Mode | Status |
|---|------|--------|
| 4.1 | Shell | **DONE** — [studio_os_shell_requirements.md](studio_os_shell_requirements.md) |
| 4.2 | Experience | **DONE** |
| 4.3 | Automation | **DONE** |
| 4.4 | Output | **DONE** |
| 4.5 | Launch | **DONE** — staging 10-point: [launch_studio_checklist.md](launch_studio_checklist.md) §4 |
| 4.6 | Control | **DONE** |

**§11.1 depth** (billing SKUs, simulation, etc.) = §5 / §11.4—not open §4 PARTIAL.

---

# 5. Toolset remediation

| § | Toolset | Target | Note |
|---|---------|--------|------|
| 5.1 | Theme & Experience | 11/10 | §11.4 for remaining SKUs |
| 5.2 | Feature Control | MET | [feature_control_ledger.md](feature_control_ledger.md) |
| 5.3–5.9 | Reports, docs, design, previews, workflows, AI/API, CCC | See ledgers | Depth = §11.4 |

---

# 6. App-by-app remediation ledger

**Status:** Actions **§6.1–§6.24** are **[x]** at the **repo behavioral** bar recorded in this plan’s history. **Per-app scores** (e.g. 5.x–8.x/10) express **remaining product depth**, not open spine failures vs §12. **Further console splits / UX** = §11.4 + [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md). **Do not** resurrect §4/§12 as PARTIAL because §6.x numeric targets are not 11/10.

---

# 7. Ecosystem and pack seeding

**Targets:** 27+ apps, 25+ blueprints, 30+ workflows, 21+ dashboards, 15+ policies — **MET**; see [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md), `generate_platform_inventory.py --check`, `test_marketplace_catalog_minimums`.

---

# 8. UX, dashboards, marketing

## 8.0 Platform UX bar (non-negotiable)

**Principles:** One design system and token layer on **all** bases (control plane, portal, backend, admin, marketing); responsive fluid layout; command palette + role-home; marketing visually aligned with product. **Implementation checklist (control plane + marketing slice):** [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md). **Responsive / lint:** `python scripts/lint_section8_responsive.py` (see doc for `--strict`).

### 8.0.11 UX acceptance standard

No “good enough” on user-facing surfaces: premium feel, consistent shells, accessible baseline (`phase_h_audit.py`), no routine “bounce to `/super/`” for core work. **Same bar** for tenant backend apps and marketing.

### 8.0.6 Responsive

Flex/Grid, fluid containers, scalable type (`clamp` / media queries)—**§12** and Phase I.5 **MET** at gate; spot-check per release.

## 8.1–8.4

- [x] **8.1** Role-home engine  
- [x] **8.2** Contextual actions + palette  
- [x] **8.3** Page archetypes on representative surfaces  
- [x] **8.4** Marketing front — proof-rich; pipeline: [MARKETING_EXECUTION.md](MARKETING_EXECUTION.md), `validate_marketing_urls`

---

# 9. Docs truth reconciliation

- [x] Truth ledger + alignment policy; **authority = §0 + §12 + §11.4**.

---

# 10. Code hygiene and ops

- [x] print ban, structured logging, management command policy, root clutter, subprocess ledger, `pre_deploy_gate` — see [code_hygiene_ledger.md](code_hygiene_ledger.md).

## 10.4 Pre-wedge hygiene baseline

| # | Check |
|---|--------|
| 1 | `pre_deploy_gate.sh` |
| 2 | `lint_no_print_in_apps` |
| 3 | `lint_tenant_settings --check-get-solo-only` |
| 4 | `lint_broad_except` strict |
| 5 | Ruff F401/F841 |
| 6 | `generate_platform_inventory.py --write` |
| 7 | `lint_mega_files` |
| 8 | TODO/FIXME hygiene |
| 9 | `makemigrations --check` |
| 10 | `lint_raw_sql_usage` |

## 10.5 Operating discipline layers

**Full layer list:** [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md). **Verify:** `python scripts/verify_section10_5_layers.py`.

### 10.5.4 Trust product (visible security)

[TRUST_PRODUCT_SURFACES.md](TRUST_PRODUCT_SURFACES.md) — trust center, sessions, audit export, compliance copy.

### 10.5.5 Dashboard taxonomy

[DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) — declare dashboards; avoid junk-drawer pages.

---

# 11. Execution order

**Phases A–H:** all **[x]** at repo program bar—see historical log for evidence. **Phase H:** automated tests + `phase_h_audit`; manual BR-13 per release — [PHASE_H_UX_VERIFICATION.md](PHASE_H_UX_VERIFICATION.md), [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md).

## Phase I — Wedges 1–6

All wedge checklist items **[x]** (K–12, LMS, UK, district, advancement, HE). **World-class bar:** [WEDGE_WORLD_CLASS_IMPLEMENTATION.md](WEDGE_WORLD_CLASS_IMPLEMENTATION.md).

## Phase I.5 — Premium UX, single pane, marketing, click reduction

**Gate: MET.** Evidence: [SINGLE_PANE_VALIDATION.md](SINGLE_PANE_VALIDATION.md), [RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md](RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md), [CLICK_REDUCTION_BASELINE.md](CLICK_REDUCTION_BASELINE.md), header/tokens on all bases (`header-no-spillage.css`, design tokens).

## Phase J — Triple wedge (interop + learning types + Studio)

**DONE** — [interop/WORLD_CLASS_TRIPLE_WEDGE.md](interop/WORLD_CLASS_TRIPLE_WEDGE.md).

## North star improvements (N1–N29) — status only

Product targets—not duplicate §12 checkboxes. **Implementation status:**

| IDs | Repo | Notes |
|-----|------|-------|
| N1–N8 | MET / N/A continuous | UX + palette + onboarding depth in releases |
| N9–N12 | MET baseline | Perf budgets, trust/ops — stricter SLO = continuous |
| N13–N16 | MET baseline | Trust center; live attestations = external |
| N17–N20 | MET / §11.4 | Marketplace certification graph depth |
| N21–N23 | MET baseline | i18n, RTL, inclusive terminology programs |
| N24–N26 | MET baseline | Runbooks, support onboarding org = N/A external |
| N27–N29 | MET baseline | AI guidance, Launch/Setup Studio iterations |

**Detail:** [NORTH_STAR_TRUST_AND_OPS.md](NORTH_STAR_TRUST_AND_OPS.md), [BEYOND_REACH_IMPROVEMENTS.md](BEYOND_REACH_IMPROVEMENTS.md).

---

# 11.1 §11.1 completion (legacy “optionals”)

**All DONE:** Experience / Automation / Launch / Control Studio §11.1 items; Phase E marketplace seed script; §12.1 gate record script. Reconcile [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §2f at milestones.

---

# 11.2 Path to 100%

**Item-level actions:** [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md). **Order:**

| Phase | Scope |
|-------|--------|
| I | Wedges 1–6 |
| I.5 | Premium UX / single pane / marketing / clicks |
| III | §6 app order 6.1→6.24 (depth) |
| IV | §5 toolsets |
| V | §7 seeding + Phase H per release |

**Implement-all runbook:** [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) + [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md) — verify-then-ship for **§11.4** slices and explicit `[ ]` (coordination block at top of runbook).

---

# 11.3 Logical order & legacy replacement

1. Phase I → I.5 → III → IV → V (as above).  
2. **Visible after deploy:** every `[x]` has a verification path (UI, API, lint, or test).  
3. **Legacy:** [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md), [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md).

**Doc cross-check:** [docs_truth_ledger.md](docs_truth_ledger.md), [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md), [WHATS_NOT_DONE_AND_HOW_TO_START.md](WHATS_NOT_DONE_AND_HOW_TO_START.md).

---

# 11.4 Consolidated tracking (single place for “what’s left”)

**Structural remediation (P0–P6):** Execute in the order in **§0 — Structural remediation stack (P0–P6)**. Use **`scoped_gravity_counts`** in `docs/generated/platform_inventory.json` (from `generate_platform_inventory.py --write`) for honest SiteSettings/SQL/Gilead trend lines; gross `baseline_counts` remain for repo-scale snapshots only.

**Status / what’s left** lives **here**—not in parallel “stock take” narratives. **Platform boundary, host matrix, impersonation, AI gateway** — **DONE** (see prior SOT revision for full evidence table; tests: `test_manager_studio_tenant_boundary`, `test_tenant_host_control_plane_isolation`, `test_super_config_migration_urls`).

| Area | Status | Action |
|------|--------|--------|
| §12 gate | **MET** | `pre_deploy_gate.sh` each train |
| §7 seeding | **DONE** | Inventory check in CI |
| Gate record | Required | `record_pre_deploy_gate_output.sh` → `docs/generated/pre_deploy_gate_run.txt` |
| Launch 10-point | **MET** (2026-03-17) | Repeat on staging per [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) |
| Phase H + BR-13 | Per release | Manual + `run_phase_h_verification.sh` |
| Phase B / §5.x depth | **Queued** | Typed tables, SKUs, diff UI, workflow simulation—**slices** with tests + log |
| Postgres Playwright (tenant portals) | CI optional | `.github/workflows/playwright-tenant-postgres.yml`, `scripts/ci_setup_postgres_tenants_for_visual_qa.sh` |
| KB/FAQ + LibreOffice tiers (T0–T6) | **BLOCKED (T4 WOPI host routing)** | **T0–T3 + KB/FAQ** are implemented in-repo. **T4** needs a WOPI-capable document server at `COLLABORA_BASE_URL`. Symptom when miswired: `curl -I …/hosting/discovery` returns **302** to the app (`school-not-found`) — **collabora hostname is served by Django, not Collabora**. **Unblock:** self-host **open-source** Collabora (`collabora/code`; repo `docker-compose.collabora.yml` / `deploy/collabora/k8s/*`) on **your** infra (Render service, k8s, or VM), not closed-source SaaS. **Policy fork:** if the org forbids any second process, record T4 as **out of scope** until policy changes. **Tenant seed:** `python manage.py tenant_command seed_office_documents --schema=<tenant_schema>`. Track: [execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md](execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md), [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). |

**§11.4 slice — AI RAG, migration playbook audit, platform health beats (evidence):**

- **A (RAG + eval):** Daily opt-in beat `ENABLE_AI_KNOWLEDGE_INDEX_BEAT` → `siteconfig.index_ai_knowledge_beat`; policy-scope tenant ranking in `services/ai_memory.py` + policy metadata in `index_ai_knowledge`; gateway regression + safe structured fallback + feedback loop tests (`services/tests/test_ai_gateway_invoke_regression.py`, `services/tests/test_ai_gateway.py`, `services/tests/test_ai_memory.py`, `apps/portal/tests/test_ai_feedback.py`, `apps/siteconfig/tests/test_ai_quality_scorecard.py`); cross-link in `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`.
- **B (Migration):** `execute_playbook` → `AutomationExecutionLog`; quarantine ↔ run FK + admin columns + **`automation:outcomes_console`** quarantine column; preflight confidence guard (`required_field_coverage`, `duplicate_risk`, `rollback_readiness`, `quarantine_risk`) with threshold `MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE` and explicit `override_reason`; tests `apps/automation/tests/test_playbook_quarantine_and_logs.py`, `test_outcomes_console_quarantine.py`, `PlaybookExecutorTests` log assertion; playbook semantics in `docs/architecture/ai_orchestration.md`.
- **C (Non-migration beats):** `ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT`, `ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT`, `ENABLE_AUTOMATION_FAILURE_TREND_BEAT` → `platform_runtime.operator_visibility_heartbeat`, `platform_runtime.database_connectivity_heartbeat`, `platform_runtime.automation_failure_trend_signal`; tests `apps/platform_runtime/tests/test_health_heartbeat_tasks.py`.
- **D (Security + deploy-path enforcement):** Release-readiness gate is code-wired into CI/deploy path (`.github/workflows/smoke.yml` → `scripts/pre_deploy_gate.sh` → `scripts/release_readiness_check.sh` with `RUN_RELEASE_READINESS_GATE=1` default). Forbidden provider scan is Python-based (no `rg` runtime dependency), so gate behavior is deterministic across local/CI shells.

**§11.4 slice — P3 (SiteSettings Django admin → control plane, tenant):** **DONE (2026-03-27)** — Escape hatch on `templates/admin/siteconfig/sitesettings/change_form.html` links to `siteconfig:theme_colors`, `siteconfig:feature_control_panel`, `siteconfig:console_domains_hub`, and `studio_os:output` only (no `super:` on tenant urlconf). Test: `apps/siteconfig/tests/test_admin_ui_smoke.py` → `test_sitesettings_change_form_links_to_control_plane_surfaces` (uses `RequestFactory`, `set_urlconf("config.tenant_urls")`, and `response.render()` because `TenantMiddleware` redirects live `Client` GET `/admin/…` on tenant hosts).

**§11.4 slice — P3 (ReportCardStyle Django admin → control plane, tenant):** **DONE (2026-03-27)** — Escape hatch on `templates/admin/siteconfig/reportcardstyle/change_form.html` links to `siteconfig:reportcard_builder`, `studio_os:output`, and `siteconfig:console_domains_hub` (tenant-safe). Test: `test_reportcardstyle_change_form_links_to_control_plane_surfaces` in the same smoke module.

**§11.4 slice — P3 (Dashboard widget / user preference / Integration admin → control plane, tenant):** **DONE (2026-03-27)** — `templates/admin/siteconfig/dashboardwidget/change_form.html` + `dashboarduserpreference/change_form.html` escape hatches; `DashboardWidget` uses that template via `DashboardWidgetBlueprintAdmin` in `apps/runtime_blueprints/admin.py` (previously the custom template was unused). New `templates/admin/integrations_marketplace/integration/change_form.html` + `IntegrationMarketplaceAdmin` in `apps/integrations_marketplace/admin.py` → `siteconfig:feature_control_panel`, `apicenter:dashboard`, `siteconfig:console_domains_hub`. Tests: `test_dashboardwidget_change_form_links_to_control_plane_surfaces`, `test_dashboarduserpreference_change_form_links_to_control_plane_surfaces`, `test_integration_change_form_links_to_control_plane_surfaces` in `apps/siteconfig/tests/test_admin_ui_smoke.py`.

**§11.4 slice — P3 (Compliance + portal banner/document admin → control plane, tenant):** **DONE (2026-03-27)** — `form_before` escape hatches on `templates/admin/compliance/compliancerule/change_form.html`, `legaldocument/change_form.html`, `portal/portalfeatureitem/change_form.html`, `portal/announcement/change_form.html` → `siteconfig:console_domains_hub`, `siteconfig:feature_control_panel`, `kb:kb_home` (compliance); `portal:document_library_manage`, `studio_os:output` (portal documents); `communication:announcement_list_pending`, `accounts:backend_dashboard` (global banner). Tests: `test_compliancerule_*`, `test_legaldocument_*`, `test_portalfeatureitem_*`, `test_announcement_*` in `apps/siteconfig/tests/test_admin_ui_smoke.py`. **i18n:** `manage.py sync_i18n_catalog --compile` (new `msgid`s in all locale `django.po` / `django.mo`).

**§11.4 slice — P4 (shell architecture matrix, automated):** **PASS (2026-03-27)** — `python scripts/verify_shell_architecture_matrix.py` green on current tree (marketing / control-plane / admin / tenant shell contracts). Premium maturity table may still list shell as **PARTIAL** until manual duplicate-removal work in [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md) is fully exhausted; automation gate is not a substitute for staging URL matrix sign-off.

**§11.4 slice — P2 (Phase B post-snapshot depth):** **Queued (unchanged)** — Next sequenced physical/product work remains per [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md) post–batch-13 note (first-class tables per high-churn domain, SKUs / workflow simulation slices as scoped §11.4 increments—not reopened in this train).

**§11.4 slice — P2 (SiteSettings name gravity, post–Phase B):** **DONE (2026-03-27)** — Drop direct `SiteSettings` import from `apps/dashboard/admin_context.py` (weather config already accepts effective-settings shape via `Any`; settings audit widget uses `ContentType.objects.get(app_label="siteconfig", model="sitesettings")`). Align guardian finance opt-in log strings in `apps/accounts/permissions.py` with `get_effective_flags_for_school`. De-`SiteSettings` finance model help_text/docstrings in `apps/finance/models.py` (platform/runtime wording). Verification: `python scripts/verify_siteconfig_decomposition_depth.py` **PASS**; `python scripts/generate_platform_inventory.py --write` lowers **`scoped_gravity_counts.site_settings_refs_apps_py_excl_migrations`** / **`_excl_migrations_tests`** (trend line); `pytest apps/siteconfig/tests/test_admin_dashboard_adaptability.py`.

**§11.4 slice — P2 (policy resolver + adjacent docstrings, no behavior change):** **DONE (2026-03-26)** — Comments, docstrings, and debug strings in `apps/policies/resolver.py` no longer spell `SiteSettings` (prefer “effective site settings” / `get_effective_site_settings` / platform-default wording). Tiny follow-through: delegation / MFA middleware / Phase B admin class docstrings in `apps/accounts/delegation.py`, `apps/accounts/middleware.py`, `apps/platform_runtime/admin.py` (avoid `help_text` / schema churn—those stay on dedicated P2 batches if needed). Smoke: `pytest apps/schools/tests/test_wave5_config_canonical.py -q`; refresh gravity: `python scripts/generate_platform_inventory.py --write`.

**§11.4 slice — P2 / runtime-first (platform compliance profile wiring):** **DONE (2026-03-27)** — `SiteSettings.compliance_profile` getter resolves `finance.ComplianceProfile` from `RuntimeDefaults.compliance_profile_id` (and legacy payload key); setter writes the **first-class** `RuntimeDefaults.compliance_profile_id` column, strips duplicate payload key, and invalidates effective-settings cache. `apps/finance/views_common._active_profile` resolves by `compliance_profile_id` on `get_effective_site_settings()` when no FK object is present on the merged namespace. Tests/commands: `apps/finance/tests/test_split_billing.py` (no invalid `save(update_fields=["compliance_profile_id"])` on `SiteSettings`; invoice list asserts via `assertContains`), `apps/finance/tests/test_split_allocation.py`, `apps/finance/management/commands/seed_finance_defaults.py`. Migration drift: `apps/finance/migrations/0054_alter_paymentreminder_reminder_channels_help_text.py` (model `help_text` already matched code; gate `makemigrations --check` clean). Verify: `pytest apps/finance/tests/test_split_billing.py apps/finance/tests/test_split_allocation.py -q`; `python scripts/verify_siteconfig_decomposition_depth.py`; `python scripts/verify_shell_architecture_matrix.py`.

**§11.4 slice — P2 (Phase B typed snapshot index + operator diff UI) + P0 (allowlist review contract):** **DONE (2026-03-27)** — **`PlatformPhaseBDomainSnapshot`**: migration **`platform_runtime.0026`** adds **`payload_key_count`** + **`payload_checksum`** (sha256 of canonical JSON); `phase_b_payload_metadata` / `snapshot_payload_for_domain` in `apps/platform_runtime/phase_b_domain_snapshots.py`; sync + Django admin **`save_model`** keep metadata aligned. **Control plane:** `super:phase_b_snapshot_diff` (`apps/schools/super_views_phase_b.py`, template `schools/super_phase_b_snapshot_diff.html`) — per-domain drift table + optional unified diff; link from **Runtime truth hub**. **P0:** `scripts/verify_security_allowlists.py` enforces **`last_reviewed`** (ISO date, default max age **730** days) + full metadata on `raw_sql` / `csrf_exempt` / `allow_any` JSON; wired **`pre_deploy_gate.sh`** after the three lints; **`build_phase8_security_ledger.py --write`** regenerated; tests **`test_security_allowlists_verify`**, **`test_super_phase_b_snapshot_diff`**, extended **`test_phase_b_domain_snapshots`**.

**§11.4 slice — P2 (Phase B per-key fingerprints + operator resync):** **DONE (2026-03-27)** — Migration **`platform_runtime.0027`** adds **`payload_key_checksums`** (JSON: each top-level payload key → sha256 of that key’s canonical value). Helpers **`phase_b_top_level_key_fingerprints`**, **`diff_top_level_payload_keys`** feed the control-plane grid (**changed keys** column) and a **key-level drift** panel (only-live / only-snapshot / value mismatch). **POST** `resync_all_snapshots` on **`super:phase_b_snapshot_diff`** re-runs **`sync_phase_b_domain_snapshots_from_site`** (super-host only, same middleware as other super views). **Not** first-class relational tables per field—that remains sequenced per [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md). Tests: `test_diff_top_level_payload_keys_detects_mismatch`, **`test_resync_post_materializes_from_live`**.

**§11.4 slice — Deploy train + residue discipline (2026-03-27):** **PASS** — `SKIP_VISUAL_QA=1 PRE_GATE_FRESH_TEST_DB=1 bash scripts/pre_deploy_gate.sh` → `docs/generated/pre_deploy_gate_run.txt` ends with `[gate-finished] EXIT=0`. **Prerequisite when i18n drifts:** run `python manage.py sync_i18n_catalog --compile` and commit updated `locale/**` when the gate reports missing msgids. Same train: Ruff **F401** fix in `apps/siteconfig/tests/test_admin_ui_smoke.py`; **removed** `apps/schools/management/commands/seed_gilead_demo_users.py` (use `seed_demo_tenant_users`). **`lint_gilead_residue.py`** = runtime-visible bar (apps/templates/config/fixtures — no `gilead` substring); **migrations/docs** may retain historic strings until a dedicated migration-retire program — do not confuse gross inventory counts with that lint. **Neutral ops surface:** `seed_cursor_twelve_phases` phase-12 title + `--strict-residue-lint` / `--skip-residue-lint` (deprecated `*gilead-lint` aliases); `report_premium_maturity_signals.py --json` key **`runtime_branding_residue_corpus`** (replaces `gilead_corpus`). **P4 shell:** control-plane topbar **Studio** quick link (`studio_os:shell`) beside **Config center**; Django admin skip link uses `{% trans %}`. **Mechanical gates:** `lint_raw_sql_usage.py`, `verify_doc_plan_density_discipline.py`, `verify_shell_architecture_matrix.py`.

**Verification commands:** `bash scripts/pre_deploy_gate.sh`; `bash scripts/run_phase_h_verification.sh` (or `PHASE_H_SKIP_LIVE=1`); `bash scripts/run_visual_qa.sh`; `python scripts/verify_phases_3_11_gates.py` *or* `python -m pytest apps/platform_runtime/tests/test_tenant_settings_lint.py -q` (pytest module **mirrors that script’s steps** — including no tracked `.env`, repo hygiene/root allowlist, **`manage.py check`**, **`makemigrations --check --dry-run`**, bounded-context + siteconfig-legacy imports, **`scan_repo_secrets`**, **no-`print`**, **ruff F401/F841 on `apps/`**, **`check_no_hardcoding --allow-tests`**, Phase B batch-3 SiteSettings FK-write lint, **broad-except allowlist/strict**, **`generate_platform_inventory.py --check`** (refresh with `--write` on the full train), **`verify_phase_5_siteconfig`** + **SiteSettings ORM singleton** lint + **north-star a11y / i18n** (`--strict`, after Phase H static audit in the script order) + §10.5 + Phase 2 + marketing nav + super-premium wedges + Phase 7/8 markers + hub registry + Phase H static + i18n catalog, and the rest of the bundle — plus phase 1–9 narrow gates; pre-deploy runs the pytest module and **does not** re-invoke `verify_phases_3_11_gates.py`); gate-map appendix drift: `python scripts/generate_gate_map_appendix.py --check`; dedicated DB: see [TEST_DATABASE.md](TEST_DATABASE.md), [CONTRIBUTING.md](../CONTRIBUTING.md).

**Bundle vs full train:** `verify_phases_3_11_gates.py` and `test_tenant_settings_lint` are **one mirrored lane** (broad mechanical + Django integrity + hygiene). They **do not** replace `pre_deploy_gate.sh`. **Full train only** — authoritative order in `scripts/pre_deploy_gate.sh` — includes at least: app-specific `showmigrations` spot checks, `migrate_gate_test_db.py`, `verify_phase_b_execution.py`, `manage.py audit_tenant_models --strict`, smoke URLs / Phase H URL reverse and the long `TARGETED_HARDENING_TESTS` / other `manage.py test` batches, **`generate_platform_inventory.py --write`** (regenerate `docs/generated/` artifacts before or alongside `--check`), **`lint_mega_files`**, optional **`lint_tenant_settings --report-allowlisted`**, advisory §8/responsive/template lints, and optional gates (`RUN_ENV_CONTRACT_GATE`, `release_readiness_check.sh` when enabled).

**Release checklist:** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) — pre-release, build, deploy, post-release.

**Phase batch indexes (reference only):** [PHASES_1_TO_255_INDEX.md](PHASES_1_TO_255_INDEX.md).

---

# 12. Final scoring gate

**Status:** **MET** for recorded program; **re-run** gate + Phase H + BR-13 each release.

- [x] siteconfig materially decomposed (bounded contexts + lints)
- [x] SiteSettings not tenant-behavior truth (runtime-first)
- [x] Runtime = legal behavior engine (contract tests + inspector)
- [x] AI secrets safe (gateway + lint_secret_exposure)
- [x] Public surfaces hardened (ledgers + lints + webhook signatures)
- [x] Gilead residue gone from live surfaces (0155 + lint)
- [x] Studio OS replaces fragmented tools (five hubs + redirects)
- [x] Package engine production-grade (`packages/engine.py` + tests)
- [x] Marketplace/packs productized (catalog minimums + UI)
- [x] Docs truth aligned (DOCS_TRUTH_AUDIT + this file)
- [x] Marketing front platform-grade ([MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md))

## 12.1 Evidence

| Gate | Verify | In `pre_deploy_gate` |
|------|--------|----------------------|
| siteconfig / SiteSettings | `lint_tenant_settings`, `lint_siteconfig_legacy_imports`, domain_ownership docs | Yes |
| Runtime | `test_runtime_contract`, `runtime_precedence.md` | Yes |
| AI | `lint_secret_exposure` | Yes |
| Public / SQL / except | csrf/allow_any/raw_sql/broad_except lints | Yes |
| Gilead | `lint_gilead_residue` | Yes |
| Packages / marketplace | packages tests, `generate_platform_inventory --check` | Yes |
| Studio OS | Staging / manual + URL matrix tests | Partial |
| Marketing | Doc + template wiring | Yes |

**One-liner:** `bash scripts/pre_deploy_gate.sh` covers the “Yes” rows.

## 12.2 Security review

- [x] Public endpoints, AI gateway, secrets — log in [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) per release policy.

---

# 13. Final statement

RunMyCampus is a **serious multi-tenant platform** with **§12** and **structural north-star** bars **MET**; **market depth** remains **continuous improvement**.

Ongoing mandate: subtractive discipline, runtime/metadata truth, security, low-click UX, honest tracking—**all recorded here and in §11.4**, not in new master plans.

---

# 14. Ledger alias (historical links)

Some docs reference **§14**. **§14 = same authority as §11.4** (consolidated tracking + what’s left). Update those docs to §11.4 when convenient; until then, treat this section as the pointer.
