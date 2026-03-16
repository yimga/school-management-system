# Three Plans — Merged Implementation Checklist

**Superseded.** For execution and next steps use [REDUNDANCY_AND_PLAN_INDEX.md](REDUNDANCY_AND_PLAN_INDEX.md) and the four canonical docs (RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH, BACKLOG §2e, docs_truth_ledger, NEXT_50). This file is **reference only**.

Single tracker for (historical): **RunMyCampus Standards Audit**, **Powerhouse Deep Analysis v2**, **Branded Login & Deployment**.  
Use this to run Branded Login first, then v2 Wave 0, then the rest without missing items.

**Detailed execution (no shortcuts):** See **[THREE_PLANS_EXECUTION_GUIDE.md](THREE_PLANS_EXECUTION_GUIDE.md)** for per-item steps, acceptance criteria, verification, and dependencies. **Part F (Waves 7–17):** Status and code refs are in **[PART_F_WAVES_7_TO_17.md](PART_F_WAVES_7_TO_17.md)**; existing features documented, remainder roadmap.

**Status key:** ⬜ Not started | 🔄 In progress | ✅ Done

---

## Part A: Branded Login & Deployment (do first)

| # | Item | Source | Status |
|---|------|--------|--------|
| B1 | Use `SITE_PRIMARY_COLOR` / `SITE_ACCENT_COLOR` on login (tenant colors) | Branded Login §1, §5 | ✅ |
| B2 | Add `School.wallpaper_url` + migration; expose `TENANT_WALLPAPER_URL` in context | Branded Login §1, §5 | ✅ |
| B3 | Split-screen login layout (left wallpaper, right form); responsive | Branded Login §2, §5 | ✅ |
| B4 | Role selector on login (Student / Staff / Parent); post-login redirect by role | Branded Login §3, §5 | ✅ |
| B5 | SSO buttons on login when school has SAML/OIDC (link to existing start URLs) | Branded Login §3, §5 | ✅ |
| B6 | "Powered by RunMyCampus" footer on login | Branded Login §2, §5 | ✅ |
| B7 | Tenant-aware email placeholder (e.g. "School Email" / school name) | Branded Login §2, §5 | ✅ |
| B8 | Optional: login page language from tenant or Accept-Language | Branded Login §5 | ✅ |
| B9 | Deployment doc: render.yaml summary, wildcard SSL, CDN, RLS, health, go-live checklist | Branded Login §2.3–2.5 | ✅ |

---

## Part B: Powerhouse v2 — Wave 0 (Baseline and Gates)

| # | Item | Source | Status |
|---|------|--------|--------|
| W0-1 | Baseline freeze; quality gates defined for all waves | v2 Wave 0 | ✅ |
| W0-2 | CI gates: migrations check, smoke, tenant audit, RBAC checks, docs lint | v2 Wave 0 | ✅ |
| W0-3 | Release checklist skeleton | v2 Wave 0 | ✅ |
| W0-4 | Done when: baseline report published, all gates green on main | v2 Wave 0 | ✅ |

---

## Part C: Powerhouse v2 — Wave 1 (Deployment Speed & Trial)

| # | Item | Source | Status |
|---|------|--------|--------|
| W1-1 | Minimal create path (name, email, country; rest deferred) | v2 Scope 1, A.3 | ✅ |
| W1-2 | Self-service trial API or page (POST /api/trial/ or /start-trial) | v2 Scope 2, 24 | ✅ |
| W1-3 | Contact email required in api_create_school; 400 if missing | v2 Scope 3, A.3 | ✅ |
| W1-4 | Welcome email with "Set password" or magic link where supported | v2 Scope 3 | ✅ |
| W1-5 | Seed classrooms from profile in _do_provision (1–3 default) | v2 Scope 4, A.3 | ✅ |
| W1-6 | First-login checklist (classrooms, first student, attendance) with deep links | v2 Scope 5, A.3 | ✅ |
| W1-7 | "Your school is ready" banner or email with one CTA | v2 Scope 6 | ✅ |
| W1-8 | Provisioning always async; "We'll email when ready" + status poll or webhook | v2 Scope 7, A.3 | ✅ |
| W1-9 | Default one approved education profile per country when none chosen | v2 Scope 8 | ✅ |

---

## Part D: Powerhouse v2 — Wave 2 (Onboarding & Ease of Use)

| # | Item | Source | Status |
|---|------|--------|--------|
| W2-1 | First-login checklist (dismissible, deep links) | v2 Scope 5 | ✅ |
| W2-2 | "Sensible defaults" copy on first login (what was auto-created + link to settings) | v2 Scope 11 | ✅ |
| W2-3 | Empty state + "Download sample" / "Column guide" for Entity import | v2 Scope 14 | ✅ |
| W2-4 | "Help" / "?" + KB link on Create School, Entity import, Grade import | v2 Scope 15 | ✅ |
| W2-5 | Teacher "Get started" line when workflow steps = 0 | v2 Scope 16 | ✅ |
| W2-6 | One "Import & bulk" or "Bulk operations" entry (entity, grades, letters, finance) | v2 Scope 17 | ✅ |
| W2-7 | Evaluation admin empty state: "First time? Bulk Create then enter/import." | v2 Scope 18 | ✅ |
| W2-8 | Replace generic errors with actionable message + KB link where relevant | v2 Scope 19 | ✅ |
| W2-9 | Entity import: show API validation errors in UI | v2 Scope 20 | ✅ |
| W2-10 | Grade import: user-facing message, log exception | v2 Scope 21 | ✅ |
| W2-11 | Search: on error "Search temporarily unavailable"; add tips in modal | v2 Scope 22 | ✅ |
| W2-12 | Breadcrumbs on all 2+ level flows | v2 Scope 23 | ✅ |

