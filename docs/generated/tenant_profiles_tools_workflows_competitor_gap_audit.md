# Tenant Profiles, Tools, Workflows, Configs Competitor Gap Audit

Generated: 2026-05-24

Scope: repo audit over tenant identity/configuration, Setup Studio, local experience profiles, template marketplace, workflow audit outputs, tenant URL surface, AI tenant studio evidence, and public competitor positioning. This is an audit and improvement direction, not a claim of live production rollout.

## Evidence Used

Local evidence:

- `apps/schools/models.py`: `School` is the tenant record, with country, data region, language, settings/features, plan/addons, workflow/dashboard defaults, school type, brand colors, custom domain, and lifecycle fields.
- `apps/setup_studio/services.py`: Setup Studio has a 9-step launch path including blueprint, branding, experience template, starter stack, data import, role preview, launch checklist, launch blockers, and readiness scoring.
- `apps/siteconfig/local_experience_profiles.py`: 50 `LocalExperienceProfile` entries across 48 countries, with currency and payment rail defaults.
- `apps/brand_experience/experience_templates.py`: 150 `ExperienceTemplateOverlay` entries, including 50 local-first templates and 10 mobile-first overlays.
- `docs/generated/tenant_workflow_gear_up_audit.md`: 27 tenant workflows audited, with explicit strong areas and fix-first gaps.
- `docs/generated/tenant_studio_onboarding_audit_first_teardown.md`: simplicity is `acceptable_improving`, with `medium_studio_os_vs_siteconfig_onboarding` fragmentation risk.
- `docs/generated/ai_tenant_studio_final_certification.md`: AI Center and Tenant Studio are ready in focused repo scope, with no live Ollama or complete RAG claim.

Competitor baseline checked from official pages:

- PowerSchool SIS: configurable SIS, parent/student portals, mobile app, integrated analytics, LMS, online registration/forms, state reporting, partner ecosystem, support community.
- Infinite Campus: all-in-one SIS/LMS/food service/communication/registration/payments/workflow/analytics in one login, one parent/student app, role coverage for staff/teachers/students/parents/admin.
- Veracross: one-person, one-record platform across academics, admissions, development, business, tuition, health, portals, and API/integrations.
- Blackbaud K-12: enrollment, billing, SIS, LMS, family portal, assignment center, gradebook shortcuts, flexible grading.
- Classe365: CRM/enrollment, SIS, LMS, finance/accounting, ecommerce, fundraising, alumni, AI assistance, 6000+ institutions in 130 countries.
- FACTS SIS: teacher ease around attendance, family contact, grades, and classroom planning; payment plans tied to academic workflows.
- ManageBac: curriculum planning, analytics, assessment, reporting, attendance, portfolios, mobile access, parent portal local language interface.

## Current Strengths To Preserve

1. Tenant identity is a real operating kernel, not a loose profile table. `School` already carries region, language, data residency, plan/addons, workflow defaults, dashboard defaults, theme, school type, custom domain, and lifecycle state.
2. Setup Studio is better than many SIS onboarding flows because it has a launch sequence, readiness score, role preview, blockers, and launch enforcement instead of only settings pages.
3. Template depth is a serious asset: 150 templates, 50 local-first profiles, 10 layout families, palette/typography/accessibility/mobile metadata, and rollback-compatible pack lifecycle.
4. Local-first posture is ahead of many US-centric SIS systems: profiles include local currencies, grading systems, calendars, languages, payment rails, and low-connectivity defaults.
5. Offline/manual fallback is a strategic differentiator for underbanked or low-connectivity markets.
6. Tenant sovereignty and brand guard evidence is strong: theme meta bridges, sync bootstrap, brand guard runtime, and theme builder gates are already passing.
7. AI routing is structured and policy-aware enough to avoid exposing manager internals to tenant prompts.

## Main Gaps Against Competitors

### 1. The tenant experience is still fragmented compared with one-login competitors.

Competitors sell one clear operating home: Infinite Campus emphasizes one login for SIS, LMS, communication, registration, payments, workflow, analytics, and more. Veracross sells one person/one record. Your repo has the underlying pieces, but tenant routes still split school admins across `/school/studio/`, `/siteconfig/onboarding/`, `/school/setup/*`, `/settings/app-catalog/`, finance, reports, and siteconfig pages.

