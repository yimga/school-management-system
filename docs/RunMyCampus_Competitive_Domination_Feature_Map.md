# RunMyCampus Competitive Domination Feature Map

**All items in this document are required. Nothing is optional or backlogged.** This document is the single source of truth for platform differentiation and the "why switch" narrative. It describes **what** the platform does and **why** it wins; it does **not** describe how (no algorithms, parsing, schema design, or proprietary logic). Marketing and sales use it for messaging; engineering uses it for alignment.

---

## 1. Positioning

- **Legacy systems are products; RunMyCampus is a platform.** A product serves customers; a platform powers an ecosystem.
- **Win on:** Easiest to switch to, easiest to launch, easiest to run daily, easiest to extend, smartest over time.
- **Strategic truth:** Incumbents are strong at the traditional SIS stack. The win is not "build attendance, grades, and parent portal"—they already have those. The win is to build a platform that is easier to switch to, faster to launch, easier to configure, easier to automate, easier to extend, more intelligent, more global, and more governable across multiple institutions.

---

## 2. Competitor gap

- **Incumbents** (e.g. PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS) focus heavily on SIS functionality and are weak in: unified platform architecture, event-driven automation, ecosystem growth, and intelligence layers.
- **Copy their strengths:** Unified family/business-office story, one-record lifecycle, district-scale breadth, marketplace and certification signs.
- **Avoid their weaknesses:** Consulting-heavy setup, fragmented navigation, too many manual steps, weak preview/simulation, vendor-shaped workflows, data spread across loosely stitched modules.

---

## 3. Platform architecture improvements

- **Unified data graph:** Everything connects through a canonical education data model (core objects: Student, Person, Enrollment, Course, Assessment, Attendance, Payment, Institution, Academic term, Communication, Compliance entity). Benefits: no duplicate records, simpler reporting, AI insights, cross-module automation.
- **Event-driven platform:** Instead of modules polling each other, use events (e.g. StudentAbsent → parent alert, counselor task, analytics update). Benefits: automation becomes natural, integrations easier, workflows powerful.
- **Tenant control plane:** Manage tenants, apps, blueprints, policies, migrations, global registries. District or enterprise administrators control multiple institutions from one console.

---

## 4. Onboarding and time-to-value

- **Automated school discovery:** When a school enters its domain or website, prefill setup wizard with school name, logo, colors, contact info, academic levels, language, location, timezone.
- **Migration readiness scanner:** Before migration, scan the incoming system and produce a report (e.g. record counts, missing guardians, duplicate emails, unsupported formats). Builds confidence and transparency.
- **Interactive setup score:** Give the admin a Setup Progress Score (e.g. Branding complete, Staff imported, Student data imported, Workflows installed, Analytics enabled). Drives activation.

---

## 5. Marketplace ecosystem

- **Categories:** Apps, blueprint packs, workflow packs, dashboard packs, policy bundles, migration packs, compliance packs, theme packs, AI assistants.
- **Vertical packs:** International School Pack, Charter School Pack, TVET Pack, Montessori Pack, etc.
- **Marketplace behavior:** Installability checks, compatibility matrix, sandbox install, trust/scopes/compliance view, lifecycle status, versioning, usage analytics. This is platform behavior, not a brochure catalog.

---

## 6. Workflow automation

- **Visual workflow builder:** Users create automation visually (e.g. condition: Attendance &lt; 85%; action: send parent email, create counselor case, add to watchlist).
- **Workflow packs and simulation:** Before activating a workflow, admins simulate it (e.g. "If this rule existed last week, 23 alerts would have triggered"). Event replay, impact preview, rollback.
- **High-value starter workflows:** Attendance intervention, fee reminders, incomplete admissions docs, re-enrollment follow-up, counselor escalation, district approval workflows.

---

## 7. Data and analytics

- **Operational intelligence:** Dashboards for attendance risk, student performance trends, financial collection health, admissions funnel.
- **Benchmarking:** Compare schools to similar institutions (e.g. "Your attendance rate is 4% below schools of similar size").
- **District command center:** Multi-campus performance, financial health, staffing metrics, compliance alerts.

---

## 8. AI capabilities

- **AI configuration assistant:** Recommend blueprint packs, workflows, dashboards; explain plan differences; detect setup gaps; recommend next best action.
- **AI workflow builder:** Admin types a natural-language rule (e.g. "Notify parents if homework is missing twice"); system generates workflow definition, simulation preview, approval requirement.
- **AI analytics and risk engine:** Detect attendance risk, academic decline, fee collection risk, admissions bottlenecks, policy non-compliance, operational anomalies.
- **AI communication assistant:** Generate parent emails, student notices, teacher announcements.
- No description of how models or pipelines work internally.

---

## 9. Mobile, global, integration, security, operational health, developer, customer success