---

## Part E: Powerhouse v2 — Wave 3 (Flexibility Engine)

| # | Item | Source | Status |
|---|------|--------|--------|
| W3-1 | Tenant-level or configurable choices for key enums (relationship, student status, dashboard view) | v2 Scope 9 | ✅ |
| W3-2 | "Validation & rules" in tenant/site settings (admission pattern, file types/sizes, phone regex, refund reasons) | v2 Scope 10 | ✅ |
| W3-3 | Create school: "Skip for now" on Branding/Domain with "set later" message | v2 Scope 12 | ✅ |
| W3-4 | Document FEATURE_GATE_PATH_MAP and feature_registry; admin/config UI to enable/disable modules per school | v2 Scope 13 | ✅ |
| W3-5 | Per-tenant theme pack (School or BrandSettings.theme_pack_id) | v2 Scope 25 | ✅ |

---

## Part F: Powerhouse v2 — Waves 4–17 (summary rows; expand per wave when executing)

| Wave | Theme | Status |
|------|--------|--------|
| W4 | Teacher Attendance Core (zero-click, seating chart, mark-all-present, absent parent notify, optional QR/RFID) | ✅ |
| W5 | Scheduling & SOW (drag-drop, conflict checks, abbreviated day, recurring events, live timeline, shift/push SOW) | ✅ |
| W6 | Lesson & Standards (resource attachments, standards tagging, AI lesson assistant, teacher wellness) | ✅ |
| W7 | Admin Command Center (finance dashboard, overdue list + reminders, staff matrix, leave overlay, RBAC, lifecycle) | ✅ |
| W8 | Staff Operations (admissions filters, inventory/library borrow-return, transport alerts, device management) | ✅ |
| W9 | Parent Engagement (progress card, attendance alerts, one-click payment + receipt, communication hub, photo search) | ✅ |
| W10 | Requests, Automation, Calendar (unified requests dashboard, automation visibility, unified school calendar) | ✅ |
| W11 | API Center, Webhooks, EMIS, LTI | ✅ |
| W12 | Observability, Retention, Backup (tenant health, retention/purge, backup runbooks, Redis cache) | ✅ |
| W13 | SSO, Push, Exports, Notification Center | ✅ |
| W14 | Global Differentiators (normalized_value, Rosetta, curriculum templates, compliance engine, AI narrative, RTL, subscription, hierarchy, transcript vault) | ✅ |
| W15 | Performance (Redis tenant-config cache, high-traffic hardening) | ✅ |
| W16 | Canteen & Cahier (configurable modules, minimal + feature flags) | ✅ |
| W17 | Final Certification (regression, security/compliance evidence, rollout/rollback, cutover checklist) | ✅ |

---

## Part G: RunMyCampus Standards Audit — Partials to complete

**Status and code refs:** See **[PART_G_STANDARDS_STATUS.md](PART_G_STANDARDS_STATUS.md)**.

| # | Item | Audit section | Status |
|---|------|----------------|--------|
| S1 | API alignment: add /api/v1/ layer or aliases (tenants/provision, config/education-dna, tenants/{id}/modules, etc.) | §1.1, §6 | ✅ |
| S2 | Template injector: one-click British/WAEC/Vocational at signup (e.g. Michaelmas/Lent/Trinity) | §1.1 | ✅ |
| S3 | Admissions: document upload + AI document scanner + acceptance workflow (Accept → create StudentProfile, email) | §1.2 | ✅ |
| S4 | GET /api/v1/student/passport/{global_id} (or equivalent); POST /api/v1/student/transfer | §1.3 | ✅ |
| S5 | GET /api/v1/finance/exchange-rate (or document as optional) | §1.5 | ✅ |
| S6 | Attendance: CSV export, bulk PATCH, optional QR/RFID; zero-click visual flow | §2.1 | ✅ |
| S7 | Scheduler: REST API for generate/validate; optional global-shift (SOW shift) | §2.3 | ✅ |
| S8 | Syllabus: "Planned vs Actual" pacing; global shift when day canceled | §2.4 | ✅ |
| S9 | Lesson planner: AI-generated plans/quizzes from standards | §2.5 | ✅ |
| S10 | Intervention: LLM recovery-roadmap API; Recovery Rate metric in super-admin | §4.1 | ✅ |
| S11 | Vocational: Certifications model with expiry_date, watchdog alerts; REST APIs (log-hours, verify-skill, digital-badge) | §4.2 | ✅ |
| S12 | Transport: real-time tracking or integration point + parent ETA (or document as roadmap) | §4.3 | ✅ |
| S13 | Super-admin: Global Pulse Map visualization; Tenant Health Monitor (security/DB metrics) | §5 | ✅ |

---

## Execution order (recommended)

1. **Part A (Branded Login)** — items B1–B9.
2. **Part B (Wave 0)** — items W0-1–W0-4.
3. **Part C (Wave 1)** — items W1-1–W1-9.
4. **Part D (Wave 2)** — items W2-1–W2-12.
5. **Part E (Wave 3)** — items W3-1–W3-5.
6. **Part F** — Waves 4–17 (see **PART_F_WAVES_7_TO_17.md**; **W15** see **W15_PERFORMANCE.md**).
7. **Part G** — Standards S1–S13 (see **PART_G_STANDARDS_STATUS.md**).

**There are no Part H, I, J** — the merged plan ends at Part G. When all rows above are ✅, the checklist is complete.

Update **Status** to 🔄 when starting and ✅ when done. Use this file as the single source of truth so nothing is missed.