Evidence: `tenant_workflow_gear_up_audit.md` flags silent redirects, sibling setup pages without shared readiness, and 5 sibling `/school/studio/<sub>/` redirects.

Improve:

- Make `/school/studio/` the canonical tenant command center for every school admin workflow.
- Convert `/school/setup/blueprints/`, `/school/setup/packs/`, and `/school/setup/imports/` into cards or tabs inside one setup workspace with one progress rail.
- Replace redirect-only import flow with a real import landing: CSV templates, sample files, import history, migration-cloud handoff, last error, and next action.
- Add one universal tenant command bar: search modules, people, settings, imports, invoices, reports, templates, help.

### 2. Role-specific portals are not equally mature.

Teacher and admin surfaces are stronger than parent/student. Competitors put heavy emphasis on parent/student mobile portals. PowerSchool and Infinite Campus specifically sell mobile and family access; Blackbaud and FACTS emphasize family/teacher ease.

Evidence: tenant role coverage says school admin has 19 workflows, teacher has key workflows, parent is mostly invoice/help/feedback/feature center, and student workflows are read-mostly.

Improve:

- Parent portal should become a true family operating app: child switcher, fees, receipts, attendance, behavior, reports, messaging, consent forms, document requests, events, transport, pickup, and offline/SMS fallback.
- Student portal should move beyond read-only: assignments, study tasks, timetable, attendance explanation, report reflection, teacher feedback, resource hub, student support requests.
- Teacher workspace needs one-click daily flow: take attendance, enter marks, message families, submit lesson evidence, resolve offline sync, publish feedback.
- Add per-role "today" home views that are mobile-first and measurable by max 3 primary actions.

### 3. Help, AI, feedback, and mobile proof are inconsistent across workflows.

The audited workflow table shows:

- readiness visible: 21 yes, 6 unclear
- blocker visible: 13 yes, 12 unclear, 2 no
- help/how-to: 7 yes, 16 no, 4 unclear
- AI guidance: 3 yes, 17 no, 7 unclear
- feedback hook: 3 yes, 24 no
- mobile signal: 9 yes, 18 unknown

Competitors increasingly sell ease of use, support community, demos, training, and AI assistance. Your platform has the components, but they are not consistently attached to tenant work.

Improve:

- Add a mandatory workflow chrome contract for every p1/p2 tenant workflow: readiness, blocker, next action, help, AI guidance, feedback, mobile proof.
- Any workflow without those six elements fails a verifier.
- Create `scripts/verify_tenant_workflow_experience_contract.py` from the existing audit JSON.
- Run Playwright at 390/768/1366 for the p1 role homes, not only Studio OS/template marketplace.

### 4. Tenant URL surface still leaks operator language.

Competitors keep customer-facing admin and vendor/operator control planes conceptually separate. Your audit shows operator naming and control-plane concepts bleeding into tenant URLs/templates.

Evidence: tenant clutter inventory flags operator/super/control-plane/evidence terms on tenant-reachable surfaces, `/marketplace/monetization/` in tenant URL config, `/admin/dashboard/`, `/internal-admin/`, and feedback `/super/*` routes mounted in a tenant-included urlconf.

Improve:

- Split feedback tenant and super URL modules.
- Move marketplace monetization to manager/operator only.
- Rename tenant-facing `evidence` and `operator` slugs to school language: readiness, history, review, audit log only where appropriate.
- Add a scanner that fails tenant URL patterns containing `super`, `operator`, `control-plane`, `internal-admin`, or monetization-only surfaces unless allowlisted.

### 5. Local-first profile coverage is strong but not yet "200+ country native."

The finance profile plan covers 250 ISO2 rows, but experience profiles currently cover 50 profiles across 48 countries. Classe365 claims 130-country reach; PowerSchool markets regional availability across US, APAC, Canada, Europe, India, LatAm, Middle East/Africa. If your strategic promise is local feel in 200+ countries, 48 countries is not enough for the tenant experience layer.

Improve:

