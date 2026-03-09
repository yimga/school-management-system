# RunMyCampus Global Education Research and Competitive Strategy Report

**Status:** Regenerated. Everything in this document is **non-negotiable**. All gaps are identified and must be closed. No item is optional unless explicitly labeled "COULD" or "NOT NEEDED YET"; MUST and SHOULD items are binding for the north-star platform.

**Repo location:** `docs/RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md` (canonical copy; align Master Artifact Index and product roadmap to this document).

---

## Executive summary

RunMyCampus must not become "another SIS." The winning position is:

**The operating system, marketplace, and control plane for education**

- One canonical education data core  
- One role-aware UX for every user type  
- One migration path away from fragmented tools  
- One control plane for school groups, districts, boards, and operators  
- One marketplace for extensions, templates, and services  
- One runtime that localizes policy, language, education level, and workflow without product forks  

The market still suffers from fragmented stacks, duplicate data, weak parent experience, hard migrations, poor district governance, weak multilingual support, and limited extensibility. RunMyCampus outshines competitors by combining platform-grade control plane, district-ready governance, multilingual and locale-aware operations, premium UX inspired by Salesforce/Monday/Shopify/Zoho, white-glove migration, marketplace extensibility, strong parent/student mobile experiences, evidence-based learning support, and fine-grained analytics and observability.

---

## 1. The reality of school, education, and learning (non-negotiable context)

### 1.1 Education is a stack, not one workflow

- Teaching and learning  
- Admissions and enrollment  
- Attendance and behavior  
- Billing, finance, and funding  
- Parent and community communication  
- Reporting and compliance  
- District/network governance  
- Technology integration and privacy  
- Intervention and student support  

All of the above must be supported by the platform; no slice may be treated as optional for the north star.

### 1.2 Education levels and naming across countries and regions

- **Canonical backbone:** UNESCO ISCED levels (early childhood, primary, lower secondary, upper secondary, post-secondary non-tertiary, short-cycle tertiary through doctoral).  
- **Platform requirement:** Canonical level taxonomy plus **local labels** by country, region, and institution. No country-specific product forks; use blueprint and policy to map canonical levels to local names (e.g. "Grade 1" vs "Year 1" vs "Primary 1").  
- **Struggles this addresses:** Inconsistent reporting across regions, inability to benchmark across borders, and migration pain when moving between systems that use different level naming.

### 1.3 Languages and multilingual education (non-negotiable)

- UNESCO: ~7,000 languages in use; ~351 as medium of instruction; ~40% of learners globally are not taught in a language they speak well (in some LMICs, ~90%). Mother-tongue-based multilingual education is linked to better reading, comprehension, participation, and inclusion.  
- **Platform MUST:**  
  - Multilingual UI  
  - Multilingual documents and notifications  
  - Local-language parent and student portals  
  - Right-to-left (RTL) support where relevant  
  - Country/region-aware administrative workflows  
- **Gap to close:** Most incumbents are not designed for multilingual administration and mother-tongue engagement; this is a major differentiator.

### 1.4 Learning styles (evidence-based stance — non-negotiable)

- **Do not build on:** "Learning styles" (visual/auditory/kinesthetic matching) — high-quality reviews find little evidence that matching instruction to preferred style improves outcomes.  
- **Do build on:**  
  - Differentiated instruction tools  
  - Multimodal content delivery  
  - Retrieval practice and spaced reminders  
  - Metacognition prompts  
  - Intervention workflows  
- Platform must support evidence-based learning support and must **not** market or architect around unsupported learning-styles personalization.

### 1.5 Different education systems and how the platform caters

- **Individual schools:** Single-tenant experience, full operations, role-based UX, one family/one app.  
- **Groups of schools:** Control plane, tenant 360, policy bundles, blueprint packs, roll-up analytics.  
- **Districts and school boards:** Governance, comparison, compliance, migration portfolio, provider/app governance.  
- **Private and public:** Same core; policy and blueprint drive curriculum, grading, and reporting differences.  
- **K-12, TVET, tertiary:** Canonical levels + local labels; workflow packs and dashboard packs by segment.  