- **Mobile-first:** Admin, teacher, parent, student apps; attendance taking, messaging, push notifications, assignments, fee payments.
- **Global:** Multi-language UI, global grading models (GPA, IB, percentage, narrative), calendar models (trimester, semester, year-round), regulatory packs (FERPA, GDPR, COPPA).
- **Integration:** Learning platforms, communication tools, finance systems, identity providers, government reporting; REST APIs, webhooks, SDKs; provider abstraction, API gateway, connector marketplace, retry/reconciliation.
- **Security:** Role-based access control, audit logs, data encryption, compliance dashboards, security alerts.
- **Operational health:** System health dashboard, data integrity monitoring, automation error alerts, migration monitoring.
- **Developer ecosystem:** Developer sandbox, API docs, marketplace publishing tools, revenue sharing model.
- **Customer success:** In-app guidance, task recommendations, setup completion score, admin playbooks; track onboarding completion, time to first value, workflow adoption, churn risk; use data to guide the school and product roadmap.

---

## 10. The 20 platform features that make schools switch

1. **Zero-drama Migration Cloud** — Connect, auto-detect, auto-map, validate, repair, sandbox, launch; schema fingerprinting, migration profiles, verification scorecards.
2. **Guided School-in-a-Box onboarding** — Sign up, choose school type, apply blueprint, import branding, install starter stack, invite users, preview portals, launch in one guided studio.
3. **Blueprint packs as institution design kits** — Structure, calendars, levels, default modules, dashboards, recommended workflows, policy compatibility, theme/template starter set.
4. **Workflow packs with simulation** — Visual workflow builder, workflow packs, simulation before activation, event replay, impact preview, rollback.
5. **Role-specific command centers** — Principal, teacher, finance officer, admissions lead, parent, student, district executive, IT/admin, counselor; each home answers what matters now, what is urgent, what action next.
6. **Parent experience that is actually pleasant** — One family dashboard for all children, multilingual communication, one-tap payment, notices + calendar + forms + messages in one stream, mobile-first, action cards.
7. **True marketplace** — Apps, blueprints, workflows, dashboards, policies, migration packs, theme packs, AI skills; installability checks, compatibility matrix, sandbox install, trust/scopes/compliance, lifecycle, versioning.
8. **Control plane for groups, districts, boards** — Govern multiple schools, compare performance, roll out policies, supervise migrations, govern installed apps and providers, view tenant health, benchmark campuses.
9. **Policy bundles with preview, diff, rollback** — Apply policy bundles, compare bundles, see impact preview, sandbox before rollout, roll back if needed.
10. **Dashboard packs (outcome-based, role-aware)** — Principal cockpit, teacher action dashboard, district executive dashboard, admissions funnel, collections, student risk, parent engagement; KPI definitions, threshold defaults, drilldowns, mobile layout, install preview, benchmark overlay.
11. **AI configuration assistant** — Recommend blueprints, workflows, dashboards; detect setup gaps; infer school stack from onboarding questions; next best action.
12. **AI workflow builder** — Natural-language → workflow definition, actors, conditions, actions, simulation preview, approval.
13. **AI analytics and risk engine** — Detect attendance risk, academic decline, fee risk, bottlenecks, policy non-compliance, operational anomalies.
14. **Website and branding import assistant** — Enter current website or portal URL; extract logo, colors, contact, messaging tone, visual identity; generate school website starter, parent portal theme, live responsive preview.
15. **School website and portal templates** — School website templates, parent portal themes, admin shell presets, dashboard presets, admissions landing pages, event pages, application forms.
16. **Integration fabric with strong abstractions** — Provider abstraction layer, API gateway, webhooks, connector marketplace, provider health status, retry/reconciliation, swap-ready adapter contracts.
17. **Data quality and audit tooling** — Data validation rules, access tracker, change tracker, data lineage, data quality score, exception inbox, repair suggestions.
18. **Global education runtime** — Multilingual UI, local labels, regional grading models, different calendar systems, local attendance states, different institution structures, compliance packs by region.
19. **Developer platform and partner ecosystem** — Developer portal, SDKs, webhook docs, app certification, sandbox tenants, marketplace publishing, partner analytics, trust/compliance requirements.
20. **Customer success intelligence** — Track onboarding completion, time to first value, workflow adoption, parent engagement, support load, migration health, expansion readiness, churn risk; guide school, CS team, and product roadmap.

---

## 11. Practical priority order (all required; sequence for execution)

- **Tier 1 — must win now:** Migration Cloud, School-in-a-box onboarding, blueprint packs, starter workflow/dashboard packs, role-based homes, parent mobile-first experience.
- **Tier 2 — must win next:** Marketplace maturity, policy bundles, workflow simulator, AI configuration assistant, district/group control plane, branding import + design studio.
- **Tier 3 — strategic moat:** AI workflow builder, AI analytics engine, developer platform, customer success intelligence, global education runtime, data quality/audit suite.

---

## 12. Competitive advantage summary table

| Capability   | Legacy SIS     | RunMyCampus goal   |
|-------------|----------------|--------------------|
| Migration   | Painful        | Automated          |
| Setup       | Manual         | Blueprint-driven   |
| Automation  | Minimal        | Visual workflows   |
| Marketplace | Weak           | Full ecosystem     |
| Analytics   | Reports        | Intelligence       |
| AI          | Limited        | Embedded everywhere|
| Global support | Limited     | First-class        |

No internal implementation detail in this table or elsewhere in this document.

---

## 13. Secret-sauce rule

This document describes **what** the platform does and **why** it wins. It does **not** describe how (algorithms, parsing, schema design, event bus implementation, or proprietary logic). Marketing and sales use this doc for messaging; engineering uses it for alignment, not as a spec that exposes internals.
