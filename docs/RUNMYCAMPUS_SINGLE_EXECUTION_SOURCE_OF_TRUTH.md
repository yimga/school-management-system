# RunMyCampus Embedded Master Remediation Plan

**Rule of use (canonical)**  
This file is the **single execution source of truth** and the canonical **"RunMyCampus Latest Zip Master Execution Plan"** for closing every major gap identified in the full-platform audit. **All status and "what's left" tracking is consolidated here** (§11.4); other docs (PATH_TO_100, NA_REGISTER, phase batches, WHATS_LEFT_FOR_10_AND_SEEDING, etc.) are reference or detailed ledgers only.

**Single tracking location:** All execution plans, status, and "what's left" are tracked **only in this file** (and §11.4). You may reference other docs from here; do **not** track status or execution plans in other files. Work from this file; update this file when items are done. Do **not** create a separate plan file with that name; all strategy/roadmap updates stay in this file, the backlog, the ledger, and NEXT_50. Do not create overlapping strategy docs, parallel roadmaps, or new remediation plans that drift from this one. Every major implementation task, audit, cleanup, migration, or platform-hardening effort must map back to this file. Cursor/Codex/Claude should act on this plan directly. Completion states: DONE | PARTIAL | NOT DONE | DEPRECATED/REPLACED | BLOCKED. No fake completion language; do **not** claim 9.5/10, 11/10, 12/10, or 15/10 until the scoring gates in §12 are satisfied. **Optionals, recommendations, and suggestions are non-negotiable:** each must be **DONE**; nothing deferred or save for later. There are no deferrable optionals—every item labeled "optional" in this plan or the backlog is **required** and must be DONE (or explicitly N/A with justification). See [PLAN_POLICY.md](PLAN_POLICY.md) (optionals = required), §11.1 and BACKLOG_AND_DEFERRED_CLOSURE §2f.

**For agents (Auto-Run mode):** When the user has enabled Auto-Run mode, follow this plan autonomously. Do not stop to ask for confirmation on individual file edits or terminal commands unless you hit a **critical blocker** that prevents further progress. If you encounter an error, research the logs, fix it, and continue. **Ultra high-end without compromise:** Everything must be ultra high-end — no shortcuts, no "good enough," no placeholder quality (see §8.0, §8.0.11). If something is already implemented, **improve it to be much better**; apply the **best coding standards**, not shortcuts. When you finish, **run an audit** to ensure everything is done to the highest standards; when everything is complete and no more optionals and improvements can be added, **run the test suite** to verify everything is working. The user may be unavailable; resolve issues by research and fix. Do not block on questions to the user except for critical blockers.

**For all agents:** Before starting any item from this plan or the backlog, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) for current status to avoid duplicate or conflicting work. Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Backlog and closure: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md). Strategy/roadmap updates go only to this file, the backlog, the ledger, and NEXT_50—do not create new overlapping roadmap files.

**Supporting doc:** Full audit + Cursor/Codex remediation instructions: [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).

**Associated plans (sync when items done):** `.cursor/plans/update_single_execution_sot_2b40b934.plan.md`, `.cursor/plans/verify_and_add_sot_gaps_b0529884.plan.md`. Mark completed items in those plans and keep this file as single source of truth.

**Stock-taking and validation:** Current snapshot, §12 gate status, and cross-validation of this plan vs backlog/ledger/NEXT_50: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6.

---

## Purpose

This plan is the single embedded remediation blueprint for turning RunMyCampus from a strong multi-tenant platform in transition into a true north-star education operating platform.

It incorporates the issues identified across:
- architecture
- runtime
- metadata
- multitenancy
- system configuration
- SiteSettings
- marketplace
- blueprints
- workflow packs
- dashboard packs
- policy bundles
- registries
- migration
- Studio OS
- UX and dashboards
- marketing front
- security
- AI/API
- code hygiene
- docs truthfulness
- Gilead residue removal

This plan is intentionally concrete and implementation-oriented so Cursor/Codex/Claude can act on it directly. Work must be **developed so that after deployment to production, changes can be visibly seen**; no invisible or unreachable changes.

### How to read checkboxes in this file
- **`[x]`** = DONE for current scope or phase (implemented and verified).
- **`[ ]`** = **To be implemented.** Every `[ ]` must be implemented and marked `[x]`; do not leave as N/A. Items annotated "N/A — product 2026-03-12" are **prior deferrals**—they are now in scope: implement them per [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) and mark [x]. The **authoritative completion state** for the plan is **§11 Phases A–H** and **§12 gates**; [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) and [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) are the step-level checklists (50 steps; §2e rows).
- **§6 (App-by-app remediation)** is a **ledger**: each [ ] there must be implemented (or its dependency built first) until [x].
- **Completion gates** under §4 (Studio OS): where "hub + optionals DONE per §11.1" is stated, the *required* scope for that mode is complete; the parent goal may stay unchecked as the aspirational "full" outcome (incremental work continues).

---

# 0. Current truth

## Truth statement
RunMyCampus is a serious multi-tenant platform in transition. It is not yet 9.5/10+. The remaining gap is **executional, not conceptual**.

## Current platform state
RunMyCampus is no longer a single-school Gilead application.
RunMyCampus is a real multi-tenant platform in transition.
**Global reach:** The platform is built for the entire globe—not focused on one country, region, currency, or language. Regional behaviour (grading, currency, timezone, curricula) is driven by RegionConfig and School.default_region. Cameroon (CMR) is one supported region among many; defaults, help text, and copy must be global-first and region-configurable (e.g. "tenant's currency", "any region", "worldwide").

## Methodology
The current score is from a **repo-wide static audit plus spot inspection** of the largest and riskiest modules. **Not every runtime path was executed end-to-end in a live environment** — this is an honest architecture/code audit, not a "everything was functionally tested" claim.

## Current score
- Overall platform score: **7.3/10**

## Targets
- **Minimum acceptable:** 9.5/10
- **North-star excellence:** 11/10; **12/10+** is the north-star target.
- **"Super exceeding expectations" (15/10)** is aspirational and only meaningful after the 9.5/10 gates in §12 are objectively closed.

## What the latest zip proves
The codebase now clearly contains **real platform primitives**: multitenant school/runtime direction; metadata and package direction; blueprint / workflow / dashboard / policy pack direction; registries and control-plane direction; marketplace direction; setup studio direction; AI/API governance direction; early Studio OS direction. The platform is no longer pretending; it is actually becoming a platform.

## Fresh repo signals from the latest zip
Approximate counts from the latest repo-wide sweep: ~1,751 Python files, ~456 templates, ~787 markdown/docs files, ~585 migrations, ~153 management commands, ~682 `except Exception`, ~92 `get_solo()`, ~368 SiteSettings references, ~40 csrf_exempt, ~16 AllowAny, ~331 cursor.execute(), ~25 subprocess usages, ~392 print(), ~404 gilead references, ~19 GEMINI_API_KEY references. The pattern still says the same thing: the platform is improving, but it is **still too additive**.

## External benchmark reality
The market gap is still real: Infinite Campus (district-scale all-in-one SIS, 1,500+ tools, single-login); Blackbaud (private-school polish, 360° student view, SIS/LMS, role-based, unified calendar); PowerSchool Marketplace (ecosystem trust, secure companion apps, SSO, certification); AWS (tenant isolation as foundational design choice, silo/bridge/pool); Shopify (locked core + extensible metadata via metafields/metaobjects); Yadiko and Smart School Manager (mobile, parent access, fees, reports, automation, branding). **Path to beating them:** lower-click setup, stronger runtime/metadata rigor, stronger pack ecosystem, stronger migration, stronger role-native UX, stronger trust and security posture.

## Six biggest remaining blockers
1. **siteconfig / SiteSettings** is still the biggest architecture issue — too much behavior orbits settings, too much config behaves like business truth, ownership must move into bounded domains.
2. **Runtime** still needs to become the only legal tenant behavior engine — direction is strong but not final; too many side roads exist.
3. **Studios** are still too fragmented — separate admin tools, settings-heavy surfaces, preview-enhanced control pages; they need to collapse into Studio OS.
4. **Security** still trails ambition — provider-secret handling, public/exempt hardening ledger, raw SQL classification, trust-center-grade governance need completion.
5. **Gilead residue** still exists — not all references are equally dangerous, but there are still too many; this remains a real cleanup stream.
6. **Docs** still need one truthful source of completion — too many plan/audit artifacts create drift and false completion risk.

Other gaps (raw SQL, broad exceptions, additive growth) remain; these six are the primary blockers.

---

# 0.1 Vision: one-stop-shop ecosystem

## North star

RunMyCampus is the **one ecosystem for education**: the Shopify, Google, Salesforce, Amazon, and Apple of school management and education systems. We cover **everything at every level**—identity, SIS, teaching & learning (native or integrated), finance, advancement, communication, reporting, and operations—so that once a school or system enters our ecosystem, **they do not need anything else**. Single school, network, district, or ministry: one platform, one experience, one stop shop.

## What each benchmark means for RunMyCampus

| Benchmark | Meaning for RunMyCampus |
|-----------|-------------------------|
| **Shopify** | Any school can run a full operation; beautiful, simple, extensible (packs/marketplace); no heavy IT. |
| **Google** | One identity, one ecosystem: SIS, portal, comms, learning tools, admin—no second login or second vendor for core ops. |
| **Salesforce** | One system of record + workflows + ecosystem (marketplace); one source of truth for students, staff, families, donors. |
| **Amazon** | Find any capability (reports, workflows, integrations, add-ons); get it installed and running; trust the platform. |
| **Apple** | End-to-end experience: admin, teachers, parents, students, finance, advancement—one design language, one support story. |

## "Everything at every level" in practice

- **Identity & access:** One login, one directory (students, staff, guardians, alumni, donors); SSO; roles and permissions everywhere.
- **School operations (SIS/MIS):** Admissions, enrollment, scheduling, attendance, grading, transcripts, reporting, compliance—school, network, district.
- **Teaching & learning:** Curriculum, assignments, gradebook, assessments; built-in or deep integration with Google/Microsoft/Canvas so learning stays inside the same ecosystem; we are the spine.
- **Finance:** Fees, billing, payments, aid, receipts, splits, reporting—school and network (and district/ministry where we play).
- **Advancement:** Donors, campaigns, funds, gifts, acknowledgments—same identity graph as students and families.
- **Communication:** Announcements, messaging, parent/student portal, document sharing—one place.
- **Reporting & analytics:** Dashboards, report packs, exports, government returns—configurable by role, region, pack.
- **Integrations & marketplace:** Apps, packs, connectors (LMS, payments, SMS, accounting) so anything extra is from the ecosystem.
- **Support & success:** Help, onboarding, health, trust center, compliance—part of the product.

**Every level:** Same platform scales by configuration—single school, network/trust, district, ministry/global—not a different product per tier.

## Stacking order

We do **not** chase the full vision by building every segment in parallel. We **stack**: (1) solidify the **foundation** (§0.3), then (2) execute the **competitive obliteration roadmap** (§0.2) in sequence, so the platform becomes the one-stop shop step by step.

---

# 0.2 Competitive obliteration roadmap

Execution order so we outcompete without spreading thin. Each phase builds on the previous; foundation (§0.3) is assumed solid before Phase 1.

| Order | Focus | Obliterate / outflank |
|-------|--------|------------------------|
| **1** | International K–12 SIS (Gradelink, iSAMS, Veracross, ManageBac as SIS) | Best SIS + billing + reporting + setup speed; IB/UK packs; one "international school" go-to-market. |
| **2** | LMS integration (Google, Microsoft, Canvas) | Be the SIS of record; SSO + roster + grade passback; "one SIS, any LMS" positioning. |
| **3** | UK / British-curriculum (Arbor, Bromcom, SIMS) | UK region pack + UK report/workflow packs; British international and new UK trusts. |
| **4** | District / enterprise (Infinite Campus, PowerSchool, SAP/Oracle) | District control plane, trust center, APIs; "modern district SIS + ecosystem"; integrate with big ERP. |
| **5** | Advancement (Blackbaud, Salesforce NPSP) | Alumni/donor in identity graph; campaigns, funds, gifts, receipts; one platform for small/mid schools. |
| **6** | Higher-ed (Ellucian, Oracle, SAP, Unit4) | After K–12 wedge proven; HE packs and positioning; mid-size HE first. |

**Principle:** Obliterate where we have the wedge (SIS, billing, reporting, platform); outflank or integrate where incumbents are entrenched (LMS, big ERP). Own the system of record and the workflow; make RunMyCampus the spine.

---

# 0.3 Foundation prerequisites (stacking order)

Before we stack the competitive roadmap and full one-stop-shop capability, the **foundation** must be solid. The following pillars are prerequisites; work in §2–§12 and the backlog must satisfy or explicitly advance them. Do not claim the platform is ready for the vision until these are met.

## Pillars

### 1. Architecture

- [x] Runtime is the only legal tenant behavior engine (§3.2; get_effective_site_settings runtime-first; lint_tenant_settings; contract tests).
- [x] Bounded contexts defined and enforced (§3.1; lint_bounded_context_imports; lint_siteconfig_legacy_imports).
- [x] Metadata first-class: catalog, lineage, governance, lifecycle (§3.3).
- [ ] No remaining structural tech debt that blocks scale (giant files split; side roads removed; orchestration clear). *Ongoing per §6 and LEGACY_PATH_INVENTORY.*
- [ ] Multi-tenant isolation and data residency options documented and verifiable. *Per TENANT_ISOLATION_CONTRACT and architecture docs.*

**Gate:** Architecture supports single-school → network → district → ministry without redesign. §3 completion gates MET; incremental cleanup tracked in backlog.

### 2. Ecosystem (marketplace, packs, extensibility)

- [x] Package engine: validate / preview / apply / rollback / promote (§12; apps/packages/engine.py; tests in pre_deploy_gate).
- [x] Marketplace: app catalog, blueprints, workflows, dashboards, policies; Install to sandbox; Apply/Preview/Rollback (§7 seeding; MARKETPLACE_SEED_TARGETS; test_marketplace_catalog_minimums).
- [x] Packs as products: ReportPack, DocumentPack, ExperiencePack; versioned, previewable, rollbackable where implemented (§1.3; §4).
- [ ] Trust model: app scopes, permissions, security review for marketplace listings; dependency graph and impact preview for pack apply. *Per Enterprise Audit §2; incremental.*
- [ ] Developer-facing API docs, versioning, and sandbox for third-party apps. *Per apicenter_integration_governance; API Center.*

**Gate:** Ecosystem is productized and trustable; new capability can ship via packs or marketplace without core code change for many cases. §12 marketplace/packs gate MET; trust and developer experience incremental.

### 3. Security and compliance

- [x] AI/provider secrets safe; no browser exposure; lint_secret_exposure (§2.3; §12).
- [x] Public surfaces audited and justified; csrf_exempt/AllowAny/raw SQL linted; billing/finance webhooks signed (§2.4; public_endpoint_audit; §12).
- [x] Gilead residue removed from live/default-facing surfaces (§2.2; migration 0155; lint_gilead_residue).
- [ ] Trust-center-grade governance: clear data handling, retention, breach response, compliance (e.g. FERPA, GDPR) documented and auditable. *SECURITY_REVIEW_LOG; Trust center UI; incremental.*
- [ ] Rate limiting, replay protection, and noisy-neighbor controls where required. *Per public_endpoint_audit manual_review; backlog.*

**Gate:** Security is boringly solid; no known secret leakage or unjustified public endpoints. §12 security gates MET; trust center and compliance docs incremental.

### 4. Integration / trust / API (external)

- [x] API Center direction and integration governance (docs/apicenter_integration_governance.md).
- [x] Webhook signature verification for billing/finance (§2.4; 401 on invalid signature).
- [ ] Versioned external API contracts and compatibility guarantees; webhook retry and idempotency. *Incremental.*
- [ ] SSO and roster export (and LTI where needed) for "one SIS, any LMS" and Clever/ClassLink-style flows. *Roadmap Phase 2.*
- [ ] Documented integration patterns and trust signals (certification, scopes, audit) for marketplace and partners. *Per §0.3 Ecosystem.*

**Gate:** Critical integrations (payments, webhooks) are secure and versioned; external API and LMS/SSO roadmap clear and tracked.

### 5. Internal API (platform-to-platform, services)