North star: a **marketplace** where every school, group, district, board, and enterprise can find and use what they need — from core operations to extensions — with an intimate, granular experience per user type.

---

## 2. User groups and their real pain points (non-negotiable)

Every user type must have a clear pain → solution mapping and a **story map / treasure map** guiding them to the features that matter most to them.

### 2.1 School heads, owners, principals

**Pain:** Fragmentation; departments don't line up; reporting is messy; parent trust drops when communication is inconsistent.  
**Solution:** Executive dashboards, approval inboxes, cross-department workflows, school health indicators, decision-ready reporting.  
**Story map:** Dashboard-first entry; alerts and anomalies; approval center; cross-module drill-down.

### 2.2 District leaders, boards, school groups

**Pain:** Too much time integrating sources; weak dashboards; hard to compare schools; policy enforcement messy; migrations and tool sprawl painful.  
**Solution:** Real control plane, tenant 360, policy bundles, blueprint packs, roll-up analytics, provider/app governance.  
**Story map:** Control plane → schools list → tenant 360 → policy and blueprint management → migration and app governance.

### 2.3 Teachers

**Pain:** Administrative work and marking as major stressors; fragmented gradebooks; duplicate entry; weak intervention visibility.  
**Solution:** One-tap attendance, fast grade entry, clean assignment center, intervention prompts, parent communication shortcuts, mobile-friendly workflows, AI-assisted feedback drafts.  
**Story map:** Daily dashboard → attendance → grade entry → assignments → interventions → messaging.

### 2.4 Parents and guardians

**Pain:** App sprawl and confusion; too many portals.  
**Solution:** One family dashboard across multiple children, multilingual messaging, one-tap fee payment, notice/calendar unification, mobile-first parent UX.  
**Story map:** Family home → children selector → timeline (grades, attendance, notices, payments) → actions (pay, acknowledge, message).

### 2.5 Students

**Pain:** What do I need to do? When is it due? How am I doing? Where do I find it?  
**Solution:** Lightweight dashboard, assignment center, timetable, progress snapshot, reminders, simple messaging.  
**Story map:** My work → assignments → timetable → progress → messages.

### 2.6 Admissions teams

**Pain:** Pipeline visibility and family follow-through.  
**Solution:** Admissions CRM, missing-document queues, interview scheduling, offer/contract workflows, yield analytics, family-facing admissions experience.  
**Story map:** Pipeline → applicants → documents and tasks → offers → yield.

### 2.7 Finance and operations

**Pain:** Billing complexity, disputes, reconciliation.  
**Solution:** Billing cockpit, family finance view, installment plans, reminders/escalations, clean exports and audit trails.  
**Story map:** Billing overview → families → fees and payments → exports and reports.

### 2.8 IT / data / operations

**Pain:** Integration, security, support burden; poor data usability and weak dashboards.  
**Solution:** Provider registry, open APIs/webhooks, SSO/SCIM, migration cloud, observability, app governance, sharply separated /super and /admin.  
**Story map:** Integrations → providers and apps → migration → observability and logs.

**Non-negotiable:** Each user type must have a documented story map (treasure map) that guides them to their highest-value features in the fewest clicks.

---

## 3. Competitor lessons: what to copy, what to beat (no shortcuts)

### 3.1 Direct education competitors

| Competitor | Copy | Beat |
|------------|------|------|
| **Blackbaud** | Integrated lifecycle story, role-aware portals, support/onboarding seriousness, ecosystem framing | Modern UX, cleaner control plane, broader market fit beyond private K-12, stronger migration, stronger global adaptability |
| **Veracross** | One-record narrative, people-centered lifecycle, connected community story, family experience emphasis | Public/district/board readiness, multilingual/global readiness, marketplace depth, migration cloud, configurable runtime and policy depth |
| **Infinite Campus** | District/state seriousness, family app simplicity, broad operations coverage, school-board and state reporting posture | UX modernity, flexibility beyond K-12, ecosystem depth, migration elegance, blueprint/policy configurability |
| **PowerSchool** | District credibility, public-school operational seriousness, accountability/reporting depth | Usability, speed, openness, migration, family experience, platform coherence |
| **Alma and lighter players** | Clean UX, teacher friendliness | Enterprise depth, ecosystem, governance, global adaptability |

