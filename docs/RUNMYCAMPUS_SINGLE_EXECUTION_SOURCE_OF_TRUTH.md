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

Order-of-magnitude repo scale and lint counts: re-run `scripts/lint_raw_sql_usage.py`, `lint_gilead_residue.py`, `generate_platform_inventory.py`, and tree counts when refreshing; do not treat static numbers as gate truth.

### Premium maturity blockers (honest)

| Theme | Status | Next execution hooks |
|-------|--------|----------------------|
| Shell triad (`/admin`, `/super`, `/studio`) | **PARTIAL** | [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md), `verify_phases_3_11_gates.py` |
| `siteconfig` decomposition | **PARTIAL** | [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md), §11.4 Phase B |
| Gilead residue (full tree) | **PARTIAL** | Runtime lint clean; corpus in docs/migrations—[GILEAD_REFERENCE_CLASSIFICATION.md](GILEAD_REFERENCE_CLASSIFICATION.md) |
| Raw SQL / endpoints | **PARTIAL** | `lint_raw_sql_usage`, Phase 8–9 ledgers |
| AI / provider scatter | **PARTIAL** | Gateway + [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md) |
| Doc / plan density | **PARTIAL** | **This file** + log A–F; no new master plans |

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
| KB/FAQ + LibreOffice tiers (T0–T6) | **BLOCKED (external rollout/sign-off)** | Internal implementation is complete (audience split + FAQ parity + manager `/kb/` + document service + WOPI routes + signed token server-flow + smoke workflow + seeded office docs). Blocker owner: Platform Ops + Release Manager. Reason: requires real staging/prod ingress/TLS + secrets + authenticated operator/tenant browser edit-save sign-off outside repo. Follow-up tracker: [execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md](execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md) and [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). |

**§11.4 slice — AI RAG, migration playbook audit, platform health beats (evidence):**

- **A (RAG + eval):** Daily opt-in beat `ENABLE_AI_KNOWLEDGE_INDEX_BEAT` → `siteconfig.index_ai_knowledge_beat`; policy-scope tenant ranking in `services/ai_memory.py` + policy metadata in `index_ai_knowledge`; gateway regression + safe structured fallback + feedback loop tests (`services/tests/test_ai_gateway_invoke_regression.py`, `services/tests/test_ai_gateway.py`, `services/tests/test_ai_memory.py`, `apps/portal/tests/test_ai_feedback.py`, `apps/siteconfig/tests/test_ai_quality_scorecard.py`); cross-link in `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`.
- **B (Migration):** `execute_playbook` → `AutomationExecutionLog`; quarantine ↔ run FK + admin columns + **`automation:outcomes_console`** quarantine column; preflight confidence guard (`required_field_coverage`, `duplicate_risk`, `rollback_readiness`, `quarantine_risk`) with threshold `MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE` and explicit `override_reason`; tests `apps/automation/tests/test_playbook_quarantine_and_logs.py`, `test_outcomes_console_quarantine.py`, `PlaybookExecutorTests` log assertion; playbook semantics in `docs/architecture/ai_orchestration.md`.
- **C (Non-migration beats):** `ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT`, `ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT`, `ENABLE_AUTOMATION_FAILURE_TREND_BEAT` → `platform_runtime.operator_visibility_heartbeat`, `platform_runtime.database_connectivity_heartbeat`, `platform_runtime.automation_failure_trend_signal`; tests `apps/platform_runtime/tests/test_health_heartbeat_tasks.py`.
- **D (Security + deploy-path enforcement):** Release-readiness gate is code-wired into CI/deploy path (`.github/workflows/smoke.yml` → `scripts/pre_deploy_gate.sh` → `scripts/release_readiness_check.sh` with `RUN_RELEASE_READINESS_GATE=1` default). Forbidden provider scan is Python-based (no `rg` runtime dependency), so gate behavior is deterministic across local/CI shells.

**Verification commands:** `bash scripts/pre_deploy_gate.sh`; `bash scripts/run_phase_h_verification.sh` (or `PHASE_H_SKIP_LIVE=1`); `bash scripts/run_visual_qa.sh`; `python scripts/verify_phases_3_11_gates.py`; dedicated DB: see [TEST_DATABASE.md](TEST_DATABASE.md), [CONTRIBUTING.md](../CONTRIBUTING.md).

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