- Expand `LocalExperienceProfile` from 50 to 220+ profiles, at least one per ISO2 supported country, with richer per-market defaults.
- Use a two-tier model: `CountryExperienceProfile` for every ISO2 and `RegionalExperienceVariant` for depth markets.
- Add required fields beyond current profile shape: phone format, address format, name order, date format, week start, term naming, guardian naming, document language, receipt language, common fee labels, national exam terms, import template aliases.
- Add proof that every supported country maps to at least one template, one payment posture, one language fallback, one school type baseline, and one demo dataset.

### 6. Curriculum/LMS depth is not as visible as the SIS/admin depth.

Blackbaud and ManageBac compete hard on LMS, curriculum planning, assignment center, portfolios, assessment, reporting, analytics, and flexible grading. Your repo has academics/evals/reports/automation, but the tenant audit highlights route fragmentation and limited p1 help/AI around reports, marks, and class setup.

Improve:

- Package curriculum and assessment as first-class tenant tools, not hidden modules.
- Add role-specific curriculum workspaces: teacher lesson plan, assessment design, grading policy, report publishing, student portfolio.
- Make "report card readiness" one guided workflow instead of sibling pages.
- Add local curriculum profiles for common systems: WAEC/WASSCE, GCE, CBSE, IGCSE/A-Level, IB, US state, French bac, German Abitur, national ministry variants.

### 7. Marketplace/templates are deep, but not yet connected to measurable adoption outcomes.

The 150-template marketplace is a differentiator, but competitors sell outcomes: faster enrollment, teacher time saved, one-stop family portal, fewer systems. Your templates need adoption telemetry and guided "best fit" selection to avoid becoming a large catalog that feels premium but still hard to choose.

Improve:

- Add template scorecards: time-to-launch, workflows enabled, role homes changed, missing setup, mobile readiness, local fit, offline posture, adoption risk.
- Add "recommend one" mode before "browse all"; show 3 best options based on school type/country/connectivity/roles.
- Add template preview with seeded realistic data per role and country.
- Add post-apply success metrics: first teacher attendance, first invoice paid, first parent login, first report published.

### 8. Integrations and partner ecosystem need tenant-facing clarity.

PowerSchool emphasizes partner ecosystem, APIs, Ed-Fi/SIF compatibility, and add-ons. Veracross highlights integrations/API. Your platform has API center, marketplace, packs, interop, and partner docs, but tenant users need a cleaner setup story.

Improve:

- Tenant app catalog should separate "available", "needs operator", "needs partner credentials", "live verified", "sandbox only", and "not in your country".
- Add setup recipes for Google Workspace, Microsoft 365, SMS/WhatsApp/email, payments, LMS exports, accounting, biometrics, transport, library.
- Add a tenant-safe integration health page: connected, failing, last sync, next fix, data shared.

## Priority Roadmap

### P0: Make tenants feel simple

- One tenant command center at `/school/studio/`.
- One setup workspace for blueprint, packs, imports, templates, apps, finance, users.
- One workflow chrome contract for readiness, blocker, next action, help, AI, feedback, mobile.
- Remove operator language and operator-only URLs from tenant-visible surfaces.

### P1: Make roles world-class

- Parent app home with child switcher, fees, reports, attendance, messages, documents, consent, events.
- Teacher daily desk with attendance, marks, family messaging, lesson plan, sync queue.
- Student action home with assignments, study plan, timetable, support, progress.
- School admin operations cockpit with launch score, adoption, data quality, finance, reports, staff, parent engagement.

### P2: Make local-global real

- Expand from 48 profile countries to 220+ country experience baselines.
- Add regional variants for depth markets.
- Link every country to payment profile, template profile, curriculum profile, demo data, language fallback, and tenant setup defaults.

### P3: Make the marketplace outcome-driven

- Recommend 3 templates before browsing 150.
- Score templates by local fit, launch readiness, role coverage, setup effort, offline posture, mobile readiness.
- Track adoption after apply.

### P4: Make enterprise trust obvious

- Tenant-facing integration health.
- Clear data residency and compliance posture per tenant.
- Customer-visible audit history for configuration changes.
- Import/export/rollback receipts everywhere.

## Verdict