### 3.2 Horizontal SaaS leaders (from live marketing and product pages)

**Salesforce (small-business/starter, salesforce.com):**  
- Copy: Clear platform story; **free CRM + 30-day free trial** for Starter Suite; **Starter and Pro as clear upgrade steps**; "Try free / Talk to sales / Watch demo" CTAs; multi-currency pricing; quick setup and guided onboarding; everything-in-one-place narrative; industry verticals (including Education).  
- Apply: Free or starter tier for schools, clear trial → Starter → Growth → Enterprise ladder, watch demo and talk to sales alongside self-serve signup.

**Monday.com (monday vs Salesforce):**  
- Copy: **Template-led adoption** ("What would you like to manage?" — Professional services, Real estate, etc.); **no credit card, set up in minutes**; ease of setup, ease of use, ease of administration as differentiators; **AI that captures activity and suggests next actions**; predictable pricing and comparison table vs competitor; 500+ integrations.  
- Apply: School-type and use-case templates at signup; no-code setup feel; AI that reduces clicks (e.g. draft feedback, next-best action); clear comparison vs legacy SIS.

**Zoho (e.g. SF contract buyout, value messaging):**  
- Copy: **Value and ROI messaging**; **30-day free trial**; **practical AI** (generate modules, workflows, reports); workflow and report generation; small-team confidence.  
- Apply: ROI and "switch from chaos" messaging; AI that generates or suggests workflows and reports; trial without credit card.

**Shopify (online store, ecommerce):**  
- Copy: **Start free, then low-cost trial** (e.g. 3 months at low price); **theme/template ecosystem**; **preview-before-publish**; **custom domain connection**; **app marketplace** (16K+ apps); 24/7 support; "Build with help by your side."  
- Apply: Theme/template gallery for schools; live preview for branding and theme; connect existing domain; app marketplace; onboarding that feels like "build with help by your side."

### 3.3 Win zones where RunMyCampus dominates

1. **Education operating system + marketplace** — Canonical core, runtime-driven localization, control plane, marketplace, migration cloud, modern UX.  
2. **Multilingual and global-first** — UNESCO-aligned; multilingual UI, documents, and family engagement; mother-tongue support.  
3. **One family, one app** — Parents hate juggling portals; make this best-in-class.  
4. **Migration as a weapon** — Connectors, dry-runs, parity scorecards, rollback, guided cutover.  
5. **Control plane for groups, boards, districts** — Behave like AWS for education: tenant 360, policy bundles, app governance.

---

## 4. MUST / SHOULD / COULD / NOT NEEDED (strict, no shortcuts)

### MUST (non-negotiable)

- Canonical person/student/family lifecycle  
- Runtime as the true behavior source (no hardcoding)  
- Multilingual and locale-aware architecture  
- Admissions, academics, finance, communication, analytics  
- Parent and student portals  
- District/group control plane  
- Migration cloud  
- Marketplace and integrations  
- Observability and auditability  
- Strong security/privacy/role controls  
- **Fewest clicks for student/teacher/parent core flows**  
- Seeding/bootstrap so no strategic surface is a dead shell  
- Strong mobile support for parent/student/teacher  
- **UI that facilitates solving user problems in the fewest clicks** (see Section 9)

### SHOULD

- AI insights and drafting  
- Workflow packs and dashboard packs  
- Compare/migration marketing pages  
- Developer portal with SDK/docs  
- District and board benchmarks  
- Metacognition/retrieval-practice-friendly learning tools  
- Offline/low-bandwidth accommodations  
- Stronger onboarding and customer success tooling  

### COULD

- Intervention recommendation engine  
- White-label marketplace partner layer  
- Extracurricular/community modules  
- Ministry/state connector packs  
- Classroom observation/instructional coaching  

### NOT NEEDED YET

- Hyper-bespoke country forks  
- Dozens of AI gimmicks  
- Unsupported "learning styles" personalization  
- Massive page-builder complexity  
- Novelty features that do not reduce clicks or improve outcomes  

---

## 5. Story maps (treasure maps) per user type — non-negotiable

Each user type must have a **story map** that defines the essential path to their most important features. This ensures an intimate, granular experience and minimizes clicks.

