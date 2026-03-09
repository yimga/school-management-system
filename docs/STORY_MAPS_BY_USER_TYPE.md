# Story Maps (Treasure Maps) by User Type — Non-Negotiable

**Source:** [RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md](RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md) Section 2 and 5.  
**Rule:** Every user type has a defined story map. Navigation and default landings must reflect these paths so users reach their highest-value features in the fewest clicks.

---

## 1. School head / owner / principal

**Pain:** Fragmentation; reporting messy; parent trust.  
**Solution:** Executive dashboards, approval inboxes, cross-department workflows, school health indicators.

**Story map (path):**

1. **Home** → Executive dashboard (default landing after login).
2. **Alerts** → Anomalies and approval-needed items visible from dashboard or one click.
3. **Approvals** → Dedicated approval center (e.g. leave, fees, documents).
4. **Reports** → By department and school health; decision-ready.

**Nav / implementation:** Backend dashboard as default for role HEAD/OWNER/PRINCIPAL; sidebar items: Dashboard, Alerts, Approvals, Reports. See `apps/dashboard/`, `apps/siteconfig/portal_sidebar_items.py`, role-based sidebar registry.

---

## 2. District leader / board / school group

**Pain:** Too many sources; weak dashboards; hard to compare schools; policy and migration pain.  
**Solution:** Control plane, tenant 360, policy bundles, blueprint packs, roll-up analytics.

**Story map (path):**

1. **Control plane** → Default when on manager/super host.
2. **Schools list** → Tenant list with health and status.
3. **Tenant 360** → Single school drill-down.
4. **Policy / blueprint** → Manage policy bundles and blueprint packs.
5. **Migration / apps** → Migration cloud and app governance.

**Nav / implementation:** `/super/` routes; control plane sidebar. See `config/manager_urls.py`, `templates/control_plane_*.html`, control plane sidebar.

---

## 3. Teacher

**Pain:** Admin workload; fragmented gradebooks; weak intervention visibility.  
**Solution:** One-tap attendance, fast grade entry, assignment center, intervention prompts, messaging.

**Story map (path):**

1. **Home** → Daily view (today’s classes, quick actions).
2. **Attendance** → One-tap per class/session.
3. **Grade entry** → Gradebook without leaving context.
4. **Assignments** → Assignment center.
5. **Interventions** → Alerts and prompts.
6. **Messages** → Parent/student communication shortcuts.

**Nav / implementation:** Teacher portal/dashboard; sidebar from portal_sidebar_items and dashboard registry. See `apps/portal/`, teacher dashboard, evals/gradebook.

---

## 4. Parent / guardian

**Pain:** App sprawl; too many portals.  
**Solution:** One family dashboard, multilingual messaging, one-tap payment, notice/calendar unification.

**Story map (path):**

1. **Family home** → Default portal landing.
2. **Child selector** → Switch between children if multiple.
3. **Timeline** → Grades, attendance, notices, fees in one place.
4. **Actions** → Pay, acknowledge, message.

**Nav / implementation:** Parent portal; family dashboard; link_child and timeline views. See `apps/portal/`, parent dashboard, finance parent view.

---

## 5. Student

**Pain:** What to do; when due; how am I doing; where to find it.  
**Solution:** Lightweight dashboard, assignment center, timetable, progress snapshot, reminders.

**Story map (path):**

1. **My work** → Assignments and tasks.
2. **Timetable** → Schedule.
3. **Progress** → Grades and progress at a glance.
4. **Messages** → Simple messaging.

**Nav / implementation:** Student portal; student dashboard and assignment/timetable views. See `apps/portal/`, student 360.

---

## 6. Admissions

**Pain:** Pipeline visibility and family follow-through.  
**Solution:** Admissions CRM, missing-document queues, interview scheduling, offer/contract workflows, yield analytics.

**Story map (path):**

1. **Pipeline** → Funnel view.
2. **Applicants** → List and detail.
3. **Documents / tasks** → Missing-document queues and tasks.
4. **Offers** → Offer and contract workflow.
5. **Yield** → Yield analytics.

**Nav / implementation:** Backend admissions module; sidebar entry "Admissions" or "Enrollment". See people/applicant flows, registries.

---

## 7. Finance / operations

**Pain:** Billing complexity, disputes, reconciliation.  
**Solution:** Billing cockpit, family finance view, installment plans, reminders, exports and audit trails.

**Story map (path):**

1. **Billing overview** → Dashboard.
2. **Families** → Family list and balances.
3. **Fees / payments** → Fees and payment history.
4. **Exports / reports** → Exports and audit.

**Nav / implementation:** Finance app; billing views; export and reporting. See `apps/finance/`, `apps/billing/`.

---

## 8. IT / data / operations

**Pain:** Integration, security, support burden; weak dashboards.  
**Solution:** Provider registry, APIs/webhooks, SSO/SCIM, migration cloud, observability, app governance.

**Story map (path):**

1. **Integrations** → Integrations overview.
2. **Providers / apps** → Provider registry and app governance.
3. **Migration** → Migration cloud (for tenant context) or super migration (control plane).
4. **Observability** → Logs and health.

**Nav / implementation:** Site config / integrations; super for migration and observability. See `apps/siteconfig/`, `apps/observability/`, control plane health.

---

## Verification (non-negotiable)

- Each role above has a story map and a nav/default landing that matches.
- Product/UX specs and implementation tickets reference this doc.
- No user type is left without a defined story map; any gap is assigned owner and target in STRATEGY_REPORT_GAP_CLOSURE.md.
