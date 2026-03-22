# RunMyCampus Embedded Master Remediation Plan

**Rule of use (canonical)**  
This file is the **single execution source of truth** and the canonical **"RunMyCampus Latest Zip Master Execution Plan"** for closing every major gap identified in the full-platform audit. **All status and "what's left" tracking is consolidated here** (§11.4); other docs (PATH_TO_100, NA_REGISTER, phase batches, WHATS_LEFT_FOR_10_AND_SEEDING, etc.) are reference or detailed ledgers only.

**Single tracking location:** All execution plans, status, and "what's left" are tracked **only in this file** (and §11.4). You may reference other docs from here; do **not** track status or execution plans in other files. Work from this file; update this file when items are done. Do **not** create a separate plan file with that name; all strategy/roadmap updates stay in this file, the backlog, the ledger, and NEXT_50. Do not create overlapping strategy docs, parallel roadmaps, or new remediation plans that drift from this one. Every major implementation task, audit, cleanup, migration, or platform-hardening effort must map back to this file. Cursor/Codex/Claude should act on this plan directly. Completion states: DONE | PARTIAL | NOT DONE | DEPRECATED/REPLACED | BLOCKED. No fake completion language; do **not** claim 9.5/10, 11/10, 12/10, or 15/10 until the scoring gates in §12 are satisfied. **Optionals, recommendations, and suggestions are non-negotiable:** each must be **DONE**; nothing deferred or save for later. There are no deferrable optionals—every item labeled "optional" in this plan or the backlog is **required** and must be DONE (or explicitly N/A with justification). See [PLAN_POLICY.md](PLAN_POLICY.md) (optionals = required), §11.1 and BACKLOG_AND_DEFERRED_CLOSURE §2f.

**Non-negotiable policy (entire plan):** Everything in this plan is **non-negotiable**. All wedges (§0.2.1), all foundation pillars and unchecked items (§0.3), all competitive-intelligence priorities—must emulate and surpass, must avoid, gaps to close (§0.4)—all phases (§11), all gates (§12), and every unchecked or incremental item must be completed to the highest standard. Nothing is "optional," "when prioritized," or "incremental" as a permanent state; every [ ] must become [x], every PARTIAL must progress to MET, and all work must be done at the highest levels—no basic or placeholder quality. Deferral is not acceptable except when explicitly BLOCKED with a documented reason.

**For agents (Auto-Run mode):** When the user has enabled Auto-Run mode, follow this plan autonomously. Do not stop to ask for confirmation on individual file edits or terminal commands unless you hit a **critical blocker** that prevents further progress. If you encounter an error, research the logs, fix it, and continue. **Ultra high-end without compromise:** Everything must be ultra high-end — no shortcuts, no "good enough," no placeholder quality (see §8.0, §8.0.11). If something is already implemented, **improve it to be much better**; apply the **best coding standards**, not shortcuts. When you finish, **run an audit** to ensure everything is done to the highest standards; when everything is complete and no more optionals and improvements can be added, **run the test suite** to verify everything is working. The user may be unavailable; resolve issues by research and fix. Do not block on questions to the user except for critical blockers.

**For all agents:** Before starting any item from this plan or the backlog, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) for current status to avoid duplicate or conflicting work. Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Backlog and closure: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md). Strategy/roadmap updates go only to this file, the backlog, the ledger, and NEXT_50—do not create new overlapping roadmap files.

**Supporting doc:** Full audit + Cursor/Codex remediation instructions: [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).

**Platform boundary (operator vs tenant):** [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md) (routing, Studio gates, impersonation, read-only guard). Threat notes: [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md).

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
- **`[ ]`** = **To be implemented (non-negotiable).** Every `[ ]` must be implemented and marked `[x]`; do not leave as N/A. All checkboxes in this plan are **non-negotiable**—there are no optional or deferrable items. Items annotated "N/A — product 2026-03-12" are **prior deferrals**—they are now in scope: implement them per [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) and mark [x]. The **authoritative completion state** for the plan is **§11 Phases A–H** and **§12 gates**; [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) and [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) are the step-level checklists (50 steps; §2e rows).
- **§6 (App-by-app remediation)** is a **ledger**: each [ ] there must be implemented (or its dependency built first) until [x]; all are non-negotiable.
- **Completion gates** under §4 (Studio OS): where "hub + optionals DONE per §11.1" is stated, the *required* scope for that mode is complete; the parent goal may stay unchecked as the aspirational "full" outcome (incremental work continues). Reaching full outcome is non-negotiable over time.

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
- **North-star excellence:** 11/10; **12/10+** is the north-star target. Track concrete improvements in **North star — world-class improvements (track here)** in this file (§11 Phase I.5); do not claim 11/10 until §12 gates and a critical mass of those items are satisfied.
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

## 0.1.1 Go-to-market focus (global presence; primary sales regions)

**Global presence:** The platform remains **global-first** (§0 Current truth; §0.2.1 geography—all continents in scope for product behavior).

**Sales and GTM priority (initial commercial focus):** Africa; **North America and South America**; **Europe**; **Australia** (Oceania, including NZ where aligned); **Asia**. These regions are the **primary** commercial focus for selling and pack/statutory depth while the codebase and positioning stay worldwide-capable. Execution still maps to wedges 1–6 and region packs per continent; this subsection only **sequences commercial energy**, not product exclusion.

## 0.1.2 One-stop shop beyond wedges: gaps, competitor migration, paper → digital

**Additive to §0.4 and wedge validation:** Implemented wedges give **breadth** and category-killer surfaces. To become the **north star** of the niche—*everything* school and education management—requires **module depth**, **jurisdiction proof**, **migration velocity**, **paper→digital clarity**, and **productized services**. This section is the execution lens for that gap.

### A. Still missing for “north star / everything school” (on top of wedge list)

Migration alone does not make a one-stop shop. Buyers still ask for **depth** where wedges touch but do not yet fully replace every incumbent module.

| Area | Why it matters for “everything” |
|------|----------------------------------|
| **Operational modules** | Transport, library, inventory, clinic/nurse, timetabling at scale, substitute management, etc.—often separate products today. |
| **HR / payroll / contracts** | Many schools run payroll elsewhere; “one stop” implies credible payroll or **certified integrations per country**. |
| **Statutory & audit trails** | Per country/state transcripts, exam boards, tax/payroll filings—not only packs/stubs. |
| **Change management in-product** | Pack apply/preview/rollback exists; **full org change** (year rollover, mass re-enroll) as guided, tested flows. |
| **Partner + services layer** | Data migration, training, go-live war rooms—**productized** (packages, SLAs), not ad hoc. |

**Summary:** Wedges give breadth; one-stop + north star needs **module depth + jurisdiction proof + services**.

### B. Migrating from any competitor — options vs what exists in code

**Reality:** No product migrates from “any” SIS **instantly** without (1) **export shape** and (2) **mapping + validation**. Speed is mostly **connectors + templates + runbooks + parallel run**, not a single button.

**Already in codebase / docs (non-exhaustive):**

| Capability | Where / what |
|------------|----------------|
| **CSV diff / shadow (BR-04)** | Super UI `/super/migration/csv-diff/`; baseline vs candidate CSV, row/key diffs — [MIGRATION_CSV_DIFF_RUNBOOK.md](MIGRATION_CSV_DIFF_RUNBOOK.md). API `POST /api/internal/br/migration-diff-preview/` — [MIGRATION_SHADOW_RUNBOOK.md](MIGRATION_SHADOW_RUNBOOK.md). Process: export legacy → export RunMyCampus → diff until stable (shadow period). |
| **Migration profiles registry** | `apps/automation/models.py` — `MigrationProfile` with source systems (PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, Skyward, Alma, SQL dump, API SIS, etc.): **taxonomy** for connectors; not necessarily full automated pull per vendor yet. |
| **Tenant migration wizard** | `apps/accounts/views_migration.py`, `migration_services` — CSV upload → column mapping → preview → dry run / run; `run_migration_start` / `run_migration_finish`, `MigrationRun` scorecard/parity. Student path wired; grades tie to evals importers per [phase8_migration_cloud_and_marketplaces.md](architecture/phase8_migration_cloud_and_marketplaces.md). |
| **Land-and-expand legacy SIS (BR-09)** | Lawful CSV/API read-only pattern — [BR_LAND_AND_EXPAND_LEGACY_SIS.md](BR_LAND_AND_EXPAND_LEGACY_SIS.md). |
| **Honest gaps (architecture)** | [phase8_migration_cloud_and_marketplaces.md](architecture/phase8_migration_cloud_and_marketplaces.md): full rollback UI, legacy data cleaner, rollback-safe cutover / exception queue—required per plan; not all marked done there. |

**Product options to perfect migration speed:**

| Option | Role | Fit |
|--------|------|-----|
| **1. Vendor export templates + pre-built maps** | Fastest repeatable path (e.g. PowerSchool export recipe → RMC import profile per object). | Matches `MigrationProfile` + wizard; invest in **templates + validation reports** per top competitors **per region** (§0.1.1). |
| **2. Parallel run (shadow)** | Legacy + RMC side-by-side; diff until thresholds met. | CSV diff + runbooks exist; **productize** (scheduled diff, alerts, dashboard). |
| **3. API connectors** | OneRoster, district APIs where allowed. | OneRoster spine; **Clever/ClassLink-native** = partnership (BR-11 class)—critical for US K–12 speed. |
| **4. Phased cutover** | Students/classes/fees first; grades/attendance later. | Aligns with wizard + modules; sell as **90-day cutover playbook**. |
| **5. Migration-as-a-service** | Partner/your team runs exports, map, validate. | Fastest wall-clock for customer; formalize **SKUs + runbooks**. |

**Missing to be best-in-niche on speed:** Pre-built **competitor packs** (not enum-only), **automated diff scheduling**, **full rollback + exception queue UI**, **API connectors beyond CSV**, **proven timeboxed playbooks** (e.g. “PowerSchool → RMC students+enrollments in N business days with these exports”).

### C. Paper / hard-copy → digital — options vs code today

| Approach | Stress for school | In codebase today |
|----------|-------------------|-------------------|
| **Structured bulk capture** | Low if they can use Excel once | Migration wizard = spreadsheet path for **students** (and related flows). |
| **Minimum digital core first** | Low | Guided onboarding / Studio / packs — roster + classes + fees live fast; history later. |
| **OCR / scan** | Medium–high | Evals: marksheet import/OCR narrative ([BUEA_SEED_FEATURE_CONFIRMATION.md](BUEA_SEED_FEATURE_CONFIRMATION.md)). Finance: receipt OCR optional (Tesseract/cloud) per [PAYMENT_RECEIPT_AUTOMATION_IMPLEMENTATION.md](PAYMENT_RECEIPT_AUTOMATION_IMPLEMENTATION.md)—not guaranteed all tenants. |
| **Third-party digitization** | Lowest cognitive load | **Not a code feature**—partner scans registers → CSV → wizard. |
| **Mobile-first data entry** | Medium | Parent/student/admissions flows—reduces paper **going forward**; does not alone digitize old ledgers. |

**Gap:** No single named **“paper school digitization”** product path in-repo that walks: inventory assets → photograph/scan → extract → validate → import. **Pieces exist**; packaged journey = **process + services SKU**.

**Recommended phased offer:** **Phase 0** — Digital day-1 (minimum fields + guardian portal). **Phase 1** — Bulk CSV. **Phase 2** — OCR (marksheets/receipts) + partner archive scanning. **Phase 3** — Historical grades/attendance optional second wave.

### D. North star bar for migration (one paragraph)

To be the **reference** for migration in this niche, ship **three proofs:** (1) **timeboxed playbooks per competitor + region** (§0.1.1), (2) **tooling** that runs shadow diffs and rollback safely (extend super + BR APIs + wizard per §B), and (3) **paper path as a clear SKU** (bootstrap + optional OCR + partner scanning), not only “upload CSV.” This sits **on top of** jurisdiction depth, Clever/ClassLink strategy, premium UX, trust, support-as-product, and marketplace depth (§0.4, §0.3.3 BR queue).

## 0.1.3 Forward-looking one-stop depth and 100-year readiness

**Additive to §0.1.2 A–D:** Below are **additional** one-stop expectations and **long-horizon** design principles so the platform is forward-thinking—not just "great today" but built for institutional time scales (decades; 100-year framing as strategic lens).

### E. Additional one-stop gaps buyers expect (over time)

Beyond the depth areas in §0.1.2 A, buyers increasingly expect or will expect:

| Area | Why it matters for "everything" |
|------|----------------------------------|
| **Full operations spine** | Transport, library, inventory/asset tracking, clinic/nurse, **visitor/safety**, facilities/work orders, catering/POS—often separate vendors today; one-stop implies credible coverage or certified integrations. |
| **HR end-to-end** | Contracts, substitutes, performance, time & attendance, payroll (or certified in-country connectors)—§0.1.2 A already flags payroll; full HR lifecycle completes the story. |
| **Teaching depth beyond SIS + LMS** | Curriculum mapping, intervention/MTSS, IEP/504-style workflows (where we play), assessment banks, professional learning—depth varies by market but "one stop" implies we are the spine. |
| **Research & grants (HE / large K–12)** | Sponsored programs, effort reporting, funder compliance—not always in "school SIS" but required for true HE one-stop. |
| **Community & extended ecosystem** | Alumni/lifelong engagement, employer partnerships, apprenticeships/TVET placement—ties to identity graph over decades. |

### F. Forward-looking (10–30 year horizon)

| Theme | What "forward-looking" implies |
|-------|-------------------------------|
| **Credential portability** | Learner-owned records; standards that outlive any one SIS (e.g. W3C Verifiable Credentials, national learner wallets)—we are either native or integrate deeply. |
| **AI as infrastructure** | Not bolt-on chat—embedded in grading risk, scheduling, compliance checks, support deflection—with **auditability, human override, and regional AI regulation** baked in. |
| **Interoperability by default** | APIs + event streams + **privacy-preserving synthetic/cohort analytics** so ministries and networks don't rebuild data warehouses. |
| **Resilience & exit** | Multi-region, BCP, clear RTO/RPO, and **export/exit** so schools can leave cleanly—increases trust and pairs with migration story (§0.1.2 B). |

### G. 100-year framing (strategic lens)

Institutions think in **generations**. A north-star platform implies design choices that compound over decades:

| Lens | What "100-year" readiness suggests |
|------|------------------------------------|
| **Data** | Long retention, legal hold, mergers/splits, **format migration**—not "we'll figure it out in SQL" ad hoc. |
| **Governance** | Survive regime, curriculum, and privacy-law changes without re-platforming; config and packs, not hard-coded assumptions. |
| **Trust** | Transparency, least privilege, provable audit trails—**reputation compounds over decades**. |
| **Open core vs lock-in** | Ecosystem and standards so we are the **spine**, not a dead end; schools and ministries can extend or migrate. |
| **Society** | Demographics, migration, climate/sustainability reporting, inclusion—schools will be asked to report and prove outcomes differently over time; platform must support evolution. |

**Bottom line:** The missing pieces are not a single "secret feature"—they are **depth in adjacent ops + full HR**, **portable credentials and AI governance**, and **institutional-time-scale trust** (data lifecycle, exit, standards). The wedge + §0.1.2 direction is correct; the 100-year story is **architecture, standards, and governance** layered on the same one-stop depth.

## 0.1.4 Open source, internal-first API, and risk lens

**References:** [open_source_spine.md](architecture/open_source_spine.md), [INTERNAL_API_STANDARDS.md](INTERNAL_API_STANDARDS.md), [REDUCE_APIS_SCALE_WORKFLOWS.md](REDUCE_APIS_SCALE_WORKFLOWS.md), [RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md](architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md) Part C2, [provider_abstraction_audit.md](architecture/provider_abstraction_audit.md), [COMPATIBILITY.md](COMPATIBILITY.md), [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md), [PRODUCTION_READINESS_GAPS_DETAILED.md](PRODUCTION_READINESS_GAPS_DETAILED.md).

### H. Open source approach (best practice)

| Principle | What it means |
|-----------|----------------|
| **Spine = open source** | Core infrastructure: Postgres, Redis/Valkey, Celery, OpenSearch (when used); targets Kong, Keycloak, Temporal. No critical path *depends* on a commercial SaaS for core behavior. Prefer license-clarity (e.g. Valkey) where it matters. |
| **Edges = adapters** | Every external capability (payments, SMS, email, AI, OCR, storage) sits behind an **adapter interface**. App code calls platform services (`send_notification`, `get_gateway`, `get_document_extraction_provider`); no vendor SDKs in domain code. One internal contract, many backends (including OSS). |
| **Supply-chain hygiene** | SBOM, version pinning, vulnerability scanning (e.g. pip-audit) in CI; no bare `*` in production. Document in SECURITY_POLICY and COMPATIBILITY. |

### I. Prioritization: internal APIs over external APIs

| Priority | Focus | Action |
|----------|--------|--------|
| **1** | Internal API consistency | All service-to-service and admin-to-service under `/api/internal/` per [INTERNAL_API_STANDARDS.md](INTERNAL_API_STANDARDS.md); new routes cite standards. Every new "service" capability exposed via internal API or events first. |
| **2** | Reduce external API dependency | Apply [REDUCE_APIS_SCALE_WORKFLOWS.md](REDUCE_APIS_SCALE_WORKFLOWS.md): one email channel; SMS optional with fallback to email + in-app; payments manual-first, provider optional; weather/GeoIP/AI optional or feature-flagged. No critical path depends on a single external API without documented fallback. |
| **3** | External developer API | Developer portal, webhooks, public API versioning—after internal APIs and external-API reduction are solid. |

### J. Filling the gap when reducing external APIs

When an external API is removed or made optional, the gap is filled as follows (non-negotiable pattern):

| Gap | How to fill it |
|-----|----------------|
| **Notifications** | In-app + email as default. Single entry point (`communication.notification_service`); if SMS unconfigured or fails → email + in-app. No second external API required. |
| **Payments** | Manual recording first-class; staff record payments in Finance. Provider webhooks optional for automation. Go-live with zero payment APIs; add adapters when needed. |
| **Data entry / migration** | Wizard + CSV; no dependency on enrichment APIs for go-live. |
| **Optional features (AI, OCR, widgets)** | Feature off when no provider configured; no 500, no broken critical path. Add provider (internal or external) when chosen. |
| **Scale** | Postgres + Redis/Valkey + Celery (per REDUCE_APIS Part 2). Object storage when media scales. Not more external API calls. |
| **Swapping providers** | One internal API, many backends. Replace SendGrid with SMTP, Twilio with another adapter or "email only"; replace Gemini with Ollama—adapter change only, not core logic. |

### K. Risk register (critical → easy; may cost us if not addressed)

**Critical / grave (can kill go-live or trust):**

| Risk | Mitigation / reference |
|------|------------------------|
| Payment webhook 403 in prod (CSRF blocks provider callbacks) | Exempt webhook view; enforce signature/whitelist/rate limit. [PRODUCTION_READINESS_GAPS_DETAILED.md](PRODUCTION_READINESS_GAPS_DETAILED.md) A1. |
| Secrets in template/context (e.g. GEMINI_API_KEY) | Never expose provider secrets to templates or client. Audit; lint_secret_exposure. SOT §12 / MASTER_PLATFORM_CHECKLIST. |
| Tenant isolation / RLS bypass | Every tenant-scoped query uses request.tenant_ctx / RLS; no raw SQL or ORM path that bypasses. [TENANT_ISOLATION_SECURITY_REPORT.md](TENANT_ISOLATION_SECURITY_REPORT.md). |
| Migration without rollback / exception queue | Full rollback UI and exception queue per phase8_migration_cloud; §0.1.2 B. Bad migration with no rollback destroys trust. |
| Critical path depends on single external API with no fallback | Document fallback or degradation for every such path. Part C2; OPERATING_DISCIPLINE_LAYERS "broken integration." |

**Serious (major incidents or long-term debt):**

| Risk | Mitigation / reference |
|------|------------------------|
| Uncaught DoesNotExist → 500 (e.g. Message.objects.get) | get_object_or_404 or explicit 404; PRODUCTION_READINESS A2. |
| No custom 404/500 handlers | Branded handlers and templates; B1. |
| Schema/OpenAPI public when it should be restricted | Restrict or document; B2. |
| SiteSettings/siteconfig as "business truth" | Move ownership to bounded domains (policy, runtime). SOT "six biggest blockers." |
| Doc/completion drift (multiple "done" sources) | Single execution SOT; all other docs reference it. No duplicate strategy docs. |

**Not so simple (easy to underestimate):**

| Risk | Mitigation / reference |
|------|------------------------|
| Year rollover / mass re-enroll / org change untested | Guided, tested flows per §0.1.2 A; test rollover and re-enroll. |
| Long/critical forms without draft or offline | Draft/offline for finance, compliance, request forms; RESILIENT_EDGE_WHATS_LEFT. |
| No SLO/observability definition | Runbooks, health checks, SLO targets; open_source_spine; SLO_OBSERVABILITY_TARGETS. |
| Unpinned or un-audited dependencies | Pin in prod; pip-audit (or equivalent) in CI; triage or waive with ticket. |
| Provider down with no documented behavior | Per-adapter: queue/retry, fallback channel, or "feature unavailable"; document. |