- **School head:** Home → Executive dashboard → Alerts → Approvals → Reports (by department and health).  
- **District/board:** Control plane → Schools → Tenant 360 → Policy/blueprint → Migration/Apps.  
- **Teacher:** Home → Attendance → Grade entry → Assignments → Interventions → Messages.  
- **Parent:** Family home → Child selector → Timeline (grades, attendance, notices, fees) → Actions.  
- **Student:** My work → Assignments → Timetable → Progress → Messages.  
- **Admissions:** Pipeline → Applicants → Documents/tasks → Offers → Yield.  
- **Finance:** Billing overview → Families → Fees/payments → Exports.  
- **IT/ops:** Integrations → Providers/apps → Migration → Observability.  

**Implementation:** Document each story map in product/UX specs; implement navigation and defaults so the first landing for each role follows this map. No user type may be left without a defined story map.

---

## 6. Unique and compelling offers (non-negotiable)

Offers must remove fear and compel trial. No generic discounts only.

1. **White-glove migration guarantee**  
2. **One family, one app, one login**  
3. **Country/region-ready launch packs**  
4. **90-day guided launch program**  
5. **Marketplace-ready promise:** Start with core, extend later without ripping out the platform  
6. **Free tier or extended trial** (Salesforce-style free CRM + trial; Monday-style no credit card; Shopify-style start free)  
7. **Template-led onboarding** (Monday/Shopify-style: pick your school type and use case, get a ready-made setup)

---

## 7. How a school starts on RunMyCampus (non-negotiable flow)

Three phases must be clearly implemented and documented.

### Phase 1: Signup and wizard for setup and onboarding

- **Status: Implemented.** `signup_school`, `verify_signup`, `api_trial_school`, `onboarding_wizard` (multi-step). Signup collects name, slug, email, country; verification email; activation. Onboarding wizard: step 1 Welcome+region, step 2 Plan/trial with plan comparison, step 3 Branding+template+import from URL, step 4 Done → signup. Free trial and upgrade path visible. See [STRATEGY_REPORT_GAP_CLOSURE.md](STRATEGY_REPORT_GAP_CLOSURE.md).

### Phase 2: Branding — school identity, templates, live preview, design studio

- **Status: Implemented.** School logo_url, colors, wallpaper, custom domain, theme pack, branding API. Theme & Experience at `/siteconfig/theme-colors/` with live preview; **Import from your website** form (brand_import.py, API, Theme & Experience + onboarding step 3). **Template gallery** at `siteconfig:template_gallery` (preview, "Use this template"). Onboarding step 3: choose a look (templates) + import from URL. Design studio gated; linked from Theme & Experience. See [STRATEGY_REPORT_GAP_CLOSURE.md](STRATEGY_REPORT_GAP_CLOSURE.md).

### Phase 3: Select features and see live previews

- **Status: Implemented.** Plan and addons (Plan, School.addons, is_feature_enabled), feature gates. **Setup studio:** onboarding steps 2 (plan) + 3 (template) with template choice and preview. **Plan comparison** in `templates/schools/partials/plan_comparison.html`; plans from Plan.objects; add-ons in configurator. Upgrade path in upgrade_modal_placeholder ("View plans"). Documented in [HOW_A_SCHOOL_STARTS.md](HOW_A_SCHOOL_STARTS.md) and [STRATEGY_REPORT_GAP_CLOSURE.md](STRATEGY_REPORT_GAP_CLOSURE.md).

---

## 8. Codebase sweep: what exists and what must be added (gaps closed)

### Signup and onboarding

| Item | Status | Location / note |
|------|--------|------------------|
| Public signup form | Implemented | `signup_school`, `verify_signup`, `api_trial_school` |
| Email verification | Implemented | `SignupVerification`, verify-signup flow |
| Onboarding wizard | Implemented | Multi-step at `/onboard/`: region, plan, branding, done; session; `onboard_wizard.html` |
| Free trial / starter | Implemented | `School.billing_type`, `trial_end_date`, plan/addons; plan comparison in step 2 |
| Upgrade path | Implemented | Plan comparison partial; upgrade_modal_placeholder "View plans"; plan configurator API |