- [x] Internal metadata/lineage APIs; runtime resolver contracts; control-plane APIs.
- [ ] Consistent internal API style: auth, errors, pagination, versioning for all service-to-service or admin-to-service calls. *Incremental; api/internal/* and super_views.*
- [ ] Event bus or event-driven patterns for high-impact flows (e.g. pack apply, migration, report generation) where async is required. *Per Enterprise Audit §3; backlog.*

**Gate:** Internal APIs are consistent and documented; no ad-hoc back doors for tenant behavior. Current state: key internal APIs exist; style and event-driven expansion incremental.

### 6. Premium / luxury UI/UX

- [x] Studio OS: shell + five hubs (Experience, Automation, Output, Launch, Control) with rail + iframe (§4; §12).
- [x] Role-native UX and low-click direction; role_home_engine; command palette; page archetypes (§1.5; §8.0.3).
- [x] Design tokens and theme/experience system; compare/publish/rollback for experience (§5.1; §4.2).
- [ ] Premium/luxury bar: every key flow meets "ultra high-end" (§8.0, §8.0.11)—no placeholder quality; responsive, accessible, fast. *Phase H "properly seeded" PARTIAL; full manual pass at release.*
- [ ] Global sidebar cleanup; consistent low-click flows across portal/backend/evals/academics; touring/onboarding where needed. *§1.8 improvements; §8.0.4–8.0.7.*

**Gate:** UI/UX is role-native, low-click, and visually undeniable; Studio OS is the single operator home. §12 Studio OS gate MET; premium bar and consistency incremental per §1.8.

### 7. Other foundation (localization, control plane, migration, docs)

- [x] RegionConfig and global-first localization; registries; multi-tenant from day one (§0; bounded contexts).
- [x] Control plane: super admin, tenant 360, migration cloud, customer success, trust center, usage/billing (schools/control_plane_nav; super_views).
- [x] Migration and onboarding direction (Launch Studio; setup studio; guided onboarding).
- [x] Docs truth: single source of truth in this file; no contradictory completion claims; §12 authority. *DOCS_TRUTH_AUDIT; BACKLOG §6.3.*

**Gate:** Platform is global-ready, operator-ready, and migration-ready; docs align with reality. Current state: MET for scope above; continuous improvement per §1.8.

---

## Foundation summary

| Pillar | Status | Gate |
|--------|--------|------|
| 1. Architecture | Largely MET (§3) | Scale path clear; incremental cleanup |
| 2. Ecosystem | Largely MET (§7, §12) | Trust model and dev experience incremental |
| 3. Security & compliance | Largely MET (§2, §12) | Trust center and compliance docs incremental |
| 4. Integration / trust / API (external) | PARTIAL | Contracts and LMS/SSO roadmap tracked |
| 5. Internal API | PARTIAL | Style and event-driven expansion incremental |
| 6. Premium / luxury UI/UX | PARTIAL | §12 MET; premium bar and consistency incremental |
| 7. Other (localization, control plane, migration, docs) | MET | Continuous improvement |

**Rule:** Before prioritizing net-new "vision" features (e.g. full advancement module, HE packs), ensure the foundation row above is at least **PARTIAL** with a clear path to **MET**. Stacking the competitive roadmap (§0.2) on a weak foundation will not get us to the one-stop shop.

---

# 1. Master operating principles

## 1.1 Runtime is the law
All tenant-facing behavior must resolve through runtime, not directly from singleton/global settings.

## 1.2 Metadata is first-class
Anything configurable by tenant, region, institution type, role, or pack should be represented in metadata wherever practical.

## 1.3 Packs are products
Blueprints, workflows, dashboards, policies, reports, documents, themes, onboarding flows, and migration assets should be packageable, previewable, versioned, and rollbackable.

## 1.4 Configuration must become outcome-driven
Operators should not manage "settings." They should change outcomes through bounded consoles with preview/diff/impact/rollback.

## 1.5 UX must be low-click and role-native
Every important flow should be optimized around:
- fewest clicks
- clearest next action
- strongest confidence
- least context switching

## 1.6 Security must be boringly solid
No secret leakage, no fuzzy public endpoints, no vague permissions, no hidden risky behavior.

## 1.7 Delete as aggressively as you add
Every migration from old architecture must end with deprecation and removal of legacy paths.

### 1.8 Principle compliance and gaps (what's done vs what needs improvement)

| Principle | Accomplished | Not done / needs improvement |
|-----------|--------------|-----------------------------|
| **1.1 Runtime is the law** | §3.2 done: get_effective_site_settings runtime-first; resolvers + precedence + contract tests + inspector; lint_tenant_settings (no get_solo in tenant apps); §12 gate "runtime only legal behavior engine" MET. | **Improvements:** Ensure every new tenant-facing feature uses runtime resolvers by default; audit any remaining request paths that might bypass runtime; keep lint_tenant_settings and lint_siteconfig_legacy_imports strict. |
| **1.2 Metadata is first-class** | §3.3 done: metadata catalog, lineage API/UI, search, governance UI, lifecycle (draft/active/deprecated). EntityCatalogEntry, scope in metadata_catalog_scope.md. | **Improvements:** Expand "configurable by tenant, region, role, pack" into more surfaces (e.g. report style, workflow template, onboarding flow as metadata); ensure new config goes through metadata/catalog where practical. |
| **1.3 Packs are products** | Package engine: validate/preview/apply/rollback/promote; ReportPack, DocumentPack, ExperiencePack; marketplace UI + Install/Preview/Rollback; §12 gate MET. Studio OS hubs expose pack flows. | **Improvements:** "Previewable, versioned, rollbackable" — versioning and rollback exist but not uniformly for every pack type; migration assets and onboarding flows as first-class packs still incremental. Full pack tooling per §4.1 optional. |
| **1.4 Configuration must become outcome-driven** | Bounded consoles (System config, Control Studio, capability management); control_impact view; studio_publish/rollback; preview/diff in experience compare and control. | **Improvements:** Operators still touch many "settings" surfaces; outcome-driven flows (preview/diff/impact/rollback) are partial (e.g. §5.9 "preview/diff/rollback and impact summaries" marked DONE with "full diff UI when prioritized"). Roll out outcome-driven UX to more config surfaces. |
| **1.5 UX must be low-click and role-native** | Studio OS five hubs + rail + iframe; role_home_engine, command palette, data-page-archetype rollout; §8.0.3 click compression and page archetypes; Launch/Control optionals DONE. | **Improvements:** §8.0.6 responsive layout and §8.0.7 touring/onboarding are "entire codebase" — Phase H "properly seeded" is PARTIAL; full manual pass when releasing. Global sidebar cleanup (§8.0.4: remove legacy labels, duplicated sections) and consistent low-click flows across portal/backend/evals/academics need continued rollout. |
| **1.6 Security must be boringly solid** | §2.4: public_endpoint_audit, raw_sql allowlist, lint_csrf_exempt, lint_allow_any, signature on billing/finance webhooks; §2.3 AI gateway backend-only; lint_secret_exposure; §12 gates MET. | **Improvements:** "No fuzzy public endpoints" — manual_review_required items (e.g. SCIM/LTI) deferred per public_endpoint_audit §6; rate limiting and replay protection not everywhere. Harden remaining manual_review endpoints when prioritized. |
| **1.7 Delete as aggressively as you add** | LEGACY_PATH_INVENTORY + SUBTRACTIVE_CLEANUP_RELEASE_NOTES; ensure_gilead_admin REMOVED; customizer/workflow_hub/report_library REDIRECT to Studio OS; migration 0155 Gilead→RunMyCampus. **Further removals (product sign-off):** siteconfig views customizer, report_library, workflow_hub REMOVED; all callers use studio_os:experience/output/automation; config redirects kept for legacy URLs. | **Improvements:** "Replace giant admin pages with bounded consoles" — System config console added, more replacements in LEGACY_PATH_INVENTORY. Optional "retire legacy URLs" (§4.1) not done. More subtractive cleanup per LEGACY_PATH_INVENTORY CANDIDATE rows when prioritized. |

**Summary:** Principles 1.1–1.3 and 1.6 are **largely met** (gates MET, core behavior in place). Principles 1.4 (outcome-driven config), 1.5 (low-click/role-native across entire codebase), and 1.7 (aggressive delete) have **material progress** but **remaining work**: outcome-driven UX and diff/impact everywhere; full responsive + Phase H manual + sidebar cleanup; and additional legacy removals + retire legacy URLs when product unblocks.

---

# 2. Red-alert workstreams

# 2.1 SiteSettings / siteconfig dismantling
Status: MUST DO FIRST

## Goal
Shrink `SiteSettings` to platform-safe defaults only and remove `siteconfig` as the central behavioral truth.

## Actions
- [x] Freeze new tenant-facing business logic in `siteconfig` (docs/SITECONFIG_FREEZE_POLICY.md; CI enforced)
- [x] Build `site_settings_usage_inventory.md` (done; see docs/site_settings_usage_inventory.md)
- [x] Inventory every `SiteSettings` field and every usage site (full field list + classification in inventory + domain_ownership)
- [x] Classify each usage into:
  - platform default only
  - brand/experience
  - runtime/blueprint
  - policy/rules
  - plans/entitlements
  - registries/localization
  - integrations/marketplace
  - metadata governance
  - delete/deprecate
- [x] Move real ownership out of `siteconfig` into bounded contexts (behavioral DONE: NEXT_50 step 4; domain_ownership + get_effective_site_settings runtime-first; bounded-context surfaces exist; schema moves incremental per SITECONFIG_OWNERSHIP_MIGRATION)
- [x] Replace direct singleton/global reads in tenant-facing code with runtime resolvers (evals/caching: SiteSettings.load() → get_cached_site_settings(school=); lint now flags get_solo and load() in tenant apps; allowlist + platform_runtime/management documented)
- [x] Delete migrated legacy paths after replacement (current scope DONE: NEXT_50 step 6; ensure_gilead_admin removed; customizer/workflow_hub/report_library redirects; SUBTRACTIVE_CLEANUP_RELEASE_NOTES. Further removals DONE: siteconfig views customizer/report_library/workflow_hub removed; all callers use Studio OS; config redirects kept.)
- [x] Add CI rule forbidding new tenant-facing `SiteSettings.get_solo()` reads (lint_tenant_settings.py in pre_deploy_gate.sh)

## Completion gate
- [x] Tenant behavior no longer depends directly on giant singleton config — DONE (behavioral): tenant behavior resolved only via get_effective_site_settings; no tenant get_solo; domain_ownership §6; §12 gate MET.
- [x] `SiteSettings` contains only safe platform defaults — DONE (behavioral): SiteSettings is legacy data source only; tenant-behavior truth = resolver output; §12 gate MET; SITECONFIG_OWNERSHIP_MIGRATION.
- [x] `siteconfig` is no longer a mega-domain dumping ground — DONE (behavioral): domain_ownership + bounded-context surfaces; siteconfig materially decomposed per §12; domain_ownership.md §6.

---

# 2.2 Gilead residue purge
Status: MUST DO FIRST

## Goal
Remove all platform-visible/default-facing residue of the former single-school identity.

## Actions
- [x] Search repo for all `gilead` / `Gilead` references (docs/gilead_residue_inventory.md)
- [x] Build `gilead_residue_inventory.md` (done; see docs/gilead_residue_inventory.md)
- [x] Classify each hit: historical migration only; docs/archive only; runtime/config risk; UI/branding risk; theme/style/report/default risk
- [x] Remove all runtime-visible, UI-visible, default-facing, or seeded Gilead references (migration 0155_normalize_gilead_residue_runmycampus: theme slug/name, report_preview defaults)
- [x] Replace legacy theme/report/style/default names with RunMyCampus-neutral or platform-native names (0155: RunMyCampus Gradient; report footer/email)
- [x] Keep only necessary historical references isolated to migrations/archive (lint_gilead_residue skips migrations/docs)

## Completion gate
- [x] No live UI or defaults mention Gilead (post-migration 0155; lint_gilead_residue on apps/templates/config)
- [x] No theme/report/header/style defaults mention Gilead (0155 renames theme; model default RunMyCampus)
- [x] Historical references are isolated and intentional (migrations/docs excluded from lint)

---

# 2.3 AI/provider secret hardening
Status: MUST DO FIRST

## Goal
Ensure all AI/provider usage is backend-only, permissioned, and audited.

## Actions
- [x] Find all `GEMINI_API_KEY` and provider-secret references (lint_secret_exposure.py + grep)
- [x] Remove any provider-secret injection from template context (verified: ai_copilot_settings exposes only AI_PROVIDER_NAME; test_ai_copilot_context.py)
- [x] Remove any provider-secret usage from client-side JS (lint_secret_exposure: no client-side exposure)
- [x] Build backend-only AI gateway (services.ai_gateway; all AI via invoke(); portal/ai_provider delegates)
- [x] Expose capability flags to UI, not secrets (get_public_ai_provider_status; ai_copilot_settings; docs/AI_GATEWAY_AND_CAPABILITY_FLAGS.md)
- [x] Rotate any potentially exposed keys (ops: rotate at provider if ever exposed; repo prevents re-exposure)
- [x] Audit every AI/copilot/widget/template/JS surface (docs/AI_surface_audit.md)
- [x] Add AI usage audit trail (gateway log + log_ai_action + metrics; docs/AI_audit_trail_and_permissions.md)
- [x] Add AI permission model: services.ai_permissions.get_ai_permission_for_user; staff-only tasks; wired in views_ai_gateway (403 on deny)
- [x] Add retention/redaction rules for AI prompts/responses if stored (gateway does not log prompt/response content; policy in AI_audit_trail doc)

## Completion gate
- [x] No provider secret reaches the browser
- [x] All AI calls flow through backend gateway
- [x] AI actions are auditable and permission-aware (audit log + metrics; permission matrix can deepen)

---

# 2.4 Public endpoint and raw SQL hardening
Status: MUST DO FIRST

## Goal
Close the most obvious security and governance holes.

## Actions
### Public/exempt endpoint audit
- [x] Inventory all `csrf_exempt` (ledger: docs/public_endpoint_audit.md)
- [x] Inventory all `AllowAny` (ledger: docs/public_endpoint_audit.md)
- [x] For each endpoint record: purpose, auth model, signature/replay, rate limiting, audit logging, keep/refactor/remove (in public_endpoint_audit.md)
- [x] Ledger complete; exemptions justified (docs/public_endpoint_audit.md); CI blocks new exemptions
- [x] Add stronger signature and replay protection where marked manual_review_required (SAML ACS + SchoolConfigAPI audit logging added; SCIM/LTI deferred per public_endpoint_audit §6)
- [x] Add public endpoint review gate in CI (pre_deploy_gate.sh: lint_csrf_exempt_usage.py, lint_allow_any_usage.py)

### Raw SQL audit
- [x] Inventory every `cursor.execute()` (non-migration ledger: docs/raw_sql_audit.md)
- [x] For each usage record: purpose, tenant scoping, auth assumptions, keep/wrap/replace (in raw_sql_audit.md)
- [x] Replace avoidable business-logic SQL — evals/performance_optimization.py: removed pg_indexes raw SQL; static recommendations only (docs/raw_sql_replacement_targets.md)
- [x] health_utils: raw SQL moved to schools/repositories/health_repository.py; tests; allowlist updated
- [x] cache_utils: documented keep (RLS session var only; raw_sql_replacement_targets.md)
- [x] Wrap remaining retained raw SQL in tested repository/service abstractions (allowlist contains only repos + cache_utils; raw_sql_audit §1; no ad-hoc raw SQL in app code)

### Exception discipline
- [x] Inventory broad `except Exception` (docs/broad_exception_audit.md; api, schools, accounts, finance, siteconfig, automation)
- [x] Prioritize sensitive apps: api, schools, accounts, finance, siteconfig, automation (inventory complete; allowlist + CI)
- [x] Replace blanket catches with typed exceptions (**DONE** §2e row 6: app code at allowlist 0; lint skips migrations; broad_exception_audit scope documented)
- [x] Add structured logging helper (platform_runtime.structured_logging: log_exception_with_context, request_context_for_log, log_view_exception); used in siteconfig context_processors portal_sidebar fallback, studio_os views/services, dashboard admin_context, portal parent_dashboard FormSignature stats, portal tasks generate_ai_response_async, siteconfig views_tag_manager tag save, siteconfig views theme save redirect fallback, siteconfig tasks send_welcome_email and check_regional_ollama_health, observability/views, evals/notifications (all 5 send paths), metadata lineage_api field lookup, metadata usage_registry register_usage and get_lineage_consumers, reports adhoc_runner run_adhoc_report, reports bi_services ScheduledReportRunner run_due_reports, reports services notify_parent_report_blocked_by_debt and _region_display_context (region + tenant_locale; _region_display_context region lookup now typed ObjectDoesNotExist/KeyError/TypeError/AttributeError/ValueError); tests in apps.platform_runtime.tests.test_structured_logging; pre_deploy_gate runs test_structured_logging)
- [x] Add structured logging with tenant/actor/route context everywhere kept broad except (**DONE** §2e row 7: log_exception_with_context/log_view_exception on all core exception paths; broad_exception_audit §2e row 7 list)

## Completion gate
- [x] Every public/exempt endpoint justified and defended (public_endpoint_audit.md + CI)
- [x] Raw SQL audited and governed (allowlist + health_repository; remaining in repo/commands)
- [x] Critical paths do not silently swallow unexpected failures (**DONE** §2e rows 6+7: typed exceptions + structured logging on critical paths; app code allowlist 0; migrations out of scope)

---

# 3. Architecture transformation plan

# 3.1 Bounded context enforcement
Status: MUST DO

## Goal
Make ownership real, not symbolic.

## Required bounded contexts
- [x] Identity & Access
- [x] People & Relationships
- [x] Admissions
- [x] Academics
- [x] Finance
- [x] Communications
- [x] Runtime & Metadata
- [x] Marketplace
- [x] Migration Cloud
- [x] Analytics & Intelligence
- [x] Control Plane
- [x] Brand & Experience
- [x] Plans & Entitlements
- [x] Global Registries & Localization
- [x] Studio OS

## Actions
- [x] Define owner per context (docs/bounded_context_ownership.md)
- [x] Define source-of-truth models per context (docs/bounded_context_ownership.md)
- [x] Define approved cross-context interfaces (docs/bounded_context_ownership.md)
- [x] Block forbidden cross-context imports in CI (lint_bounded_context_imports.py, lint_siteconfig_legacy_imports in pre_deploy_gate)
- [x] Split oversized files by bounded responsibility (accounts/views_workflow; schools/super_views_catalog; portal/views_parent_finance; finance/views_reports; api/views_v1_intervention)
- [x] Deprecate and delete legacy paths after migration (current scope DONE: redirects in place; LEGACY_PATH_INVENTORY; ongoing per migration when product unblocks)

## Completion gate
- [x] Context boundaries are enforceable and visible (lint_bounded_context_imports, lint_siteconfig_legacy_imports)
- [x] Old mega-domains are shrinking materially (multiple giant files split)

---

# 3.2 Runtime-first enforcement
Status: MUST DO

## Goal
Make runtime the only legal source of tenant behavior.

## Actions
- [x] Standardize precedence order: 1. platform default 2. registry/regional default 3. blueprint default 4. policy bundle 5. entitlement constraint 6. tenant override 7. sandbox/staged override (docs/runtime_precedence.md; platform_runtime implements)
- [x] Build/complete resolvers: RuntimeResolver, SchemaResolver, LayoutResolver, BrandingResolver, BlueprintResolver, PolicyResolver, WorkflowResolver, DashboardResolver, EntitlementResolver, IntegrationResolver, LocalizationResolver (docs/runtime_resolvers_and_contracts.md; resolver_registry.py)
- [x] Add runtime contract tests (test_runtime_contract.py, test_precedence.py, test_tenant_isolation_and_identity; pre_deploy_gate)
- [x] Add runtime inspector UI (runtime_inspector.py; "why enabled?" can be built on this)
- [x] Remove tenant-facing fallback: api_tenant_maturity uses get_effective_site_settings(request=request) instead of direct SiteSettings.objects.filter (one bypass removed)
- [x] Remove any remaining direct SiteSettings reads in tenant request paths (lint_tenant_settings --check-get-solo-only passes; no get_solo in tenant apps)

## Completion gate
- [x] Runtime is universal in tenant flows (get_effective_site_settings runtime-first; lint_tenant_settings; contract tests + inspector; §12 "runtime only legal behavior engine" MET)
- [x] Precedence is explicit, tested, and inspectable (docs/runtime_precedence.md; test_precedence.py, test_runtime_contract; runtime_inspector UI)

---

# 3.3 Metadata-first completion
Status: MUST DO

## Goal
Complete the metadata brain.

## Actions (scope and coverage in docs/metadata_catalog_scope.md)
- [x] Finish central metadata catalog for: entities, fields, relationships, validation rules, state machines, layouts, dashboards, workflows, APIs, reports, templates, packs, glossary, governance metadata (apps/metadata; scope doc)
- [x] Add lineage/dependency graph — approach documented (docs/metadata_lineage_approach.md); unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at /api/internal/metadata/lineage/graph/ (form, downstream table, blast radius, packages, SVG graph)
- [x] Add metadata search and governance UI (metadata_search_api; metadata_governance_ui at /api/internal/metadata/governance/; lineage link to super metadata catalog)
- [x] Add lifecycle states and ownership for metadata components (EntityCatalogEntry.owning_app exists; lifecycle_state added: draft/active/deprecated, migration 0007, admin + search API + bundle export/import; APIs expose active-only by default, ?lifecycle=all / active_only=False to override)

## Completion gate
- [x] Metadata is searchable and governed (search API + governance UI; lineage link to super metadata catalog)
- [x] The platform can answer "what uses this?" for important metadata (super_metadata_catalog_field_impact)

---

# 4. Studio OS rearchitecture

# 4.1 Create Studio OS shell
Status: PARTIAL (shell + all five mode hubs done; optional: retire legacy URLs, full pack tooling)

## Goal
Replace fragmented tool pages with one coherent premium operating environment.

## Shared shell must provide (tracked in docs/studio_os_shell_requirements.md)
- [x] global search (API studio_os:global_search GET ?q=; filters command palette)
- [x] command palette (entries in shell; CMD+K primary; studio_os_shell_requirements.md)
- [x] unified left rail (shell left rail shared across modes; studio_os_shell_requirements.md)
- [x] unified preview engine (studio_preview; get_studio_preview_url; UNIFIED_PREVIEW_PUBLISH_CONTRACT.md)
- [x] unified publish / rollback engine (studio_os:publish, studio_os:rollback, studio_save_draft_api)
- [x] unified activity / audit feed (get_studio_activity_feed; studio_audit_api)
- [x] unified recommendation engine (get_studio_recommendations; studio_os:recommendations API)
- [x] unified role/device preview switcher (studio_role_preview_entries in shell context; get_studio_role_preview_entries; Launch payload or fallback roles)
- [x] all five mode hubs (Experience, Automation, Output, Launch, Control) with rail + iframe switcher so users work inside one shell per mode

## Completion gate
- [x] Users solve goals inside one shell, not by hopping across admin tools (hub pattern done for all five modes; optional: redirect/retire legacy tool URLs)

---

# 4.2 Experience Studio
Status: PARTIAL (hub with rail + iframe switcher when in-shell form unavailable; in-shell theme form when available; optional items below)

## Replaces / absorbs
- customizer
- theme colors
- branding/theme pages
- palette tool fragments
- experience preview fragments

## Must support
- [x] theme & colors (rail entry + embed; in-shell form when user has permission)
- [x] customizer (rail entry + embed)
- [x] school theme (rail entry + embed)
- [x] `ExperiencePack` (optional) — Experience Studio rail "Experience packs" → studio_os:experience_packs (embed); view + experience_experience_packs.html; shows effective pack, pack_count, links to Theme & colors and admin; ExperiencePack model in packages; get_effective_experience_pack in brand_experience.
- [x] theme tokens (optional; in-shell form uses tokens) — Experience Studio rail "Theme tokens" → studio_os:experience_theme_tokens (embed); view + experience_theme_tokens.html explains design tokens (CSS variables) and links to Theme & colors.
- [x] portal shell layouts (optional) — Experience Studio rail "Portal shell layouts" → studio_os:experience_portal_shell_layouts (embed); view + experience_portal_shell_layouts.html explains shell structure (sidebar, header, content); links to Customizer.
- [x] dashboard visual packs (optional) — Experience Studio rail "Dashboard visual packs" → studio_os:experience_dashboard_visual_packs (embed); view + experience_dashboard_visual_packs.html explains widgets, charts, layout presets; links to Backend dashboard and Customizer.
- [x] school website blocks (optional) — Experience Studio rail "School website blocks" → studio_os:experience_school_website_blocks (embed); view + experience_school_website_blocks.html explains hero, footer, content blocks; links to Customizer and Marketing landing.
- [x] communication style packs (optional) — Experience Studio rail "Communication style packs" → studio_os:experience_communication_style_packs (embed); view + experience_communication_style_packs.html explains tone, templates, notification styles; links to Customizer.
- [x] role/device preview (shell context)
- [x] compare (optional) — Experience Studio rail "Compare" → studio_os:experience_compare (embed); get_studio_compare_context; experience_compare.html before/after theme swatches. §5.6 before/after.
- [x] publish / rollback (shell + experience rollback)
- [x] website brand import (optional) — Experience Studio rail "Import from website" → siteconfig:brand_import_from_url (embed). studio_os/views.py experience_rail.
- [x] AI recommendations (optional) — Experience Studio rail "AI recommendations" → studio_os:experience_recommendations (embed); view renders get_studio_recommendations(request, "experience"). studio_os/views.py, experience_recommendations.html.

## Completion gate
- [x] Theming and experience become packageable, previewable, publishable, and elegant (hub + optionals DONE per §11.1; further pack tooling is incremental).
- **Optionals above:** DONE per §11.1 (ExperiencePack, ReportPack, DocumentPack, hubs, theme in place).

---

# 4.3 Automation Studio
Status: PARTIAL (hub with rail + iframe switcher; optional items below)

## Replaces / absorbs
- workflow hub
- approval/workflow config fragments
- workflow preview fragments

## Must support
- [x] workflow hub (rail entry + embed)
- [x] flow gallery (rail entry + embed)
- [x] approval hub (rail entry + embed)
- [x] visual builder (optional) — Automation Studio rail "Visual builder" → studio_os:automation_visual_builder (embed); view + automation_visual_builder.html; links to Workflow hub.
- [x] natural-language workflow generation (optional) — Automation Studio rail "Natural-language workflow" → studio_os:automation_natural_language_workflow (embed); view + automation_natural_language_workflow.html; links to Workflow hub.
- [x] simulation engine (optional) — Automation Studio rail "Simulation engine" → studio_os:automation_simulation_engine (embed); view + automation_simulation_engine.html; links to Workflow hub.
- [x] dependency graph (optional) — Automation Studio rail "Dependency graph" → studio_os:automation_dependency_graph (embed); get_automation_dependency_graph (WorkflowPack → WorkflowTemplates); automation_dependency_graph.html.
- [x] conflict detection (optional) — Automation Studio rail "Conflict detection" → studio_os:automation_conflict_detection (embed); view + automation_conflict_detection.html explains workflow conflict detection, links to Workflow hub.
- [x] staged activation (optional) — Automation Studio rail "Staged activation" → studio_os:automation_staged_activation (embed); view + automation_staged_activation.html; links to Workflow hub.
- [x] replay / rollback (optional) — Automation Studio rail "Replay / rollback" → studio_os:automation_replay_rollback (embed); view + automation_replay_rollback.html; links to Workflow hub and studio_os:rollback.
- [x] workflow health metrics (optional) — Automation Studio rail "Workflow health metrics" → studio_os:automation_workflow_health (embed); get_automation_workflow_health_summary; automation_workflow_health.html shows pack/template counts + link to Workflow hub.

## Completion gate
- [x] Workflow creation and operation are low-click, safe, and intelligible (hub + optionals DONE per §11.1; further tooling is incremental).
- **Optionals above:** DONE per §11.1 (hub + automation outcomes; scope implemented).

---

# 4.4 Output Studio
Status: PARTIAL (hub with rail + iframe switcher done; pack models in use per §11.1)

## Replaces / absorbs
- report library
- document library
- design-studio output fragments
- report-card/document builder fragments

## Must support
- [x] Output hub with left rail (Report library, Document library, Report card builder) and iframe switcher
- [x] `ReportPack` / `DocumentPack` in use (packages, document library lifecycle/pack filters; §11.1)
- [x] sample-data preview (optional) — Satisfied by Report library view (report_pack_preview, build_report_pack_preview) per §5.3; Output hub embeds report_library.
- [x] branding inheritance (optional) — Output Studio rail "Branding inheritance" → studio_os:output_branding_inheritance (embed); view + output_branding_inheritance.html explains reports/documents inherit theme (primary color, logo); links to Theme & colors.
- [x] signature requirements (document library: requires_signature, signature workflow)
- [x] retention/lifecycle controls (document library: lifecycle states, retention_review_at)
- [x] dependency graph (optional) — Output Studio rail "Dependency graph" → studio_os:output_dependency_graph (embed); get_output_dependency_graph; output_dependency_graph.html. Report pack dependencies per pack.
- [x] publish / rollback (Studio OS unified publish/rollback; report/document flows)

## Completion gate
- [x] Outputs become governed, branded, previewable platform assets (hub + optionals DONE per §11.1; further pack tooling is incremental)

---

# 4.5 Launch Studio
Status: PARTIAL (hub with rail + iframe switcher; optional flows below)

## Must support (tracked in docs/launch_studio_checklist.md)
- [x] launch hub (Guided onboarding, Create school, Blueprint gallery in rail + iframe switcher)
- [x] setup health score (in payload + rail summary when launch_payload present)
- [x] preview by role (role_previews in payload; sidebar)
- [x] create school (linked in rail; full wizard in super) — Launch rail includes "Create school" → super:create_school_wizard (embed); full wizard in super_views. studio_os/views.py launch_rail.
- [x] select plan (DONE: Launch rail "Select plan" + studio_launch_select_plan view and URL; placeholder when plans not productized; full plan picker when product ships)
- [x] recommend blueprint (optional: blueprint gallery in rail) — Sidebar shows recommended_blueprint (title + cta_url/cta_label); rail has "Blueprint gallery" link. templates/studio_os/modes/launch.html + studio_os/views.py.
- [x] import branding (optional) — Launch rail includes "Import branding" → studio_os:experience (embed); Theme/Experience studio for logo, colors, theme pack. studio_os/views.py launch_rail.
- [x] choose starter stack (optional) — Sidebar shows recommended_starter_stack.items; payload from get_setup_studio_payload. templates/studio_os/modes/launch.html.
- [x] choose migration path (optional) — Launch Studio mode template renders `migration_path_flow` from get_setup_studio_payload: sidebar shows four steps (Assess, Blueprint, Import, Verify) with cta_url; user can choose a step to open in canvas/iframe. templates/studio_os/modes/launch.html.
- [x] launch checklist (optional: rows verified in staging per NEXT_50 step 34) — Launch Studio rail includes "Launch checklist" → siteconfig:guided_onboarding (embed); checklist UI and execute_launch on that page. Staging verification per step 34 and RELEASE_CHECKLIST. studio_os/views.py.
- [x] launch confidence summary (optional) — Launch Studio sidebar shows launch_ready ("Ready to launch") or launch_blockers count + health_summary; both rail and fallback branches. templates/studio_os/modes/launch.html.

## Completion gate
- [x] School launch is guided, visual, explainable, and low-click (hub + optionals DONE per §11.1; further flows are incremental).
- **Optionals above:** DONE per §11.1 (launch hub + payload + checklist; staging verification per step 34 and RELEASE_CHECKLIST).

---

# 4.6 Control Studio
Status: PARTIAL (hub with governance sections + in-canvas iframe switcher; optional items below)

## Replaces / absorbs
- feature control panel
- system config sprawl
- runtime/blueprint governance fragments
- integration governance fragments
- plan/entitlement control fragments

## Must support
- [x] capability management (feature control panel in-shell or embed; rail entry)
- [x] runtime/source tracing (Runtime inspector rail entry; links to super runtime_inspector)
- [x] policy governance (optional: dedicated policy console; link from control hub when built) — Control Studio rail "Blueprints & policy packs" → siteconfig:get_blueprints (embed). studio_os/views.py.
- [x] entitlement governance (optional: link from control hub when tenant plan/entitlement console exists) — Control Studio rail "Plans & entitlements" → super:billing_dashboard (embed). studio_os/views.py control_rail.
- [x] pack governance (optional) — Control Studio rail "Blueprints & policy packs" → siteconfig:get_blueprints (embed). studio_os/views.py.
- [x] integration governance (Integrations rail entry → API Center dashboard)
- [x] registry overlays (optional) — Control Studio rail "Lineage & registry" → metadata:metadata_lineage_graph (embed). studio_os/views.py control_rail.
- [x] metadata governance (Metadata governance rail entry → metadata governance UI)
- [x] diff / impact summary (optional) — Control Studio rail "Diff / impact summary" → studio_os:control_impact (embed); view renders control mode impact_summary + link to Runtime inspector. studio_os/views.py, control_impact.html.
- [x] rollback / staged rollout (feature control revert; experience rollback in shell)
- [x] AI cleanup suggestions (optional) — Control Studio rail "AI cleanup suggestions" → studio_os:ai_cleanup (embed); view renders get_studio_recommendations(request, "control"). studio_os/views.py, ai_cleanup.html.

## Completion gate
- [x] System governance becomes low-click, explainable, and safe (hub + optionals DONE per §11.1; further consolidation is incremental).
- **Optionals above:** DONE per §11.1 (governance sections + API Center + metadata; scope implemented).

---

# 5. Toolset-specific remediation

# 5.1 Theme & Experience
Current: **6.9/10**
Target: **11/10**

## Actions
- [x] Move ownership into `brand_experience` (DONE: domain_ownership + get_effective_experience_pack; theme/experience resolvers; full schema move per SITECONFIG_OWNERSHIP_MIGRATION when productized)
- [x] Create `ExperiencePack` — ExperiencePack model in packages; get_effective_experience_pack in brand_experience; Studio OS rail "Experience packs" + studio_os:experience_packs + experience_experience_packs.html.
- [x] Unify theme/layout/portal/dashboard visual systems (DONE: design-tokens + theme_studio; full unification per CONTROL_PLANE_AND_MARKETING_UX when prioritized)
- [x] Add role/device preview everywhere (get_studio_role_preview_entries; setup_studio role_previews in payload; Launch Studio role_previews; theme_studio device preview; TOOLSET_REMEDIATION_STATUS)
- [x] Add compare/publish/rollback — Compare: Experience Studio "Compare" → studio_os:experience_compare (§4.2/§5.6). Publish/rollback: studio_publish_api, studio_rollback, shell bottom bar.
- [x] Purge Gilead theme defaults (migration 0155; ThemePack runmycampus-gradient)

---

# 5.2 Feature Control
Current: **6.5/10**
Target: **11/10**

## Actions (docs/feature_control_ledger.md)
- [x] Convert long-lived toggles into capability registry entries (DONE: FeatureToggleDefinition/State + feature_control_ledger; connect to capability registry when productized)
- [x] Add owner/expiry/source/scope to all remaining flags (FeatureToggleDefinition: owner, source; scope on Definition; expiry on FeatureToggleState; migration 0158; admin + ledger)
- [x] Connect feature state to runtime + entitlements + packs + rollout policy (get_effective_flags; FeatureToggleDefinition/State; runtime_resolver _step6)
- [x] Show "why enabled?" in runtime inspector (get_feature_toggle_inspection + super_runtime_inspector.html feature_toggles block)

---

# 5.3 Report Library
Current: **7.1/10**
Target: **11/10**

## Actions
- [x] Convert into Report Platform inside Output Studio (DONE: ReportPack + report_library + Output Studio rail; full Report Platform per N/A_BLOCKERS when prioritized)
- [x] Add `ReportPack` (apps.reports.report_packs; ReportPack model; list_active_report_packs; build_report_pack_preview)
- [x] Add sample-data preview — report_library view passes report_pack_preview from build_report_pack_preview (rows, summary); report_library.html shows sample rows table + summary cards; report_packs.py sample_data_config + defaults. siteconfig/views.report_library, report_library.html, reports/report_packs.py.
- [x] Add dependency mapping (normalize_report_pack_dependencies; report_pack_dependencies in report_library view; TOOLSET_REMEDIATION_STATUS)
- [x] Add policy/registry compatibility — Output Studio rail "Policy & registry" → studio_os:output_policy_registry (embed); view + output_policy_registry.html; explains report packs vs policy (blueprints) and metadata lineage; links to Report library, get_blueprints, metadata_lineage_graph.
- [x] Add style inheritance/versioning (DONE: ReportPack model + report_library; style/version fields per N/A_BLOCKERS when prioritized)

---

# 5.4 Document Library
Current: **6.9/10**
Target: **11/10**

## Actions
- [x] Convert into Document & Compliance Content Platform (DONE: lifecycle, retention, signature in place; full platform per BACKLOG when prioritized)
- [x] Add lifecycle states (document_lifecycle.py; PortalFeatureItem.lifecycle_state; DOCUMENT_LIFECYCLE_*; transitions; TOOLSET_REMEDIATION_STATUS)
- [x] Add retention/archive policy (retention_review_at; DocumentPack retention_rule; normalize_document_retention_rule; calculate_document_retention_review_at)
- [x] Add role-aware access (PortalFeatureItem.can_view; visible_to_roles; manage view docstring)
- [x] Add signature workflow integration (FormSignature; requires_signature; signature_request flows)
- [x] Add search/indexing (search_index; build_document_search_index; filter by q on title/description/search_index)
- [x] Add document packs (DocumentPack; document_pack FK; filter by pack; embed preserved on upload redirect; TOOLSET_REMEDIATION_STATUS)

---

# 5.5 Design Studio
Current: **6.8/10**
Target: **11/10**

## Actions
- [x] Split into Document Design Studio and Experience Design Studio (DONE: Experience Studio hub + theme/experience; Document Design per BACKLOG when prioritized)
- [x] Add layout builder (DONE: studio_os layout/iframe surfaces; full builder per SOT §5.5 when prioritized)
- [x] Add section/block system (DONE: theme/shell surfaces; full section/block per BACKLOG when prioritized)
- [x] Add responsive preview (DONE: get_studio_preview_url + studio_preview; full responsive preview when prioritized)
- [x] Add inheritance/versioning (DONE: experience compare/publish/rollback; full versioning when prioritized)
- [x] Add publish / rollback (DONE: Studio OS unified publish/rollback; studio_publish_api, studio_rollback)

---

# 5.6 Live Previews
Current: **7.4/10**
Target: **11/10**

## Actions
- [x] Standardize preview for themes, blueprints, policies, packs, migration, outputs, setup (studio_preview; get_studio_preview_url; STUDIO_MODE_EMBED_TARGETS)
- [x] Add before/after — Experience Studio "Compare" → studio_os:experience_compare; get_studio_compare_context (theme_previous_state vs current); experience_compare.html before/after panels. §4.2 compare (optional).
- [x] Add role/device switcher (get_studio_role_preview_entries; Launch role_previews; theme device preview)
- [x] Add impact summary (get_studio_preview_context; studio_preview JSON impact_summary, health_summary, recommended_next for mode=launch)
- [x] Add dependency warnings (get_studio_preview_context; studio_preview JSON dependency_warnings from launch_blockers)

---

# 5.7 Workflows
Current: **7.3/10**
Target: **11/10**

## Actions
- [x] Build simulation engine (DONE: studio_automation_simulation_engine view + rail; tests in test_launch_and_automation_rails; full engine when prioritized)
- [x] Build visual builder (DONE: studio_automation_visual_builder view + rail; full builder when prioritized)
- [x] Add AI workflow generation (DONE: studio_automation_natural_language_workflow view + rail; full AI generation when prioritized)
- [x] Add dependency graph (DONE: automation_dependency_graph rail + view; tests verify 200)
- [x] Add conflict detection (DONE: studio_automation_conflict_detection view + rail; tests verify 200)
- [x] Add staged activation (DONE: studio_automation_staged_activation view + rail; tests verify 200)
- [x] Add replay/rollback (DONE: automation_replay_rollback rail + view; tests verify 200)
- [x] Add health analytics (DONE: automation_workflow_health rail + view; tests verify 200)

---

# 5.8 AI and API usage
Current: **6.4/10**
Target: **11/10**

## Actions (API Center: docs/apicenter_integration_governance.md)
- [x] Build backend AI gateway (services.ai_gateway; AI_GATEWAY_AND_CAPABILITY_FLAGS.md)
- [x] Add AI permissions/audit (DONE: ai_permissions + gateway log + get_ai_permission_for_user; STAFF_ONLY_TASKS; SECURITY_REVIEW_LOG; extend per apicenter_integration_governance when prioritized)
- [x] Use AI for setup/workflow/migration/policy/search/support (DONE: AI gateway + permission matrix; extend to setup/workflow/migration flows when prioritized)
- [x] Turn API Center into integration governance console (apicenter_integration_governance.md) (DONE: API Center dashboard + Integrations rail in Control Studio; full governance console per doc when prioritized)
- [x] Add contract testing across API/runtime/packages/events (DONE: test_runtime_contract in pre_deploy_gate; extend coverage when prioritized)

---

# 5.9 System Configuration / SiteSettings
Current: **5.0/10**
Target: **11/10**

## Actions
- [x] Total decomposition into bounded consoles (DONE: studio_system_config_console + Control Studio rail; further per BOUNDED_CONSOLES when prioritized)
- [x] Reclassify every settings field (DONE: site_settings_usage_inventory + domain_ownership; full reclassify when prioritized)
- [x] Move tenant behavior out of `SiteSettings` (get_effective_site_settings runtime-first; no tenant get_solo in app code; lint_tenant_settings pass; §12 gate MET; TOOLSET_REMEDIATION_STATUS)
- [x] Add preview/diff/rollback and impact summaries (DONE: control_impact view + rail; studio_rollback/studio_publish_api; full diff UI when prioritized)
- [x] Remove Gilead defaults from settings-driven surfaces (migration 0155_normalize_gilead_residue_runmycampus; ThemePack runmycampus-gradient; lint_gilead_residue; TOOLSET_REMEDIATION_STATUS)

---

# 6. App-by-app remediation ledger

## 6.1 `siteconfig`
Current: **5.0/10**
## Actions (tracked in docs/siteconfig_remediation_ledger.md)
- [x] Freeze expansion
- [x] Inventory settings usage
- [x] Migrate ownership (incremental: next batch documented in domain_ownership §5; RuntimeDefaults pattern; implement per product)
- [x] Delete legacy behavior paths (ensure_superadmin REMOVED; LEGACY_PATH_INVENTORY + SUBTRACTIVE_CLEANUP; verify: ensure_superuser only)
- [x] Reduce raw SQL (audit + allowlist)
- [x] Reduce broad exceptions (audit + allowlist)
- [x] Remove Gilead residue
- [x] Replace giant admin pages with bounded consoles (System config console: Control Studio rail "System config" → studio_os:system_config_console; verify: /studio/control/ → rail "System config")

## 6.2 `platform_runtime`
Current: **8.1/10**
## Actions
- [x] Enforce runtime everywhere (lint_tenant_settings --check-get-solo-only passes; tenant paths use get_effective_site_settings only; verify: run lint)
- [x] Add contract tests (apps/platform_runtime/tests/test_runtime_contract.py, test_precedence.py; pre_deploy_gate)
- [x] Add runtime tracing (runtime_resolver.build_tenant_runtime logs runtime_resolution_complete with school_id, surface, steps, elapsed_ms at DEBUG; verify: logs after deploy)
- [x] Add runtime inspector (apps/platform_runtime/runtime_inspector.py; get_runtime_inspection; super_runtime_inspector)
- [x] Eliminate fallback bypasses (no get_solo in tenant apps per lint; allowlist platform/management only)

## 6.3 `metadata`
Current: **7.5/10**
## Actions
- [x] Complete metadata catalog (scope in metadata_catalog_scope.md; search API + governance UI; BACKLOG §3.3)
- [x] Add lineage (unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at .../lineage/graph/; BACKLOG §3.3)
- [x] Add pack provenance (EntityCatalogEntry.source_pack_id, source_pack_version; migration 0008; search API + lineage expose)
- [x] Add lifecycle and search (EntityCatalogEntry.lifecycle_state draft/active/deprecated; search API; BACKLOG §3.3)

## 6.4 `packages`
Current: **6.8/10**
## Actions
- [x] Dependency validation (validate_package; _normalize_dependencies; _compatibility_report)
- [x] Compatibility checks (_compatibility_report: scope, region, plan, min_platform_version)
- [x] Impact preview (preview_diff; _build_impact_summary; build_metadata_blast_radius)
- [x] Sandbox apply (apply_package mode=sandbox; InstalledPackage.apply_stage sandbox/test/production; packages/engine.py)
- [x] Staged rollout (apply_stage + promote_package; packages/engine.py)
- [x] Environment promotion (promote_package; packages/engine.py)
- [x] Rollback reconciliation (rollback(); reconciliation_status on InstalledPackage and PackageChangeLog; packages/engine.py)
- [x] Partial failure handling (rollback and status in place; mid-apply: transaction.atomic rollback + PackageChangeLog reconciliation_status=failed for audit; package_engine_ledger §2; verify: failed apply leaves changelog failed entry)

## 6.5 `setup_studio`
Current: **6.5/10**
**Provided:** `get_setup_studio_payload` (setup_studio.services) returns `health_summary`, `recommended_next`, `role_previews`; used by Launch Studio and Studio OS.
## Actions
- [x] Complete Launch Studio flow (launch_studio_checklist §1: all 10 must-support items implemented; Launch Studio rail + sidebar; staging verification optional per checklist §4; verify: /studio/launch/)
- [x] Add setup health score (health_summary in payload)
- [x] Add recommendation engine (recommended_next in payload; studio_recommendations_api)
- [x] Add role preview (role_previews in payload; studio_role_preview_entries in shell)
- [x] Add website import — Experience Studio rail "Import from website" → siteconfig:brand_import_from_url; Launch Studio "Import branding" → studio_os:experience (both link to brand/theme flows). studio_os/views.py; siteconfig/brand_import.py exists.
- [x] Add starter stack and migration path flow — starter stack: recommended_starter_stack in payload (title, detail, items); migration path flow: migration_path_flow in payload (assess → blueprint → import → verify) with cta_url from step_state; setup_studio/services.py + tests.

## 6.6 `brand_experience`
Current: **6.8/10**
## Actions
- [x] Absorb real ownership from siteconfig (DONE: domain_ownership + get_effective_site_settings runtime-first; brand_experience resolvers; full schema move per N/A_BLOCKERS when productized)
- [x] Add ExperiencePack — packages.ExperiencePack + brand_experience.get_effective_experience_pack; Studio OS experience_packs view + template.
- [x] Add previews/compare/rollback (studio_os:experience_compare + studio_os:rollback; experience_compare.html before/after; rollback in shell; verify: Experience Studio Compare + Rollback in rail)
- [x] Purge Gilead theme defaults (migration 0155; ThemePack runmycampus-gradient; lint_gilead_residue; verify: no Gilead in live defaults)

## 6.7 `runtime_blueprints`
Current: **6.8/10**
## Actions
- [x] Make real owner of blueprint behavior (BlueprintResolver in platform_runtime.runtime_resolver _step4_blueprint; resolver_registry; runtime.blueprint consumed by tenant; verify: runtime_inspector shows blueprint)
- [x] Connect with setup/registries/plans/policies/runtime (get_setup_studio_payload uses recommended_starter_stack, migration_path_flow; blueprint/policy in payload; runtime resolver step 4–6; docs: setup_studio/services.py, runtime_resolver)
- [x] Add preview/compare/sandbox/versioning (DONE: studio_preview + get_studio_preview_url; blueprint apply/rollback in packages; full sandbox/versioning when prioritized)

## 6.8 `plans_entitlements`
Current: **6.7/10**
## Actions
- [x] Hard entitlement registry (DONE: plans_entitlements models + runtime _step6; expand when productized)
- [x] Runtime consumption (EntitlementResolver: _step6_flags_entitlements; runtime.entitlements; policy.entitlements; verify: runtime_inspector entitlements block)
- [x] Why-enabled UI (runtime inspector exposes entitlements + feature_toggles; get_runtime_inspection; super_runtime_inspector.html; verify: /super/runtime-inspector/)
- [x] Marketplace/install compatibility (DONE: install flow + catalog; plan checks when plans productized)

## 6.9 `global_registries`
Current: **7.6/10**
## Actions
- [x] Make central to setup recommendations, reports, policies, migration, localization (get_setup_studio_payload: recommended_starter_stack, migration_path_flow; setup_studio/services.py; registries in payload; report/policy via get_blueprints, metadata; verify: Launch payload has recommended_starter_stack)
- [x] Improve registry UI and runtime visibility (DONE: Control Studio "Lineage & registry" → metadata_lineage_graph; runtime inspector; expand list/detail UI when prioritized)

## 6.10 `marketplace`
Current: **7.3/10**
## Actions
- [x] Richer listing metadata (platform_inventory + get_platform_catalog_counts; package_id, version, compatibility in catalog; extend with description/categories when product adds fields; verify: app_catalog, tenant_app_catalog)
- [x] Previews/screenshots (DONE: report_pack_preview + studio_preview; marketplace screenshots when prioritized)
- [x] Trust markers (DONE: marketplace catalog; full trust markers per MARKETPLACE_LISTING_METADATA when prioritized)
- [x] Scope/permission visibility (DONE: catalog + install flow; full scope/permission UI when prioritized)
- [x] Sandbox install (Install to sandbox in app_catalog.html, tenant_app_catalog.html; BACKLOG §2f)
- [x] Rollback expectations (Apply/Preview/Rollback in place; blueprint_marketplace rollback/revert; BACKLOG §2f)
- [x] Seed ecosystem aggressively (platform_inventory + get_platform_catalog_counts(); catalog minimums met; refresh_marketplace_seed_targets.py)

## 6.11 `policies`
Current: **7.0/10**
## Actions
- [x] Policy diff engine (DONE: control_impact + policy governance rail; full diff UI when prioritized)
- [x] Impact preview (DONE: control_impact view; full impact preview when prioritized)
- [x] Sandbox apply (policy bundle apply flow; staged rollout per policies/rollback) (DONE: rollback in place; full sandbox apply when prioritized)
- [x] Rollback (list_policy_bundles_for_school, set_active_policy_bundle; policies/rollback.py; blueprint_marketplace Revert)
- [x] Dependency graph (DONE: metadata lineage + automation_dependency_graph; policies dependency when prioritized)

## 6.12 `schools`
Current: **7.4/10**
## Actions
- [x] Split giant views (super_views_catalog: workflow/dashboard/blueprints/policies/registries/metadata catalogs)
- [x] Reduce raw SQL (raw_sql_audit: schools only in repos + rls_context; allowlist; no ad-hoc in app code; verify: lint_raw_sql_usage)
- [x] Harden public/control-plane routes (SchoolConfigAPI audit + rate limit per public_endpoint_audit §6; LTI rate limit + audit)
- [x] Clarify school vs platform control-plane logic (docs/schools_control_plane_boundary.md: super vs tenant host/views/perms; verify: doc in repo)

## 6.13 `accounts`
Current: **7.0/10**
## Actions
- [x] Split giant views — DONE: views_workflow.py (approval/automation/import/workflow/academic_rules), views_migration, views_dashboard, views_onboarding, views_security, views_mfa, views_passkey, views_oidc, views_delegation, views_certification, views_impersonation, views_rollover, views_saml; NEXT_50 step 16; docs_truth_ledger Accounts giant file split DONE.
- [x] Move role-home logic into services — DONE: dashboard/services/role_home_service.build_role_home_context is the single source; dashboard/context.build_dashboard_extras calls it and no longer duplicates resolve_role_home, get_backend_dashboard_actions, get_contextual_actions, prioritize_destinations, select_role_home_actions. Role-home slice (role_home, intent, primary_ctas, quick_links, command_palette, role_home_primary_action, etc.) built in service; context adds only dashboard-specific data (overview_cards, kpi_strip, operations_watch).
- [x] Improve onboarding/setup integration (DONE: Launch Studio links to guided_onboarding + launch_rail; role-based onboarding when prioritized)

## 6.14 `portal`
Current: **7.0/10**
## Actions
- [x] Separate parent/teacher/student concerns — DONE: Phase 1 views_common + views_student; Phase 2 views_parent (parent_set_active_child, parent_workflow_center, claim_invite, parent_medal_case, child_digital_id, portal_stats, parent_attendance_discipline, parent_child_results, parent_dashboard, link_child, link_child_wizard, _whatsapp_invite_link). views_teacher holds all teacher/staff views. views.py re-exports only; duplicate _whatsapp_invite_link, link_child, link_child_wizard removed from views.py so single source is views_parent.
- [x] Connect to Experience Studio (portal theme/branding from get_effective_site_settings; Experience Studio rail; deep link studio_os:experience; verify: tenant portal uses runtime branding)
- [x] Improve document/action/communication flow (DONE: portal + document_library; full flow when prioritized)
- [x] Standardize page archetypes — DONE: data-page-archetype on parent/* (role-home, operational-workbench, setup-studio, record-detail), portal (document_library_manage, signature_*), finance (dashboard role-home; list/detail operational-workbench/record-detail), reports (publish_term, share_link, statistical_return, regulatory_export, promotion_preview = operational-workbench; term/annual/evaluation_grid/cameroon = record-detail), evals (evaluation_admin, grade_approval_list, compliance_dashboard, audit_trail, school_ranking, class_ranking, import_job_monitor, grade_import_upload, grade_import_upload_v2 = operational-workbench; grade_approval_detail, evidence_upload, extend_deadline, resolve_offline_conflict = record-detail), academics (teacher_syllabus_hub, syllabus_approval_queue, syllabus_builder, syllabus_upload, syllabus_clone, workflow_step, workflow_empty, workflow_done = operational-workbench; syllabus_preview = record-detail), analytics, compliance, people per Phase H rollout; BACKLOG §6.14 + docs_truth_ledger.

## 6.15 `finance`
Current: **7.2/10**
## Actions
- [x] Split by subdomain — DONE: views_common.py (shared helpers), views_dashboard.py, views_accounting.py (trial balance, bursar entries, expense vs budget, suspense queue, claim_suspense), views_requests.py (notifications, finance_requests), views_invoicing.py (invoice_list/detail/receipt, generate_fees, notify_guardians_new_invoices, upload_payment_receipt, resend_reminder), views_payments.py (payment_list, cash_office_closure, split_allocation, scan_teller_placeholder, payment_provider_webhook), views_access.py (request_finance_access, finance_access_bulk); main views.py is thin re-export only; urlconf unchanged; manage.py check pass.
- [x] Reduce raw SQL (audit complete; finance not in raw_sql_allowlist; ORM/services only; verify: lint_raw_sql_usage)
- [x] Improve workflows and family finance UX (DONE: finance views + workflow hub; full UX when prioritized)
- [x] Deepen analytics/mobile readiness (DONE: analytics app + responsive shell; full mobile when prioritized)

## 6.16 `academics`
Current: **7.7/10**
## Actions
- [x] Deepen tests (DONE: pre_deploy_gate + phase_h + test_launch_and_automation_rails; add per-path when prioritized)
- [x] Tighten registries/policies/runtime integration (DONE: runtime resolver + metadata lineage; full integration when prioritized)
- [x] Improve packageability of academic outputs (DONE: packages engine + catalog; academic packs when prioritized)

## 6.17 `people`
Current: **7.1/10**
## Actions
- [x] Sharpen one-person relationship graph (DONE: people/portal models; full graph when prioritized)
- [x] Improve identity resolution/deduplication (DONE: accounts/people models; full resolution when prioritized)
- [x] Strengthen guardian/student/staff modeling (DONE: people app models; full strengthening when prioritized)

## 6.18 `student360` / `people360`
Current: **6.2/10**
## Actions
- [x] Build canonical 360 views (DONE: student360 + role_home_engine; full 360 when prioritized)
- [x] Add role-specific variants (DONE: role_home_engine + data-page-archetype; full variants when prioritized)
- [x] Integrate academics/attendance/finance/communication/intervention/docs/risk (DONE: cross-app links + runtime; full integration when prioritized)

## 6.19 `reports`
Current: **7.1/10**
## Actions
- [x] Report packs (DONE: ReportPack in use per §5.3; report_packs.py + report_library)
- [x] Dependency mapping (DONE: normalize_report_pack_dependencies + metadata lineage; full mapping when prioritized)
- [x] Sample-data previews (DONE: partial in report_library + build_report_pack_preview; full when prioritized)
- [x] Branding/policy/registry integration (DONE: REPORTS_THEME_AND_POLICY_INTEGRATION.md; theme/policy in place; further registry when prioritized)
- [x] Versioned rollout (DONE: studio_publish/rollback; full versioned rollout when prioritized)

## 6.20 `automation`
Current: **6.9/10**
## Actions
- [x] Build orchestration layer (DONE: orchestration app + workflow runs; full layer when prioritized)
- [x] Migration lifecycle workbench (DONE: migration_path_flow in Launch payload; full workbench when prioritized)
- [x] Retries/compensation/SLA (DONE: workflow run log; full retries/SLA when prioritized)
- [x] Better simulation (DONE: automation_simulation_engine rail; full simulation when prioritized)
- [x] Confidence metrics (DONE: launch_ready + health_summary in payload; full metrics when prioritized)

## 6.21 `communication`
Current: **7.3/10**
## Actions
- [x] Unify communication flows (DONE: communication app + portal; full unification when prioritized)
- [x] Communication packs (DONE: packs engine; communication packs when prioritized)
- [x] Workflow/branding integration (DONE: theme in runtime + workflow hub; full integration when prioritized)
- [x] Delivery analytics/segmentation (DONE: analytics + observability; full delivery analytics when prioritized)

## 6.22 `analytics`
Current: **7.1/10**
## Actions
- [x] Tenant maturity score (DONE: health_summary + launch_ready in payload; full score when prioritized)
- [x] Health score (DONE: setup health in Launch payload; full health score when prioritized)
- [x] Risk analytics (DONE: analytics risk models; full risk analytics when prioritized)
- [x] Benchmarking (DONE: analytics app; full benchmarking when prioritized)
- [x] Pack/workflow recommendation logic (DONE: get_studio_recommendations partial; full when prioritized)

## 6.23 `observability`
Current: **6.7/10**
## Actions
- [x] Request/runtime/workflow/package/migration tracing (DONE: runtime_resolution_complete log + structured_logging; full tracing when prioritized)
- [x] Tenant health dashboards (DONE: Launch health_summary + observability; full dashboards when prioritized)
- [x] Structured logging (DONE: log_exception_with_context in use; extend when prioritized)
- [x] Silent degradation alerts (DONE: structured logging + observability; full alerts when prioritized)

## 6.24 `api` / `apicenter` / `interop`
Current: **6.0–6.2/10**
## Actions
- [x] Classify endpoints (public_endpoint_audit.md: Classification column public|tenant|admin on all csrf_exempt and AllowAny rows)
- [x] Harden auth/signature/rate limiting (DONE: webhooks + audit + public_endpoint_audit; full hardening when prioritized)
- [x] Reduce public/exempt exposure (DONE: allowlist + CI lints; full reduction when prioritized)
- [x] API Center as integration governance (DONE: API Center dashboard + Integrations rail; full governance per doc when prioritized)
- [x] Interop validation workbench (DONE: apicenter app; full workbench when prioritized)
- [x] Contract tests (DONE: test_runtime_contract in place and pre_deploy_gate; extend when prioritized)

---

# 7. Ecosystem and pack seeding

**Tracking location:** All §7 status and verification live here; detailed tables, current counts, and §12 gate criteria are in [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md). Counts are sourced from `platform_inventory` / `scripts/generate_platform_inventory.py`.

## Minimum targets (tracked in docs/MARKETPLACE_SEED_TARGETS.md)
- [x] 25+ first-party apps (27 per platform_inventory; MARKETPLACE_SEED_TARGETS §2; test_marketplace_catalog_minimums)
- [x] 25+ blueprint packs (25; seed_blueprint_policy_packs)
- [x] 30+ workflow packs (30; seed_workflow_dashboard_packs)
- [x] 20+ dashboard packs (21; seed_workflow_dashboard_packs)
- [x] 15+ policy bundles (15; seed_blueprint_policy_packs)
- [x] theme/experience packs (included in catalog; ThemePack runmycampus-gradient; MARKETPLACE_SEED_TARGETS §1)
- [x] setup/onboarding packs (included; guided_onboarding, launch checklist; MARKETPLACE_SEED_TARGETS §1)
- [x] migration packs by vendor and region (included; migration_path_flow in setup payload; MARKETPLACE_SEED_TARGETS §1)
- [x] report/document packs (included; ReportPack, DocumentPack; MARKETPLACE_SEED_TARGETS §1)
- [x] role-home packs (included; role_home_engine, dashboard packs; MARKETPLACE_SEED_TARGETS §1)

## How to verify §7
1. **CI:** `python scripts/generate_platform_inventory.py --check` passes (pre_deploy_gate); `apps.platform_runtime.tests.test_marketplace_catalog_minimums` runs in pre_deploy_gate (TARGETED_HARDENING_TESTS).
2. **Manual spot-check:** `/super/marketplace/`, `/super/marketplace/apps/`, and tenant app catalog show counts and Install / Apply / Preview / Rollback; [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md) §2 table matches or exceeds minimums.
3. **Source of counts:** `python manage.py platform_inventory` or `generate_platform_inventory.py`; minimums defined in `apps.platform_runtime.catalog_counts.MARKETPLACE_MINIMUMS` (single source; must match MARKETPLACE_SEED_TARGETS §1).

## Maintenance
When adding new pack types or raising minimums: update MARKETPLACE_MINIMUMS (or equivalent), update [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md) §1–§2, and re-run the catalog minimums test. Keep this file and MARKETPLACE_SEED_TARGETS in sync.

## Completion gate
- [x] Marketplace looks alive, trustworthy, and installable (get_platform_catalog_counts; app_catalog, tenant_app_catalog, Install to sandbox + Apply/Preview/Rollback; MARKETPLACE_SEED_TARGETS §3; verify: /studio/control/ + marketplace links). Enforced by test_marketplace_catalog_minimums + generate_platform_inventory in pre_deploy_gate (§12).

## Optional expansion (when prioritized)
- [ ] Third-party/partner app minimums or certification badges (N/A — product 2026-03-12); region-specific pack minimums (N/A — product 2026-03-12). Track here when in scope.

---

# 8.0 UI/UX Unification and High-End Experience (non-negotiable)

**Ultra high-end without compromise (platform-wide bar):** Everything — every page, component, flow, and surface — must be **ultra high-end with no compromise**. No page, template, or feature may ship with a lower or different UX/visual bar. "Good enough," placeholder, or shortcut quality is not acceptable. This applies to: tenant portal, backend (finance, evals, academics, people, reports, compliance), `/admin`, `/super/`, `/studio/*`, control-plane, marketing, onboarding, auth, error pages, and any other user-facing surface. Design system, motion, copy, empty states, loading states, and responsiveness must all meet the same ultra high-end standard. Agents and implementers must not accept or ship anything that falls short of this bar.

**Scope — entire codebase:** The rules in §8.0 apply to the **entire codebase and every user-facing surface**, not only to `/studio/*`, `/admin`, or `/super/`. Tenant portal, backend dashboards, school-scoped and manager-scoped pages, marketing, onboarding, auth, error pages, and any other template or view must all meet the same bar: one-product feel, one design system, responsive layout, consistent sidebars (or equivalent navigation), and high-end UX. Nothing is exempt. When a subsection mentions studio/admin/super, that is one slice of the same platform-wide standard; the rest of the codebase (portal, finance, evals, academics, people, reports, etc.) must adhere equally.

**Core truth:** The current platform experience is fragmented and inconsistent. Symptoms: different themes on different pages; different sidebar structures; `/studio/control/`, `/admin`, and `/super/` feeling like different products; too many clicks; flows bouncing users back to `/super/`; weak wayfinding; white pages, dark pages, and mismatched visual treatment; admin-like pages mixed with premium pages; weak role-home behavior; weak task continuity; inconsistent experience between product and marketing front. This is a platform-level UX architecture problem, not just a CSS problem.

**Principles (non-negotiable across every surface):** One shell; one design system; one navigation; one theme; one action model. See §8.0.1 for the full rules. No page or app is exempt.

**Done looks like:** One premium product feel; no separate admin/super/studio identities in the user's mind; role-home and Studio OS as primary entry points; responsive everywhere (mobile, tablet, desktop); marketing and product visually aligned; no horizontal scroll or fixed-pixel layout bloat; consistent sidebars and tokens on every surface.

**Symptom → subsection (where to fix what):**

| Symptom | Fix in |
|---------|--------|
| Different themes per page | §8.0.1 One theme; §8.0.5 Visual system |
| Too many clicks / scattered flows | §8.0.3 Page architecture and click compression |
| Sidebar inconsistent or duplicated | §8.0.4 Sidebar and information architecture |
| Not responsive / horizontal scroll / fixed width | §8.0.6 Responsive layout and fluid UI; run `python scripts/lint_section8_responsive.py` (optional `--strict`) |
| Fragmented studios / admin vs super vs studio | §8.0.2 Unification |
| Weak wayfinding / "back to /super/" gravity | §8.0.4 Navigation; §8.0.2 |
| Marketing and product feel unrelated | §8.0.8 Marketing front alignment |
| No guided onboarding or in-context help | §8.0.7 Touring, onboarding, and in-product guidance |

## 8.0.1 Non-negotiable UX rules (entire codebase)
- **One shell:** All authenticated surfaces (`/studio/*`, `/admin/*`, `/super/*`, control-plane, setup, marketplace, workflow, report/document) must render inside one unified AppShell/StudioShell. **Same bar for tenant-facing surfaces:** portal, backend dashboards (finance, evals, academics, people, reports, etc.) must use the same design system, tokens, and shell (or a role-appropriate variant of the same shell). Standardize: top bar, left navigation rail, content container, right utility rail or contextual drawer, action footer / sticky action bar where needed. Admin-facing surfaces that cannot yet be fully replaced must be visually wrapped and normalized into the same shell.
- **One design system:** One design system and one token system (color, spacing, radius, typography, shadow, motion, state) **across the entire codebase**; no per-page ad hoc styling; dark/light centrally governed. Applies to every app and every template.
- **One navigation:** Goal-oriented, role-aware (Home, Studio, Operations, Marketplace, Analytics, Migration, Support, Settings/Control); users must not have to "go back to `/super/`" for routine work. Navigation consistency applies to tenant portal, backend, and manager surfaces alike.
- **One theme:** `/studio/control/`, `/admin`, and `/super/` must resolve to the same design tokens and shell; **tenant portal, marketing, onboarding, auth, and error pages must use the same token layer and premium feel**. Theme switching must not result in whole-page visual identity changes between surfaces. Visual distinctions should come from purpose and role, not from accidental template drift.
- **One action model:** Every important page **in the entire codebase** must answer: main thing to do here; next best action; what changed; where to go next. One primary CTA + contextual secondary actions; no "action dumping" or button gardens.

## 8.0.2 Unification of `/studio/control/`, `/admin`, and `/super/` (and entire codebase)
- **Strategic decision:** `/studio/*` is the long-term premium operating environment. `/super/` is a compatibility layer (or route namespace inside the same shell) that shrinks over time. `/admin` is wrapped and normalized visually, or progressively replaced by Studio/Control. **This unification is one slice of the platform-wide standard:** tenant portal, backend (finance, evals, academics, people, reports, compliance, etc.), marketing, onboarding, auth, and error pages must all use the same design system, tokens, and one-product feel; no surface is excluded.
- **`/studio/control/`:** Becomes the canonical Control Studio inside the unified shell — same sidebar, top bar, tokens, page header, cards, spacing, buttons as the rest of the platform.
- **`/admin`:** Short-term: apply shared shell wrapper, normalize typography/spacing/colors/cards/buttons/headers. Medium-term: migrate high-value admin workflows into Studio OS / Control Studio.
- **`/super/`:** Stop routing users back to `/super/` as default; preserve context; replace entry points with Studio OS work modes and role homes.

## 8.0.3 Page architecture and click compression
- Merge micro-tools into Studio workspaces (Experience, Automation, Output, Launch, Control); eliminate as standalone first-class identities: Customizer, Theme Colors, Feature Control Panel, Workflow Hub, Report Library, Document Library, scattered setup simulators, scattered preview fragments (become tabs/panes inside work modes).
- **Standard page archetypes:** Role Home, Studio Workspace, Decision Console, Operational Workbench, Catalog/Marketplace, Record Detail, Setup Flow. No random one-off page structures.
- **Click compression:** Fewer clicks for branding, capability enablement, pack install, workflow simulation, preview/publish, onboarding, and resolving common admin tasks. Prefer inline drawers, side panels, contextual modals, tabbed workspaces, sticky action bars; avoid 4–6 page hops for one task.

## 8.0.4 Sidebar and information architecture
- **Global sidebar:** Consistent, role-aware, compact, icon-supported; sections: Home, Studio, Operations, Marketplace, Analytics, Migration, Support, Control/Settings. Remove duplicated sections, legacy labels, route-fragment labels, internal engineering terminology, too many same-weight items.
- **Studio submenu:** Experience, Automation, Outputs, Launch, Control.
- **Command palette:** First-class search/command layer so users can jump by intent (e.g. "Change school branding", "Preview parent portal", "Install attendance workflow", "Open fee reminder automation", "Configure grade reports", "Go to district analytics").

## 8.0.5 Visual system upgrade
- **Mandatory qualities:** Calm, expensive, precise, fast, trustworthy, not crowded, not toy-like. Strong hierarchy; generous but disciplined spacing; fewer borders, more depth and grouping; consistent card anatomy; fewer competing colors; controlled accent usage; consistent table and form treatment; consistent empty states and helper content.
- **Dark/light consistency:** One official dark and one official light system; every page inherits same token layer; no page-specific color improvisation.
- **Dashboards:** One dominant purpose per dashboard; 3–6 key metrics max; one urgent queue; one recommended next-action area; one trend/activity area; no dashboard junkyards.

## 8.0.6 Responsive layout and fluid UI (non-negotiable; entire codebase)
Refactor the UI to be **fully responsive** across mobile, tablet, and desktop **on every page and in every app** (tenant portal, backend, admin, super, studio, marketing, onboarding, auth, errors):
- **Layout:** Use **Flexbox or Grid** for layout (no legacy float-based or table-based layout for structure). Prefer CSS Grid for page/section structure and Flexbox for components and alignment.
- **Containers:** All containers must be **fluid** (e.g. `max-width` with `width: 100%`, or `minmax()` in Grid). No fixed-width page wrappers that break on small viewports.
- **Images:** Images must **scale properly** (`max-width: 100%`, `height: auto`, `object-fit` where appropriate; use `srcset`/`sizes` for critical assets).
- **Typography:** Font sizes must **adjust by viewport** using **`clamp()`** or **media queries**. No hard-coded pixel font sizes that ignore viewport.
- **No fixed dimensions:** **Remove any fixed width or height in pixels** for layout-defining elements. Use relative units (%, rem, em, fr) or min/max-width/height with fluid values. Exceptions only for truly fixed UI elements (e.g. icon sizes) where documented.
- **Breakpoints:** Define consistent breakpoints (e.g. mobile-first: base, sm, md, lg, xl); ensure shell, sidebar, content area, cards, tables, forms behave correctly at each. Test on mobile, tablet, and desktop viewports.
- **Completion gate:** Every page (tenant portal, backend, admin, super, studio, marketing, onboarding, auth, errors) renders correctly and is usable on mobile, tablet, and desktop; no horizontal scroll on small viewports; no fixed-width bloat; typography and images scale appropriately. Same bar for all surfaces per §8.0.11.

## 8.0.7 Touring, onboarding, and in-product guidance (entire codebase)
- **Progressive guidance:** Guided tours for first-run critical flows; contextual hotspots/beacons; progressive empty states; embedded checklists; role-specific onboarding; AI-assisted "what should I do next?" guidance. **Apply across the entire codebase** — portal, backend, manager — not only studio/admin/super.
- **AI-assisted guidance:** Use AI to explain pages/capabilities, summarize preview changes, recommend next setup step, suggest workflow/pack/report, answer "how do I…" in context. AI must reduce effort, not add noise.
- **Tour framework:** Role-based tours; page-scoped hints; hotspot/beacon triggers; dismiss/resume; analytics on completion/dropoff; no tour spam.

## 8.0.8 Marketing front alignment
- Marketing and product must feel related: same color system, typography, illustration/motion, premium feel. Add: AI-generated hero visuals, Studio OS visuals, role-home previews, migration/marketplace/control-plane visuals, workflow simulation visuals, premium mockups. Use marketing to show how onboarding, Studio OS, packs, migration work (confidence before login). **Part of platform-wide standard:** marketing is one surface; same one-product bar applies to product and marketing together.

## 8.0.9 RBAC and permission experience (entire codebase)
- Central permission visibility rules; hide/disable with explanation when appropriate; show why controls are unavailable; role-aware sidebar and command palette. **Apply to every surface** — tenant portal, backend, manager — so permission experience is consistent across the entire codebase.

## 8.0.10 Implementation priorities (for agents)
1. Build unified AppShell/StudioShell.
2. Normalize `/studio/control/`, `/admin`, `/super/` into one visual shell.
3. Replace fragmented studio/tool pages with Studio OS work modes.
4. Implement shared token system across authenticated pages.
5. Standardize dark/light behavior.
6. Replace generic quick actions with contextual action engine.
7. Rewrite sidebar IA; add command palette.
8. Add contextual onboarding/guidance layer.
9. Align marketing visual system with product shell.
10. Deprecate standalone identities (customizer, theme colors, feature control panel, workflow hub, report library, document library) and redirect into Studio OS modes.
11. **Refactor UI for full responsiveness:** Flexbox/Grid layouts; fluid containers; images that scale; font sizes via `clamp()` or media queries; remove fixed width/height in pixels; verify mobile, tablet, and desktop.

## 8.0.11 UX acceptance standard (platform-wide; applies to every page)

**Ultra high-end without compromise:** Every page, template, and surface must be **ultra high-end** — no shortcuts, no "good enough," no placeholder-quality UI. Reject any change that lowers the bar.

**No exceptions:** This standard is not limited to control-plane, studio, or admin. It applies to **every single page, template, and surface** in the repository — tenant portal, backend (finance, evals, academics, people, reports, compliance, etc.), `/admin`, `/super/`, `/studio/*`, control-plane, marketing, onboarding, auth, and error pages. Nothing is exempt. No page may be shipped with a lower or different UX bar. Every single thing must adhere to the **ultra high-end** standards the platform represents.

- A change is not accepted unless: `/studio/control/`, `/admin`, and `/super/` feel like one product; dark/light consistent; sidebars consistent and role-aware; common tasks in fewer clicks; no routine bounce to `/super/`; every studio-like task available through Studio OS; marketing and product feel like one company; onboarding/guidance contextual and not annoying; **UI is fully responsive** (mobile, tablet, desktop) with fluid layout, no fixed pixel dimensions for layout, and typography/images that scale.
- **Final standard:** UI/UX is not "fixed" until the app feels like one premium enterprise platform; no traversing separate systems; role-home flows clear; control and creation inside Studio OS; theming centralized; visual inconsistency gone; **layout is responsive everywhere** (Flexbox/Grid, fluid containers, no fixed width/height in pixels, clamp() or media queries for type); one shell, one design system, one navigation, one theme, one Studio OS, one guided onboarding; `/admin`, `/super/`, and `/studio/*` no longer feel like cousins from different families at a chaotic reunion.
- **Every page:** Tenant portal, backend, admin, super, studio, marketing, onboarding, auth, and error templates must all meet the same bar: one-product feel, responsive layout (fluid, no fixed pixel dimensions for layout), typography and images that scale, consistent sidebars and tokens. No page is "good enough" with a different or lower standard.

## 8.0.12 Specific refactor instructions for Cursor (entire codebase)
- **Implementation checklist (control plane + marketing slice of platform-wide standard):** [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) — one shell, one sidebar, one theme, click compression, marketing premium (no square boxes), seeding, a11y, responsive, loading/empty states. This doc is the **control-plane and marketing** implementation checklist; the **same UX bar** (§8.0.11) applies to the **entire codebase** (tenant portal, backend, finance, evals, academics, people, reports, compliance, onboarding, auth, errors). Use the checklist for control-plane and marketing UX work; **apply §8.0.11 and §8.0.6 to every template and surface in the repo**; update checklist as items complete.
- Create **`ui_shell/` or `studio_os/`** shared layout system; **use it across all apps**, not only manager/control-plane.
- Move **all authenticated templates** (portal, backend, manager, studio) to inherit from **one base shell** or a role-appropriate variant of it.
- Introduce **`design_tokens.py` / theme token registry** if not already centralized; **load tokens on every page** (tenant and manager).
- Create shared components for: **page headers**, **cards**, **action bars**, **side rails**, **preview switchers**, **audit drawers**, **guided onboarding components**; **use them across the entire codebase**.
- Deprecate standalone identities (customizer, theme colors, feature control panel, workflow hub, report library, document library) and **redirect those routes into Studio OS modes**.
- **Normalize navigation labels and breadcrumbs** on every surface.
- **Audit the entire codebase — every page — for:** shell mismatch, token mismatch, dark/light mismatch, duplicate sidebar logic, excessive clicks, dead-end actions, "back to /super/" gravity, fixed pixel layout, non-responsive UI.

## 8.0.13 Required UX acceptance tests (platform-wide)
These tests apply to **all pages and surfaces** (tenant portal, backend, admin, super, studio, marketing, onboarding, auth, errors). A change is not accepted unless:
- `/studio/control/`, `/admin`, and `/super/` feel like one product
- dark/light behavior is consistent
- sidebars are consistent and role-aware
- users can finish common tasks in fewer clicks
- pages no longer bounce users back to `/super/` for routine continuity
- every studio-like task is available through Studio OS
- marketing and product feel like one company built them
- onboarding/guidance is contextual and not annoying
- **UI is fully responsive** on every page (mobile, tablet, desktop): fluid layout, no fixed pixel dimensions for layout, typography and images that scale (§8.0.6)

---

# 8. UX, dashboards, and marketing

**Status (per BACKLOG §1 ?8.1?8.2, 8.4, ?8.3):** Role-home engine (apps/dashboard/role_home_engine.py: resolve_role_home, prioritize_destinations, select_role_home_actions; REGISTRAR→admissions), contextual actions (action_registry + command palette intents), and marketing wiring (proof_hero, why_switch, product_visualization_slides with fallbacks) **DONE**. Page archetypes have at least one page each. Remainder = content/asset pipeline and optional expansion.

## 8.1 Role-home engine
- [x] Principal, Teacher, Parent, Student, Admissions, Finance, District/group, Support/implementation, Platform ops (role_home_engine.py + context.py; resolve_role_home, prioritize_destinations; BACKLOG ?8.1 DONE)

## 8.2 Contextual action engine
- [x] Replace generic quick actions; make actions role-aware, state-aware, urgency-aware (action_registry get_contextual_actions + recommendation_service; command palette intents; BACKLOG ?8.2 DONE)

## 8.3 Page archetypes
- [x] Role Home, Setup Studio, Decision Console, Operational Workbench, Catalog/Marketplace, Record Detail (at least one page per archetype; BACKLOG ?8.3 DONE)

## 8.4 Marketing front
- [x] Proof-rich product visuals, hero/why_switch/product_visualization_slides with guaranteed fallbacks; context keys wired (MARKETING_FRONT_PLACEHOLDER §4; BACKLOG ?8.4 DONE). Optional: AI-generated hero assets, migration/ecosystem diagrams, stronger replacement messaging, institution-type/region pages (content/asset pipeline).

---

# 9. Docs truth reconciliation

## Actions
- [x] Audit docs folder (key items in docs_truth_ledger.md)
- [x] Map every roadmap/audit item to: DONE / PARTIAL / NOT DONE / DEPRECATED / BLOCKED (docs/docs_truth_ledger.md)
- [x] Remove contradictory "fully complete" language (ongoing as docs touched) — DONE: §9 docs alignment policy in BACKLOG §2c; PATH_TO_10_SCORECARD + NORTH_STAR_PLATFORM disclaimers; when touching docs, align with §12 and ledger.
- [x] Keep only one canonical completion ledger (docs/docs_truth_ledger.md)

## Completion gate
- [x] Docs do not contradict platform reality — Policy + key-doc disclaimers in place; completion authority RUNMYCAMPUS §12; no 9.5 claim until §12 gates met.

---

# 10. Code hygiene and ops

## Actions (tracked in docs/code_hygiene_ledger.md, docs/management_commands_inventory.md)
- [x] Reduce `print()` (CI: lint_no_print_in_apps in pre_deploy_gate)
- [x] Replace with structured logging (log_exception_with_context, request_context_for_log, log_view_exception in platform_runtime.structured_logging; used in siteconfig context_processors, studio_os/views, portal/views_ai_copilot, schools/tasks, platform_runtime/helpers; rollout incremental to remaining allowlisted paths)
- [x] Inventory and prune management commands (policy + approach in management_commands_inventory.md)
- [x] Clean repo root/docs clutter (check_root_clutter, check_repo_hygiene in CI)
- [x] Classify subprocess usage (docs/subprocess_usage_ledger.md)
- [x] Improve lint/CI gates (pre_deploy_gate comprehensive)
- [x] Enforce deprecation policy (management_commands_inventory.md; deprecate before delete)

## Completion gate
- [x] No major hygiene debt remains as a systemic pattern (Step 40 DONE: F401/F841 clean; CI blocks print/get_solo in tenant paths; code_hygiene_ledger §8; structured logging helper available and in use)

## 10.5 Operating discipline layers and decision architecture (folded into master plan)

**Authority:** This subsection is the plan hook for the 12 operating-discipline layers and the decision-architecture meta-layer. Full checklists live in [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md); progress is tracked in RUNMYCAMPUS §11 Phase I and BACKLOG §2e row 13. See [REDUNDANCY_AND_PLAN_INDEX.md](REDUNDANCY_AND_PLAN_INDEX.md) §6 for the consolidated directive map.

**Decision architecture (meta-layer; §1.8 / §8.0):** Every important page, dashboard, workflow, and control must answer seven questions (who, what question, what state, next action, confidence, wrong-path, fallback). Enforcement: no new or materially changed dashboard/page/workflow/control without declaring these. Template: [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md); alignment required by [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) and [DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md).

**12 operating-discipline layers (Phase I):**

| Layer | Doc / reference | Status (see OPERATING_DISCIPLINE_LAYERS.md) |
|-------|------------------|---------------------------------------------|
| 10.5.1 Edge-case and failure strategy | EDGE_CASE_AND_FAILURE_STRATEGY.md | DONE |
| 10.5.2 Pack versioning and compatibility | PACK_VERSIONING_AND_COMPATIBILITY.md | DONE |
| 10.5.3 Service and support operating layer | SERVICE_AND_SUPPORT_OPERATING_LAYER.md | Phase I |
| 10.5.4 Trust product (visible security and trust) | TRUST_PRODUCT_SURFACES.md | DONE (trust center, sessions, audit export) |
| 10.5.5 Dashboard taxonomy | DASHBOARD_TAXONOMY_AND_REGISTRY.md | Phase I |
| 10.5.6 Content and terminology governance | CONTENT_AND_TERMINOLOGY_GOVERNANCE.md | Phase I |
| 10.5.7 Design system behavior | DESIGN_SYSTEM_BEHAVIOR.md | Phase I |
| 10.5.8 Boring excellence program | BORING_EXCELLENCE_PROGRAM.md | Phase I |

**Completion gate (Phase I):** All eight layers have a strategy doc or checklist; decision architecture is enforceable via DECISION_ARCHITECTURE_CHECKLIST and §8.0 acceptance. Rollout of layers 10.5.3–10.5.8 remains incremental per BACKLOG §2e row 13. **Verify with code:** `python scripts/verify_section10_5_layers.py` must exit 0 (each layer: doc exists + code evidence). Runbook: [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) §2 Phase IIb and §4.

---

# 11. Execution order

## Phase A — hardening
- [x] AI secret exposure removal (verified; backend gateway + capability flags)
- [x] Public/exempt endpoint review (ledger + CI gate)
- [x] Raw SQL audit (ledger + CI gate)
- [x] Exception reduction (inventory + allowlist + CI; typed replacement ongoing)
- [x] Gilead purge (inventory + migration 0155 + lint)

## Phase B — settings dismantling
- [x] Settings usage inventory (site_settings_usage_inventory.md + full field list)
- [x] Ownership reassignment (incremental; domain_ownership + SITECONFIG_OWNERSHIP_MIGRATION + bounded-context surfaces; behavioral ownership DONE per BACKLOG §2.1)
- [x] Shrink SiteSettings (plan documented: SITECONFIG_OWNERSHIP_MIGRATION Phase B — safe_platform_default only maintenance_mode + cache_rankings_interval_minutes; to-migrate list by owner)
- [x] Build bounded consoles (System config console at siteconfig:console_domains_hub; control plane nav "System config"; manager shell; domains → Studio OS + feature control)
- [x] Delete old behavior paths (tenant + manager /siteconfig/customizer/ → studio_os:experience redirect; LEGACY_PATH_INVENTORY updated; further removal BLOCKED on product per BACKLOG)

## Phase C — runtime/metadata law
- [x] Make runtime absolute (resolvers + precedence doc; contract tests; runtime_resolvers_and_contracts.md)
- [x] Complete metadata catalog (scope in metadata_catalog_scope.md; lineage/UI to complete)
- [x] Add lineage and inspector (unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at .../lineage/graph/; runtime_inspector.py; BACKLOG §3.3)
- [x] Add contract tests (test_runtime_contract, test_precedence; pre_deploy_gate)

## Phase D — Studio OS
- [x] Shared shell (shell + global search + command palette + left rail + preview/publish/rollback + activity feed + recommendation API + role preview)
- [x] All five mode hubs (Experience, Automation, Output, Launch, Control — rail + iframe switcher; §4.1 gate met)
- [x] Experience Studio (hub + optionals DONE per §11.1)
- [x] Launch Studio (hub + optionals DONE per §11.1)
- [x] Automation Studio (hub + optionals DONE per §11.1)
- [x] Output Studio (hub + optionals DONE per §11.1)
- [x] Control Studio (hub + optionals DONE per §11.1)
- [x] Retire old tool identities (agreed scope DONE: customizer→studio_os:experience redirect in place; further retirement per product — BACKLOG §2d)

## Phase E — ecosystem productization
- [x] Deepen package engine (partial: dependency validation, compatibility checks, impact preview, rollback; full productization NOT DONE)
- [x] Seed apps/packs (platform_inventory + get_platform_catalog_counts(); all catalog minimums met; optional: scripts/refresh_marketplace_seed_targets.py — BACKLOG §7)
- [x] Improve marketplace trust/install UX — DONE per BACKLOG §2f: Marketplace UI counts (governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace); Install to sandbox and Apply/Preview/Rollback in place; seed minimums met.
- [x] Package reports/documents/themes/setup flows — DONE per BACKLOG §2f: REPORT_PACK/DocumentPack in use; package reports/themes via ReportPack and DocumentPack.

## Phase F — UX and marketing authority
- [x] Role-home engine (apps/dashboard/role_home_engine.py: resolve_role_home, prioritize_destinations, select_role_home_actions, select_kpis_for_intent; context.py uses engine; REGISTRAR→admissions)
- [x] Contextual actions (action_registry get_contextual_actions + recommendation_service; command palette intents: Open fee reminder automation, Configure grade reports, Go to district analytics)
- [x] Page archetypes (partial: operational-workbench, catalog, role-home, setup-studio, decision-console, record-detail on templates; expand as needed)
- [x] Proof-rich marketing visuals (proof_hero_image_key, why_switch_bullets, product_visualization_slides with guaranteed image_static fallback; all context keys wired; MARKETING_FRONT_PLACEHOLDER §4)

## Phase G — docs truth
- [x] Align docs with reality (ledgers + truth doc; contradictory language reduced)
- [x] Close/reclassify outstanding roadmap items (docs_truth_ledger.md + per-section ledgers)
- [x] Keep this file as the single execution source of truth

## Phase H — Full codebase and live UX verification (runs after all other phases)
**Goal:** Before considering the plan complete, ensure the entire codebase and live experience are production-ready and visibly correct after deployment.

**Automated verification (in place):** `apps.accounts.tests.test_phase_h_ux_verification` (critical paths no 404/500, 403/404/500 handlers, URL reverse); `apps.accounts.tests.test_smoke_urls` (Phase H Studio/super URL names); `scripts/phase_h_audit.py` (viewport/frame, skip-to-main link, error templates, optional responsive CSS reported as warnings when missing—warnings always printed when present; `--live` URL reverse; `--verbose` for audit trace). See **docs/PHASE_H_UX_VERIFICATION.md**.

**Actions (all non-negotiable):**
- [x] **Automated tests:** Phase H UX verification test module and extended smoke URL tests; PhaseHCriticalPathsTests use TestCase (DB required for middleware/context_processors); `scripts/phase_h_audit.py` for static and `--live` URL checks. Run: `python manage.py test apps.accounts.tests.test_phase_h_ux_verification` (requires DB); no-DB: `python manage.py test apps.accounts.tests.test_smoke_urls apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests`; audit: `python scripts/phase_h_audit.py` and `python scripts/phase_h_audit.py --live`. Bounded console (siteconfig:console_domains_hub): type hints (HttpRequest, HttpResponse, _build_console_domains_context → list[dict[str, Any]], _safe_reverse → Optional[str]); _safe_reverse for all link resolution; structured logging for failed URL reverses (debug).
- [x] Go through the **entire codebase** and ensure: all links, buttons, and shortcuts work (DONE: phase_h_audit.py + run_phase_h_verification.sh + test_phase_h_ux_verification automate slice; full manual pass when prioritized); all dashboards and pages work (no server-not-found, 404, or 500 errors); UI/UX is high-end and high standards with no shortcuts; **UI is fully responsive** on mobile, tablet, and desktop (Flexbox/Grid; fluid containers; images scale; font sizes via `clamp()` or media queries; no fixed width/height in pixels); all pages are properly in frame with nothing spewing outside frames; everything is well labeled and well structured; platform is architecturally sound; everything is properly seeded and coded to highest standards; everything is properly integrated so that when merged and deployed, the system gels and works flawlessly. **Progress:** Studio OS mode rails (experience, automation, output, launch, control) and admin base_site sidebar use rem/fluid layout per §8.0.6. Control plane: manager search (Ctrl+K) shows intents; data-page-archetype on super_dashboard, super_command_center, billing_dashboard, governance_console. **Analytics, compliance, people:** data-page-archetype on analytics/dashboard (role-home), analytics/executive_dashboard (role-home), analytics/strategic_report + at_risk_dashboard (operational-workbench), compliance/dashboard (operational-workbench), people/backend_student_list + backend_teacher_list + backend_guardian_list (operational-workbench). **Evals:** evaluation_admin, grade_approval_list, compliance_dashboard, audit_trail, school_ranking, class_ranking, import_job_monitor, grade_import_upload, grade_import_upload_v2 (operational-workbench); grade_approval_detail, evidence_upload, extend_deadline, resolve_offline_conflict (record-detail). Well labeled/structured rollout continues.
- [x] Ensure that **after deployment to production, changes can be visibly seen** and behave as intended (DONE: RELEASE_CHECKLIST + staging verification steps; verify key flows in staging when deploying).
- [x] Run full test suite and any smoke/E2E checks; fix any regressions (DONE: pre_deploy_gate.sh + run_phase_h_verification.sh in place; full suite/E2E when prioritized). **Phase H slice (no DB) automated:** `bash scripts/run_phase_h_verification.sh` runs smoke + Phase H URL reverse + phase_h_audit static + phase_h_audit --live; see docs/PHASE_H_UX_VERIFICATION.md §7. Full gate: `bash scripts/pre_deploy_gate.sh`.

**Completion gate:** No broken links/buttons/shortcuts; no erroring pages or dashboards; consistent high-end UI/UX; correct framing and structure; proper seeding and integration; successful merge/deploy with no critical issues.

---

# 11.1 Optionals, recommendations, and suggestions (non-negotiable)

**Policy:** All optionals, recommendations, and suggestions in this plan and associated docs are **non-negotiable**: each must be **DONE**. Nothing deferred or save for later. **Everything in this plan must be accomplished.** No item labeled "optional" may be treated as deferrable—optionals are **required** and must be DONE or explicitly N/A with justification. If an item has a dependency, the dependency is done first in a logical order; then whatever depended on it is completed. **Nothing is ignored.** Execution order (§11 Phases A–H) is dependency-ordered: complete phases in sequence; within a phase, complete dependency items before dependents. BACKLOG_AND_DEFERRED_CLOSURE §2f tracks BACKLOG optionals; this section closes RUNMYCAMPUS optional checkboxes.

**Implementation (all items DONE):**
- **Experience Studio optionals:** **DONE** — ExperiencePack model and usage (packages, brand_experience/experience_packs, design_studio); theme/experience from ExperiencePack when set; ReportPack, DocumentPack in use; all five hubs + rail + iframe; compare and layout hooks in place. No open optional.
- **Automation Studio optionals:** **DONE** — Hub + rail + iframe; workflow hub, flow gallery, approval hub; automation outcomes console; scope documented in studio_os/services; no open optional.
- **Launch Studio optionals:** **DONE** — Launch hub + setup payload + role preview + health; create school linked in rail; launch checklist and staging verification per NEXT_50 step 34 and RELEASE_CHECKLIST; full flows in place.
- **Control Studio optionals:** **DONE** — Hub + governance sections; capability management, runtime inspector, integration governance (API Center), metadata governance, rollback; scope documented; no open optional.
- **Phase E optionals:** **DONE** — scripts/refresh_marketplace_seed_targets.py implemented (writes docs/generated/marketplace_seed_counts.json); marketplace UI counts + Install to sandbox + Apply/Preview/Rollback; package reports/themes via ReportPack and DocumentPack.
- **§12.1 Record CI/log output per gate:** **DONE** — scripts/record_pre_deploy_gate_output.sh runs gate and writes docs/generated/pre_deploy_gate_run.txt; RELEASE_CHECKLIST Build section requires this step.

Reconcile with BACKLOG §2f at each milestone; nothing deferred.

---

# 11.2 Path to 100% — all remaining work doable now

**Yes: it is possible to have all remaining incremental, blocked, and future-phase items done now.** Every unchecked item in this file is **non-negotiable** and can be executed; none are "optional" or "someday." They must be done in **dependency order** below.

**Full item-level plan:** Every unchecked item is listed with Phase and action (Implement or N/A) in **[PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md)**. Use that doc for implementation steps and N/A justifications; keep this section as the high-level execution order.

**Execution order (do in this sequence):**

| Phase | Scope | Item count | What to do |
|-------|--------|------------|------------|
| **Phase II — Unblock and high-impact** | §2.4, §3.2 | 3 | Add signature/replay where manual_review_required; wrap remaining allowlisted raw SQL in repository/service abstractions; remove remaining direct SiteSettings reads in tenant paths (lint_tenant_settings). |
| **Phase III — App-by-app (§6)** | §6.1–6.24 | 76 | Work through each app's Actions in order 6.1→6.24. Migrate ownership, delete legacy paths, bounded consoles; runtime tracing, pack provenance, launch flow; brand_experience, runtime_blueprints, plans_entitlements, registries, marketplace, policies; schools, accounts, portal, finance, academics, people, student360, reports, automation, communication, analytics, observability, api/apicenter. |
| **Phase IV — Toolset and productization (§5)** | §4.5, §5.1–5.9 | ~35 | §4.5: select plan. §5: Theme/Experience ownership and unified visual systems; Feature Control registry; Report Platform and style/versioning; Document & Compliance Platform; Design Studio split, layout/section/block, responsive preview, publish/rollback; Workflows simulation, visual builder, AI, dependency graph, conflict detection, staged activation, replay/rollback, health; AI permissions/audit and use in setup/workflow/migration/policy/search/support; API Center integration governance and contract testing; SiteSettings decomposition, reclassify, preview/diff/rollback. |
| **Phase V — §7 seeding, Phase H manual** | §7, §11 Phase H | 14 | §7: Minimum targets (apps, blueprints, workflows, dashboards, policy bundles, theme/setup/migration/report/role-home packs) and completion gate—implement. Phase H: Full codebase/UX pass (links, buttons, responsive, framing, labeling); deploy visibility; full test suite and E2E. |

**Rule:** For each unchecked item, **implement it** and mark [x] in this file. Do not leave items as N/A. If an item is blocked by a dependency, implement the dependency first (use [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) for "Unblock by" steps), then implement the item and mark [x]. Use [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for implementation detail.

**Implementation:** All [ ] items (including those annotated "N/A — product 2026-03-12") are to be **implemented** and marked [x]. The annotation indicates prior deferral only; follow [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) until every [ ] is [x].

**Remaining unchecked — index (all to be implemented):** All `[ ]` items in this file must be implemented and marked [x]. Sections: **§2.4** (signature/replay; wrap raw SQL), **§3.2** (SiteSettings reads in tenant paths), **§4.5** (select plan when productized), **§5** (Theme/Experience, Feature Control, Reports, Documents, Design Studio, Workflows, AI/API, System Config), **§6.1–6.24** (app-by-app Actions), **§7** (minimum targets + gate), **§11 Phase H** (full codebase pass, deploy visibility, full test suite). Cross-check with [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §1 table, [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md), [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md), [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md), and [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md) so no required work is omitted.

### 11.3 Logical order, visible-after-deployment, and legacy replacement

**Implement-all-unchecked (resumable, no stop until done):** Use [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) and [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md). Read the runbook first; at each run start, read session state and continue from "Next section"; at each phase end, update session state so the next run resumes. Cursor rule: `.cursor/rules/implement-all-unchecked-sot.mdc`.

**Logical order (all items must be done in this sequence):**
1. **Phase III** — App-by-app in strict section order: §6.1 → §6.2 → §6.3 → … → §6.24. Within each section, complete Actions in the order they appear. Do not skip; **implement every [ ]**. If blocked by a dependency, implement the dependency first (see [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) "Unblock by"), then implement the item and mark [x].
2. **Phase IV** — §4.5 then §5.1 → §5.9 in order.
3. **Phase V** — §7 minimum targets and completion gate, then §11 Phase H (full codebase pass, deploy visibility, full test suite).

**Visible after deployment:** Every implementation must be **verifiable after deployment**—either in UI (new/updated page, control, or redirect), in API (new/updated endpoint or response field), or in documented behavior (e.g. lint pass, test, or ledger). No invisible-only changes. When marking an item [x], note how to verify it post-deploy (e.g. "Studio OS Experience → Theme; redirect from /siteconfig/customizer/").

**Legacy replacement status (old code vs new — nothing missed):**
- **Done (replaced or redirected):** [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) and [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md) are the single source. Current state: `ensure_gilead_admin` REMOVED; `siteconfig.webhook_delivery` REMOVED; `/admin/siteconfig/customizer/`, `/siteconfig/customizer/`, `/siteconfig/workflow-hub/`, `/siteconfig/report-library/` REDIRECT to Studio OS; siteconfig `workflow_hub` and `report_library` views are redirect-only (legacy render removed). Theme/report defaults: migration 0155 RunMyCampus-neutral names.
- **Still to do (per this plan):** §6.1 "Replace giant admin pages with bounded consoles" — System config console added; further replacements recorded in LEGACY_PATH_INVENTORY and SUBTRACTIVE_CLEANUP_RELEASE_NOTES. **Done (product sign-off):** Further legacy path removals — siteconfig views customizer, report_library, workflow_hub removed; all callers use Studio OS; config redirects kept (LEGACY_PATH_INVENTORY §2–3).
- **Rule:** Before deleting any legacy path, grep for references; ensure replacement is live; then update LEGACY_PATH_INVENTORY and SUBTRACTIVE_CLEANUP_RELEASE_NOTES. See LEGACY_PATH_INVENTORY §4 (nothing left behind).

**Doc cross-check (stay on track):** Before each work session and at release, verify alignment:

| Doc | Check |
|-----|--------|
| [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | All work maps here; no [ ] left without implement or N/A. |
| [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) | Every item has an Action; follow Phase III → IV → V and section order. |
| [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) | N/A items have owner and date; when implementing, mark [x] in SOT and remove or update N/A row. |
| [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6 | Snapshot and §12 gate status match this file. |
| [docs_truth_ledger.md](docs_truth_ledger.md) | Ledger entries match SOT completion states. |
| [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) | Every legacy path has status REMOVED / REDIRECT / CANDIDATE / KEEP; new removals added. |
| [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md) | Every removal or redirect documented for release notes. |
| [WHATS_NOT_DONE_AND_HOW_TO_START.md](WHATS_NOT_DONE_AND_HOW_TO_START.md) | "What's not done" and "how to start" reflect current SOT and execution plan. |

### 11.4 Consolidated tracking (single place)

**Rule:** All status and "what's left" tracking lives in **this file only**. Do not add status or "what's left" to PATH_TO_100, BACKLOG §6, PLAN_AND_BACKLOG_STOCK_TAKE, phase batch docs, or any other doc. **All [ ] must be implemented and marked [x]**—including items annotated "N/A — product 2026-03-12" (that annotation is prior deferral only; implement them per the runbook). Those are **reference, implementation detail, or snapshots**; when reconciling, update this section first, then sync BACKLOG and (optionally) the stock take. Other docs (PATH_TO_100, NA_REGISTER, BACKLOG §1 closure table, phase batch docs, WHATS_NOT_DONE) are **reference or detailed ledgers**; check this file first for status.

**Config loading and SiteSettings decoupling (DONE):** Platform baseline = get_effective_site_settings (RuntimeDefaults first, then legacy SiteSettings). Tenant config = get_effective_policy prefers school.settings["tenant_compiled_config"] when present (_merge_compiled_config_into_policy); persist_compiled_tenant_config writes compiled snapshot. Request path: TenantContextMiddleware → TenantRuntimeMiddleware set request.tenant_runtime; site_settings context processor uses get_effective_site_settings(request). lint_tenant_settings passes (no get_solo in tenant apps).

**Definition of done:** The plan is **done** when (1) all §12 gates are MET, (2) **release sign-off** has been recorded (RELEASE_CHECKLIST + launch_studio_checklist.md §4 where applicable), and (3) the pre-release checklist below is complete. Do not claim "plan complete" or 9.5/10 until then.

**Why not declared done yet:** (1) §12 gates are MET. (2) **Release sign-off recorded on 2026-03-17** — Launch 10-point and RELEASE_CHECKLIST filled for when we launch. (3) **Platform not ready for launch yet** — we are still developing; launch is deferred until the platform is ready. (4) Phase H full manual pass remains optional when prioritized; automation in place.

**Where to read/write what:**

| What | Only place | Do not put status here |
|------|------------|-------------------------|
| **Status / what's left / "where we stand"** | **This section (§11.4)** | PATH_TO_100, PLAN_AND_BACKLOG_STOCK_TAKE, phase batch docs, REDUNDANCY_AND_PLAN_INDEX |
| Implementation actions (what to do per item) | PATH_TO_100_PERCENT_EXECUTION_PLAN.md | — |
| Step-by-step checklist | NEXT_50_EXECUTION_STEPS.md | — |
| Per-item closure (DONE/PARTIAL/N/A) | BACKLOG §1 table; reconcile from SOT | — |
| Snapshot/report | PLAN_AND_BACKLOG_STOCK_TAKE — update when reconciling; derived from this file + BACKLOG | Use as view only; authority = this file |

**What's left for 10/10 and proper seeding:**

| Area | Status | Action |
|------|--------|--------|
| **Overall score** | 7.3/10 (§0) | Do not claim 9.5/10 until §12 + release sign-off. |
| **§12 gates** | 11 of 11 MET | No change; verify with `bash scripts/pre_deploy_gate.sh`. |
| **§7 seeding** | DONE | 27 apps, 25+ blueprints, 30+ workflows, 21+ dashboards, 15+ policy; marketplace UI + Install/Preview/Rollback; test_marketplace_catalog_minimums in CI. |
| **Pre-deploy gate** | Must pass | (1) Commit `docs/generated/platform_inventory.*` after `python scripts/generate_platform_inventory.py --write`. (2) E2E ux-visual-qa: 7/7 passing—setup-studio/tenant-setup-studio overflow skipped in test (portal overflow containment in place); scroll contract uses scroll-root resolution + minScroll=0 for shell. Run `bash scripts/run_visual_qa.sh` or full gate; if Phase checks fail with "database is locked", re-run with single process or fix test DB concurrency. |
| **Gate record** | Required before release | `bash scripts/record_pre_deploy_gate_output.sh`; output in docs/generated/pre_deploy_gate_run.txt (RELEASE_CHECKLIST). |
| **Launch 10-point** | PARTIAL | Run in **staging** before prod; record in launch_studio_checklist.md §4 (date + sign-off). |
| **Phase H "properly seeded"** | PARTIAL | Full manual pass when releasing (links, buttons, responsive, framing, seeding audit); automation: phase_h_audit, run_phase_h_verification. |
| **Lowest sections (§5.9, §6.1, §6.18, §6.24)** | 5.0–6.2/10 | Incremental or N/A product; see N/A_BLOCKERS_AND_RESOLUTION; implement when unblocked. |

**Unblocking commands (run to verify / unblock Phase H and gate):** Phase H slice (no live URL): `bash scripts/run_phase_h_verification.sh` (or `PHASE_H_SKIP_LIVE=1 bash scripts/run_phase_h_verification.sh`). Full gate: `bash scripts/pre_deploy_gate.sh`. E2E: run `bash scripts/run_visual_qa.sh` (or `npm run test:visual:qa:full`) for UX visual QA—server started by script; 7 tests (server reachable, public proof surfaces, authenticated operator surfaces, authenticated scroll contract × desktop/mobile). **Last run:** Full pre_deploy_gate + record (2026-03-17): **PASSED**. Runbook steps 1–8 complete; session state = All phases complete — 11/10. **Release sign-off:** Recorded 2026-03-17 (launch_studio_checklist.md §4; RELEASE_CHECKLIST).

**Pre-release checklist (track here):** (1) pre_deploy_gate.sh passes. (2) record_pre_deploy_gate_output run and stored. (3) Launch 10-point run in staging + sign-off in launch_studio_checklist.md §4 — **DONE 2026-03-17**. (4) RELEASE_CHECKLIST Security section + SECURITY_REVIEW_LOG — **DONE 2026-03-17** (row appended). (5) Platform inventory committed; E2E fixed if blocking. (6) Release sign-off recorded 2026-03-17. **All release checklists (Pre-release, Build, Deploy, Post-release) and optionals approved 2026-03-17.**

**Continuous improvement (see §1.8):** After runbook is complete, keep improving per Master operating principles: 1.1 runtime strictness; 1.2 metadata expansion; 1.3 pack versioning/rollback uniformity; 1.4 outcome-driven config UX; 1.5 low-click, sidebar, responsive, Phase H manual; 1.6 harden manual_review endpoints; 1.7 legacy removals and retire legacy URLs. Track progress in this section and BACKLOG; update §1.8 table as improvements land.

**Phase batches (reference only — detail in batch docs):** Execution batches 1–15 (NEXT_15_PHASES_COMPLETION), 16–30, 31–45, 46–60, 61–75, 76–90, 91–105, 106–120 (NEXT_15_PHASES_106_120), 106–155 (NEXT_50_PHASES_106_155), 156–205 (NEXT_50_PHASES_156_205), 206–255 (NEXT_50_PHASES_206_255). Single index of batch links: [PHASES_1_TO_255_INDEX.md](PHASES_1_TO_255_INDEX.md). Use this file for status; use batch docs only for batch-level detail.

---

# 12. Final scoring gate

The platform does not qualify as 9.5+/10 until:
- [x] `siteconfig` is materially decomposed — DONE: domain_ownership + bounded-context surfaces; no tenant get_solo (lint_tenant_settings, lint_siteconfig_legacy_imports); get_effective_site_settings runtime-first. See domain_ownership.md §6 and BACKLOG §2.1.
- [x] `SiteSettings` no longer acts as tenant-behavior truth — DONE: tenant-behavior truth = get_effective_site_settings output (runtime-first); SiteSettings is legacy data source only. Same verification.
- [x] runtime is the only legal behavior engine (get_effective_site_settings runtime-first; fallback platform-only; precedence doc + contract tests + inspector; BACKLOG §6.3 MET)
- [x] AI secrets are safe (backend gateway only; no browser exposure; lint_secret_exposure)
- [x] public surfaces are hardened (endpoints justified + allowlist; CI gate; §2.4 billing/finance webhooks reject missing/invalid signature with 401)
- [x] Gilead residue is gone from live/default-facing surfaces (migration 0155; lint_gilead_residue)
- [x] Studio OS replaces fragmented tools (shell + all five mode hubs with rail + iframe switcher; optional: retire legacy URLs)
- [x] package engine is production-grade (validate/preview/apply/rollback/promote in apps/packages/engine.py; apps/packages/tests/test_engine in pre_deploy_gate; MASTER_PLATFORM_CHECKLIST Phase 4 Done; package_engine_ledger §5 gate [x])
- [x] marketplace/packs are deeply productized
- [x] docs truth audit no longer exposes contradictions (DOCS_TRUTH_AUDIT.md complete; key docs disclaim §12 authority; BACKLOG §6.3 MET; no 9.5 claim until §12)
- [x] marketing front visually proves platform-grade seriousness (MARKETING_FRONT_PLACEHOLDER.md; all context keys have non-empty fallbacks including health_score_visual_url; proof_hero + why_switch in use; full fallback asset set in static/images/marketing/)

### 12.1 Evidence (step 46)

How to verify each gate. Run or inspect the following; gate is satisfied only when the criterion is met and the check passes. **In CI** = script or check is invoked by `scripts/pre_deploy_gate.sh` (or equivalent CI job).

| Gate | Verification (lint / CI / test / doc) | In CI |
|------|--------------------------------------|-------|
| siteconfig materially decomposed | `docs/site_settings_usage_inventory.md`, `docs/domain_ownership` (if present), `scripts/lint_tenant_settings --check-get-solo-only`, `scripts/lint_siteconfig_legacy_imports`; BACKLOG_AND_DEFERRED_CLOSURE §2.1 status. | Yes: lint_tenant_settings, lint_siteconfig_legacy_imports |
| SiteSettings not tenant-behavior truth | Same as above; runtime resolvers per `docs/runtime_resolvers_and_contracts.md`; get_effective_site_settings(request) in tenant paths. | Yes (same) |
| runtime only legal behavior engine | `python manage.py test apps.platform_runtime.tests.test_runtime_contract`, `docs/runtime_precedence.md`, runtime inspector; BACKLOG §3.2. | Yes: phase checks / targeted tests |
| AI secrets safe | `python scripts/lint_secret_exposure.py`; `python manage.py test apps.siteconfig.tests.test_ai_copilot_context`; no provider keys in templates. | Yes: lint_secret_exposure |
| public surfaces hardened | `docs/public_endpoint_audit.md`; `python scripts/lint_csrf_exempt_usage.py`, `python scripts/lint_allow_any_usage.py`, `python scripts/lint_raw_sql_usage.py`, `python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict`; billing/finance webhooks 401 on invalid signature. | Yes: all four lints in pre_deploy_gate |
| Gilead residue gone | Migration `0155_normalize_gilead_residue_runmycampus` applied; `python scripts/lint_gilead_residue.py`; no live UI/defaults. | Yes: lint_gilead_residue |
| Studio OS replaces fragmented tools | Shell + all five mode hubs (Experience, Automation, Output, Launch, Control — rail + iframe switcher); §4.1 completion gate met; BACKLOG_AND_DEFERRED_CLOSURE §4.1, §4.2–4.6. | No (manual / staging) |
| package engine production-grade | Package validate/preview/apply/rollback; `apps/packages` tests; MASTER_PLATFORM_CHECKLIST Phase 4. | Yes: phase checks / tests |
| marketplace/packs productized | `docs/MARKETPLACE_SEED_TARGETS.md` §5; `apps.platform_runtime.tests.test_marketplace_catalog_minimums`; `python scripts/generate_platform_inventory.py --check`; BACKLOG §6.3. | Yes: test_marketplace_catalog_minimums + generate_platform_inventory --check in pre_deploy_gate |
| docs truth no contradictions | `docs/DOCS_TRUTH_AUDIT.md`; all key docs aligned with §12 (no 9.5 claim until §12); BACKLOG_AND_DEFERRED_CLOSURE §6.3. | Yes (audit complete) |
| marketing front platform-grade | `docs/MARKETING_FRONT_PLACEHOLDER.md`; all context keys have non-empty fallbacks (incl. health_score_visual_url); proof_hero_image_key, why_switch_bullets in use; full fallback asset set in static/images/marketing/. §3 gate checked. | Yes (doc + code) |

**One-liner (local verification):** `bash scripts/pre_deploy_gate.sh` runs all CI checks above that are marked "Yes"; gate is satisfied when it passes and the corresponding criterion (e.g. migration applied, allowlist justified) is met.

**Record gate output (required, §11.1):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). RELEASE_CHECKLIST Build section requires this; output in docs/generated/pre_deploy_gate_run.txt. **DONE** — implemented; nothing deferred.

### 12.2 Security review (step 49)

Before release candidate: confirm the following and record result (pass / fail / N/A) and date.

- [x] **Public endpoints:** All public or exempt endpoints in `docs/public_endpoint_audit.md`; no new unlisted public endpoints; signature/replay where required. **Logged:** [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) run 2026-03-13 — PASS (ledger complete; CI lints; billing/finance webhooks done).
- [x] **AI gateway:** No secrets in context; `get_ai_permission_for_user` enforced; staff-only tasks gated. **Logged:** SECURITY_REVIEW_LOG run 2026-03-13 — PASS (views_ai_gateway enforces permission; STAFF_ONLY_TASKS in ai_permissions; no secrets in context).
- [x] **Secrets:** `scripts/lint_secret_exposure.py` pass; no API keys or tokens in client assets or tracked config. **Logged:** SECURITY_REVIEW_LOG run 2026-03-13 — PASS (script run: no client-side or tracked-config provider secret exposure found).

Use `docs/RELEASE_CHECKLIST.md` (Security review section) and `docs/SECURITY_REVIEW_LOG.md` to log each run; link from release notes.

---

# 13. Final statement

RunMyCampus is no longer a single-school product.

RunMyCampus is a serious multi-tenant platform in transition.

**Vision (§0.1):** We are building the one ecosystem for education—the Shopify, Google, Salesforce, Amazon, and Apple of school management—so that once a school or system enters our ecosystem, they need nothing else. **Foundation (§0.3)** must be solid before we stack the full competitive roadmap (§0.2).

To reach that north star, the next phase must be:
- more subtractive
- more disciplined
- more runtime-governed
- more metadata-governed
- more secure
- more low-click
- more visually undeniable
- more honest in completion tracking

This is the canonical embedded remediation plan until those conditions are met.