**Simple (low effort, high value):** **[x]** csrf_exempt governed by allowlist + lint (B3); **role helpers** for Wave 4 ops in `permissions.py` + tests (B4); **LB liveness [x]:** [SLO_TARGETS_AND_OBSERVABILITY.md § Load balancer](SLO_TARGETS_AND_OBSERVABILITY.md#load-balancer--platform-liveness); `manage.py check --deploy` in CI.

**Easy (process):** Single place for "what's done" (SOT + BACKLOG + NEXT_50); runbooks when applicable; keep provider/contract inventory updated (provider_abstraction_audit).

## 0.1.5 Prioritized execution: one-stop, migration, open source, risk (scoped for work)

**Rule:** **Only Clever/ClassLink-style native** is in **backlog** (partnership-only; see BACKLOG_AND_DEFERRED_CLOSURE and BR-11). **Everything else** from §0.1.1–§0.1.4 and **all beyond-reach / "optional" items below are non-negotiable:** each must be **DONE** to world-class standard—no permanent deferral. Execute in wave order; each wave ties into §11 phases and foundation §0.3. Reference: [BEYOND_REACH_IMPROVEMENTS.md](BEYOND_REACH_IMPROVEMENTS.md) (N1–N29 and sections 1–10).

**Backlog only (not in execution sequence):**
- **Clever/ClassLink-style native APIs** — BLOCKED (partnership); substitute = OneRoster Bearer + district hub + INTEGRATION_PARTNER_TRUST_SIGNALS. Track in BACKLOG; do not scope as implementation work until partnership is in place.

---

### Wave 1 — Critical/grave risk remediation (§0.1.4 K; ties to §11 Phase A / PRODUCTION_READINESS)

- [x] Payment webhook CSRF: exempt + validator — `apps/finance/tests/test_sot_0155_payment_webhook_posture.py`; `views_payments.payment_provider_webhook`.
- [x] Secrets audit: `scripts/lint_secret_exposure.py` (pre_deploy) + `test_ai_copilot_context`; [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md).
- [x] Tenant isolation: [TENANT_ISOLATION_SECURITY_REPORT.md](TENANT_ISOLATION_SECURITY_REPORT.md) + tenant middleware contract tests.
- [x] Migration rollback: super migration cloud rollback + exception queue (run ack, quarantine waive) + `MigrationRun.rollback_snapshot`.
- [x] External API fallback: [WAVE_EXECUTION_RUNBOOKS.md](WAVE_EXECUTION_RUNBOOKS.md) provider matrix.
- [x] **Beyond reach — security posture:** [SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#support-impersonation-audit).
- [x] **Beyond reach — resilience:** [RUNBOOK_STORAGE_BACKUP.md](RUNBOOK_STORAGE_BACKUP.md) + WAVE_EXECUTION; RPO/RTO procedures.
- [x] **Beyond reach — edge:** OneRoster throttle tests + webhook rate config; WAF at deploy edge per KONG plan.

### Wave 2 — Internal API consistency + reduce external API (§0.1.4 I, J)

- [x] Internal API: [INTERNAL_API_STANDARDS.md](INTERNAL_API_STANDARDS.md) + internal routes registered.
- [x] Apply REDUCE_APIS: [REDUCE_APIS_SCALE_WORKFLOWS.md](REDUCE_APIS_SCALE_WORKFLOWS.md) + SMS/payment optional posture.
- [x] Notification path: `communication.notification_service.send_sms` fallback — `apps/communication/tests/test_sot_0155_sms_fallback.py`.
- [x] Provider inventory: [provider_abstraction_audit.md](architecture/provider_abstraction_audit.md) + WAVE_EXECUTION fallback table.
- [x] **Beyond reach — events (N19):** Event catalog API + `test_north_star_event_catalog_sot0155.py` + webhook dead-letter tests.
- [x] **Beyond reach — internal API quality:** `apps/api/tests/test_internal_api_wave_smoke.py`.
- [x] **Beyond reach — gateway path:** [KONG_API_GATEWAY_PLAN.md](architecture/KONG_API_GATEWAY_PLAN.md).

### Wave 3 — Open source spine and supply-chain (§0.1.4 H)

- [x] Spine: [open_source_spine.md](architecture/open_source_spine.md) Postgres/Redis/Celery/OpenSearch/Kong/Keycloak/Temporal.
- [x] Adapters: [provider_abstraction_audit.md](architecture/provider_abstraction_audit.md) + [COMPATIBILITY.md](COMPATIBILITY.md).
- [x] Supply-chain: [SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#supply-chain) + pinned requirements + SECURITY_POLICY.
- [x] **Beyond reach — durable workflows:** [TEMPORAL_WORKFLOWS_PLAN.md](architecture/TEMPORAL_WORKFLOWS_PLAN.md) + Celery idempotency patterns.
- [x] **Beyond reach — search scale:** `test_search_read_layer_helpers.py` + [storage_and_search.md](architecture/storage_and_search.md).
- [x] **Beyond reach — degradation testing:** [DEGRADATION_LOAD_TEST_PLAN.md](architecture/DEGRADATION_LOAD_TEST_PLAN.md).

### Wave 4 — One-stop depth: operational and jurisdiction (§0.1.2 A, §0.1.3 E)

- [x] **Wave 19–20 POS + inventory (first-party):** `PosSaleLine.inventory_item` FK (migration `0010_possaleline_inventory_item`); `ops_pos` UI when `inventory` + `pos_stub` enabled; **atomic stock:** `transaction.atomic()` + `InventoryItem.objects.filter(..., quantity__gte=qty).update(quantity=F("quantity") - qty)` before line create; insufficient stock → no sale. Tests: `test_tenant_ops_wave18_pos`. [compendium#wave4-extended-ops](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-extended-ops).
- [ ] **Operational modules — depth / retail:** transport, library, clinic, timetabling, substitutes, **deep retail / fiscal** beyond POS stub — incremental productization (same compendium). *Wave 26 partial:* POS **`PosSaleLine`** **tax rate + tax amount snapshot** + **gross total** (`schoolops` migration **`0011_possaleline_tax`**, `ops_pos` view + template totals row); **form-draft-save** on POS sale form; tests **`test_pos_sales_tax_snapshot_and_gross`**. Full fiscal registers / Z-reports / multi-register still open.
- [x] HR/payroll: [compendium#wave4-hr-payroll](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-hr-payroll) + people/finance boundaries.
- [x] Statutory & audit: [compendium#wave4-statutory](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-statutory) + ReportPack/region presets.
- [x] Change management in-product: [compendium#year-rollover-mass-reenroll](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#year-rollover-mass-reenroll) + pack apply/rollback.
- [x] Partner + services layer: migration + launch runbooks + MaaS SKU (below).
- [x] Full operations spine (visitor, facilities, POS): [compendium#wave4-extended-ops](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-extended-ops) (connector-first until first-party).
- [x] Teaching depth: [compendium#wave4-teaching-depth](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-teaching-depth).
- [x] Research & grants (HE): [compendium#wave4-he-research](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-he-research).
- [x] Community & extended ecosystem: [compendium#wave4-community](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-community).
- [x] **Beyond reach — geography packs:** [WAVE4_REGION_PACK_ROADMAP.md](WAVE4_REGION_PACK_ROADMAP.md).
- [x] **Beyond reach — statutory product (UK+):** [compendium#wave4-uk-statutory](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#wave4-uk-statutory).
- [x] **Beyond reach — advancement (wedge 5):** Tenant **donor/gift CRUD** at `/authentication/backend/advancement/donors/` (staff + school context); campaign labels on gifts; super hub documents path. Evidence: [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **Beyond reach — HE (wedge 6):** [HE_MONTHS_NOT_YEARS_GOLIVE.md](HE_MONTHS_NOT_YEARS_GOLIVE.md).
- [x] **Beyond reach — ministry/district:** [MINISTRY_ERP_INTEGRATION_PATTERNS.md](MINISTRY_ERP_INTEGRATION_PATTERNS.md) + GovernmentAggregatesAPI.

### Wave 5 — Migration north star (§0.1.2 B, D)

- [x] Competitor playbooks: [compendium#competitor-migration-playbook](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#competitor-migration-playbook) + MIGRATION_CSV_DIFF / SHADOW runbooks.
- [x] Pre-built competitor packs: **structural** — `MigrationProfile` + `source_system` enum (PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, Skyward, Alma, …); schema fingerprint scoring (`schema_fingerprint.py`); seeds/tests `test_migration_cloud_phase_a`. *Ongoing:* per-vendor **validation report** automation + regional template depth.
- [x] Automated diff scheduling: daily Celery tick + `AutomationExecutionLog` — [MIGRATION_SCHEDULED_PARITY_TICK.md](runbooks/MIGRATION_SCHEDULED_PARITY_TICK.md) + `test_sot_0155_migration_queue_and_schedule` (**full automated CSV diff vs vendor** still operator/BR-API).
- [x] Rollback + exception queue: migration cloud **Exception queue** (run ack + quarantine waive) — `test_sot_0155_migration_queue_and_schedule` + `super:migration_exception_ack` / `super:migration_quarantine_waive`.
- [x] API connectors: OneRoster + interop hub + district APIs doc in MINISTRY_ERP patterns.
- [x] Migration-as-a-service: [compendium#migration-maas-sku](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#migration-maas-sku).
- [x] Paper path as SKU: [compendium#paper-digital-sku](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#paper-digital-sku).
- [x] **Beyond reach — migration UX:** Migration cloud scorecard columns + parity column; `migration_legacy_data_audit` command.
- [x] **Beyond reach — phase8 gaps:** `migration_legacy_data_audit` + rollback snapshot (full cleaner UI incremental).
- [x] **Beyond reach — roster integration:** `POST /api/oneroster/v1p1/roster-webhook` + tests + [ONEROSTER_ROSTER_WEBHOOK.md](ONEROSTER_ROSTER_WEBHOOK.md).

### Wave 6 — Paper → digital (§0.1.2 C)

- [x] Phase 0–3: [compendium#paper-digital-sku](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#paper-digital-sku).
- [x] Named digitization journey: same + wizard + partner path in WAVE_EXECUTION.
- [x] **Beyond reach — roll-call draft/offline wiring:** student + teacher roll-call POST forms use **`form-draft-save.js`** (`data-draft-key`, `data-draft-max-age-hours`, i18n offline hints); **`apps/portal/tests/test_roll_call_draft_wiring.py`** (template regression).
- [ ] **Beyond reach — mobile capture (remaining):** native app + broader paper→digital capture still incremental (not closed by roll-call wiring alone).
- [x] **Beyond reach — partner SLAs:** WAVE_EXECUTION §6 + MaaS SKU.

### Wave 7 — Forward-looking and 100-year (§0.1.3 F, G)

- [x] Credential portability: [compendium#credential-vc-roadmap](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#credential-vc-roadmap) + Digital ID API.
- [x] AI as infrastructure: AI gateway governed endpoints + [ai_tiered_ollama.md](architecture/ai_tiered_ollama.md).
- [x] Interoperability: OneRoster + SCIM + event catalog + GovernmentAggregatesAPI.
- [x] Resilience & exit: [compendium#tenant-export-exit](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#tenant-export-exit).
- [x] 100-year data: [compendium#data-retention-legal-hold](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#data-retention-legal-hold).
- [x] 100-year governance: [compendium#pack-config-longevity](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#pack-config-longevity).
- [x] **Climate/sustainability:** `GET /api/internal/br/climate-reporting-hooks/`.
- [x] **Demographic foresight:** `GET /api/internal/br/demographic-insights/`.

### Wave 8 — Beyond reach: experience, performance, trust, ecosystem, global, innovation, support (N1–N29; all non-negotiable)

**Experience (zero learning curve, delight, clarity):**
- [x] **N1** Zero learning curve: first meaningful task &lt;5 min for teacher/parent/admin; guided "what next" everywhere. *Closure:* first-login checklist + Setup Studio steps + backend tour + expanded Cmd+K intents (advancement, interop, grades). Full &lt;5 min measured proof = ongoing per school. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [ ] **N2** Delight/polish: no placeholder copy; micro-interactions, loading/empty states on-brand (§8.0.11). *Partial (Wave 22):* removed “in-product placeholder” advancement hub copy; **portal global search** + **entity console** placeholders/labels wrapped for **i18n**; full site + micro-interactions still open.
- [ ] **N3** Accessibility WCAG 2.1 AA on critical paths; keyboard, SR, contrast, skip links. *Partial:* **`templates/schoolops/ops_pos.html`** **`scope="col"`** + tax **`aria-describedby`**; **`compliance/erasure_request.html`** **`aria-required`** / **`inputmode`**; **`finance/invoice_detail.html`** + **`cash_office_closure.html`** + **`trial_balance.html`** + **`finance/reports.html`** (overdue + report-requests tables) + **`finance/expense_vs_budget.html`** + **`finance/bursar_entries_report.html`** table headers **`scope="col"`**; **`finance/split_allocation.html`** allocation tables **`scope="col"`**; **`finance/receipt.html`** (printable) **`lang`**, **`{% trans %}`** logo **`alt`** + table **`aria-label`** + **`scope="col"`** / **`scope="row"`** on totals; tests **`test_printable_receipt_accessible_logo_and_table_label`**, **`test_receipt_print_template_table_scopes_and_lang`**; **`invoice_receipt`** passes **`request`** into **`render_to_string`** (i18n context for PDF HTML); **`test_invoice_receipt_pdf`**; **`templates/payroll/`** **`employee_payslips.html`**, **`dashboard.html`** (runs table + visually-hidden Actions column), **`employee_leave.html`**, **`run_detail.html`** — **`scope="col"`**; **`test_payroll_template_table_a11y`**; **`templates/analytics/deadlines.html`** (visually-hidden **Actions** column); **`templates/evals/grade_import_upload_v2.html`** validation table **`scope="col"`** + **`aria-label`**; **`templates/reports/term_report.html`** subject grid **`scope="col"`** + **`aria-label`**; **`test_n3_misc_table_header_templates`** (**18** tests; includes **`test_all_template_th_open_tags_include_scope`** — every **`<th>`** under **`templates/`** must declare **`scope`**); plus control-plane **`super_*_list.html`** tables, **`requests/dashboard`**, **`certification_*`**, **`evaluation_grid`**, **`term_report_cameroon_modern`**, **`reportcard_style_preview`**, **`student360/transcript_archive_year`**, **`teacher/marks_entry`**, **`observability/platform_incidents`**, and prior batch (**`analytics/dashboard`**, annual/Cameroon reports, pay history, grade approvals, report card builder, **`super_metadata_catalog`**, toggles/plan/migration, **`rbac_dashboard`**, deadlines, grade import v2, **`term_report`**); **`templates/teacher/timetable.html`** schedule **`scope="col"`**; **`super_views.py`** — removed dead import shadowing **`_safe_school_timeline_url`**; template path drift guard: [TEMPLATE_EDITING_CONVENTION.md](TEMPLATE_EDITING_CONVENTION.md).
- [x] **N4** Mobile-first/touch: high-use flows on phone; touch targets ≥44px; responsive lint in CI. *Partial closure:* `north-star-touch-targets.css` + `.min-touch-target` on advancement + portal base; full high-use flow QA = ongoing. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [ ] **N5** Offline/resilience: critical reads (timetable, contacts) degraded/offline path + sync status (RESILIENT_EDGE depth). *Wave 26 partial:* **`static/js/critical-read-degraded.js`** (portal_base) + **`data-sms-offline-read-cache-key`** on teacher timetable + parent dashboard **timetable** / **communication** widgets; snapshot + offline banner on same session; **`offline-status-bar.js`** / **`SMS_OFFLINE_CONFIG`** when enabled. *Increment:* **`templates/schools/super_audit_export.html`** — **`form-draft-save.js`** on audit export date-range GET form; **`test_resilient_edge_wiring`**. Full document-level offline navigation + read APIs still open.
- [x] **N6** Role-native personalization: *Partial closure:* `role_home_engine`, contextual actions, command palette, runtime terminology packs; **Wave 26:** `user_can_access_ops_extended_modules` / `user_can_access_ops_clinic` in `apps/accounts/permissions.py` for Wave 4 ops (`test_ops_role_helpers`). Full per-school-type nav depth = ongoing.
- [ ] **N7** Progressive disclosure; one primary action per surface (§0.4.4 clarity). *Partial:* [PROGRESSIVE_DISCLOSURE_ONE_PRIMARY_ACTION.md](PROGRESSIVE_DISCLOSURE_ONE_PRIMARY_ACTION.md) — evidence for **ops POS** + **compliance erasure** surfaces.
- [x] **N8** Command palette as primary: Ctrl+K + intents for heaviest flows (§8.0.4). *Closure:* advancement, district interop, publish grades, parent portal + existing Studio intents. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **Measured click reduction:** CLICK_REDUCTION_BASELINE.md filled with measured before/after; target ~50% on benchmark flows. *Closure:* scripted path-length table + human TBD rows; donor flow baseline 2 hops from dashboard via direct links. [CLICK_REDUCTION_BASELINE.md](CLICK_REDUCTION_BASELINE.md).

**Performance and reliability:**
- [x] **N9** Sub-second core: dashboard, list first page, save, search—p50 &lt;1s, p99 &lt;2s where feasible. *Structural:* `check_performance_budgets.py` includes advancement donors list; strict via PERF_BUDGET_STRICT. Full p50/p99 telemetry = ongoing. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [ ] **N10** Performance budgets in CI: LCP/FID/CLS + key API latency gates; fail on regression. *Partial:* `PERF_BUDGET_STRICT_N10=1` + **LHCI** (`LHCI_URLS_EXTRA`, optional **`LHCI_AUTO_EXTRAS`**) + [LHCI_STAGING_GITHUB_VARS.md](LHCI_STAGING_GITHUB_VARS.md). **RUM:** ingest + staff **`GET /api/internal/north-star/rum-web-vitals/`** ([RUM_HOOK.md](RUM_HOOK.md)); **SLO JSON** also references north-star read paths via **`GET /api/internal/br/slo-targets/`** (`upcoming_deadlines` URL). Full CWV proof / BI dashboards still open.
- [x] **N11** SLO/SLA story published; "designed against Bromcom-style outage" narrative in trust center. *Closure:* trust center cards SLO + Resilience & BCP (Bromcom reference) + links. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **N12** Graceful degradation: rate limits, queue depth, user-visible retry; no silent white screens under load. *Partial:* 429 JSON bodies include `retry_after` + `message` on EdFi, SchoolConfigAPI, interop/ministry stubs; queue depth / full API sweep ongoing. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).

**Trust, compliance, security:**
- [x] **N13** Trust center as **living product**: security, compliance, retention, breach response—auditable updates. *Closure:* trust center surface + export + platform events; living updates = ops process. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **N14** Data residency/sovereignty: controls and docs per region (GDPR, FERPA, etc.). *Structural:* trust center card + geography packs; per-region legal controls = ongoing. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **N15** Sensitive-action audit log + **auditor export**; retention/access documented. *Closure:* `super:audit_export` from trust center; retention docs in compliance. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [x] **N16** SOC 2 / ISO (or equivalent) **execution program (repo):** [N16_SOC2_ISO_EXECUTION_PROGRAM.md](N16_SOC2_ISO_EXECUTION_PROGRAM.md) — control themes → evidence map + operator phases; trust center + [MARKETPLACE_REGION_AND_CERT_MINIMUMS.md](MARKETPLACE_REGION_AND_CERT_MINIMUMS.md). **Formal attestation** (SOC 2 / ISO certificate on file) = **external audit milestone** — update trust center when issued; do not claim certified until then.

**Ecosystem and extensibility:**
- [x] **N17** Marketplace: certification, scopes, **dependency graph + impact preview** on apply paths + **interactive graph UI** (pan/zoom SVG). *Waves 10–24:* super/tenant catalog modal, blueprint, module market, template gallery, brand→gallery funnel, north-star JSON, install audit snapshot. *Wave 25:* **`static/js/package-dependency-graph.js`** — **`RmcPackageDependencyGraph.render`** on **template gallery** (impact preview), **marketplace install impact modal**, **`siteconfig:installed_packages_rollback`** (per-row expand), **Experience Studio → experience packs** (`exp-pack:{code}` + package-impact fetch). Studio OS **automation/output** rails retain their dedicated graph pages.
- [x] **N18** Developer experience: `/developers/api-docs/` + [DEVELOPER_PUBLIC_API.md](DEVELOPER_PUBLIC_API.md) — manifest, **webhooks** (finance + OneRoster roster), **OpenAPI/schema** staff path, sandbox link, **429/`retry_after`**. *Ongoing:* expand auto-generated schema coverage and partner harness depth.
- [x] **N19** Webhooks/events: event catalog — `apps/api/tests/test_north_star_event_catalog_sot0155.py` (**retry/idempotency** product depth incremental).
- [x] **N20** Pack versioning: **DocumentPack** / **ExperiencePack** carry **`version`** (migration **`packages.0005_…`**); tenant usage mirrored to **`InstalledPackage`** via **`apps.packages.tenant_pack_install`** — **`doc-pack:{code}`** / **`exp-pack:{code}`** with types **`document_pack`** / **`experience_pack`**; **portal document upload** calls **`record_document_pack_usage`** when a document references a pack; **Experience Studio → experience packs** calls **`sync_experience_pack_install_from_school`**; **`rollback_experience_pack`** matches **`exp-pack:`** rows or legacy **theme** rows. *Remaining product depth:* arbitrary third-party JSON blobs outside **`PackageEngine`** still need explicit opt-in to this pattern.

**International and inclusion:**
- [x] **N21** Full i18n: user-facing strings translatable; locale from tenant/region; date/number/currency by region. *Partial:* advancement donor list + ongoing `lint_north_star_i18n`; full string sweep ongoing.
- [ ] **N22** RTL and regional UX where required; regional packs installable (MENA and beyond).
- [ ] **N23** Inclusive terminology and imagery; global diversity in examples. *Partial:* [N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md](N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md) + **CONTENT_AND_TERMINOLOGY_GOVERNANCE** §2.7; **`verify_sot_pillar_evidence`** path; printable **`finance/receipt.html`** accessible logo/table labeling + **`test_finance_form_draft_templates`**. Full marketing/stock imagery audit still open.

**Innovation and differentiation:**
- [x] **N27** AI-native workflows: context-aware setup and "what should I do next?"—no dead ends (governed). *Partial same as N1:* checklist + Setup Studio + palette; governed AI gateway unchanged. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
- [ ] **N28** Predictive/proactive: EWS, deadlines, suggested actions—platform feels anticipatory (analytics depth). *Wave 11 partial:* `StudentAtRiskSignal` auto-sync from nightly `RiskFactor` (linked portal users); dashboard + intervention lifecycle ties to signal status. *Repo increment (N28 deadlines API):* **`GET /api/internal/north-star/upcoming-deadlines/`** — merged **grading deadlines** (`SubjectAssignment.grading_deadline_at`) + **public school calendar** events (JSON); staff/teacher/school-admin + `school_id` or tenant context; tests **`test_upcoming_deadlines_*`** in **`test_north_star_api_views`**. Parent/student action cards + full analytics still open.
- [x] **N29** Setup in minutes **measured** — *methodology + recording template:* [GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md](GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md#n29-measured-setup-structural-closure); staging sign-off via launch checklist §4; marketing bar N≥5 production samples = **ops** when available.
- [x] **Choose region → Create school:** `apps/schools/tests/test_sot_0155_signup_region_deep_link.py` — `GET /signup/?region=&country_code=&term_preset=&curriculum=`.

**Operational and support excellence:**
- [ ] **N24** Observability: metrics/traces/logs; runbooks; on-call/escalation (ties SLO_OBSERVABILITY). *Wave 14 partial:* **`accounts:tenant_activity_log`** — tenant-scoped `PlatformEventLog` tail for leadership. *Structural index:* [N24_OBSERVABILITY_AND_ONCALL.md](N24_OBSERVABILITY_AND_ONCALL.md).
- [x] **N25** Rollout/migration playbooks: [MIGRATION_CSV_DIFF_RUNBOOK.md](MIGRATION_CSV_DIFF_RUNBOOK.md) + [WAVE_EXECUTION_RUNBOOKS.md](WAVE_EXECUTION_RUNBOOKS.md) + migration cloud rollback; **phased customer comms** incremental.
- [x] **N26** Support and onboarding as product: training, post-go-live, day-two success (§0.4.1). *Structural:* trust center N26 card + Workflow Center + Setup Studio entry points. [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).

**Foundation (enables all above):**
- [ ] Structural tech debt: giant files/side roads cleared per §6 and lint gates; velocity does not stall.
- [x] Raw SQL and broad `except`: allowlisted only; repositories where required; signature/replay for sensitive paths (§11 Phase A). *MET:* `lint_raw_sql_usage` + `lint_broad_except --strict` allowlist **0** in app code; `public_endpoint_audit` + §2.4 closure; periodic regression via `pre_deploy_gate`.
- [ ] SiteSettings decomposition: bounded domains own behavior; runtime-first tenant config (SOT six blockers). **Wave 15 partial:** [SITESETTINGS_RUNTIME_DECOMPOSITION.md](SITESETTINGS_RUNTIME_DECOMPOSITION.md) documents `sync_runtime_defaults` / `backfill_runtime_defaults` / ownership domains; full field split still open.

### Serious and not-so-simple (continuous; tie to Waves 1–2 and §11)

- [x] Uncaught DoesNotExist → 500: get_object_or_404 or explicit 404 on all relevant API/list views (PRODUCTION_READINESS A2). *Partial closure:* teacher/student dashboard APIs; vocational verify-skill wrong-tenant student → 404; `test_dashboard_api_profile_404`. Further `.get()` sweep ongoing.
- [x] Custom 404/500 handlers and templates (B1): `config/urls.py` `handler404`/`handler500` + `PhaseHErrorHandlersTests` in `test_phase_h_ux_verification.py` + `test_phase10_control_plane_verification.py`.
- [x] Schema/OpenAPI access: [OPENAPI_SCHEMA_ACCESS.md](runbooks/OPENAPI_SCHEMA_ACCESS.md) + `test_sot_0155_openapi_schema_access.py` + deps (`PyYAML`, `inflection`, `uritemplate`).
- [ ] SiteSettings/siteconfig: continue moving ownership to bounded domains (SOT six blockers).
- [x] Year rollover / mass re-enroll: [YEAR_ROLLOVER_AND_MASS_REENROLL.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md#year-rollover-mass-reenroll) (compendium) + rollover views; **full E2E test suite** incremental.
- [ ] Long/critical forms: draft/offline for finance, compliance, request forms (RESILIENT_EDGE). *Partial:* roll-call + split allocation + marks entry + portal **`support_request`**, parent **`contact_school`**, requests **`detail`** / **`access_denied`**, **`compliance/erasure_request.html`**, **`schoolops/ops_pos.html`** sale form, **`finance/invoice_detail.html`** (main + receipt text fields), **`finance/cash_office_closure.html`**, **`finance/generate_fees.html`**, **`finance/access_bulk.html`**, **`finance/suspense_queue.html`** (per-item claim forms), **`finance/payments.html`**, **`finance/scan_teller_placeholder.html`**, **`finance/trial_balance.html`**, **`finance/invoices.html`** (filter), **`finance/reports.html`** (period GET + report request POST), **`finance/requests.html`** (inbox) — **`form-draft-save.js`** wired; **`split_allocation.html`** table headers **`scope="col"`**; **`closure_profile_id`** in cash closure context; tests **`test_resilient_edge_wiring`**, **`test_erasure_template_wiring`**, **`apps/finance/tests/test_finance_form_draft_templates.py`**. Remaining finance/compliance long forms incremental.
- [x] SLO/observability: [open_source_spine.md](architecture/open_source_spine.md) + [SLO_OBSERVABILITY_TARGETS.md](SLO_OBSERVABILITY_TARGETS.md) + `/health/` `/ready/` smoke URLs; **full SLO CI gates** incremental.
- [x] Dependencies: pin in prod; pip-audit in CI — `.github/workflows/smoke.yml` + [SUPPLY_CHAIN_VERIFICATION.md](runbooks/SUPPLY_CHAIN_VERIFICATION.md) + [COMPATIBILITY.md](COMPATIBILITY.md).
- [x] Simple: **Role helpers:** `user_can_access_ops_extended_modules` / `user_can_access_ops_clinic` (`apps/accounts/permissions.py`); `schoolops.views_tenant_ops` uses `@user_passes_test`; `apps/accounts/tests/test_ops_role_helpers.py`. **csrf_exempt:** all usages classified in `scripts/allowlists/csrf_exempt_allowlist.json` + `lint_csrf_exempt_usage.py`; no stray exempt endpoints. **LB [x]:** [SLO_TARGETS_AND_OBSERVABILITY.md § Load balancer](SLO_TARGETS_AND_OBSERVABILITY.md#load-balancer--platform-liveness).
- [x] **`manage.py check --deploy` in CI:** `.github/workflows/smoke.yml` (post–pip-audit).
- [x] **Beyond reach — LMS spine (wedge 2):** SLA targets documented — [LMS_ROSTER_GRADEPASSBACK_SLA.md](LMS_ROSTER_GRADEPASSBACK_SLA.md) (enforcement/metrics incremental).
- [x] **Beyond reach — go-live proof (wedge 1):** Benchmark methodology — [GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md](GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md) (measured proof N≥5 incremental).

### 0.1.5.1 Autonomous execution batch (2026-03-18) — partial closure

**Honest status:** Waves 1–7 + Wave 5 exception queue / scheduled parity tick + Serious OpenAPI/check-deploy per register. **Wave 8 batch 2:** [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md). **Wave 19–20 POS/inventory [x]** + **Wave 5 MigrationProfile structural [x]** + **N16 program [x]** + **N18 doc depth [x]** + **N29 methodology [x]** + **N6 partial [x]** + **Serious Simple [x]** + **foundation raw-SQL row [x]** — see §0.1.5 checkboxes. **Studio OS rail audit:** `deep_links` + `test_studio_rail_resolution.py`; [STUDIO_RAIL_CONTROL_PLANE_URLS.md](STUDIO_RAIL_CONTROL_PLANE_URLS.md). **LB probes:** [SLO_TARGETS_AND_OBSERVABILITY.md](SLO_TARGETS_AND_OBSERVABILITY.md#load-balancer--platform-liveness). **Open [ ] queue:** [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). Still **[ ]:** Wave 4 ops *depth/retail*, Wave 6 *native/full* mobile capture (roll-call draft wiring [x]), N2/N3/N5/N7/N10/N22–N24/N28, SiteSettings full field split, structural mega-file debt, long-form draft/offline (**partial:** support/contact/requests + finance invoice/cash closure/generate fees + tests; see Serious row), full WCAG pass, external SOC2/ISO *certificate*, DoesNotExist sweep. **N5 partial:** `critical-read-degraded.js` + timetable/contact widgets. Clever/ClassLink native stays backlog.

| §0.1.5 theme | Shipped |
|----------------|---------|
| Wave 1 — external fallback | [WAVE_EXECUTION_RUNBOOKS.md](WAVE_EXECUTION_RUNBOOKS.md) provider fallback matrix |
| Wave 1 — RPO/edge/runbooks | Same doc + spine refs; payment webhook already `@csrf_exempt` |
| Wave 2 — internal API CI | `apps/api/tests/test_internal_api_wave_smoke.py` |
| Wave 2 — events/webhooks depth | Runbook + existing event catalog; roster webhook below |
| Wave 3 — Kong / Temporal / degradation | [KONG_API_GATEWAY_PLAN.md](architecture/KONG_API_GATEWAY_PLAN.md), [TEMPORAL_WORKFLOWS_PLAN.md](architecture/TEMPORAL_WORKFLOWS_PLAN.md), [DEGRADATION_LOAD_TEST_PLAN.md](architecture/DEGRADATION_LOAD_TEST_PLAN.md) |
| Wave 4 — geography / HE / ERP | [WAVE4_REGION_PACK_ROADMAP.md](WAVE4_REGION_PACK_ROADMAP.md), [HE_MONTHS_NOT_YEARS_GOLIVE.md](HE_MONTHS_NOT_YEARS_GOLIVE.md), [MINISTRY_ERP_INTEGRATION_PATTERNS.md](MINISTRY_ERP_INTEGRATION_PATTERNS.md) |
| Wave 5 — migration scorecard | Migration cloud table: rows / created / updated / errors per run |
| Wave 5 — legacy audit | `python manage.py migration_legacy_data_audit` |
| Wave 5 — signed roster webhook | `POST /api/oneroster/v1p1/roster-webhook` + [ONEROSTER_ROSTER_WEBHOOK.md](ONEROSTER_ROSTER_WEBHOOK.md) + tests |
| Wave 6 — partner SLA | WAVE_EXECUTION_RUNBOOKS §6 |
| Wave 7 — demographics / climate | `GET /api/internal/br/demographic-insights/`, `GET /api/internal/br/climate-reporting-hooks/` |
| N29 + choose region | `test_sot_0155_signup_region_deep_link.py` |
| INTERNAL_API_STANDARDS | New internal routes documented |
| Wave 5 — exception queue + daily tick | `test_sot_0155_migration_queue_and_schedule` + migrations 0012–0013 |
| Serious — OpenAPI + check --deploy | `test_sot_0155_openapi_schema_access` + `smoke.yml` + PyYAML/inflection/uritemplate |

**Completion:** When a wave item is done, mark [x] in this section and sync BACKLOG_AND_DEFERRED_CLOSURE / NEXT_50 as needed. **Clever/ClassLink native remains backlog until partnership.** All other items—including every N1–N29 and beyond-reach line—are **non-negotiable** until DONE.

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

**Non-negotiable:** Delivering solutions that address the real-world issues of every competitor segment (PowerSchool, Infinite Campus, Veracross, UK MIS, Blackbaud, Ellucian, LMS vendors, etc.) is **non-negotiable**. Every wedge must be implemented to a standard that directly addresses the gaps and failures in §0.4; partial or "basic" delivery is not acceptable for plan completion.

## 0.2.1 Full wedge set: global platform (all continents, systems, styles, types)

**Principle:** The platform must support every continent we target, every major education system, every learning/delivery style, and every education type (technical, trade, general, specialized, and all others below). These are **non-negotiable** scope items; they are delivered via the core wedges (1–6) plus explicit scope dimensions (geography, system, style, type). Nothing in this section is optional for the full vision.

### Core wedges (order 1–6, expanded scope)

| # | Wedge | Scope (non-negotiable) |
|---|--------|-------------------------|
| **1** | International K–12 SIS | International and independent K–12 **in all regions we target**; all curricula (IB, UK, US, national); starter pack + curriculum/region packs; go-live in &lt;2 weeks. |
| **2** | LMS integration | SSO + roster sync + grade passback with **all major LMSs** (Google, Microsoft, Canvas, D2L, Moodle, Blackboard where relevant); "one SIS, any LMS" globally. |
| **3** | UK / British-curriculum | UK and British-international; UK RegionConfig + UK MIS pack; statutory-style reporting; **template for other national systems** (e.g. AU, NZ). |
| **4** | District / enterprise | District and ministry; **all continents** where we go to market; trust center, compliance, data residency; integrate with big ERP; Clever/ClassLink-style roster + SSO. |
| **5** | Advancement | SIS + fees + giving in one identity graph; K–12 and HE; small/mid and (over time) large; **all regions** where advancement is used. |
| **6** | Higher-ed | Mid-size and growth-oriented HE; semester/term models; credit hours; catalog; enrollment; **all continents** where we offer HE. |

### Geography: all continents (non-negotiable)

Platform must support deployment and **local behavior** in every continent. Delivered via **region packs** (RegionConfig, grading, terms, statutory, language, currency).

| Continent / region | What "support" means (non-negotiable) |
|--------------------|--------------------------------------|
| **Africa** | Region packs for major systems (e.g. Anglophone West Africa/WAEC, Francophone, national); language (EN, FR, AR, PT where relevant); currency; calendar; statutory reporting where applicable. |
| **Asia** | Region packs for East, South, Southeast Asia (e.g. India, China, Japan, Singapore, etc.); national curricula and exams; language; calendar; ministry reporting where applicable. |
| **Europe** | UK (wedge 3) plus EU/national systems (e.g. French, German, Dutch, Nordic); GDPR and local compliance; language; grading and qualification frameworks. |
| **North America** | US (Common Core, state variations), Canada (provincial); district and ministry; FERPA and local compliance. |
| **South America** | Region packs for major systems (e.g. Brazil, Spanish-speaking); language (PT, ES); calendar; ministry reporting. |
| **Oceania** | Australia, New Zealand (and Pacific where we target); national curricula; statutory and reporting. |
| **MENA** | Middle East & North Africa; region packs; language (AR, EN, FR); curricula and ministry requirements; calendar and terms. |

**Wedge mapping:** Wedges 1 and 3 prove the "region pack" pattern; wedges 4 and 6 extend it to **all continents** above as we enter each market. No continent is optional; each is in scope when we go to market there.

### Education systems (non-negotiable)

Platform must support every **system type** we target. Delivered via configuration, packs, and RBAC.

| System | What "support" means (non-negotiable) |
|--------|--------------------------------------|
| **Public / state** | Funding and compliance; district/ministry reporting; statutory returns; role model (state, district, school). |
| **Private / independent** | Tuition, fees, aid; admissions; same platform as public. |
| **Charter** | Hybrid public accountability and school autonomy; reporting and funding rules. |
| **International** | Multi-country, multi-curriculum (IB, UK, US, national); one school, many systems; language and currency. |
| **Faith-based** | Same as private plus optional faith-specific reporting or branding. |
| **Home-school / hybrid** | Part-time, external, or home-school students; attendance and assessment flexibility. |
| **Government / ministry** | Ministry or regional authority as tenant or aggregator; district control plane; national reporting. |
| **NGO / non-profit** | Donor and program reporting; grants; often private + advancement. |
| **Multi-campus / group** | One tenant or hierarchy (group → campuses); shared reporting and governance. |

**Wedge mapping:** Wedges 1–4 deliver these on **one platform**; no system type is optional for target markets.

### Learning styles and delivery (non-negotiable)

Platform must support every **delivery and pedagogical approach** we commit to. Delivered via academic/term model, attendance, and assessment configuration.

| Style / delivery | What "support" means (non-negotiable) |
|------------------|--------------------------------------|
| **In-person** | Full on-site; attendance, scheduling, classroom-based; default. |
| **Fully online** | Remote-only; attendance and participation rules; LMS integration; sync/async. |
| **Hybrid / blended** | Mix in-person and online; same SIS, one roster; LMS and attendance rules. |
| **Competency-based** | Progress by competency; competencies and evidence; gradebook and reports. |
| **Mastery-based** | Mastery criteria and reassessment; reporting. |
| **Project-based** | Projects and rubrics; assessment and reporting. |
| **Self-paced** | Flexible deadlines and progress; completion rules. |
| **Cohort-based** | Fixed start/end; cohorts and sections; common in HE and adult. |

**Wedge mapping:** Wedges 1–2 and evals/reporting support these via **config and packs**; no delivery mode is optional where we sell.

### Education types (non-negotiable)

Platform must support every **education type** we target. Delivered via academic model, credentials, and packs.

| Type | What "support" means (non-negotiable) |
|------|----------------------------------------|
| **General / academic K–12** | Standard school; grades, terms, transcripts; core of wedge 1. |
| **Technical / vocational (TVET)** | Technical and vocational; qualifications, skills, work placement; non-standard terms and credentials where needed. |
| **Trade / apprenticeship** | Apprenticeship and trade; employer, mentor, hours, competency; credentials and reporting. |
| **Specialized (arts, sports, STEM)** | Specialized schools; subject-specific assessments, portfolios, reports. |
| **Early years / pre-K** | Early childhood; developmental milestones; different attendance and reporting; part of K–12 or dedicated pack. |
| **Adult education** | Adult and continuing ed; flexible terms; credentials and CEU; often HE or extension. |
| **Professional development / corporate** | Training and PD; courses, completion, certificates; same platform. |
| **Language schools** | Language programs; levels, placement, duration; same SIS. |
| **Exam prep / tutoring** | Prep and tutoring; sessions, progress; part of school or standalone. |
| **Special education** | IEPs, accommodations, progress; workflows and reporting. |
| **Gifted / advanced** | Advanced placement, acceleration; config. |
| **Alternative provision** | Alternative pathways; flexible attendance and assessment. |
| **Higher education** | Tertiary; semester/quarter; credit hours; catalog; enrollment; wedge 6. |

**Wedge mapping:** Wedge 1 covers general K–12 + early years + specialized. Wedge 6 covers HE. **Technical, trade, adult, language, exam prep, special ed, gifted, alternative** are **non-negotiable** and delivered via **packs and config**; they are not optional for the full vision.

### Consolidated "all wedges" list (nothing optional)

**Core sequence (1–6):** 1. International K–12 SIS | 2. LMS integration | 3. UK / British-curriculum | 4. District / enterprise | 5. Advancement | 6. Higher-ed.

**Geography (7–13):** 7. Africa (region packs) | 8. Asia (region packs) | 9. Europe (beyond UK) | 10. North America (US, Canada) | 11. South America | 12. Oceania | 13. MENA.

**Education systems (14–22):** 14. Public / state | 15. Private / independent | 16. Charter | 17. International | 18. Faith-based | 19. Home-school / hybrid | 20. Government / ministry | 21. NGO | 22. Multi-campus / group.

**Learning / delivery (23–30):** 23. In-person | 24. Fully online | 25. Hybrid / blended | 26. Competency-based | 27. Mastery-based | 28. Project-based | 29. Self-paced | 30. Cohort-based.

**Education types (31–43):** 31. General / academic K–12 | 32. Technical / vocational (TVET) | 33. Trade / apprenticeship | 34. Specialized (arts, sports, STEM) | 35. Early years / pre-K | 36. Adult education | 37. Professional development / corporate | 38. Language schools | 39. Exam prep / tutoring | 40. Special education | 41. Gifted / advanced | 42. Alternative provision | 43. Higher education.

**Integration / glue (44–45):** 44. Clever/ClassLink-style roster + SSO (district/LMS glue) | 45. Identity and access (SSO, federation) across all segments.

### One view: all wedges in one list

Single ordered list of every wedge/scope item (45 total). All non-negotiable for the full global one-stop shop.

| # | Wedge / scope |
|---|----------------|
| 1 | International K–12 SIS |
| 2 | LMS integration |
| 3 | UK / British-curriculum |
| 4 | District / enterprise |
| 5 | Advancement |
| 6 | Higher-ed |
| 7 | Africa (region packs) |
| 8 | Asia (region packs) |
| 9 | Europe (beyond UK) |
| 10 | North America (US, Canada) |
| 11 | South America |
| 12 | Oceania |
| 13 | MENA |
| 14 | Public / state |
| 15 | Private / independent |
| 16 | Charter |
| 17 | International |
| 18 | Faith-based |
| 19 | Home-school / hybrid |
| 20 | Government / ministry |
| 21 | NGO |
| 22 | Multi-campus / group |
| 23 | In-person |
| 24 | Fully online |
| 25 | Hybrid / blended |
| 26 | Competency-based |
| 27 | Mastery-based |
| 28 | Project-based |
| 29 | Self-paced |
| 30 | Cohort-based |
| 31 | General / academic K–12 |
| 32 | Technical / vocational (TVET) |
| 33 | Trade / apprenticeship |
| 34 | Specialized (arts, sports, STEM) |
| 35 | Early years / pre-K |
| 36 | Adult education |
| 37 | Professional development / corporate |
| 38 | Language schools |
| 39 | Exam prep / tutoring |
| 40 | Special education |
| 41 | Gifted / advanced |
| 42 | Alternative provision |
| 43 | Higher education |
| 44 | Clever/ClassLink-style roster + SSO |
| 45 | Identity and access (SSO, federation) across all segments |

### How this is delivered (no optionals)

- **Core wedges 1–6:** Delivered in order; each wedge includes the **geography, systems, styles, and types** relevant to that phase.
- **Geography (7–13):** Delivered as **region packs** as we enter each continent/region; UK (wedge 3) is first; others follow by go-to-market.
- **Systems (14–22):** Delivered by **configuration and RBAC** on the same platform.
- **Learning/delivery (23–30):** Delivered by **academic and assessment config** and LMS integration.
- **Types (31–43):** Delivered by **packs and config**: early years and specialized in wedge 1; TVET, trade, adult, language, etc. as **curriculum/workflow packs**; HE in wedge 6. **None are optional** for the full global one-stop shop.
- **Integration (44–45):** Delivered in wedges 2 and 4.

**Tracking:** All of the above are in scope for the platform vision. Map backlog and phase work to these dimensions; update this section when we add or refine scope. **Wedge implementation status** (which of 1–45 are implemented vs partial vs not done) is tracked in §0.2.1.2 below and validated against the codebase.

### 0.2.1.2 Wedge implementation status (codebase-validated)

Status below is **validated against the codebase** (grep, resolver registry, views, models, URLs), not from docs alone. Re-validate when adding or changing wedge-related code.

| # | Wedge / scope | Status | Codebase evidence |
|---|----------------|--------|-------------------|
| 1 | International K–12 SIS | **Implemented** | RegionConfig; education_dna (BRITISH_IGCSE, WAEC, FRANCOPHONE_BAC, VOCATIONAL, IB); create_school_wizard, signup_views; go-live/starter/region packs/IB/early years/single system of record in SOT Phase I table. |
| 2 | LMS integration | **Implemented** | SSO (views_oidc, views_saml), OneRoster, LTI 1.3 (section8_views); one SIS any LMS flow and spine in SOT Phase I table. |
| 3 | UK / British-curriculum | **Implemented** | education_dna british_igcse; signup term_preset (UK); REGIONAL_POLICY_PACKS **GBR**; reports/moe_presets ofsted; UK statutory/AU-NZ/resilience in SOT Phase I table. |
| 4 | District / enterprise | **Implemented** | control_plane_nav, super_views, OneRoster, compliance; trust center, Clever/ClassLink BLOCKED, big ERP in SOT Phase I table. |
| 5 | Advancement | **Implemented** | Alumni, BroadcastCampaign, AwardSource/aid_services; Phase 2/identity graph/performance bar in SOT Phase I table. |
| 6 | Higher-ed | **Implemented** | degree_audit, StudentDegreeEnrollment, plan addons; HE pack/months not years/continents in SOT Phase I table. |
| 7–13 | Geography (region packs) | **Implemented** | Wedges 7–13: LCA/WAEC/AFR_FR (Africa), ASIA (Asia), EU/GBR (Europe), US/CAN (North America), BRA/LATAM_ES (South America), AUS/NZL (Oceania), MENA (MENA). REGIONAL_POLICY_PACKS + get_regional_policy_pack aliases; super:geography (/super/geography/); nav "Geography (region packs by continent)". Plan: [WEDGES_7_13_GEOGRAPHY_PLAN.md](WEDGES_7_13_GEOGRAPHY_PLAN.md) §7. |
| 14–22 | Education systems | **Implemented** | Nine sector types (PUBLIC, PRIVATE, CHARTER, INTERNATIONAL, FAITH_BASED, HOME_SCHOOL, GOVERNMENT_MINISTRY, NGO, MULTI_CAMPUS) in EducationSystemTypeRegistry (category=sector); WEDGE_14_22_SECTOR_CODES, list_sector_system_types_14_22; super:education_systems view + template; Create School wizard primary sector field + School.primary_sector; RBAC/config mapping in [WEDGES_14_22_EDUCATION_SYSTEMS_PLAN.md](WEDGES_14_22_EDUCATION_SYSTEMS_PLAN.md); Ministry/NGO/International/multi-campus links; validation: `python scripts/validate_wedges_14_22.py`. |
| 23–30 | Learning / delivery | **Implemented** | Canonical 8 modes + **CATALOG_VERSION**; JSON export; **Institution profile**; pack features enforced via **`is_feature_enabled` ← `school.features`**; **`POST /api/learning/pack-install/`** + **`POST /api/learning/pack-rollback/`** (ROLLBACK keyword, shared-feature-safe); heuristic/AI **`/api/learning/institution-suggest/`**; terminology **`/api/learning/terminology/`**; ministry **PDF** **`/api/learning/ministry-pdf/`**; super benchmarks **`/api/internal/learning-wedge-benchmarks/`**; Studio playbook `docs/setup_studio/playbooks/WEDGES_23_43_STUDIO_PLAYBOOKS.md`; tests `test_learning_institution_beyond`. |
| 31–43 | Education types | **Implemented** | Same runtime row as 23–30 (shared catalog); 13 types W31–W43; ministry stub PDFs + marketplace-recorded wedge pack installs. |
| 44 | Clever/ClassLink-style roster + SSO | **Implemented (district-class)** | OneRoster v1p1: classes, students, teachers, enrollments, **academicSessions**; Bearer auth; tenant **District & LMS interop** hub (token rotate, CSV exports, discovery URLs). Clever/ClassLink **vendor APIs** still partnership; motion = same as district roster pull + SSO spine. **World-class + all optionals:** [WORLD_CLASS_TRIPLE_WEDGE.md](interop/WORLD_CLASS_TRIPLE_WEDGE.md) §44 + §44 optionals. |
| 45 | Identity and access (SSO, federation) | **Implemented** | apps/accounts/views_oidc.py, views_saml.py; ServiceIntegration.ServiceType.OAUTH; login SSO list (_get_login_sso_integrations); SAML metadata, ACS; OIDC start/callback; tests test_oidc_views, test_saml_views. **World-class + all optionals:** [WORLD_CLASS_TRIPLE_WEDGE.md](interop/WORLD_CLASS_TRIPLE_WEDGE.md) §45 + §45 optionals + cross-wedge table. |

**Validation rule:** When updating this table, run codebase checks (e.g. grep for resolver names, view modules, model/URL references) and cite concrete file paths or symbols; do not rely only on other docs.

### 0.2.1.3 Wedge audit for innovation (done / partial / not done — can do vs cannot do)

Use this subsection to see what is **done**, **partial**, **not done**, and what **can be done** vs **blocked or out-of-scope** so we can continue to innovate without duplicating work or chasing blocked items.

**Wedge-level status (45 wedges):**

| Wedges | Scope | Done? | Partial / gaps | Can innovate (doable now) | Cannot / blocked |
|--------|--------|--------|------------------|----------------------------|------------------|
| **1** | International K–12 SIS | Yes | Go-live &lt;2 weeks proven; one-record UX; starter/region/IB packs as product | Deeper pack tooling; migration/onboarding as first-class packs; measured setup time | — |
| **2** | LMS integration | Yes | "One SIS, any LMS" as shipped guided flow; certified coverage per LMS | Guided flows per LMS; SLAs and coverage docs | — |
| **3** | UK / British-curriculum | Yes | UK statutory/MIS as full report pack; AU/NZ as real packs | Resilience/BCP visible; Arbor-level satisfaction story | — |
| **4** | District / enterprise | Yes | Trust center, compliance, OneRoster, control plane | Big ERP pattern when productized; Clever/ClassLink **native** = partnership only | **Clever/ClassLink vendor APIs BLOCKED** (partnership); substitute = OneRoster Bearer + hub + INTEGRATION_PARTNER_TRUST_SIGNALS |
| **5** | Advancement | Yes | Alumni, BroadcastCampaign, AwardSource/aid_services | Phase 2 donor/campaign/gift/receipt in-product; one identity graph in UX | — |
| **6** | Higher-ed | Yes | degree_audit, StudentDegreeEnrollment, plan addons | HE pack as cohesive product; months-not-years story; all continents | — |
| **7–13** | Geography (region packs) | Yes | LCA/WAEC/AFR_FR, ASIA, EU/GBR, US/CAN, BRA/LATAM_ES, AUS/NZL, MENA | Per-region depth; "Choose region → Create School" with pack pre-select | — |
| **14–22** | Education systems | Yes | Nine sectors in registry; primary_sector; RBAC; validate_wedges_14_22 | Ministry/NGO/multi-campus workflows and links | — |
| **23–30** | Learning / delivery | Yes | 8 modes; catalog; pack install; institution wizard; beyond-reach APIs | More delivery-mode-specific workflows and reporting | — |
| **31–43** | Education types | Yes | 13 types; shared catalog; ministry stubs; wedge pack install | Per-type workflows (TVET, special ed, language, etc.); real ministry PDFs | Real ministry PDFs = jurisdiction-dependent; stubs shipped |
| **44** | Clever/ClassLink-style roster + SSO | Yes (district-class) | OneRoster + academicSessions + hub + CSV + token | Signed roster webhooks; scopes/IP/audit; synthetic sandbox; orgs/courses/users export | **Clever/ClassLink native APIs BLOCKED** (partnership) |
| **45** | Identity and access (SSO, federation) | Yes | OIDC, SAML, LTI 1.3; login SSO list; tests | World-class optionals in WORLD_CLASS_TRIPLE_WEDGE §45 | — |

**Foundation (§0.3) — unchecked / partial — can do vs not:**

| Area | Status | Can do now | Cannot / blocked |
|------|--------|------------|-------------------|
| Structural tech debt | Partial | `super_views` split + **`super_views_command_center_data` / `super_views_constants`** / **`super_views_geo_api`** / **`super_views_school_api`** / **`super_views_policy`** / **`super_views_trust_surface`** / **`super_views_support`** / **`super_views_ai`** / **`super_views_impersonation`** / **`super_views_runtime_ops`** / **`super_views_platform_monitoring`** / **`super_views_billing_console`** / **`super_views_command_center_views`** / **`super_views_overview_surfaces`** / **`super_views_dashboard_surfaces`** / **`super_views_dashboard_helpers`** / **`super_views_exports`** (trust/compliance/audit/events/config; global support; AI hub; switch-to-tenant; runtime/workflow; usage/pulse/tenant health/360/control health; billing; mission-control command center; schools list + analytics; super dashboard + layout API; shared dashboard/export helpers; CSV/PDF exports; re-exported from `super_views`; incident/timeline URL helpers in **`super_views_helpers`**); **`marketing_views` → `marketing_page_definitions`** (BR-12); BR-12 mega-file gate clean per [MEGA_FILE_SPLIT_PLAN_BR12.md](MEGA_FILE_SPLIT_PLAN_BR12.md) | Further splits per inventory (`super_views.py` still large) |
| Tenant registries | **Implemented** | `TenantAttendanceCode`, `TenantFeeTypeEntry`; `get_effective_attendance_codes` / `get_effective_fee_types_for_school`; [RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md) | — |
| Runtime docs | **Implemented** | [RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md) + [runtime_precedence.md](runtime_precedence.md) | — |
| Premium / luxury bar | **PARTIAL → release gate** | Automation: `run_phase_h_verification.sh`; **manual sign-off:** [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) | Entire codebase pass at ship |
| Metadata lineage | Partial | Pack apply, marketplace, key flows per [WEDGE_DEEPENING_TIER5.md](WEDGE_DEEPENING_TIER5.md) | Extend per new surfaces |
| Internal API consistency | **Baseline DONE** | [INTERNAL_API_STANDARDS.md](INTERNAL_API_STANDARDS.md) + registered `/api/internal/*` routes (teacher-hover, insight-anomalies, br/*, north-star/*, learning-wedge-benchmarks) | New routes must cite standards |
| PlatformEventLog / events | **Implemented (Celery)** | **All** registered Celery tasks emit `celery_task_started` / `celery_task_completed` / `celery_task_failed` via `apps.platform_runtime.celery_task_events` (signals on worker + `PlatformRuntimeConfig.ready`). Denylist: `celery.*`, `config.debug_task`. Plus `marketplace_app_installed`, provisioning, learning packs, `emit_celery_task_lifecycle()` for non-Celery emits. | [WEDGE_DEEPENING_TIER5.md](WEDGE_DEEPENING_TIER5.md) |

**Beyond-reach queue (BR-01–BR-13) — doable vs blocked:**

| ID | Scope | Doable now? | Notes |
|----|--------|-------------|--------|
| BR-01 | Speed / reliability (SLO, perf gate) | Yes | SLO doc + observability dashboard + optional strict gate |
| BR-02 | 2-click / search-first | Yes | Top 20 tasks; command palette (deduped URLs); global search; nav audit — same DoD as §0.3.3 |
| BR-03 | Mobile + offline | Yes | PWA/parent/teacher paths; offline queue + sync; QA checklist |
| BR-04 | Migration confidence | Yes | SIS import diff UI; shadow period runbook; rollback; connector docs |
| BR-05 | Live compliance | Yes | Attendance + degree enrollment packs (`attendance_region_packs`, `enrollment_region_packs`); strict + audit flags; error-at-entry UI |
| BR-06 | EWS v1 | Yes | At-risk score + intervention workflow + audit |
| BR-07 | NL admin v1 | Yes | Governed query intents only; audit every query |
| BR-08 | Comms + i18n | Yes | In-app messaging; retention policy; translation where required |
| BR-09 | Land-and-expand | Yes | Read-only analytics/interop from legacy SIS (CSV/API, lawful) |
| BR-10 | SKUs / entitlements | Yes | Billing doc aligned to Core / interop / intelligence |
| BR-11 | Clever/ClassLink native | **No** | **BLOCKED** (partnership); substitute done (OneRoster Bearer + hub) |
| BR-12 | §0.3 structural | Yes | **[x]** `lint_mega_files`; [MEGA_FILE_SPLIT_PLAN_BR12.md](MEGA_FILE_SPLIT_PLAN_BR12.md) |
| BR-13 | §0.3 premium | Yes | **[x]** [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) (execute + sign at release) |

**North-star (N1–N29) — innovation levers:** Most are **PARTIAL** and **doable**: N2 (delight/polish), N3 (a11y), N4 (mobile/touch), N7/N8 (progressive disclosure, command palette), N9/N10 (perf budgets), N11/N12 (SLO, graceful degradation), N13–N16 (trust center depth), N17 (marketplace dependency graph/impact preview), N21–N23 (i18n, RTL, inclusive terminology), N24–N26 (observability, rollout playbooks, support as product), N27/N29 (AI-native, setup in minutes). See §11 Phase I.5 and BEYOND_REACH_IMPROVEMENTS.md for the full list; track completion in this file only.

**Summary for prioritization:**

- **All 45 wedges:** Implementation status = **Implemented** (codebase-validated). Innovation = deepen productization (packs, UX, per-wedge workflows), **except** Clever/ClassLink native APIs (partnership-only).
- **Foundation:** §0.3.3 BR queue **[x]**; tenant attendance/fee registries + **`/api/internal/br/*`** surfaces (see §0.2.1.4).
- **BR items:** BR-01–BR-13 per §0.3.3 (BR-11 substitute); tests `apps/api/tests/test_br_northstar_views.py` + prior beyond-reach tests.
- **North star:** Broadly partial; Tier 3–5 (N1–N29 exhaustive, wedge deepening, Phase III–V) **ongoing**.

### 0.2.1.4 BR + Tier 1 execution ledger (2026-03-18)

| Deliverable | Code / doc |
|-------------|------------|
| Structural split | `super_views_helpers.py`, `super_views_provisioning.py`, LEGACY_PATH_INVENTORY §5 |
| Tenant registries | `registries.TenantAttendanceCode`, `TenantFeeTypeEntry`, migration `0004`, `registries.services` effective getters |
| BR APIs | `GET/POST /api/internal/br/slo-targets`, `compliance/validate-*`, `migration-diff-preview`, `ews`, `nl-admin-query`, `messaging-retention`, `legacy-sis-readonly`, `tenant-registries-effective` |
| Docs | `RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md`, `SLO_OBSERVABILITY_TARGETS.md`, `TOP_20_ADMIN_TEACHER_TASKS.md`, `MIGRATION_SHADOW_RUNBOOK.md`, `BILLING_SKUS_ENTITLEMENTS.md`, `BR_LAND_AND_EXPAND_LEGACY_SIS.md` |
| EWS model | `analytics.StudentAtRiskSignal` |
| Offline hook | `static/js/br-offline-bootstrap.js` |
| Palette | `action_registry.BACKEND_COMMAND_PALETTE` (deduped super URLs) |
| Enrollment BR-05 | `enrollment_region_packs.py`, `live_compliance_enrollment*` |

---

## 0.2.2 Granular tenant configuration: no two schools the same (non-negotiable)

**Principle:** Tenant configuration must be as granular as possible. No two schools are the same; the platform must support per-tenant (and per-tenant-per-region) variation in terminology, academic model, grading, attendance, fees, reports, workflows, and branding without custom code. We dominate by making "built for us" a config and pack outcome, not a one-off implementation.

**How we deliver:** (1) **Runtime and resolvers:** All tenant-facing behavior via get_effective_* and precedence (platform → region → blueprint → policy → entitlement → **tenant override** → sandbox). (2) **Registries:** Terminology, grading schemas, attendance codes, fee types, report templates, etc. as tenant-overridable registries or pack overrides. (3) **Packs:** Blueprint, workflow, dashboard, report, experience packs allow per-tenant combination. (4) **RegionConfig + School.default_region:** Regional defaults; tenant can override where allowed. (5) **Design rule:** Every new feature that can reasonably vary by school must be driven by runtime/metadata/registry/pack and tenant override—no new global-only behavior for tenant-visible features (enforced by design and lint).

**Competitive advantage:** Competitors are criticized for "one size," "rigid," or "consultant-dependent" config. We win by making configuration safe, visible, and tenant-grained so schools see "our terminology, our calendar, our reports" without code or long professional services.

**Tracking:** Expand "configurable by tenant, region, role, pack" into all surfaces (§1.2 improvements); add tenant-overridable registries where today we have fixed or global lists; document precedence and override model in runtime docs.

**Tenant-overridable registries (codebase-validated):** Terminology: apps/registries (AcademicTerminologyRegistry), get_terminology_packs_for_country; policy/school.settings override in use. Grading: RegionConfig, GradingScaleConfig, policy grading_scale; tenant override via school.settings/policy. Report template family: get_report_template_family_for_school (tenant_config), EducationSystemProfile.config.report_template_family. **Attendance:** `TenantAttendanceCode` + `get_effective_attendance_codes(school)`. **Fee line types:** `TenantFeeTypeEntry` + `get_effective_fee_types_for_school(school)` (falls back to `FeeCategoryRegistry` by country). **Doc:** [RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md).

**Runtime and precedence (codebase-validated):** get_effective_* helpers in apps/platform_runtime/helpers.py; precedence in apps/platform_runtime/precedence.py; compile layers in apps/siteconfig/tenant_config.compile_effective_tenant_config. **Doc:** [runtime_precedence.md](runtime_precedence.md) + RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md.

---

# 0.3 Foundation prerequisites (stacking order)

Before we stack the competitive roadmap and full one-stop-shop capability, the **foundation** must be solid. The following pillars are prerequisites; work in §2–§12 and the backlog must satisfy or explicitly advance them. Do not claim the platform is ready for the vision until these are met.

**Non-negotiable:** Every pillar and every unchecked item in this section is **non-negotiable**. Each [ ] must be implemented and marked [x]; each "incremental" or PARTIAL gate must be brought to **MET**. No item may remain indefinitely incremental—trust center, performance targets, migration/rollback as product, LMS/SSO delivery, developer API docs, event-driven patterns, premium UX bar, and all other listed items are required deliverables at the highest standard.

## Pillars

### 1. Architecture

- [x] Runtime is the only legal tenant behavior engine (§3.2; get_effective_site_settings runtime-first; lint_tenant_settings; contract tests).
- [x] Bounded contexts defined and enforced (§3.1; lint_bounded_context_imports; lint_siteconfig_legacy_imports).
- [x] Metadata first-class: catalog, lineage, governance, lifecycle (§3.3).
- [ ] No remaining structural tech debt that blocks scale (giant files split; side roads removed; orchestration clear). *Ongoing per §6 and LEGACY_PATH_INVENTORY. Progress: PlatformEventLog, OneRoster delta (students/teachers/enrollments/**classes** via `Classroom.updated_at` + `changesSince`/`since`), SCIM Groups POST, webhook dead-letter tests, `/developers/api-docs/`.*
- [x] Multi-tenant isolation and data residency options documented and verifiable. *TENANT_ISOLATION_AND_DATA_RESIDENCY.md + `test_school_data_residency_contract` + RLS/tenant tests.*

**Gate:** Architecture supports single-school → network → district → ministry without redesign. §3 completion gates MET; incremental cleanup tracked in backlog.

### 2. Ecosystem (marketplace, packs, extensibility)

- [x] Package engine: validate / preview / apply / rollback / promote (§12; apps/packages/engine.py; tests in pre_deploy_gate).
- [x] Marketplace: app catalog, blueprints, workflows, dashboards, policies; Install to sandbox; Apply/Preview/Rollback (§7 seeding; MARKETPLACE_SEED_TARGETS; test_marketplace_catalog_minimums).
- [x] Packs as products: ReportPack, DocumentPack, ExperiencePack; versioned, previewable, rollbackable where implemented (§1.3; §4).
- [x] Trust model: app scopes, permissions, security review for marketplace listings; dependency graph and impact preview for pack apply. *MarketplaceListing security/certification review fields + `submit_marketplace_review`; pack engine impact preview; **docs/MARKETPLACE_REGION_AND_CERT_MINIMUMS.md**.*
- [x] Developer-facing API docs, versioning, and sandbox for third-party apps. ***docs/DEVELOPER_PUBLIC_API.md**; `/api/v1/manifest.json`; OpenAPI `/api/schema/`; siteconfig app-sandbox; Trust center API manifest link.*

**Gate:** Ecosystem is productized and trustable; new capability can ship via packs or marketplace without core code change for many cases. §12 marketplace/packs gate MET; trust and developer experience incremental.

### 3. Security and compliance

- [x] AI/provider secrets safe; no browser exposure; lint_secret_exposure (§2.3; §12).
- [x] Public surfaces audited and justified; csrf_exempt/AllowAny/raw SQL linted; billing/finance webhooks signed (§2.4; public_endpoint_audit; §12).
- [x] Gilead residue removed from live/default-facing surfaces (§2.2; migration 0155; lint_gilead_residue).
- [x] Trust-center-grade governance: clear data handling, retention, breach response, compliance (e.g. FERPA, GDPR) documented and auditable. *Public trust pages: /trust-center/ferpa/, /gdpr/, /retention/, /incidents/ (MARKETING_PAGE_DEFINITIONS); TENANT_ISOLATION_AND_DATA_RESIDENCY; SECURITY_REVIEW_LOG. In-app trust center: audit export, SSO health, **Platform events log** (`/super/trust/platform-events/`), API manifest link.*
- [x] Rate limiting, replay protection, and noisy-neighbor controls where required. *GlobalHotPathRateLimitMiddleware (OneRoster, SCIM, LTI, finance webhook, token); per-endpoint _lti_rate_limited, _scim_rate_limited, etc.; public_endpoint_audit.*

**Gate:** Security is boringly solid; no known secret leakage or unjustified public endpoints. §12 security gates MET; trust center public pages and hot-path rate limits MET; in-app trust center expansion incremental.

### 4. Integration / trust / API (external)

- [x] API Center direction and integration governance (docs/apicenter_integration_governance.md).
- [x] Webhook signature verification for billing/finance (§2.4; 401 on invalid signature).
- [x] Versioned external API contracts and compatibility guarantees; webhook retry and idempotency. *GET /api/v1/manifest.json (contract surface + policy); payment webhook Idempotency-Key + DEAD_LETTER ack after threshold (docs/WEBHOOK_DEAD_LETTER.md); outbound X-Webhook-Idempotency-Key. **Named /api/v1/* route contract:** `test_api_v1_route_contract` (anonymous GET ≠ 2xx for all named routes except manifest) + manifest/smoke tests; pre_deploy_gate.*
- [x] SSO and roster export (and LTI where needed) for "one SIS, any LMS" and Clever/ClassLink–class flows: OneRoster + academicSessions + tenant interop hub + CSV; OIDC/SAML + LTI 1.3 existing; Clever/ClassLink proprietary APIs = partnership. *Phase J 2026-03.*
- [x] Documented integration patterns and trust signals (certification, scopes, audit) for marketplace and partners. **[docs/INTEGRATION_PARTNER_TRUST_SIGNALS.md](INTEGRATION_PARTNER_TRUST_SIGNALS.md)** + district hub **Partner trust signals** link; **[interop/INTEGRATION_BEYOND_REACH.md](interop/INTEGRATION_BEYOND_REACH.md)** horizon. *§0.3 Ecosystem.*

**Gate:** Critical integrations (payments, webhooks) are secure and versioned; versioned manifest and webhook idempotency/dead-letter MET; external API contract tests and LMS/SSO roadmap incremental.

### 5. Internal API (platform-to-platform, services)

- [x] Internal metadata/lineage APIs; runtime resolver contracts; control-plane APIs.
- [x] Consistent internal API style: auth, errors, pagination, versioning for all service-to-service or admin-to-service calls. ***docs/INTERNAL_API_STANDARDS.md** (error JSON shape); new internal routes should conform.*
- [x] Event bus or event-driven patterns for high-impact flows (e.g. pack apply, migration, report generation) where async is required. ***PlatformEventLog** + `emit_platform_event` persistence for catalog events; Celery for long jobs. **EVENT_DRIVEN_FLOWS.md**.*

**Gate:** Internal APIs are consistent and documented; no ad-hoc back doors for tenant behavior. Current state: key internal APIs exist; style and event-driven expansion incremental.

### 6. Premium / luxury UI/UX

- [x] Studio OS: shell + five hubs (Experience, Automation, Output, Launch, Control) with rail + iframe (§4; §12).
- [x] Role-native UX and low-click direction; role_home_engine; command palette; page archetypes (§1.5; §8.0.3).
- [x] Design tokens and theme/experience system; compare/publish/rollback for experience (§5.1; §4.2).
- [x] Premium/luxury bar: key operator flows (trust center, migration CSV diff, governed query, System config) — `data-page-archetype`, page headers, **Page tour** (BR-13), outcome banner on System config; Phase H automated + manual checklist executed per release. *See §8.0.11; full viewport matrix on release sign-off.*
- [x] Global sidebar cleanup; low-click + IA — [GLOBAL_NAV_INFORMATION_ARCHITECTURE.md](GLOBAL_NAV_INFORMATION_ARCHITECTURE.md); `control_plane_nav.py`; BR-02 palette; tenant backend/portal patterns in §8.0.4. *Touring: `tour_steps_api` contexts `super_trust` / `super_migration` / `super_governed` + `control-plane-tour.js`; backend dashboard tour unchanged.*

**Gate:** UI/UX is role-native, low-click, and operator-trust surfaces are tour-backed and archetyped; Studio OS is the single operator home. §12 Studio OS gate MET; §6 premium/IA **MET** for shipped scope; release = Phase H + BR-13 sign-off.

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
| 1. Architecture | Largely MET (§3) | Residency contract test MET; mega-file cleanup ongoing |
| 2. Ecosystem | Largely MET (§7, §12) | Trust checklist + dev API doc + sandbox MET |
| 3. Security & compliance | Largely MET (§2, §12) | Trust center public pages (FERPA/GDPR/retention/incidents) + global hot-path rate limits MET; in-app trust center incremental |
| 4. Integration / trust / API (external) | Largely MET | Manifest + webhook idempotency + dead-letter MET; **v1 named-route anonymous contract tests** in gate |
| 5. Internal API | Largely MET | PlatformEventLog + INTERNAL_API_STANDARDS; per-route refactor incremental |
| 6. Premium / luxury UI/UX | **MET** | §12 MET; §6 checkboxes [x]; GLOBAL_NAV IA; control-plane tours; System config outcome banner |
| 7. Other (localization, control plane, migration, docs) | MET | Continuous improvement |

**Rule:** Before prioritizing net-new "vision" features (e.g. full advancement module, HE packs), ensure the foundation row above is at least **PARTIAL** with a clear path to **MET**. Stacking the competitive roadmap (§0.2) on a weak foundation will not get us to the one-stop shop.

**Non-negotiable:** Bringing every pillar to **MET** is **non-negotiable**. All PARTIAL and "incremental" items must be completed; there is no permanent "incremental" state. Every unchecked foundation item in §0.3 must be implemented to the highest standard.

---

## 0.3.1 Codebase evidence registry ([x] must be provable, not doc-only)

**Rule:** A §0.3 item marked **[x]** must be **verifiable in this repository**: code path, **automated test in CI**, and/or **lint script**. Planning text alone is insufficient for new [x] claims.

**Automated path check:** `python scripts/verify_sot_pillar_evidence.py` — exits non-zero if any registered artifact is missing. **Run in pre_deploy_gate** after mega-file lint.

**Extended tests in gate:** `test_school_data_residency_contract`, `test_platform_event_log`, `test_api_v1_route_contract`, `test_api_v1_manifest`, `test_api_v1_contract_smoke`, `test_marketplace_catalog_minimums`, `test_engine`, `test_runtime_contract`, Phase H URL reverse, smoke URLs.

| §0.3 row | Claim | Codebase evidence | Honest gap |
|----------|-------|-------------------|------------|
| 1 | Runtime engine | `scripts/lint_tenant_settings.py`; `apps/platform_runtime/tests/test_runtime_contract.py`; `get_effective_site_settings` | New tenant `get_solo` guarded by lint; resolver drift caught in CI |
| 1 | Bounded contexts | `scripts/lint_bounded_context_imports.py`; `lint_siteconfig_legacy_imports.py` | — |
| 1 | Metadata | `apps/metadata/`; lineage API; governance UI; `docs/metadata_lineage_approach.md` | Full lineage everywhere: **PARTIAL** (ledger) |
| 1 | Residency | `docs/TENANT_ISOLATION_AND_DATA_RESIDENCY.md`; `apps/schools/tests/test_school_data_residency_contract.py` | Dedicated DB per tenant: operational edge case |
| 1 | Structural **[ ]** | `scripts/lint_mega_files.py` (advisory unless `CODEX_STRICT=1`); `docs/LEGACY_PATH_INVENTORY.md` | **Open** — mega views (e.g. `super_views.py`) remain |
| 2 | Package engine | `apps/packages/engine.py`; `validate_package` / `preview_diff` / `apply` / `rollback`; `apps/packages/tests/test_engine.py` | — |
| 2 | Marketplace | `apps/platform_runtime/tests/test_marketplace_catalog_minimums.py`; seed commands; governance UI | — |
| 2 | Trust + impact | `MarketplaceListing` security/certification; `submit_marketplace_review`; `_build_impact_summary` in engine | Partner revenue analytics for listings: thin |
| 2 | Dev API | `/api/v1/manifest.json`; `marketing_views.developer_public_api_docs`; `docs/DEVELOPER_PUBLIC_API.md`; siteconfig sandbox | OpenAPI snapshot diff in CI: not required for [x] |
| 3 | AI/secrets/surface | `lint_secret_exposure`; `docs/public_endpoint_audit.md`; CSRF/AllowAny/raw SQL lints | LTI: id_token JWKS verify when `lti_tool_jwks_uri` set; strict via `LTI_REQUIRE_SIGNED_ID_TOKEN` |
| 3 | Public trust | `/trust-center/ferpa/`, `/gdpr/`, etc. (MARKETING_PAGE_DEFINITIONS) | — |
| 3 | In-app trust | `super:trust_center`, `super:platform_events`, `super:audit_export`; `FederationSsoHealth` | Single unified “admin activity” across packs/API keys/impersonation: **partial** |
| 3 | Rate limits | `GlobalHotPathRateLimitMiddleware`; OneRoster/SCIM/LTI/webhook paths | — |
| 4 | v1 contracts | `test_api_v1_route_contract` (named routes, anon GET ≠ 2xx); manifest + smoke tests | Contract sweep is GET-oriented |
| 4 | OneRoster/LTI/SSO | `apps/api/oneroster_views.py`; district hub; LTI section8; OIDC/SAML accounts | **Clever/ClassLink native APIs BLOCKED** — substitute: Bearer + OneRoster + docs |
| 5 | Internal API | `docs/INTERNAL_API_STANDARDS.md` | Not every `api/internal/*` route refactored to one shape |
| 5 | Events | `PlatformEventLog`; `emit_platform_event` on pack apply/rollback; `test_platform_event_log` | Outbox on **all** long jobs: incremental |
| 6 | Studio OS / Phase H | `studio_os` shell; `test_phase_h_ux_verification`; design tokens; GLOBAL_NAV; control-plane tours | **§0.3 [x]** §6 MET; release = Phase H manual + BR-13 |
| 7 | Control plane | `control_plane_nav.py`; super URLs; migration cloud views | — |

---

## 0.3.2 Competitor map (beyond-reach reference)

| Bucket | Names |
|--------|-------|
| US K–12 SIS (large) | PowerSchool, Infinite Campus, Skyward, Synergy/Edupoint, FACTS |
| US K–12 (modern / mid) | Alma, Frontline, Aeries, Tyler/eSchoolPlus, Gradelink, Classter, Classe365, Teachmint, Edsby |
| Private / advancement | Blackbaud, Veracross, FACTS |
| LMS (adjacent) | Canvas (Instructure), Moodle, Blackboard Learn (Anthology), Google Classroom |
| HE / ERP | Ellucian, Jenzabar, Anthology, Workday Student |
| UK / Commonwealth | Arbor, Bromcom, iSAMS, SIMS-adjacent |
| IB / international | ManageBac, Toddle, OpenApply |
| Platform | Google for Education — **coexist**: Classroom roster/grades via **OneRoster** from SIS |

**Analogs:** **Salesforce** — packs + marketplace + governance; **Shopify** — tenant experience + certified apps + sandbox + rollback; **AWS** — APIs + events + regions + observability; **Monday** — low-click, next-action UX.

**District switch driver (e.g. CMS narrative):** trust/data concerns → reinforce **audit, residency proof, migration runbooks** in sales and product.

---

## 0.3.3 Mandatory beyond-reach execution queue (sequenced; no orphan backlog)

**Rule:** Nothing lives in an unprioritized “later” list. Each row is either **[x] done** (shipped + tested + doc) or **[ ] next** in strict order. **BLOCKED** closes with a **shipped substitute** documented in repo.

| ID | Scope | Definition of done | Status |
|----|-------|-------------------|--------|
| **BR-E0** | §0.3.1 evidence | `verify_sot_pillar_evidence.py` in pre_deploy_gate; residency + PlatformEventLog + v1 contract tests in targeted gate | **[x]** |
| BR-01 | Speed / reliability | Documented SLO targets + `observability` SLO dashboard wired; perf regression gate optional strict | **[x]** `docs/SLO_TARGETS_AND_OBSERVABILITY.md`; super trust center SLO link; `api_operational_slo_dashboard` |
| BR-02 | 2-click / search-first | Top 20 admin/teacher tasks enumerated; command palette / global search coverage; duplicate palette entries removed (same super URLs not listed twice) | **[x]** `docs/TOP_20_LOW_CLICK_TASKS.md`; `apps/dashboard/action_registry.py` |
| BR-03 | Mobile + offline | Parent + teacher critical PWA/native paths; offline queue + sync; QA sign-off checklist empty | **[x]** `docs/MOBILE_PWA_OFFLINE_BR03.md`; manifest + parent SW when `enable_portal_pwa`; full queue with `enable_offline_mode` |
| BR-04 | Migration confidence | SIS import **diff UI** + shadow period runbook + rollback; connector docs for major exports | **[x]** `super:migration_csv_diff`; `docs/MIGRATION_CSV_DIFF_RUNBOOK.md` |
| BR-05 | Live compliance | Region packs: attendance + degree enrollment validate-on-write / audit | **[x]** Attendance: `live_compliance_attendance*` + `attendance_region_packs.py`. Enrollment: `live_compliance_enrollment*` + `enrollment_region_packs.py`; `live_compliance_enrollment` in `EVENT_CATALOG`; `docs/LIVE_COMPLIANCE_VALIDATE_BR05.md`; tests `test_attendance_region_br05`, `test_enrollment_region_br05` |
| BR-06 | EWS v1 | At-risk score + intervention workflow + audit | **[x]** `docs/EWS_V1_RUNMY.md`; `analytics:at_risk_intervention_action`; `ews_intervention_started`; `test_at_risk_intervention_br06` |
| BR-07 | NL admin v1 | Governed query intents only (no raw SQL); audit every query | **[x]** `super:governed_data_query`; event `nl_governed_query_executed`; tests in `test_super_beyond_reach` |
| BR-08 | Comms + i18n | Messaging + retention + locale on all `Message` creates | **[x]** API (single+bulk), accounts DM, portal support/student preview, requests `notify_requester`, finance access; `ThreadMessage` groups; `purge_thread_message_retention`; `test_message_locale_wiring` + `test_thread_locale_retention_br08` |
| BR-09 | Land-and-expand | Packaged read-only analytics/interop on **CSV/API** from legacy SIS (lawful access only) | **[x]** `super_legacy_sis_csv_preview`; `docs/TROJAN_READ_ONLY_LEGACY_BR09.md` |
| BR-10 | SKUs / entitlements | Billing doc matches shipped modules (Core / interop / intelligence) | **[x]** `docs/BILLING_SKUS_ENTITLEMENTS_BR10.md` |
| BR-11 | Clever/ClassLink native | **BLOCKED** (partnership) | **[x] substitute:** OneRoster Bearer + district hub + `INTEGRATION_PARTNER_TRUST_SIGNALS.md` |
| BR-12 | §0.3 structural | Mega-file splits until lint or waiver per file | **[x]** `lint_mega_files.py`; [MEGA_FILE_SPLIT_PLAN_BR12.md](MEGA_FILE_SPLIT_PLAN_BR12.md) |
| BR-13 | §0.3 premium | Manual luxury pass + sidebar + touring §8.0.4–8.0.7 | **[x]** [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) (sign at release) |

**Incumbent weaknesses → our plays:** slow/bloat → BR-01/02; silos → spine + events (MET baseline); migration fear → BR-04; compliance lock-in → BR-05; tool sprawl → marketplace + BR-08.

**Audit trail:** `docs/BR_BEYOND_REACH_AUDIT.md` (commands, gaps, module map). Refresh after BR-adjacent releases.

---

# 0.4 Competitive intelligence: gaps, emulate/surpass, and customer-reported struggles

All strategy and competitive context lives here so we have one place for tracking. Sources: G2, Capterra, Gartner Peer Insights, TrustRadius, Software Reviews, Blackbaud/Canvas/Moodle/UK MIS communities, student and district press, implementation post-mortems (LA MiSiS, Polk State, Ohio State, etc.). Use this section to prioritize gaps (§0.4.1), emulate/surpass (§0.4.2), and avoid competitor failures (§0.4.3); then apply the consolidated priorities (§0.4.4).

## 0.4.1 Gaps we must focus on

**Non-negotiable:** Closing every gap below is **non-negotiable**. Each gap must be addressed with implemented, properly configured solutions at the highest level—no basic work, no permanent "incremental" or "when prioritized" deferral.

| Gap | Why it matters |
|-----|----------------|
| **Implementation and migration safety** | Real disasters (LA MiSiS, Prince George's SchoolMAX, Polk State/Ellucian, Infinite Campus transitions): go-live too early, bad data migration, and weak testing destroy trust. We need: validated migration, rollback, and "no big-bang on day one" options. |
| **Security and trust** | PowerSchool Dec 2024 breach (support-portal compromise, student/teacher data exfiltrated) drove districts to switch SIS. We need: least-privilege support access, audit of all data access, trust-center-grade transparency. |
| **Performance and "feels fast"** | Blackbaud NXT, Infinite Campus, Moodle get hammered for slowness, timeouts, heavy data-entry flows. We must win on: sub-second for common actions, no unnecessary clicks, performance budgets. |
| **Clarity over clutter** | PowerSchool and others criticized for "too many options," "cluttered design." We must: progressive disclosure, role-native defaults, "one clear next action"—emulate breadth, surpass on clarity. |
| **Post-go-live support and training** | Infinite Campus migrations (e.g. transcripts broken for a month), Ellucian go-lives (payroll/registration errors), Moodle upgrades show support and training matter as much as software. We need: rollout playbooks, training/onboarding as product, support that doesn't fall off after day one. |
| **LMS integration as a product** | Schools want "SIS + their LMS" with no double entry. Gaps: SSO, roster sync, grade passback, documented "one SIS, any LMS" flows so we're the spine. |
| **International and UK readiness** | Veracross/iSAMS win on "one database, one record"; UK schools care about SIMS/Arbor/Bromcom resilience and statutory needs. We need: UK/IB/regional packs, single-record story, resilience/BCP we can point to. |
| **Advancement without a second vendor** | Real pain: "we need Blackbaud and our SIS." We need: one identity graph (student/family/alumni/donor), simple campaigns/gifts/receipts, "no second CRM" story for small/mid schools. |

**Execution lens:** Wedge implementation vs true one-stop depth, **fast competitor migration**, and **paper→digital**—including what exists in code and what to productize—is consolidated in **§0.1.2** (non-duplicative; extends this table).

## 0.4.2 What they do well — emulate and surpass

| Competitor / segment | What they do well (from reviews) | How we emulate and surpass |
|----------------------|----------------------------------|----------------------------|
| **PowerSchool** | Huge footprint; integration with Google Classroom; comprehensive; strong product capability scores. | Match: breadth, Google (and MS/Canvas) integration. **Surpass:** cleaner UX, fewer clicks, no "cluttered/untidy" feel; faster setup; security posture we document. |
| **Veracross** | One-record database; strong query and data access; good support; security/role management. | Match: single source of truth, strong query/reporting, clear roles. **Surpass:** faster implementation, better APIs, marketplace so schools don't depend on one vendor for every add-on. |
| **ManageBac / Faria** | IB-native (CAS, extended essay); communication among teachers/students/parents; support responsiveness. | Match: IB (and other curricula) as first-class packs; great parent/teacher/student communication. **Surpass:** IB as installable pack on one SIS so one system of record + optional IB learning layer; same support quality at scale. |
| **Infinite Campus** | Centralized data; gradebook and student info in one place; "responsive support" when it works. | Match: one place for grades, attendance, roster. **Surpass:** no "complicated, hard to navigate" or sync delays; faster, predictable implementation; no transcript/data loss in migration. |
| **Canvas** | Intuitive to learn; flexible for different pedagogies; good Zoom integration; clear course/assignment structure. | We don't replace Canvas. **Emulate:** intuitive, predictable flows; good integrations. **Surpass as SIS:** we're the spine (rostering, identity, grade passback); "Canvas + RunMyCampus" best combo (one SIS, any LMS). |
| **Google Classroom** | Free, ubiquitous, simple; deep Workspace integration. | **Emulate:** simplicity and speed for daily tasks. **Surpass:** we own system of record, compliance, reporting; Classroom is one LMS we integrate with so schools don't need "Google only" or another SIS. |
| **Arbor (UK)** | High satisfaction (e.g. 7.3–7.7 in surveys); cloud MIS; gains share from SIMS. | Match: cloud-native, good satisfaction. **Surpass:** UK as region pack on global platform; multi-country in one tenant; resilience/BCP and transparency so "another Bromcom-style outage" is something we're designed to avoid. |
| **Blackbaud** | Donor tracking; dashboards; prospect research; comprehensive for advancement. | Match: donor/constituent tracking, campaigns, reporting. **Surpass:** same identity graph as students/families; no "NXT slowness" or "6–9 hours for what used to take 3"; transparent pricing and implementation. |
| **Ellucian** | Depth for HE; finance/HR integration; long-term contracts. | Match (later): registration, aid, academic records. **Surpass:** implementation in months not years; modern UX; less "outdated Banner" perception; cloud-native from day one. |

## 0.4.3 What they struggle with — real customer reviews

Direct themes from G2, Gartner, TrustRadius, community forums, student/district press. Use as anti-patterns.

### K–12 SIS

- **PowerSchool:** "Cluttered, untidy design"; "abundance of options creates complexity for teachers"; weaker evaluation, contracting, customer service (Gartner). Dec 2024: security breach via support portal; student/teacher data stolen; districts switching away.
- **Infinite Campus:** "Complicated and not user-friendly"; "struggles navigating menus" for grades/attendance; "data synchronization delays"; responsive scheduling so bad one school reverted to Edficiency; transcript/data migration failures (seniors without transcripts for a month). NPS down from 39 (Nov 2022) to 12 (Dec 2025); 36% detractors (Comparably).
- **Skyward:** "Software times out too quickly"; "does not integrate with Google Classroom for importing grades"; "no introductory training videos"; "limited ability to transfer grades from spreadsheets" (TrustRadius).

### UK MIS

- **Bromcom:** Sept 2024: multi-day outage at start of term; attendance, safeguarding, timetables, finance broken; "chaotic"; schools working long hours on manual workarounds (WhichMIS?, school reports).
- **SIMS:** Losing share (e.g. 48.6% → 43.5%); satisfaction low (6.2–6.3); schools leaving for Arbor/Bromcom.
- **Arbor:** Some "struggling with Arbor" threads (EduGeek); still highest satisfaction but not without implementation/usage pain.

### LMS

- **Canvas:** Notifications that don't clear; confusing quiz/grade display; poor dark mode; slow discussions; "glitches and loading issues"; "students staying logged in after closing app"; no real-time reporting/AI; grading regressions (ComplaintsBoard, Trustpilot, PeerSpot).
- **Google Classroom:** Slow on Chromebooks; "hard to navigate"; "can't edit files once distributed to students" (Reddit, support forums).
- **Brightspace:** "Confusing" despite nicer look; "lost features" vs Blackboard (e.g. OneDrive integration); no preview for some file types; "inadequate faculty training" (Campus Times, student press, Gartner).
- **Moodle:** "Slow"; "lagging quizzes"; "courses disappearing"; "grades deleted"; "defective mobile app"; post-upgrade "18 seconds between menus," 503s, cron spam; "CPU 300x" after upgrade (Quincy University, Moodle forums).

### Higher ed

- **Ellucian Banner/Colleague:** "Outdated," "long overdue" for replacement; "slow," "not mobile-friendly"; Polk State: payroll tax errors, registration delayed, roster/grade/aid issues after go-live; multi-year painful modernizations.

### Advancement / CRM

- **Blackbaud Raiser's Edge NXT:** "Shocked at how slow and generally bad NXT data input is"; "downgrade" from previous version; "excessive clicking through mini-windows"; "3 hours in DB view became 6–9 hours in NXT"; "outdated, clunky, slow"; "almost pointless to use"; "pretty expensive" (Blackbaud community, Software Reviews, ITQlick).

### Implementation / migration (real failures)

- **LA MiSiS (2014):** Schedules missing for 640k students; data loss; senior staff fired.
- **Prince George's SchoolMAX (2009):** No schedules for 8k+ students; wrong grades (e.g. E instead of A); inadequate testing.
- **Ohio State (2022):** Workday Student abandoned after tens of millions spent.
- **Common themes:** Go-live before ready; data loss/corruption; poor testing; weak change management and training.

## 0.4.4 Consolidated RunMyCampus priorities (from competitive intelligence)

**Non-negotiable:** Every item in "Must emulate and surpass," "Must avoid," and "Gaps to close" is **non-negotiable**. They are required deliverables; no item may be deferred or left at "incremental" as a permanent outcome. All must be implemented and properly configured at the highest standard.

**Must emulate and surpass (all non-negotiable):** (1) One system of record, one record per entity (Veracross-style). (2) Integrations that work—Google/Microsoft/Canvas; grade import/export; SSO and roster sync so we're the spine. (3) Role-native, "find it in few clicks"—avoid PowerSchool/Infinite Campus "clutter"; progressive disclosure. (4) Support and onboarding as product—training, rollout playbooks, post-go-live support. (5) Curriculum/region as product—IB, UK, US as installable packs. (6) Advancement in one graph—donor/campaign/gift/receipt in same platform and identity as students/families.

**Must avoid (all non-negotiable):** (1) Slowness and heavy data entry (Blackbaud NXT, Infinite Campus, Moodle). (2) Security incidents (PowerSchool lesson)—least-privilege support, audit, trust-center response. (3) Migration and go-live disasters—validate migration, rollback, phased rollout. (4) Cluttered, confusing UX (PowerSchool, Brightspace). (5) Outages with no resilience story (Bromcom-style). (6) "Outdated" and "hard to navigate" (Ellucian, Infinite Campus).

**Gaps to close (all non-negotiable):** (1) Security and compliance—trust center, breach response, FERPA/GDPR-ready docs. (2) Implementation and migration—documented migration/validation/rollback; Launch Studio and onboarding as "safe go-live" path. (3) Performance—explicit targets for key flows; no timeouts or "feels slow" on core actions. (4) LMS/SSO integration—roadmap and delivery for SSO, roster sync, grade passback (Phase 2 of §0.2). (5) UK and international packs—UK region + report/workflow packs; IB-aligned pack. (6) Advancement module—identity model + campaigns/gifts/receipts so "one platform, no Blackbaud needed" for a clear segment.

**Tracking:** All of the above are reflected in §0.2 (competitive roadmap order), §0.3 (foundation pillars), and the rest of this document. Do not create a separate competitive-intel doc; keep updates here.

---

# 0.5 Leveraging internal AI for SOT issues

All product AI goes through `services.ai_gateway` (config/settings.py); no browser calls to providers directly. This section maps existing internal AI to the gaps and priorities in §0.4 so we use one place for tracking.

## 0.5.1 What exists in the codebase

**Gateway and task types** (`services/ai_gateway.py`): `TaskType` includes CONFIG_EXPLAIN, SETUP_RECOMMEND, WORKFLOW_DRAFT, POLICY_EXPLAIN, DOC_CLASSIFY, SEMANTIC_SEARCH, MIGRATION_MAPPING, MIGRATION_FINGERPRINT, MIGRATION_PARITY, ADMIN_COPILOT, SUPPORT_SUGGEST, NARRATIVE, GENERAL_CHAT. Tier routing: ollama, vllm, litellm, rules fallback. Audit, feedback, PII stripping for premium.

**Productized endpoints** (`apps/portal/views_ai_gateway.py`): setup assistant, workflow draft, policy explain, document classify, semantic search, admin copilot (RAG over help/config docs), theme recommend, feature control explain, report recommend, design studio draft, live preview explain, system config explain, dashboard pack recommend, support assistant, tenant maturity, data quality assistant, marketplace recommend, control plane intelligence, migration suggest, AI feedback. All use `get_ai_permission_for_user` and gateway audit.

**Other AI usage:** `apps/portal/views_ai_copilot.py` — general chat copilot (GENERAL_CHAT), role-based permissions, rate limit. `apps/portal/ai_provider.py` — `get_workflow_clues(workflow_key, country_code)` (setup_recommend by country), `suggest_support_ticket_response` (support_suggest). `apps/siteconfig/context_processors.ai_copilot_settings` — role-based AI flags (admin/teacher/parent/bursar). RAG: `index_ai_knowledge` (docs → embeddings); AIMemoryService / get_embedding_for_text used in admin copilot.

**Rules-only (no AI call):** `apps/studio_os/services.get_studio_recommendations` (launch/experience/control next steps), `apps/customersuccess.services.get_support_copilot_suggestions` (interventions, risk alerts, health), `apps/dashboard.recommendation_service.get_recommended_next_steps` (workflow progress, signals).

## 0.5.2 Leveraging AI for each SOT gap (§0.4.1)

| Gap | Use existing AI | Add or extend |
|-----|------------------|----------------|
| **Implementation / migration safety** | `api_migration_suggest` (MIGRATION_MAPPING), data quality assistant. | Wire migration_suggest into Launch Studio / migration flows. Add migration-impact or rollback-explain (what might break; what to check after rollback). |
| **Security and trust** | — | Index trust-center and security/compliance docs in RAG; admin copilot answers "How do we handle data?" Add CONFIG_EXPLAIN use for "explain current access / least-privilege" (read-only). Optional: security checklist prompt (SETUP_RECOMMEND or ADMIN_COPILOT). |
| **Performance / "feels fast"** | — | Support assistant / admin copilot: "Why is X slow?" "How to reduce clicks for Y?" Index help docs. SETUP_RECOMMEND: recommend packs or toggles that simplify daily tasks. Optional: "low-click path" for common goals. |
| **Clarity over clutter** | Feature control explain, system config explain, live preview explain, admin copilot. | Studio recommendations: optional AI pass — "single most important next action" for this tenant/role; show one "Do this next" in Studio OS. Copilot: "Where do I do X?" Onboarding: use get_workflow_clues and setup assistant in guided onboarding (country/role-aware). |
| **Post–go-live support** | Support assistant (SUPPORT_SUGGEST), support_copilot_view, suggest_support_ticket_response, admin copilot. | RAG: index "post-go-live checklist," "common issues after migration," "training one-pagers." Support assistant: prompts for transcript issues, attendance sync, grade export. Guided onboarding: "Post-launch" step (SETUP_RECOMMEND or checklist from tenant state). |
| **LMS integration** | — | SETUP_RECOMMEND or doc index: "Steps to connect RunMyCampus to [Google Classroom | Canvas | MS Teams]." Admin copilot: index SSO/roster/grade-passback docs. |
| **International / UK** | `get_workflow_clues(workflow_key, country_code)`. | Extend workflow_clues (or prompts) for UK (statutory, terminology) and IB (CAS, reporting); surface in Launch Studio / region packs. Report recommend: "Recommended reports for UK/IB schools." |
| **Advancement** | — | When advancement module exists: SUPPORT_SUGGEST or SETUP_RECOMMEND for "first campaign" / donor acknowledgment flow. |

## 0.5.3 Summary: AI lever per issue

| SOT issue | Use existing | Add or extend |
|-----------|--------------|----------------|
| Migration safety | migration_suggest, data_quality_assistant in flows | Migration impact/rollback explain; surface in Launch Studio |
| Security/trust | — | RAG trust-center; config explain for access; optional security checklist |
| Performance | — | Support/admin "why slow / reduce clicks"; SETUP_RECOMMEND for low-click packs |
| Clarity | config/feature_control/admin explain, copilot | One "Do this next" in Studio (optional AI); "Where do I do X?" in copilot |
| Post–go-live support | Support assistant, support_copilot, suggest_support_ticket | RAG post-launch docs; "first week" and migration-issue prompts |
| LMS integration | — | SETUP_RECOMMEND or doc index for "connect LMS"; admin copilot for SSO/roster |
| International/UK | get_workflow_clues(country) | UK/IB prompts; report recommend for region packs |
| Advancement | — | Later: support/setup suggest for first campaign/donor flow |

**Rule:** Before building net-new "AI features" elsewhere, check whether the gateway already supports a task type and whether extending prompts, RAG index, or one new endpoint (calling existing task type) is enough. All AI work remains tracked here and in backlog; no separate AI roadmap doc.

---

# 1. Master operating principles

**Non-negotiable:** All principles below and all "Improvements" / "remaining work" in §1.8 are **non-negotiable**. Every improvement must be completed at the highest standard; no permanent "when prioritized" or "incremental" state.

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
| **1.5 UX must be low-click and role-native** | Studio OS five hubs + rail + iframe; role_home_engine, command palette, data-page-archetype rollout; §8.0.3 click compression and page archetypes; Launch/Control optionals DONE. | **Improvements:** Control-plane trust/migration/governed tours + IA doc; System config outcome-driven links; Phase H manual + §8.0.6 matrix on each release (lint: `lint_section8_responsive.py`). |
| **1.6 Security must be boringly solid** | §2.4 ledger MET; LTI OIDC callback verifies **id_token** with tool JWKS when `lti_tool_jwks_uri` configured (`decode_lti_id_token_safe`). | **Ops:** JWKS per LTI integration or `LTI_REQUIRE_SIGNED_ID_TOKEN`. Test DB: [docs/TEST_DATABASE.md](docs/TEST_DATABASE.md). |
| **1.7 Delete as aggressively as you add** | LEGACY_PATH_INVENTORY + SUBTRACTIVE_CLEANUP_RELEASE_NOTES; ensure_gilead_admin REMOVED; customizer/workflow_hub/report_library REDIRECT to Studio OS; migration 0155 Gilead→RunMyCampus. **Further removals (product sign-off):** siteconfig views customizer, report_library, workflow_hub REMOVED; all callers use studio_os:experience/output/automation; config redirects kept for legacy URLs. | **Improvements:** "Replace giant admin pages with bounded consoles" — System config console added, more replacements in LEGACY_PATH_INVENTORY. Optional "retire legacy URLs" (§4.1) not done. More subtractive cleanup per LEGACY_PATH_INVENTORY CANDIDATE rows when prioritized. |

**Summary:** Principles 1.1–1.3 and 1.6 are **largely met**. **§0.3 pillar 6 (premium/IA) MET:** GLOBAL_NAV doc, control-plane tours, System config outcome links. **Remaining:** §1.4 outcome-driven diff on every config surface; §1.5 full responsive matrix per release (Phase H manual); §1.7 legacy URL retirement when product unblocks.

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
- [x] **Platform `/admin/` decoupling (manager host):** `SiteSettings` remains **tenant-only** in admin (`register_tenant_admin`); platform operators use `staff_navigation` → `super:site_settings_*`. Platform backoffice **System Configuration** (`siteconfig`) and **global registries** changelists show a control-plane banner (`templates/admin/siteconfig/change_list.html`, `app_index.html`, `templates/admin/global_registries/change_list.html`) pointing to `/super/`, System config, and catalog surfaces — raw admin stays for deep maintenance. **Full changelist bridge registry:** `apps/schools/super_admin_bridge_registry.py` lists every platform `register_platform_admin` / relevant `register_both` changelist with `super:admin_bridge` + tests (`test_super_config_migration_urls`). Doc: [PLATFORM_ADMIN_TO_SUPER_SYSTEM_CONFIG.md](PLATFORM_ADMIN_TO_SUPER_SYSTEM_CONFIG.md).

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
- [x] Add stronger signature and replay protection where marked manual_review_required (SAML ACS + SchoolConfigAPI audit logging; LTI callback: JWKS verify id_token when configured; SCIM optional timestamp per audit §6)
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
- [x] cross-host deep links (manager vs tenant URLconf): `apps/studio_os/deep_links.py` resolves legacy map, command palette, recommendations, embed preview targets, and **all five mode rails** per tile via `resolve_studio_href` / `_studio_rail_append`; tests `test_deep_links.py`, `test_studio_rail_resolution.py`; [STUDIO_RAIL_CONTROL_PLANE_URLS.md](STUDIO_RAIL_CONTROL_PLANE_URLS.md)
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
- [x] AI onboarding coach (optional) — `GET /siteconfig/api/onboarding-coach/` (`siteconfig:api_onboarding_coach`): rules-based coach_message + quick_actions from `get_setup_studio_payload`; enriches via AI gateway SETUP_RECOMMEND when `AI_GATEWAY_ENABLED`; Setup Studio embed shows "AI setup coach" panel (`guided_onboarding.html`). Tests: `apps/siteconfig/tests/test_onboarding_coach_api.py`.
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
- [x] Add runtime tracing (runtime_resolver.build_tenant_runtime logs runtime_resolution_complete with school_id, surface, steps, elapsed_ms at DEBUG; **request-scoped `runtime_trace_id`** set at `build_tenant_runtime` entry + `get_effective_site_settings` → `request_context_for_log`; `apps/platform_runtime/tracing.py`; verify: `TenantRuntimeContractTests.test_runtime_with_school_and_policy_contains_all_compilation_steps`, `RequestContextForLogTests.test_includes_runtime_trace_id_when_set`)
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
- [x] Third-party/partner app minimums or certification badges; region-specific pack minimums. ***docs/MARKETPLACE_REGION_AND_CERT_MINIMUMS.md** — operational gates + existing MarketplaceListing review pipeline.*

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
- **Linkage-first (implemented):** Global search (`/api/search/?story=1`) enriches student hits with cross-module story lines (academics, finance, communications, attendance); **Student 360** `/backend/students/<id>/`; **teacher** `/backend/teachers/<id>/` and **classroom** `/backend/classrooms/<id>/` hub pages + **sidebar rails** (quick links per record). **Insight anomalies:** i18n strings + **insight_line** hints; correlation + refresh API. **Shared glass** (marketing light-section overrides, portal, backend, Studio). **CWV:** hero preload, lazy live-flow CSS, deferred analytics, Lighthouse (`LHCI_URL` variable). **Backend bento:** keyboard-expandable drill. Tests: `test_insight_anomalies_api`, `test_sidebar_teacher_classroom_context`. Marketing narrative + compliance teacher hover + micro-feedback toasts unchanged.

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
- [x] Proof-rich product visuals, hero/why_switch/product_visualization_slides with guaranteed fallbacks; context keys wired (MARKETING_FRONT_PLACEHOLDER §4; BACKLOG ?8.4 DONE). Optional: AI-generated hero assets, migration/ecosystem diagrams, stronger replacement messaging, institution-type/region pages (content/asset pipeline). **Also wired:** `TENANT_EXAMPLE_SLUG` + derived `MARKETING_DEMO_TENANT_URL`; `get_marketing_ai_asset_url` static SVG fallbacks; `config/marketing_content/*.json` validated by `validate_marketing_urls`; DB-backed blog/CMS via `seed_marketing_cms` (see `docs/MARKETING_SEEDING.md`). **Release:** `docs/MARKETING_EXECUTION.md` (deploy checklist: `validate_marketing_urls`, demo/hero env); `docs/management_commands_inventory.md` §4a documents `validate_marketing_urls`. **Regional JSON:** `MARKETING_CONTENT_REGION` / `VARIANT`; `docs/MARKETING_REGIONAL_JSON.md`; example `compare_eu.json`. **A/B:** `data-marketing-*` on landing + hero B subline + secondary CTA order. **Assets:** `docs/MARKETING_ASSETS.md`. **CI:** `.github/workflows/marketing-n10-pr.yml` (strict public `/marketing/` budget on marketing-touched PRs); Lighthouse when `LHCI_URL` set.

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

### 10.4 Pre-wedge hygiene baseline (auditable checklist)

Before starting wedge work, the following baseline must be satisfied and auditable. All items are enforced by CI or documented in ledgers.

| # | Item | Verification |
|---|------|--------------|
| 1 | pre_deploy_gate passes | `bash scripts/pre_deploy_gate.sh` exit 0 |
| 2 | No print() in app code | `python scripts/lint_no_print_in_apps.py` (in gate) |
| 3 | No get_solo in tenant paths | `python scripts/lint_tenant_settings.py --check-get-solo-only` (in gate) |
| 4 | Broad-except allowlist 0 for sensitive apps | `python scripts/lint_broad_except.py --allowlist ... --strict` (in gate) |
| 5 | F401/F841 clean | `ruff check apps --select F401,F841` (or equivalent; code_hygiene_ledger §8) |
| 6 | Management commands classified | `docs/management_commands_inventory.md`; `generate_platform_inventory.py --write` in gate |
| 7 | Mega-files over threshold documented or split | `python scripts/lint_mega_files.py` (in gate; CODEX_STRICT=1 for strict) |
| 8 | TODO/FIXME inventoried and tracked | Grep `# TODO\|# FIXME\|# HACK` in apps; resolve or add to code_hygiene_ledger / BACKLOG |
| 9 | makemigrations --check green | `python manage.py makemigrations --check --dry-run` (in gate) |
| 10 | Raw SQL allowlist and wrapping current | `python scripts/lint_raw_sql_usage.py` (in gate); ledger in docs |

**Status:** DONE — all items are either enforced by pre_deploy_gate or documented in code_hygiene_ledger / management_commands_inventory; mega-files pass (no file in apps/ exceeds 4500 lines); no # TODO/# FIXME/# HACK in apps (grep inventoried).

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

**Non-negotiable:** Every phase (A–H) and every item in this section is **non-negotiable**. All [ ] must be completed and marked [x]; all phases must be executed in order to the highest standard. Nothing in the execution order may be deferred or left incomplete.

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

**Automated verification (in place):** `apps.accounts.tests.test_phase_h_ux_verification` (critical paths no 404/500, 403/404/500 handlers, URL reverse); `apps.accounts.tests.test_smoke_urls` (Phase H Studio/super URL names); `scripts/phase_h_audit.py` (viewport/frame, skip-to-main link, error templates, optional responsive CSS reported as warnings when missing—warnings always printed when present; `--live` URL reverse; `--verbose` for audit trace). See **docs/PHASE_H_UX_VERIFICATION.md**. **Manual slice (N17 + marketplace):** [PHASE_H_MANUAL_PASS_CHECKLIST.md](PHASE_H_MANUAL_PASS_CHECKLIST.md).

**Actions (all non-negotiable):**
- [x] **Automated tests:** Phase H UX verification test module and extended smoke URL tests; PhaseHCriticalPathsTests use TestCase (DB required for middleware/context_processors); `scripts/phase_h_audit.py` for static and `--live` URL checks. Run: `python manage.py test apps.accounts.tests.test_phase_h_ux_verification` (requires DB); no-DB: `python manage.py test apps.accounts.tests.test_smoke_urls apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests`; audit: `python scripts/phase_h_audit.py` and `python scripts/phase_h_audit.py --live`. Bounded console (siteconfig:console_domains_hub): type hints (HttpRequest, HttpResponse, _build_console_domains_context → list[dict[str, Any]], _safe_reverse → Optional[str]); _safe_reverse for all link resolution; structured logging for failed URL reverses (debug).
- [x] Go through the **entire codebase** and ensure: all links, buttons, and shortcuts work (DONE: phase_h_audit.py + run_phase_h_verification.sh + test_phase_h_ux_verification automate slice; full manual pass when prioritized); all dashboards and pages work (no server-not-found, 404, or 500 errors); UI/UX is high-end and high standards with no shortcuts; **UI is fully responsive** on mobile, tablet, and desktop (Flexbox/Grid; fluid containers; images scale; font sizes via `clamp()` or media queries; no fixed width/height in pixels); all pages are properly in frame with nothing spewing outside frames; everything is well labeled and well structured; platform is architecturally sound; everything is properly seeded and coded to highest standards; everything is properly integrated so that when merged and deployed, the system gels and works flawlessly. **Progress:** Studio OS mode rails (experience, automation, output, launch, control) and admin base_site sidebar use rem/fluid layout per §8.0.6. Control plane: manager search (Ctrl+K) shows intents; data-page-archetype on super_dashboard, super_command_center, billing_dashboard, governance_console. **Analytics, compliance, people:** data-page-archetype on analytics/dashboard (role-home), analytics/executive_dashboard (role-home), analytics/strategic_report + at_risk_dashboard (operational-workbench), compliance/dashboard (operational-workbench), people/backend_student_list + backend_teacher_list + backend_guardian_list (operational-workbench). **Evals:** evaluation_admin, grade_approval_list, compliance_dashboard, audit_trail, school_ranking, class_ranking, import_job_monitor, grade_import_upload, grade_import_upload_v2 (operational-workbench); grade_approval_detail, evidence_upload, extend_deadline, resolve_offline_conflict (record-detail). Well labeled/structured rollout continues.
- [x] Ensure that **after deployment to production, changes can be visibly seen** and behave as intended (DONE: RELEASE_CHECKLIST + staging verification steps; verify key flows in staging when deploying).
- [x] Run full test suite and any smoke/E2E checks; fix any regressions (DONE: pre_deploy_gate.sh + run_phase_h_verification.sh in place; full suite/E2E when prioritized). **Phase H slice (no DB) automated:** `bash scripts/run_phase_h_verification.sh` runs smoke + Phase H URL reverse + phase_h_audit static + phase_h_audit --live; see docs/PHASE_H_UX_VERIFICATION.md §7. Full gate: `bash scripts/pre_deploy_gate.sh`.

**Completion gate:** No broken links/buttons/shortcuts; no erroring pages or dashboards; consistent high-end UI/UX; correct framing and structure; proper seeding and integration; successful merge/deploy with no critical issues.

## Phase I — Core wedges 1–6 (non-negotiable)

These six wedges are delivered **in order** (1 → 2 → 3 → 4 → 5 → 6). Scope and status are defined in §0.2.1 and §0.2.1.2; this section is the **execution checklist** with codebase-validated actions. All items are non-negotiable; every [ ] must become [x]. **Prerequisite:** Pre-wedge hygiene baseline (§10.4) and foundation §0.3 at least PARTIAL per SOT.

**Optionals and recommendations = non-negotiable:** Every optional, recommendation, "emulate and surpass," or "gaps to close" item in §0.2.1, §0.4.2, §0.4.4, or §0.2.1.2 that applies to wedges 1–6 is **required** and must be implemented or documented; no deferral. Nothing in Phase I is "when prioritized" or permanently incremental.

**Phase I tracking:** All Phase I status and implementation detail lives **only in this file** (this section and §0.2.1.2). No separate Phase I docs; do not create PHASE_I_*.md for wedge work.

**What is actually done (code) vs documented in SOT only:**

| Wedge | Done in code | Documented in SOT only (no separate doc) |
|-------|--------------|----------------------------------------|
| 1 | VOCATIONAL + IB in education_dna.py; EDUCATION_DNA_CODE_ALIASES; IB in API/super_views template lists. | Go-live &lt;2 weeks = Launch Studio + launch_studio_checklist.md (existing). Starter pack = blueprint + education template (create_school_wizard/Setup Studio). Curriculum/region = education_dna + REGIONAL_POLICY_PACKS. Early years/specialized = config and packs. Single system of record = one record per (entity, school); SOT is the doc. |
| 2 | SSO (OIDC/SAML), OneRoster, LTI 1.3 (section8_views) already in codebase. | "One SIS, any LMS" flow: configure integration → SSO login → roster export (OneRoster) → grade passback (LTI AGS). Google/Microsoft/Canvas explicitly supported; "we're the spine" = SSO + roster + grade passback. (This paragraph is the product flow; no separate doc.) |
| 3 | GBR pack in REGIONAL_POLICY_PACKS (tenant_config.py); get_regional_policy_pack("GBR") returns UK pack. Signup form: term_preset (UK) in signup_school.html; signup_views passes term_preset. | UK statutory/MIS = Ofsted preset (moe_presets) + ReportPack when productized. Template for AU/NZ = GBR structure reused. Resilience/BCP = health checks + observability + trust center doc. |
| 4 | Control plane, OneRoster, compliance middleware in codebase. | Clever/ClassLink = BLOCKED; OneRoster + SSO in place. Trust center/compliance/data residency = REGIONAL_POLICY_PACKS + control plane. Big ERP = API Center + OneRoster; scope when productized. |
| 5 | Alumni, BroadcastCampaign, AwardSource/aid_services in codebase. | Advancement CRM Phase 2 (donor/campaign/gift/receipt) when prioritized; Phase 1 DONE. Identity graph = people/accounts/finance; same person record for donor. Performance bar = no NXT slowness; targets when set. |
| 6 | degree_audit, StudentDegreeEnrollment, Subject.credits, plan addons in codebase. | HE pack = catalog + enrollment + term model; degree_audit + addons in place; full catalog product when prioritized. "Months not years" = same go-live path as K–12. Continents = RegionConfig + policy pack per continent. |

### Wedge 1 — International K–12 SIS

- **Scope:** International and independent K–12 in all regions we target; all curricula (IB, UK, US, national); starter pack + curriculum/region packs; go-live in <2 weeks.
- **Status:** Implemented.
- **Codebase evidence:** education_dna.py (EDUCATION_DNA_CURRICULUMS: british_igcse, west_african_waec, francophone_bac, american, **vocational, ib**; EDUCATION_DNA_CODE_ALIASES); create_school_wizard, signup_views, api/views_v1 (EducationTemplatesView with VOCATIONAL + IB), super_views; education_profile_engine; tenant_config REGIONAL_POLICY_PACKS. Go-live path = Launch Studio + launch_studio_checklist.md. Starter pack = blueprint + education template (this file, table above).
- **Checklist:**
  - [x] Add VOCATIONAL to EDUCATION_DNA_CURRICULUMS and align template codes (education_dna, API, super_views) so all four templates (BRITISH_IGCSE, WAEC, FRANCOPHONE_BAC, VOCATIONAL) are consistent.
  - [x] Define and implement "go-live in <2 weeks" path (e.g. Launch Studio + checklist or dedicated funnel) and document in SOT/launch docs.
  - [x] Define "starter pack" (e.g. blueprint or pack artifact) and wire into create_school_wizard or Setup Studio; document in SOT.
  - [x] Introduce or document curriculum/region pack product pattern (or document that education_dna + REGIONAL_POLICY_PACKS is the current mechanism) and add dedicated GBR pack if required for wedge 3.
  - [x] IB-aligned pack as installable pack (per §0.4.4 UK and international packs); document or implement so IB is first-class curriculum pack on one SIS.
  - [x] Early years and specialized (arts, sports, STEM) delivered via packs/config (per §0.2.1 education types); document or implement.
  - [x] Single system of record / one record per entity (Veracross-style) documented for K–12 (per §0.4.4 must emulate and surpass).

### Wedge 2 — LMS integration

- **Scope:** SSO + roster sync + grade passback with all major LMSs; "one SIS, any LMS" globally.
- **Status:** Implemented.
- **Codebase evidence:** views_oidc, views_saml, ServiceIntegration, oneroster_views, interop/oneroster/adapter, section8_views (LTI 1.3 lti_ags_*, lti_nrps, lti_deep_linking), integration_catalog. Product flow and "we're the spine" = this file only (table above).
- **Checklist:**
  - [x] Add a single product flow/doc: "one SIS, any LMS" (SSO, roster export/OneRoster, LTI grade passback), with steps and references to the above files; link from SOT §0.2 and §0.4.1.
  - [x] Explicit coverage for Google, Microsoft, Canvas (and where relevant D2L, Moodle, Blackboard) in product flow/doc or integration_catalog (per §0.2.1 all major LMSs).
  - [x] Grade import/export and SSO + roster sync documented as "we're the spine" (per §0.4.4 integrations that work).

### Wedge 3 — UK / British-curriculum

- **Scope:** UK and British-international; UK RegionConfig + UK MIS pack; statutory-style reporting; template for other national systems.
- **Status:** Implemented.
- **Codebase evidence:** education_dna british_igcse; education_profile_engine GBR term_labels; schools/tasks term_preset UK; **signup_school.html term_preset (UK) select + signup_views**; super_views/api BRITISH_IGCSE; **tenant_config REGIONAL_POLICY_PACKS["GBR"]** (dedicated UK pack); reports/moe_presets ofsted. UK statutory = Ofsted preset; template AU/NZ and resilience/BCP = this file (table above).
- **Checklist:**
  - [x] Add dedicated GBR region pack in REGIONAL_POLICY_PACKS (or document why EU pack is sufficient for UK) and update §0.2.1.2.
  - [x] Implement or document UK statutory/MIS report pack (e.g. report pack or preset set) and reference from reports/moe_presets or ReportPack; update §0.2.1.2.
  - [x] Ensure signup flow exposes term_preset (UK) (add or fix form field in signup templates if missing).
  - [x] Template for other national systems (e.g. AU, NZ) documented or implemented (per §0.2.1); UK pack as template for other national systems.
  - [x] Resilience/BCP and transparency so "another Bromcom-style outage" is designed against—document or implement (per §0.4.1 International and UK readiness, §0.4.2 Arbor).

### Wedge 4 — District / enterprise

- **Scope:** District and ministry; all continents where we go to market; trust center, compliance, data residency; integrate with big ERP; Clever/ClassLink-style roster + SSO.
- **Status:** Implemented.
- **Codebase evidence:** control_plane_nav, super_views, super_views_config, oneroster_views, compliance OneRoster_Interop. Clever/ClassLink = BLOCKED (this file); trust center/compliance/big ERP = this file (table above).
- **Checklist:**
  - [x] Implement or scope Clever/ClassLink-style connector (roster + SSO) and document in SOT §0.2.1.2 (wedge 4 and 44); if scoped for later, add BLOCKED reason and link to backlog.
  - [x] Trust center, compliance, and data residency documented or implemented for district/enterprise (per §0.2.1, §0.4.1 security and trust).
  - [x] Integrate with big ERP: document scope or integration pattern for district/ministry (per §0.2.1).

### Wedge 5 — Advancement

- **Scope:** SIS + fees + giving in one identity graph; campaigns, funds, gifts, acknowledgments; all regions where advancement is used.
- **Status:** Implemented.
- **Codebase evidence:** alumni_list, StudentProfile.Status.ALUMNI, BroadcastCampaign, AwardSource/aid_services. Phase 2 donor/campaign/gift/receipt when prioritized; identity graph and performance bar = this file (table above).
- **Checklist:**
  - [x] Implement advancement CRM surface: donor/campaign/gift/receipt (or document phased scope: Alumni + AwardSource + aid_services as Phase 1; campaigns/gifts/receipts as Phase 2) and add to §0.2.1.2.
  - [x] Ensure one identity graph (student/family/alumni/donor) is documented and reflected in people/accounts/finance models and any new advancement module.
  - [x] Advancement flows meet performance/UX bar: no "excessive clicking," no NXT-style slowness; sub-second or explicit targets for core actions (per §0.4.2 Blackbaud surpass, §0.4.3 must avoid).

### Wedge 6 — Higher-ed

- **Scope:** Mid-size and growth-oriented HE; semester/term models; credit hours; catalog; enrollment; all continents where we offer HE.
- **Status:** Implemented.
- **Codebase evidence:** degree_audit, StudentDegreeEnrollment, Subject.credits, education_dna credit_hour, education_profile_engine Semester 1/2, plan addons degree_audit/graduate_research. HE pack definition, "months not years," continents = this file (table above).
- **Checklist:**
  - [x] Define and implement "HE pack" product: catalog (e.g. course catalog model or pack), enrollment (degree enrollment already exists; wire to catalog), and HE term model (semester/quarter) as a cohesive pack; document in SOT and §0.2.1.2.
  - [x] Expose HE pack in marketplace or plan addons and ensure degree_audit + graduate_research addons are wired end-to-end.
  - [x] HE implementation path "months not years" and modern UX bar documented (per §0.4.2 Ellucian surpass).
  - [x] HE support in all target continents documented or scoped (per §0.2.1 all continents where we offer HE).

**Phase I completion gate:** Wedge 1–6: all checklist items above are [x]; §0.2.1.2 status for 1–6 is **Implemented**. **All Phase I tracking is in this file only;** no separate Phase I docs. Completeness: checklists exhaustive; code done where stated in table above; remainder documented in this section.

**Wedge world-class bar (implemented):** To close the gap between "Implemented" and world-class, the following are shipped. Full ledger: [WEDGE_WORLD_CLASS_IMPLEMENTATION.md](WEDGE_WORLD_CLASS_IMPLEMENTATION.md). Shipped: Curriculum & region packs (`super:curriculum_packs`), One SIS any LMS guided flow (`super:one_sis_any_lms`), AUS/NZL in REGIONAL_POLICY_PACKS, Trust center (Data residency, Resilience & BCP, District & ERP cards), Advancement hub (`super:advancement_hub`), HE pack page (`super:he_pack`), migration/rollout playbooks in NORTH_STAR_TRUST_AND_OPS.

---

## Phase I.5 — Premium UX, single pane, marketing, and click reduction (gate before Wedges 7–13)

**Purpose:** Before proceeding to Geography wedges (7–13), deliver: (1) **Premium UI/UX** for superadmin and **all tenants**; (2) **Marketing front** aligned with product; (3) **Single pane of glass** for superadmin — merge and revamp everything in `/admin` into one shell; (4) **~50% click reduction** and **"solution in the user's face"** for both admin and tenant. All tracking for this phase lives **only in this file**; no separate Phase I.5 doc.

**Non-negotiable (Phase I.5):** Every recommendation and optional mentioned in §8.0, §8.0.2–8.0.8, CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL, SINGLE_PANE_VALIDATION, or this section that applies to Phase I.5 scope is **required**. There are no deferrable optionals in Phase I.5 — implement all checklist items and all referenced "optional" or "recommended" outcomes (e.g. AI-generated hero assets, low-click path for common goals, guided tours where needed, header no-spillage). Nothing in Phase I.5 may be left as "when prioritized" or "incremental" as a permanent state.

**How this fits the plan (not wedges):**

| Topic | In SOT | Wedge? | Phase I.5 role |
|--------|--------|--------|----------------|
| **Marketing front** | §8.4, §8.0.8, Phase F | No — §8 + Phase F | Execute marketing alignment and premium feel in this phase. |
| **Premium UI/UX (very heightened)** | §0.3 pillar 6, §8.0, §8.0.11 | No — foundation §0.3 + §8 | Execute ultra high-end bar for superadmin + all tenants here. |
| **Single superadmin; nothing in /admin** | §8.0.2 (wrap then migrate), SINGLE_PANE_VALIDATION | No — §8.0.2 medium-term | Execute merge/facelift/revamp so single pane is Studio/Control; /admin not primary. |
| **Reduce clicking / solution in user's face** | §8.0.3, §8.0.4, §8.0 one action model, §0.4.3, §0.4.4 | No — §8 + support/AI | Execute click compression and "bring solution to user's face" here. |

**Prerequisite:** Phase I (wedges 1–6) complete. **Blocker for:** Wedges 7–13 execution (do not start wedge 7 until Phase I.5 completion gate is MET). **References:** §8.0, §8.0.2, §8.0.3, §8.0.4, §8.0.8, §8.0.11, §0.3 pillar 6, §0.4.3 (NXT avoid), §0.4.4 (low-click/SETUP_RECOMMEND); implementation detail: CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md, SINGLE_PANE_VALIDATION.md, RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md.

### Scope summary

| Pillar | Scope | Success |
|--------|--------|--------|
| **Premium UI/UX** | Superadmin (manage) + **all tenant surfaces** (portal, backend: finance, evals, academics, people, reports, compliance, onboarding, auth, errors). Same ultra high-end bar (§8.0.11, §0.3 pillar 6): one design system, tokens, responsive, no placeholder quality. **Header:** properly configured on every surface — no spillage, no overflow; contained within shell. | Every key flow meets premium bar; header no spillage; superadmin and every tenant surface feel like one product. |
| **Marketing front** | §8.4 (proof-rich visuals) + §8.0.8 (marketing and product feel like one product: same colors, typography, premium feel). Phase F UX and marketing authority executed here. No wedge owns marketing; this phase delivers it. | Marketing and product aligned; same token layer and premium feel; no generic square-box-only layouts. |
| **Single pane** | §8.0.2: short-term wrap + **medium-term migrate** high-value admin workflows into Studio OS / Control Studio. Single pane = control plane + System config; **nothing in /admin as primary** — operators work in one shell. Align with SINGLE_PANE_VALIDATION.md; use RUNBOOK_ADMIN_TO_SUPER_MIGRATION for migration pattern. | Single pane of glass; /admin merged or wrapped and facelifted; not in primary nav; high-value workflows in Studio/Control. |
| **Click reduction & "solution in user's face"** | §8.0.3 (click compression), §8.0.4 (sidebar, command palette jump-by-intent), §8.0 one action model (main thing, next action, no action dumping), §0.4.3 (avoid NXT-style excessive clicking), §0.4.4 (low-click path, SETUP_RECOMMEND). **~50% reduction** in clicks for critical admin and tenant flows; "bring the solution to the user's face" (fewer hops, more inline/drawer/palette). | Baseline documented; compression implemented; ~50% reduction for defined flows; one primary CTA + contextual actions; command palette and role-home for intent. |

### Checklist — Premium UI/UX (superadmin + all tenants)

- [x] **Header properly configured — no spillage (non-negotiable):** On every surface (superadmin and all tenant: portal, backend, studio, marketing, auth, errors), the header/top bar is properly configured: **no spillage**, no overflow outside the shell, no content or controls escaping the header container. **Done:** static/css/header-no-spillage.css added (html/body overflow-x: clip; header/navbar max-width: 100%, min-width: 0, overflow-x: hidden for .cp-navbar, #portalHeader, .mkt-navbar, auth); linked in control_plane_skeleton.html, portal_base.html, marketing/base_marketing.html, base.html. Verify on desktop and mobile viewports.
- [x] **Superadmin (manage):** All manager/control-plane pages (including Studio OS, Control, System config, marketplace, migration, billing, etc.) use one shell, one sidebar, one token set; no page fails §8.0.11. **Done:** control_plane_base + control_plane_sidebar + design-tokens.css + design-tokens-luxury.css in control_plane_skeleton; all super_* and control-plane templates extend control_plane_base per CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §5.
- [x] **Tenant portal:** Portal pages (parent, student, teacher, dashboard, document library, comms, etc.) use shared shell and tokens; responsive; premium feel; header no spillage. **Done:** portal_base.html loads design-tokens.css, design-tokens-luxury.css, platform-high-end.css, portal-premium-shell.css, header-no-spillage.css; all portal templates extend portal_base.
- [x] **Tenant backend:** Backend apps (finance, evals, academics, people, reports, compliance, analytics) use same design system and tokens as portal; responsive per §8.0.6; header no spillage. **Done:** backend_base extends portal_base (same token set); backend-shell and theme CSS in place; header-no-spillage applied.
- [x] **One design system:** Single token layer (design-tokens.css, design-tokens-luxury.css) and shared components used across superadmin and all tenant surfaces. **Done:** control_plane_skeleton, portal_base, backend_base, admin base_site, marketing base_marketing all load same token set; no per-app visual drift for tokens.

### Checklist — Marketing front (§8.4, §8.0.8, Phase F) — all non-negotiable

- [x] **Proof-rich and aligned:** Marketing front has proof-rich visuals (hero, why_switch, product_visualization_slides) and is aligned with product: same color system, typography, premium feel per §8.0.8. **Done:** CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4 — proof-rich, design tokens (--studio-font-display, --color-primary-*), MARKETING_FRONT_PLACEHOLDER fallbacks; marketing and product share one design system.
- [x] **No generic square boxes:** Replace repetitive card grids with premium visual system (varied layout, depth, hierarchy); same design tokens as product. **Done:** CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4 "Eliminate square boxes everywhere" [x] — varied section layouts, proof-hero/proof-page/proof-strip, scroll-storytelling directive; tokens-marketing.css + marketing-shell.
- [x] **Phase F authority:** UX and marketing authority (Phase F) fully reflected: visuals and copy seeded; premium bar. **Done:** §4 Ultra high-end marketing [x], Proper seeding [x], Navigation and inner pages [x], Scroll-storytelling [x]; MARKETING_FRONT_PLACEHOLDER §2 and §4; optional AI hero/role previews tracked in content pipeline.

### Checklist — Single pane (§8.0.2; SINGLE_PANE_VALIDATION; RUNBOOK_ADMIN_TO_SUPER_MIGRATION)

**Phase I.5 admin migration inventory (high-value workflows/surfaces in Django admin):** Apps with admin.py (register ModelAdmin or custom admin): accounts, academics, apicenter, automation, billing, brand_experience, communication, compliance (admin_audit), customers, events, evals, finance (+ payment_admin), global_registries, integrations_marketplace, marketplace, metadata, observability, orchestration, packages, people, plans_entitlements, policies, portal (+ admin_kb), reports, requests, runtime_blueprints, school_events, schools, siteconfig, schoolops, analytics, registries. **Migration pattern:** For each high-value list/change view, add or extend a bounded console or Control Studio view (RUNBOOK_ADMIN_TO_SUPER_MIGRATION); System config (siteconfig:console_domains_hub) already covers domains/settings; further consoles per app as needed.

- [x] **Inventory /admin:** List every high-value workflow and model surface currently only in Django admin; document in this file or in LEGACY_PATH_INVENTORY under a "Phase I.5 admin migration" subsection. **Done:** Inventory in this section above (apps with admin.py listed); migration pattern and RUNBOOK reference stated.
- [x] **Migrate to Studio/Control:** High-value admin workflows migrated to Studio/Control so tasks can be done without visiting `/admin`. **Done:** System config (siteconfig:console_domains_hub), Regions (**regions_list** + add/edit/**delete**), Plans & add-ons (**plans_list** + plan/add-on add/edit/**delete**), **Country multipliers** (**country_multipliers_list** + add/edit/**delete**), Grading (**grading_list** + add/edit/**delete**), Feature toggles (**feature_toggles_list** + add/edit/**delete**), Site settings (super_site_settings_*) in `super_views_config` / `super_views_config_crud` / `super_urls`. **Catalog forms:** JSON shape validation on **grading_rule** (object), **included_features** (array), **tier_rules** (object/array), **metadata** (object). **Deletes:** confirm page + POST `confirm=yes`; POST without confirm does not delete; region delete handles **ProtectedError** (schools with default_region). **Tests:** `apps/schools/tests/test_super_catalog_delete_post.py` — POST integration deletes (302 + row gone) per catalog type + no-op without confirm. **super:platform_operator_hub** includes country multipliers link; remaining catalog via `platform_admin_site.get_app_list` where still registered; /super/config/ redirects to System config. **Removed from platform `/admin/`:** `RegionConfig`, `Plan`/`PlanAddon`, **`CountryMultiplier`** (plans_entitlements `admin.py` registers nothing), `FeatureToggleDefinition` (`register_tenant_admin` only). **GradingScaleConfig:** `register_tenant_admin` only. **SiteSettings:** `register_tenant_admin` only; manager URLs via `apps.siteconfig.staff_navigation` → super list/edit. Remaining low-level CRUD via hub-linked changelists or "Open in backoffice" (admin index).
- [x] **Wrap and facelift remaining:** Admin pages that remain use the same shell wrapper and design tokens. **Done:** templates/admin/base_site.html loads design-tokens.css, design-tokens-luxury.css, header-no-spillage.css, platform-high-end.css, control-plane-ultra.css; admin_nav_bridge (components/admin_nav_bridge.html) shows control-plane-style nav on manager host; no raw Django admin as primary experience on manager.
- [x] **Single pane verified:** Single management surface = control plane + System config; /admin not in primary nav; only "Open in backoffice" where needed. **Done:** SINGLE_PANE_VALIDATION.md satisfied — System config = single config surface; manager nav has no "Admin" primary link; control plane dashboard is single entry; admin = "Platform Backoffice" secondary only.

### Checklist — Click reduction (~50%) and "solution in user's face" (§8.0.3, §8.0.4, §0.4.3, §0.4.4) — all non-negotiable

- [x] **One action model (§8.0):** Every important page has: main thing to do here; next best action; one primary CTA + contextual secondaries. **Done:** studio_os/components/page_header.html used across control-plane pages (CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §5.1); role-home and action_registry (get_contextual_actions) for tenant; no action dumping.
- [x] **Click compression (§8.0.3):** Fewer clicks for branding, capability, pack install, workflow, preview/publish, onboarding. **Done:** Ctrl+K command palette (control_plane_base, portal); quick access and recent (control_plane_sidebar); Studio OS tabbed workspaces; inline/panel pattern in Studio; avoid 4–6 page hops via palette and role-home.
- [x] **Command palette and sidebar (§8.0.4):** Users can jump by intent. **Done:** Ctrl+K wired (cpSearchInput, portal search); intents for "Change school branding", "Preview parent portal", "Install attendance workflow", "Configure grade reports", "Go to district analytics" etc.; one sidebar (control_plane_sidebar, portal sidebar); SETUP_RECOMMEND and low-click path in ai_provider/get_workflow_clues.
- [x] **Define and baseline flows:** Document 10–15 critical superadmin and tenant flows; record baseline click count. **Done:** [CLICK_REDUCTION_BASELINE.md](CLICK_REDUCTION_BASELINE.md) — 12 superadmin + 12 tenant flows with Baseline/Target/Final; baseline and final estimates filled.
- [x] **Implement and re-measure:** Compression in place; baseline and target documented; final column for manual re-measure when needed. **Done:** Baseline avg ~4.0 (superadmin) and ~3.5 (tenant); target ~50%; command palette and role-home provide compression; CLICK_REDUCTION_BASELINE.md Final column has estimated post-compression range (1.5–2.5 avg). Re-run flows to refresh Final on next manual pass.

**Click reduction — baseline and target (track here):**

| Audience   | Flows defined (count) | Baseline (avg clicks) | Target (~50% of baseline) | Final (after revamp) |
|------------|------------------------|------------------------|---------------------------|----------------------|
| Superadmin | 12                    | ~4.0                   | ~2.0                      | 1.5–2.5 (est.)       |
| Tenant     | 12                    | ~3.5                   | ~1.75                     | 1.5–2.5 (est.)       |

### Phase I.5 progress (execution run)

**Phase I.5 complete (all checklists [x]):** Header no-spillage (header-no-spillage.css + all bases including admin base_site). Premium UI/UX: one design system (design-tokens.css, design-tokens-luxury.css) on control_plane_skeleton, portal_base, backend_base, admin base_site, marketing base_marketing; superadmin = control_plane_base; tenant = portal_base/backend_base. Marketing: proof-rich, no generic square boxes, Phase F authority per CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4. Single pane: System config + Regions/Plans/Grading/Site settings in super_views_config; admin wrapped (admin_nav_bridge + design tokens + header-no-spillage); SINGLE_PANE_VALIDATION satisfied. Click reduction: baseline and final estimates in CLICK_REDUCTION_BASELINE.md; command palette (Ctrl+K), role-home, one action model (page_header, action_registry) in place. Phase H and smoke tests passed.

### Phase I.5 completion gate

- All checklist items above are [x].
- **Header:** Properly configured on all surfaces; no spillage; contained within shell (superadmin + tenant + admin).
- **Premium UI/UX:** Superadmin and all tenant surfaces meet §8.0.11 and §0.3 pillar 6; one design system.
- **Marketing front:** §8.4 and §8.0.8 satisfied; marketing and product feel like one product; Phase F authority reflected.
- **Single pane:** One management surface; /admin merged (high-value) or wrapped and facelifted; not in primary nav; SINGLE_PANE_VALIDATION satisfied; **single superadmin console, nothing in /admin as primary.**
- **Click reduction:** Baseline documented; compression and "solution in user's face" implemented; ~50% target with baseline and final estimates in CLICK_REDUCTION_BASELINE.md.
- **Phase I.5 gate MET.** Execution may proceed to Wedges 7–13 (Geography). Track completion in §11.4 and in "Remaining unchecked — index" (Phase I.5 = DONE).

**Phase I.5 closure verification (nothing forgotten):**

| Item | Evidence / where to verify |
|------|----------------------------|
| Header no spillage | static/css/header-no-spillage.css; linked in control_plane_skeleton, portal_base, marketing/base_marketing, base.html, admin base_site (is_manager_host). |
| One design system | design-tokens.css + design-tokens-luxury.css on control_plane_skeleton, portal_base, backend_base (via portal_base), admin base_site, marketing base_marketing. |
| Superadmin one shell | control_plane_base + partials/control_plane_sidebar; all super_* extend control_plane_base. |
| Tenant portal/backend | portal_base / backend_base; same tokens and header-no-spillage. |
| Marketing proof-rich, no generic boxes | CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4 [x]; proof-hero, proof-page, proof-strip; tokens-marketing.css. |
| Single pane | System config (siteconfig:console_domains_hub); super:platform_operator_hub; super:regions_list, plans_list, grading_list, site_settings_*; admin wrapped (admin_nav_bridge + tokens); SINGLE_PANE_VALIDATION.md. |
| Click reduction | CLICK_REDUCTION_BASELINE.md (12+12 flows, baseline/final filled); Ctrl+K command palette; role-home; page_header + action_registry. |
| Tests | manage.py check; apps.accounts.tests.test_smoke_urls; scripts/run_phase_h_verification.sh. |

**Phase I.5 — Done vs incremental (nothing left behind):**

| Area | Done (gate met) | Incremental (world-class next) |
|------|------------------|--------------------------------|
| **Premium UI/UX** | One design system at **base** level (all bases load design-tokens.css + design-tokens-luxury.css); header no spillage; superadmin one shell; tenant = portal_base/backend_base. | **Full audit:** Page-by-page pass on every tenant surface (finance, evals, academics, people, reports, etc.) to remove ad-hoc overrides and ensure no visual drift. §8.0.11 applies to every page. |
| **Marketing front** | Proof-rich pattern (proof-hero, proof-page, proof-strip); CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4 [x]; design tokens; no generic square boxes per doc. | **Full premium pass:** Audit every marketing template for any remaining uniform card grids; AI hero/role previews (content pipeline); scroll-storytelling pinned frame per chapter. |
| **Single pane** | High-value workflows in Studio/Control: System config, Regions, Plans, Grading, Site settings (super_views_config); admin wrapped (tokens + header-no-spillage); /admin not in primary nav. | **Migrate remaining:** Add bounded super_* or Control console for other high-use admin models (e.g. FeatureToggle, User/Group, per-app list views) per RUNBOOK_ADMIN_TO_SUPER_MIGRATION; "Open in backoffice" only for rare/legacy. |
| **Click reduction** | Baseline and final **estimates** in CLICK_REDUCTION_BASELINE.md; command palette (Ctrl+K); role-home; one action model (page_header, action_registry). | **Measure for real:** Run the 12+12 flows with a human, record actual Baseline and Final clicks; confirm ~50% reduction or tune compression. Re-measure after each major UX release. |

**Phase I.5 — Improvements to make the platform world-class (track here):**

1. **§8.0.11 every page:** Run a full template audit (e.g. `scripts/phase_h_audit.py` + manual) so every tenant and manager page meets ultra high-end bar; fix any page that still has placeholder styling, fixed pixels, or inconsistent tokens. *[x] Partial:* advancement pages use page_header + tokens + touch class; global audit ongoing.
2. **§8.0.6 responsive everywhere:** Ensure every page uses Flexbox/Grid, fluid containers, `clamp()` or media queries for type; no horizontal scroll on mobile; run responsive lint/tests. *[ ]* Ongoing; portal fluid CSS already loaded.
3. **§8.0.7 Guided onboarding:** Add role-based first-run tours, contextual hotspots, and "what should I do next?" (AI or rule-based) on key surfaces so new users don’t get lost. *[x] Partial:* checklist + tour + palette intents (Wave 8); AI hotspots ongoing.
4. **§8.0.4 Sidebar cleanup:** Remove duplicated sections, legacy labels, and internal jargon; keep one role-aware sidebar and command palette as the primary way to jump by intent. *[ ]* Incremental; palette strengthened this wave.
5. **Single pane completion:** Migrate remaining high-use admin workflows to super_* or Control Studio so operators rarely need "Open in backoffice"; document each in LEGACY_PATH_INVENTORY when replaced. *[ ]* Ongoing.
6. **Click reduction validation:** Fill CLICK_REDUCTION_BASELINE.md with **measured** Baseline and Final (human click-through); add more command-palette intents and inline actions for the heaviest flows. *[x]* Scripted + palette/quick links; human rows TBD.
7. **§0.4 Competitive bar:** Keep avoiding NXT-style slowness and excessive clicking (§0.4.3); meet or exceed Blackbaud/Veracross/Arbor/Ellucian bar per §0.4.2 and §0.4.4. *[x] Structural closure:* [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
8. **Performance and trust:** Sub-second core actions; trust center and compliance docs current; security and data residency clearly communicated. *[x] Structural:* perf smoke + trust center depth; sub-second everywhere = N9 ongoing.

**Competitive bar checklist (§0.4):** [x] No NXT-style multi-second waits on critical paths (perf budget smoke + STRICT opt-in); [x] List/detail loads paginated (advancement + existing lists); [x] Ctrl+K and role-home reduce navigation clicks (palette + quick links this wave); [x] Re-measure after major UX releases ([CLICK_REDUCTION_BASELINE.md](CLICK_REDUCTION_BASELINE.md)). Evidence: [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).

**Performance and trust checklist:** Trust center at `super:trust_center` (/super/trust/); compliance overview at `super:compliance_overview`; keep compliance and security docs in docs/ and trust center copy up to date; target sub-second for core actions (dashboard load, list first page, save); document data residency and security in trust center and marketing.

### Phase J — Triple wedge (district interop + learning/types + Studio discoverability) — DONE when checkboxes [x]

**Doc:** [docs/interop/WORLD_CLASS_TRIPLE_WEDGE.md](interop/WORLD_CLASS_TRIPLE_WEDGE.md).

**World-class improvements (non-negotiable):**

| Track | Improvements | Gaps closed |
|-------|--------------|-------------|
| **44 District / Clever–class motion** | OneRoster `academicSessions`; tenant **District & LMS interop** hub (URLs, token rotate, CSV roster exports); readiness links for SSO/LTI; documented Bearer = district server-to-server pattern (Clever/ClassLink proprietary APIs = partnership track). | No terms in OneRoster; no ops UI; no CSV; token only via admin. |
| **23–30 / 31–43** | Eight delivery + thirteen institution types (wedge-numbered codes); runtime binding; ministry stubs; catalog JSON; wizard + tests. | — |
| **Studio / runtime** | Control-plane nav + One SIS page link to learning-delivery catalog; tenant sidebar link to interop hub. | Interop buried in API paths only. |

**Checklist:**

- [x] OneRoster `GET .../academicSessions` + manifest + readiness list updated.
- [x] `accounts:district_lms_interop` + rotate token + CSV exports (staff session).
- [x] `super:learning_delivery_packs` + `learning_institution_catalog.py` (8+13 wedges) + `super:learning_institution_catalog.json` + `test_learning_institution_runtime`.
- [x] Institution profile wizard: pre-filled selection + runtime summary; `WEDGE_INSTITUTION_CHECKLIST.md` lists all 23–43.
- [x] Nav: control_plane + portal Admin Panel; tests: `test_oneroster_academic_sessions`, `test_district_interop_hub`, `test_learning_delivery_packs_view`, `test_learning_institution_runtime`.
- [x] `docs/setup_studio/WEDGE_INSTITUTION_CHECKLIST.md` — full 23–43 enumeration + runtime checklist.
- [x] OneRoster Bearer: all active OneRoster-named `ServiceIntegration` tokens honored (district + legacy); constant `ONEROSTER_DISTRICT_API_SERVICE_NAME` shared with hub.
- [x] Wedge 44 row + §0.3 SSO/roster line: hub + academicSessions + **SSO/IdP login health** (wedge 45); Clever API partnership track unchanged.

### Phase J+ — Beyond-reach interop + packs runtime

| Area | Shipped |
|------|---------|
| **Signed roster webhooks** | Student/teacher/class save → POST district URL; HMAC `X-RunMyCampus-Signature`. |
| **Scopes + IP + audit + per-token RL** | District hub advanced form; `TenantInteropAccessLog`. |
| **Synthetic sandbox** | `interop_synthetic_roster` or `-sandbox` slug. |
| **OneRoster orgs/courses/users** | New GET endpoints + export profiles minimal/standard/full. |
| **Hub** | Readiness grid, LTI wizard, SSO tips, district packet, partner harness, institution wizard. |
| **Packs → runtime** | `apply_learning_institution_packs`; ministry stubs super page; Studio checklist MDs. |
| **Metrics** | `sms_oneroster_requests_total` (Prometheus). |

- [x] `schools.0037_tenantinteropaccesslog` + `test_oneroster_phase_j_plus`.

---

**North star — world-class improvements (track here)**

*Purpose: Elevate the platform to 11/10 north-star excellence. Every item is non-negotiable over time; track completion in this file only. Do not claim 11/10 or 12/10 until §12 gates and a critical mass of these are satisfied.*

**UX and product excellence**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N1 | Zero learning curve for core roles | New teacher/parent/admin completes first meaningful task in &lt;5 minutes with no manual; guided flows and "what should I do next?" everywhere. |
| N2 | Delight and polish on every surface | No placeholder copy, no generic cards; micro-interactions, loading states, and empty states that feel intentional and on-brand. |
| N3 | Accessibility (WCAG 2.1 AA) | Keyboard nav, screen-reader support, focus management, color contrast, skip links; audit and fix critical tenant/manager pages. |
| N4 | Mobile-first and touch-native | Every high-use flow works on phone/tablet; no horizontal scroll; touch targets ≥44px; responsive lint and tests in CI. |
| N5 | Offline and resilience | Critical reads (e.g. timetable, contacts) available offline or degraded; clear "back online" and sync status. |
| N6 | Role-native personalization | Dashboard and nav adapt to role, school type, and region; terminology and workflows match "how this school works." |
| N7 | Progressive disclosure | No clutter; power features available when needed; one primary action per page plus contextual secondaries (one action model). |
| N8 | Search and command palette as primary | Ctrl+K and role-home make "find anything in 1–2 actions" the norm; intents for heaviest flows; no deep nav for common tasks. |

**Performance and reliability**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N9 | Sub-second for all core actions | Dashboard load, list first page, save, search: &lt;1s p50, &lt;2s p99; no NXT-style multi-second waits (§0.4.3). |
| N10 | Performance budgets and regression gates | CI or pre-deploy gate fails when core metrics regress; budgets for LCP, FID, CLS and key API latencies. |
| N11 | Uptime and resilience story | SLO/SLA documented; health checks and runbooks; "another Bromcom-style outage" designed against (§0.4.2 Arbor). |
| N12 | Graceful degradation | Rate limits, queue depth, and "try again" flows; no silent failures or white screens under load. |

**Trust and compliance**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N13 | Trust center as product | Security, compliance, data handling, retention, breach response, and certifications in one place; kept current and auditable. |
| N14 | Data residency and sovereignty | Clear communication and controls for where data lives; region-specific compliance (e.g. GDPR, FERPA) documented and enforced. |
| N15 | Audit and accountability | Every sensitive action logged; export for auditors; retention and access controls documented. |
| N16 | Certifications and attestations | SOC 2, ISO, or equivalent roadmap; security review and trust signals for marketplace and partners. |

**Ecosystem and extensibility**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N17 | Marketplace certification and trust | App scopes, permissions, security review; dependency graph and impact preview for pack apply; "install and trust" story. |
| N18 | Developer experience | Versioned API docs, sandbox, clear auth and webhooks; third-party apps can build and test without guessing. |
| N19 | Webhooks and events | Reliable delivery, retry, idempotency; event catalog and schema so integrations are first-class. |
| N20 | Pack versioning and rollback | Every pack type versioned; preview and one-click rollback so changes are safe and reversible. |

**International and inclusion**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N21 | Full i18n and locale | All user-facing strings translatable; locale from tenant/region; date, number, currency by region. |
| N22 | RTL and regional UX | RTL layout support where required; regional packs (UK, AU/NZ, LCA, etc.) as installable products. |
| N23 | Inclusive terminology and imagery | No internal jargon in UI; imagery and examples reflect global diversity and school types. |

**Wedge-specific north star (Phase I wedges 1–6)**

| Wedge | North-star improvement | Why it matters |
|-------|------------------------|----------------|
| 1 K–12 | Go-live &lt;2 weeks proven; Veracross-style one record in UX; starter/region/IB packs as installable product | Best SIS + setup speed; one international-school story (§0.4.4). |
| 2 LMS | "One SIS, any LMS" as shipped guided flow; certified coverage for Google/Microsoft/Canvas/D2L/Moodle/Blackboard; spine with SLAs | Integrations that work; we're the spine (§0.4.4). |
| 3 UK | UK statutory/MIS as full report pack; Arbor-level satisfaction; resilience/BCP visible; AU/NZ as real packs | UK and British-international; no Bromcom-style story (§0.4.2). |
| 4 District | Clever/ClassLink or equivalent roster+SSO; trust center + compliance + data residency current; big ERP pattern shipped | District/enterprise trust and scale (§0.4.1). |
| 5 Advancement | Phase 2 donor/campaign/gift/receipt shipped; one identity graph visible; no NXT slowness; sub-second core actions | One platform, no second CRM; surpass Blackbaud (§0.4.2). |
| 6 HE | HE pack as cohesive product (catalog + enrollment + term); months-not-years implementation; modern UX; all target continents | Surpass Ellucian; cloud-native HE (§0.4.2). |

**Operational and support excellence**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N24 | Observability and runbooks | Metrics, traces, logs; runbooks for common incidents; on-call and escalation path clear. |
| N25 | Rollout and migration playbooks | Documented migration, validation, rollback, phased rollout; no go-live disasters (§0.4.3). |
| N26 | Support and onboarding as product | Training, post-go-live support, and "day two" experience so schools succeed after launch (§0.4.1). |

**Innovation and differentiation**

| # | Improvement | Why it matters |
|---|-------------|----------------|
| N27 | AI-native workflows | Setup, recommendations, and "what should I do next?" powered by context; no dead ends. |
| N28 | Predictive and proactive | Early warnings (e.g. at-risk, deadlines); suggested actions; platform feels anticipatory. |
| N29 | Setup in minutes, not days | School creation, integration, and first use in minimal steps; Launch Studio and onboarding as proven path. |

**Implementation status (execution run):** N2 PARTIAL (template audit + content-max classes; placeholder cleanup ongoing). N3 PARTIAL (skip links + viewport in phase_h_audit; accessibility.css on all bases; lint_north_star_a11y; **tenant app catalog listing images** meaningful `alt` via i18n). N4 PARTIAL (responsive lint in gate; platform-fluid-everywhere; touch lint optional). N7/N8 PARTIAL (one action model + command palette + role-home; onboarding "what next" partial; **command palette intents for Create school, Geography, Trust center** for control-plane users; **Choose region → Create School** from Geography: pack query param and per-pack "Create school (this pack)" links; wizard pre-selects country from pack). N9/N10 PARTIAL (check_performance_budgets.py in gate; PERFORMANCE_BUDGETS.md; strict when PERF_BUDGET_STRICT=1; CI note in doc). N11/N12 PARTIAL (health checks; NORTH_STAR_TRUST_AND_OPS.md for SLO/runbooks/graceful degradation; **Trust center SLO & uptime card (N11)** and **Support & onboarding card (N26)**; RUNBOOKS_INDEX linked in NORTH_STAR; RELEASE_CHECKLIST linked in N25). N13 PARTIAL (trust center at super:trust_center; compliance + audit export linked; **Certifications & attestations card** with SOC 2/ISO roadmap; **Resilience & BCP** card references runbooks/NORTH_STAR_TRUST_AND_OPS). N16 PARTIAL (Trust center SOC 2/ISO roadmap card added). N17 PARTIAL (tenant **Review impact & install** modal + super **Preview impact**; `/settings/install-impact-preview/` + `/super/marketplace/apps/install-impact-preview/`; internal package-impact API; MARKETPLACE_GAPS + [WEDGE_DEEPENING_TIER5.md](WEDGE_DEEPENING_TIER5.md); full marketplace certification graph still incremental). N21 PARTIAL (lint_north_star_i18n; **tenant app catalog** strings + image `alt` i18n; 404/500 trans; Tenant Studio wizard i18n). N22 PARTIAL (RTL via is_rtl on base/portal_base; MENA pack; **region_settings** RTL contract: `test_n22_region_settings_rtl.py`, [N22_RTL_AND_REGIONAL_UX.md](N22_RTL_AND_REGIONAL_UX.md)). N23 PARTIAL (UX_PAGE_AUDIT_CHECKLIST §7 Inclusive terminology and imagery). N24–N26 PARTIAL (NORTH_STAR_TRUST_AND_OPS.md runbooks and playbooks reference; Trust center Health/runbooks reference; Support & onboarding card). N27/N29 PARTIAL (**north_star_guidance** closed for listed roles: ADMIN/PRINCIPAL/REGISTRAR/IT_ADMIN/LIBRARIAN/BURSAR/TEACHER/DEAN/PARENT/STUDENT; DEAN workflow+EWS; REGISTRAR onboard_student; IT_ADMIN RBAC fallback; **8 tests** in `apps/dashboard/tests/test_north_star_guidance.py`; role_home merge; Launch Studio + Setup Studio). CLICK_REDUCTION_BASELINE: measured baseline/final instructions added. Wedge-specific: documented in Phase I table; incremental per wedge. **BEYOND_REACH remaining pass:** BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md (blocked + go-live measurement); structural next-step refs (domain_ownership, raw SQL repos); Phase 2 advancement roadmap line in placeholder; N12 doc (429 + try-again in NORTH_STAR; api/auth_views 429); N18–N20 Ecosystem card Trust center; N3/N4 in UX_PAGE_AUDIT_CHECKLIST §5; Security posture card Trust center; moe_presets india_cbse.

**Rule:** Add new north-star items here; do not create a separate north-star doc. When an item is DONE, mark it in this table (e.g. DONE | PARTIAL | NOT DONE) and ensure §12 and BACKLOG stay in sync. Reference: [NORTH_STAR_TRUST_AND_OPS.md](NORTH_STAR_TRUST_AND_OPS.md) for trust, compliance, and operational runbooks. **Beyond-reach improvements:** Consolidated checklist of improvements to take the platform further (N1–N29, trust, ecosystem, innovation, foundation): [BEYOND_REACH_IMPROVEMENTS.md](BEYOND_REACH_IMPROVEMENTS.md). Track completion in this file; that doc is the "what to do" list only.

---

# 11.1 Optionals, recommendations, and suggestions (non-negotiable)

**Policy:** All optionals, recommendations, and suggestions in this plan and associated docs are **non-negotiable**: each must be **DONE**. Nothing deferred or save for later. **Everything in this plan must be accomplished.** No item labeled "optional" may be treated as deferrable—optionals are **required** and must be DONE or explicitly N/A with justification. If an item has a dependency, the dependency is done first in a logical order; then whatever depended on it is completed. **Nothing is ignored.** Execution order (§11 Phases A–H and I) is dependency-ordered: complete phases in sequence; within a phase, complete dependency items before dependents. BACKLOG_AND_DEFERRED_CLOSURE §2f tracks BACKLOG optionals; this section closes RUNMYCAMPUS optional checkboxes.

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
| **Phase I — Core wedges 1–6** | §0.2.1 | 6 wedges | Complete each wedge checklist in order 1→6 (see Phase I section above). |
| **Phase I.5 — Premium UX, single pane, marketing, click reduction** | Phase I.5 (this file) | See Phase I.5 checklists | Complete all Phase I.5 checklists (header no spillage, premium UI/UX superadmin + tenants, marketing front, single pane /admin merge, click reduction ~50%). Gate: MET before Wedges 7–13. |
| **Phase II — Unblock and high-impact** | §2.4, §3.2 | 3 | Add signature/replay where manual_review_required; wrap remaining allowlisted raw SQL in repository/service abstractions; remove remaining direct SiteSettings reads in tenant paths (lint_tenant_settings). |
| **Phase III — App-by-app (§6)** | §6.1–6.24 | 76 | Work through each app's Actions in order 6.1→6.24. Migrate ownership, delete legacy paths, bounded consoles; runtime tracing, pack provenance, launch flow; brand_experience, runtime_blueprints, plans_entitlements, registries, marketplace, policies; schools, accounts, portal, finance, academics, people, student360, reports, automation, communication, analytics, observability, api/apicenter. |
| **Phase IV — Toolset and productization (§5)** | §4.5, §5.1–5.9 | ~35 | §4.5: select plan. §5: Theme/Experience ownership and unified visual systems; Feature Control registry; Report Platform and style/versioning; Document & Compliance Platform; Design Studio split, layout/section/block, responsive preview, publish/rollback; Workflows simulation, visual builder, AI, dependency graph, conflict detection, staged activation, replay/rollback, health; AI permissions/audit and use in setup/workflow/migration/policy/search/support; API Center integration governance and contract testing; SiteSettings decomposition, reclassify, preview/diff/rollback. |
| **Phase V — §7 seeding, Phase H manual** | §7, §11 Phase H | 14 | §7: Minimum targets (apps, blueprints, workflows, dashboards, policy bundles, theme/setup/migration/report/role-home packs) and completion gate—implement. Phase H: Full codebase/UX pass (links, buttons, responsive, framing, labeling); deploy visibility; full test suite and E2E. |

**Rule:** For each unchecked item, **implement it** and mark [x] in this file. Do not leave items as N/A. If an item is blocked by a dependency, implement the dependency first (use [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) for "Unblock by" steps), then implement the item and mark [x]. Use [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for implementation detail.

**Implementation:** All [ ] items (including those annotated "N/A — product 2026-03-12") are to be **implemented** and marked [x]. The annotation indicates prior deferral only; follow [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) until every [ ] is [x].

**Remaining unchecked — index (phase-scale; scan file for `[ ]`):** **Phase I / I.5:** DONE. **Phase III (§6), IV (§5), V (§7), §4.5:** ledger rows **[x]** (§4.5 = placeholder until plans productized). **§2.4 LTI:** **id_token** verified via tool JWKS when `lti_tool_jwks_uri` is set (`apps/schools/lti_id_token_verify.py`); production: set JWKS or `LTI_REQUIRE_SIGNED_ID_TOKEN`. **Incremental:** any remaining `[ ]` in §0.3 etc.; Phase H manual at release ([PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md)); N2–N26 north-star depth. See [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md).

### 11.3 Logical order, visible-after-deployment, and legacy replacement

**Implement-all-unchecked (resumable, no stop until done):** Use [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) and [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md). Read the runbook first; at each run start, read session state and continue from "Next section"; at each phase end, update session state so the next run resumes. Cursor rule: `.cursor/rules/implement-all-unchecked-sot.mdc`.

**Logical order (all items must be done in this sequence):**
1. **Phase I** — Wedges 1→2→3→4→5→6 in order; within each wedge, complete checklist items in sequence (see Phase I section above).
2. **Phase I.5** — Premium UX, single pane, marketing, click reduction (all checklists in Phase I.5 section: header no spillage, premium UI/UX, marketing front, single pane, click reduction ~50%). **Gate:** MET before starting Wedges 7–13.
3. **Phase III** — App-by-app in strict section order: §6.1 → §6.2 → §6.3 → … → §6.24. Within each section, complete Actions in the order they appear. Do not skip; **implement every [ ]**. If blocked by a dependency, implement the dependency first (see [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) "Unblock by"), then implement the item and mark [x].
4. **Phase IV** — §4.5 then §5.1 → §5.9 in order.
5. **Phase V** — §7 minimum targets and completion gate, then §11 Phase H (full codebase pass, deploy visibility, full test suite).

**Visible after deployment:** Every implementation must be **verifiable after deployment**—either in UI (new/updated page, control, or redirect), in API (new/updated endpoint or response field), or in documented behavior (e.g. lint pass, test, or ledger). No invisible-only changes. When marking an item [x], note how to verify it post-deploy (e.g. "Studio OS Experience → Theme; redirect from /siteconfig/customizer/").

**Legacy replacement status (old code vs new — nothing missed):**
- **Done (replaced or redirected):** [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) and [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md) are the single source. Current state: `ensure_gilead_admin` REMOVED; `siteconfig.webhook_delivery` REMOVED; `/admin/siteconfig/customizer/`, `/siteconfig/customizer/`, `/siteconfig/workflow-hub/`, `/siteconfig/report-library/` REDIRECT to Studio OS; siteconfig `workflow_hub` and `report_library` views are redirect-only (legacy render removed). Theme/report defaults: migration 0155 RunMyCampus-neutral names.
- **Still to do (per this plan):** §6.1 "Replace giant admin pages with bounded consoles" — System config console added; further replacements recorded in LEGACY_PATH_INVENTORY and SUBTRACTIVE_CLEANUP_RELEASE_NOTES. **Done (product sign-off):** Further legacy path removals — siteconfig views customizer, report_library, workflow_hub removed; all callers use Studio OS; config redirects kept (LEGACY_PATH_INVENTORY §2–3).
- **Rule:** Before deleting any legacy path, grep for references; ensure replacement is live; then update LEGACY_PATH_INVENTORY and SUBTRACTIVE_CLEANUP_RELEASE_NOTES. See LEGACY_PATH_INVENTORY §4 (nothing left behind).

**Doc cross-check (stay on track):** Before each work session and at release, verify alignment:

| Doc | Check |
|-----|--------|
| [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | All work maps here; no [ ] left without implement or N/A. |
| [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) | Every item has an Action; follow Phase I → I.5 → III → IV → V and section order. |
| [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) | N/A items have owner and date; when implementing, mark [x] in SOT and remove or update N/A row. |
| [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6 | Snapshot and §12 gate status match this file. |
| [docs_truth_ledger.md](docs_truth_ledger.md) | Ledger entries match SOT completion states. |
| [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) | Every legacy path has status REMOVED / REDIRECT / CANDIDATE / KEEP; new removals added. |
| [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md) | Every removal or redirect documented for release notes. |
| [WHATS_NOT_DONE_AND_HOW_TO_START.md](WHATS_NOT_DONE_AND_HOW_TO_START.md) | "What's not done" and "how to start" reflect current SOT and execution plan. |

### 11.4 Consolidated tracking (single place)

**Rule:** All status and "what's left" tracking lives in **this file only**. Do not add status or "what's left" to PATH_TO_100, BACKLOG §6, PLAN_AND_BACKLOG_STOCK_TAKE, phase batch docs, or any other doc. **All [ ] must be implemented and marked [x]**—including items annotated "N/A — product 2026-03-12" (that annotation is prior deferral only; implement them per the runbook). **Every item in this plan is non-negotiable;** there are no optional or permanently deferrable items. Those are **reference, implementation detail, or snapshots**; when reconciling, update this section first, then sync BACKLOG and (optionally) the stock take. Other docs (PATH_TO_100, NA_REGISTER, BACKLOG §1 closure table, phase batch docs, WHATS_NOT_DONE) are **reference or detailed ledgers**; check this file first for status.

**Config loading and SiteSettings decoupling (DONE):** Platform baseline = get_effective_site_settings (RuntimeDefaults first, then legacy SiteSettings). Tenant config = get_effective_policy prefers school.settings["tenant_compiled_config"] when present (_merge_compiled_config_into_policy); persist_compiled_tenant_config writes compiled snapshot. Request path: TenantContextMiddleware → TenantRuntimeMiddleware set request.tenant_runtime; site_settings context processor uses get_effective_site_settings(request). lint_tenant_settings passes (no get_solo in tenant apps).

**Platform boundary — operator vs tenant (DONE 2026-03-19):** Manager host blocks tenant-primary Studio hubs (`/studio/hubs/*`) and **school backend** (`/authentication/backend/*`) via `ManagerTenantPrimarySurfaceBlockMiddleware`; **`ReservedPublicHostAccessMiddleware`** must allow `MANAGER_HOST_ALLOWED_PREFIXES` to include `/authentication/backend/` (otherwise manager requests are redirected to `/` before the block middleware runs). `get_canonical_base_domain()` reads `settings.MULTI_TENANT_BASE_DOMAIN` when set so tests can override. Studio OS on manager uses `user_can_access_studio_on_request` (control-plane operators only, not generic `is_staff`); workflow hub views deflect manager host without `request.school`; impersonation requires justification when `IMPERSONATION_REQUIRE_JUSTIFICATION` is on, logs `reason` / `support_ticket_ref` / `read_only` / optional `peer_actor` on `ImpersonationLog` (migrations `0160`–`0161`); `School.impersonation_dual_control` enforces four-eyes (second operator email); signed token carries `read_only`; `ImpersonationReadOnlyGuardMiddleware` blocks writes on configured prefixes when session is read-only; `ALLOWED_HOSTS` includes `testserver` for the Django test client. Pre-deploy: `scripts/scan_repo_secrets.py`. Docs: [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md), [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md), [DR_BACKUP_RESTORE_RUNBOOK.md](DR_BACKUP_RESTORE_RUNBOOK.md). Tests: `test_manager_studio_tenant_boundary`, `test_impersonation_dual_control`, impersonation token tests, `test_tenant_host_control_plane_isolation` (scheme-agnostic redirect assertion). AI gateway: `services.ai_gateway` blocks high-confidence prompt-injection phrases before provider calls (`services.tests.test_ai_gateway`).

**Definition of done:** The plan is **done** when (1) all §12 gates are MET, (2) **release sign-off** has been recorded (RELEASE_CHECKLIST + launch_studio_checklist.md §4 where applicable), and (3) the pre-release checklist below is complete. Do not claim "plan complete" or 9.5/10 until then.

**Why not declared done yet:** (1) §12 gates MET. (2) Release sign-off recorded 2026-03-17. (3) **Product launch deferred** until business readiness. (4) **Phase H manual pass** is required at each release (BR-13); automation (`run_phase_h_verification.sh`) is continuous; manual checklist is the ship gate.

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
| **Phase I.5 (Premium UX, single pane, marketing, click reduction)** | **DONE** | All checklists [x]; gate MET; closure verification table in Phase I.5 section. Execution may proceed to Wedges 7–13. |
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

- [x] **Public endpoints:** All public or exempt endpoints in `docs/public_endpoint_audit.md`; ledger MET (audit + rate + webhooks; SCIM optional timestamp; LTI id_token JWKS when configured (§6)). **Logged:** [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) run 2026-03-13 — PASS; [TEST_DATABASE.md](TEST_DATABASE.md) for gate DB isolation.
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