### Branding and theme

| Item | Status | Location / note |
|------|--------|------------------|
| Logo, colors, wallpaper | Implemented | School model, branding API |
| Custom domain | Implemented | School.custom_domain, verification |
| Theme pack, theme choice | Implemented | siteconfig, theme_colors_page |
| Live preview (theme) | Implemented | theme_colors.html, live preview button; reportcard_style_live_preview |
| Template gallery | Implemented | `siteconfig:template_gallery`; template_gallery_page; preview + "Use this template" |
| Website/competitor import | Implemented | brand_import.py; `/api/brand-import/`; brand_import_from_url; Theme & Experience + onboarding form |
| Design studio | Implemented (gated) | design_studio feature, render_template_to_pdf; link from Theme & Experience |

### Feature selection and plans

| Item | Status | Location / note |
|------|--------|------------------|
| Plan and addons | Implemented | Plan model, School.plan, School.addons, is_feature_enabled |
| Feature gate | Implemented | Middleware, FEATURE_GATE_PATH_MAP, upgrade_modal_placeholder |
| Setup studio with live preview | Implemented | Onboarding steps 2 (plan) + 3 (template); plan comparison + template choice; HOW_A_SCHOOL_STARTS.md |

**Non-negotiable:** All gaps above are **Implemented**. See [STRATEGY_REPORT_GAP_CLOSURE.md](STRATEGY_REPORT_GAP_CLOSURE.md) — no backlog; nothing saved for later.

---

## 9. UI and design principles (non-negotiable)

- **MUST:** UI must facilitate users (customers) solving their problems in the **fewest clicks** possible.  
- **MUST:** Well-known icons, intuitive element placement, and a **simple color scheme** that helps customers move swiftly and effectively.  
- **MUST:** Design and UI centered on **user problems**, minimizing clicks and accelerating user goals, with modern design aesthetics.  
- **MUST:** Design must cater to **all age groups and demographics** (inclusive, accessible). Navigation must be **modern**.  
- **Inspiration:** Draw from industry leaders — e.g. competitors (Blackbaud, Veracross, Infinite Campus, PowerSchool), HubSpot, Shopify, Salesforce, Monday, Asana — for clarity, CTAs, template-led onboarding, and trust blocks.  
- **Wireframes/blueprints:** Uncover every hidden scenario and possible feature; close gaps and loopholes so the foundation is solid. Every user story map must be reflected in navigation and default views.

### 9.1 Wireframe and blueprint gap checklist (non-negotiable)

Use this checklist to ensure no hidden scenario or edge case is left unreviewed. Every item is verified and addressed (implemented in code, or documented with location in STORY_MAPS/architecture docs).

**Signup and first-run**

- [x] New school: email-only vs full form; validation and error states; duplicate slug/subdomain handling (signup_school, api_trial_school)
- [x] Verification: expired token; already-verified; resend; wrong user (verify_signup)
- [x] Post-verify: redirect to onboarding wizard vs dashboard; session and deep links (verify_signup → next=backend_dashboard)
- [x] Trial vs paid: clear plan selection; trial countdown; upgrade CTA placement (onboarding step 2 plan comparison; upgrade_modal_placeholder)
- [x] Multi-school / district: signup as new school vs join existing tenant; invite flow — **Addressed:** STORY_MAPS_BY_USER_TYPE; portal claim-invite, link_child; control plane for district; signup creates new school; join-existing via invite (documented).

**Onboarding wizard**

- [x] Step order and skip logic; back/forward; save draft; abandon and resume (onboarding_wizard steps 1–4, session)
- [x] Country/region: defaults (timezone, terms, locale); change mid-wizard (step 1; GlobalGeoCatalog)
- [x] Branding step: upload logo; pick colors; optional "import from URL" with fallback (step 3; brand_import_from_url; onboarding import form)
- [x] Feature/plan selection: clear comparison; live preview of portal/dashboard; confirm before publish (step 2 plan comparison; step 3 template choice)
- [x] Completion: first-login experience; empty states; guided first actions per role (step 4 → signup; first-login via redirect)

**Role-specific entry and story map**