RunMyCampus is not lacking raw ambition or module count. The repo already has a stronger local-first and template-marketplace posture than many SIS products. The competitive gap is operational simplicity: competitors package complexity as one app, one record, one family portal, one teacher desk, one setup path. Your next push should aggressively collapse tenant fragmentation, complete role-specific mobile workflows, enforce workflow guidance everywhere, and expand local experience coverage from 48 countries to 200+ country-native baselines.

## Closure Addendum 2026-05-24

Repo-side first closure pass shipped:

- Tenant feedback URL surface now includes `apps.feedback.tenant_urls`, which excludes `/super/*` operator feedback routes from tenant hosts.
- Operator feedback has a dedicated `apps.feedback.operator_urls` mount under `/super/feedback/`.
- Tenant marketplace purchase-intent routes no longer expose the operator monetization dashboard under `/marketplace/monetization/`.
- `/school/setup/imports/` now renders a real `tenant_import_setup` landing instead of redirecting to onboarding. It carries workflow-contract markers for readiness, blocker state, help, feedback, and mobile proof.
- `CountryExperienceBaseline` derives 200+ country-native tenant baselines from `regional_payment_profiles.json`, giving every supported payment country a currency, rail, fallback, and setup posture even before a premium deep local profile exists.
- `scripts/verify_tenant_experience_competitor_gap_closure.py` gates the above so the biggest competitor-gap closures cannot silently regress.

## Tenant 10x Addendum 2026-05-24

Second pass shipped a shared tenant command layer across role homes:

- `apps.portal.tenant_experience_command` now builds one role-aware payload for school readiness, profile readiness, local/global country context, and the user's immediate toolbelt.
- The shared tenant hero includes `partials/tenant/experience_command_strip.html`, so admin, teacher, parent, and student dashboards all expose the same command grammar instead of each role inventing its own next-step surface.
- `apps.portal.context_processors.tenant_experience_command` registers the same payload for inner tenant pages, and `templates/accounts/profile.html` now renders the strip so profile readiness is connected to dashboard/tools/workflow readiness.
- The command strip uses `data-rmc-tenant-experience-command`, `data-rmc-tenant-signal`, and `data-rmc-tenant-toolbelt` markers so automated checks can prove tenant dashboards still show readiness, profile, local rails, and role tools.
- Admin command actions prioritize School Studio, import setup, template marketplace, finance setup, and help. Teacher actions prioritize attendance, marks, syllabus, timetable, and messages. Parent and student actions stay focused on family workflow, finance/results/contact, messages, syllabus, profile, and help.
- The country baseline lookup is cached, making the 200+ country local/global posture cheap enough for every tenant role-home render.

## Workflow Portal Redesign Addendum 2026-05-24

Third pass replaced fragmented role workflow screens with one competitor-grade workflow portal pattern:

- `apps.portal.tenant_workflow_portal` normalizes parent, teacher, and student workflow data into one payload: completion score, next best action, compact metrics, step lanes, help, feedback, active year, and active term.
- Parent and teacher workflow screens now use `partials/tenant/workflow_portal.html` instead of separate dense card grids.
- A first-class student workflow route was added at `/portal/student/workflow/`, closing the gap where students had a home page but no focused workflow center.
- Teacher workflow no longer dead-ends when the active academic year/term is missing; it renders the tenant workflow portal with setup guidance.
- The shared workflow portal carries `data-rmc-tenant-workflow-portal`, `data-rmc-workflow-focus`, and `data-rmc-workflow-step` markers, so browser and semantic tests can prove the redesign remains attached.

## Intrusive Final Audit Addendum 2026-05-24

Final audit closed the remaining role-navigation leaks and hidden student gaps:

- Config-driven sidebar generation now includes `student_workflow`, `student_home`, `student_syllabus`, and `student_help`, so students keep the same workflow access even when tenant sidebar ordering/preferences are active.
- First-time student users now pin `student_workflow` by default, matching teacher and parent workflow defaults.
- Student post-login redirect now lands on `/portal/student-portal/grades/`, or `/portal/student/workflow/` when the user preference is `WORKFLOW`, instead of falling through to `admin:index`.
- Student sidebar no longer exposes a parent-only `portal_stats`/`/portal/parent/stats/` link under a generic "Progress" label.
- The regression suite now covers student redirect behavior, config-driven student sidebar generation, command registry workflow actions, and the prior unrouted `student_learning_home`/sidebar regression.