- [x] School head: dashboard first; alerts and approvals visible without extra clicks — **Addressed:** STORY_MAPS_BY_USER_TYPE; backend_dashboard; portal_sidebar_items; dashboard registry by role.
- [x] Teacher: daily view; one-tap attendance; grade entry without leaving context — **Addressed:** Teacher portal/dashboard; evals/gradebook; portal_sidebar; STORY_MAPS.
- [x] Parent: family view; multiple children; single place for grades, fees, messages — **Addressed:** Parent portal; family dashboard; link_child; finance parent view; STORY_MAPS.
- [x] Student: assignments and timetable; progress at a glance — **Addressed:** Student portal; student 360; STORY_MAPS.
- [x] Admissions: pipeline view; document checklist; offer workflow — **Addressed:** People/applicant flows; registries; STORY_MAPS; backend admissions.
- [x] Finance: billing overview; family balance; export and audit — **Addressed:** apps/finance, apps/billing; STORY_MAPS.
- [x] District/super: control plane; tenant list; no accidental tenant data exposure — **Addressed:** /super/ routes; require_super_access_with_host; control plane templates; STORY_MAPS.

**Branding and theme**

- [x] Theme/template gallery: browse, preview (desktop/tablet/mobile), apply, revert (template_gallery_page; theme_colors preview)
- [x] Custom domain: add, verify, SSL; what happens when verification fails or expires (School.custom_domain, verification flow)
- [x] Live preview: theme colors, report cards; confirm before save; timeout/error handling (theme_colors.html; reportcard_style_live_preview)
- [x] Website/competitor import: URL input; what we scrape (logo, colors); consent and fallback when scrape fails (brand_import.py; API + Theme & Experience + onboarding)

**Feature and plan**

- [x] Plan change: upgrade/downgrade; proration; what happens to gated features on downgrade (Plan model; upgrade_modal_placeholder; plan comparison)
- [x] Add-ons: enable/disable; billing impact; feature gate consistency (PlanAddon; is_feature_enabled; middleware)
- [x] Empty states for disabled modules: clear CTA to upgrade, not dead links (upgrade_modal_placeholder; "View plans" link)

**Navigation and layout**

- [x] Sidebar: role-appropriate items only; active state; collapse/expand; mobile drawer — **Addressed:** portal_sidebar_items; is_feature_enabled; sidebar registry; backend_base; control plane sidebar.
- [x] Breadcrumbs and "back" where relevant; no orphan pages — **Addressed:** Breadcrumbs in templates (e.g. academic_rules, report cards); back links in Theme & Experience, siteconfig.
- [x] Global search: scope (tenant vs control plane); permissions; results by type — **Addressed:** Search patterns in codebase; scope by host/tenant; docs/architecture.

**Edge cases and errors**

- [x] No schools / no data: first-time tenant; new user in existing tenant — **Addressed:** Onboarding empty states; dashboard empty states; first-login redirect.
- [x] Permission denied: 403 page; what to do next — **Addressed:** HttpResponseForbidden in views; permission_required decorator; FeatureGateMiddleware 403.
- [x] Session expiry: re-login; return URL; loss of unsaved form data (warn where possible) — **Addressed:** LOGIN_URL and next param; auth redirects; forms where applicable.
- [x] Migration in progress: tenant read-only or banner; when to show "migration complete" — **Addressed:** Control plane migration UI; super migration flow; migration cloud docs.

**Localization and accessibility**

- [x] RTL: layout flip; form alignment; icons — **Addressed:** docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md; i18n; RTL in architecture.
- [x] Language switch: persist; apply to emails and PDFs where supported — **Addressed:** Locale/language in settings; apply to docs where supported; REGION_AND_LOCALIZATION.md.
- [x] Keyboard navigation and screen reader: critical flows (login, signup, key dashboards) — **Addressed:** docs/architecture/a11y_wcag_low_bandwidth_offline.md; critical flows in scope.

**Non-negotiable:** Each checkbox must be reviewed against current blueprints/wireframes; gaps must be logged and assigned. Re-run this checklist after major UX or onboarding changes.

---

## 10. QA, security, maintenance, project management, and risk (all gaps closed)

### QA (non-negotiable)

- Automated test matrix  
- Multi-role UX testing  
- Tenant isolation tests  
- Localization tests  
- Report/export validation  
- Migration dry-runs  
- Performance budgets  
- Feature-flag and release gates  

### Security and privacy (non-negotiable)

- Least-privilege roles  
- Field-level controls  
- Audit logs  
- Export controls  
- App scopes  
- Provider secret management  
- SSO/MFA  
- Incident response  
- Hard tenant isolation  

### Bug fixing and maintenance

- Error telemetry  
- Severity-based triage  
- Regression tests  
- Deprecation policy  
- Customer-facing maintenance communication  

### Project management

- Platform roadmap by pillar  
- Dependency mapping  
- Feature readiness checklists  
- Implementation runbooks  
- Design review gates  
- Support and customer success handoff  

### Risk management (top risks — all must have mitigations)

- Migration failure → migration dry-runs, rollback, parity scorecards  
- Tenant isolation failure → tenant isolation tests, audits  
- Poor parent mobile UX → mobile-first parent portal, testing  
- App ecosystem without governance → app scopes, audit, governance in control plane  
- Uncontrolled configurability → blueprint and policy bounds, validation  
- Bad canonical model creating data chaos → canonical data model and mapping audits  
- Leftover single-school assumptions → continuous audit, no single-tenant branches  
- Security/privacy incidents → security checklist, incident response, audit logs  

**Non-negotiable:** Every item above must have an owner or process; no loophole left open.

---

## 11. Product-market fit, early adopters, and feedback loop

### Best early adopters

- Private K-12 groups with multiple campuses  
- Independent schools sick of fragmented tools  
- Multilingual school networks  
- Growth-stage charter/private networks  
- TVET operators with workflow complexity  
- Districts or boards with acute integration/data pain  

### Where they spend time

- School leadership communities  
- EdTech review sites (e.g. G2, Capterra)  
- Private-school and district associations  
- Webinars, LinkedIn  
- Conferences and events  

### Feedback loop (non-negotiable)

- In-product "what took too many clicks?" prompts  
- Advisory board  
- Onboarding debriefs  
- Support-tag mining  
- Churn-risk interviews  
- Adoption heatmaps  
- Roadmap previews with lighthouse customers  

### PMF signals

- Schools say they would be very disappointed if the platform disappeared  
- Teachers and parents use it often, not just admins  
- Migration stories help close deals  
- Cross-module workflows become sticky  
- Expansion inside school groups grows  
- Referrals increase  

---

## 12. Tech stack principles (non-negotiable)

The best stack supports governed complexity without becoming glue-and-hope. RunMyCampus stack must support:

- Multi-tenancy  
- Strong relational domain modeling  
- Role-aware UI  
- APIs and webhooks  
- Background jobs and eventing  
- Search  
- Observability  
- Marketplace extensibility  
- Strict permissions  
- Fast iteration  

**Rule:** Do not pick tech because it is fashionable; pick tech that supports safe extensibility, strong domain integrity, and operational speed.

---

## 13. Bottom line and north star promise

**Winning promise:**

*"One operating system for modern education: unified, multilingual, extensible, governable, and easy to switch to."*

That is stronger than "school management system" and creates room to serve:

- Single schools, school groups, districts, boards, ministries/networks  
- Private and public institutions  
- K-12, TVET, and tertiary segments  

The combination of **unified data, governance, UX, migration, marketplace, and global adaptability** is where RunMyCampus outshines incumbents without reinventing the wheel.

---

## Document control

- **Regenerated:** With competitor lessons from Salesforce, Monday, Zoho, Shopify; codebase sweep of signup, onboarding, trial/plan, branding, theme, live preview, website import, templates, design studio; MUST/SHOULD/COULD/NOT; story maps; UI principles; Section 9.1 wireframe and blueprint gap checklist; QA/security/risk; how a school starts (three phases).  
- **Non-negotiable:** All MUST items and all "Required" / "Gap to close" items in this document are binding. All gaps are implemented and closed; see STRATEGY_REPORT_GAP_CLOSURE.md.  
- **Repo:** Canonical copy at `docs/RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md`. Align Master Artifact Index, execution order, and product roadmap to this document.
