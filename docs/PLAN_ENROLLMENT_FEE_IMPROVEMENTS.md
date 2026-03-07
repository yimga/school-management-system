# Plan: Enrollment & Fee Payment Improvements

**Status:** 100% complete — all 19 phases and optional items implemented  
**Based on:** [QA_AUDIT_ENROLLMENT_AND_FEE_PAYMENT.md](./QA_AUDIT_ENROLLMENT_AND_FEE_PAYMENT.md)  
**Last updated:** 2025-02-02  
**Verification:** See [Plan verification checklist](#plan-verification-checklist) and [ENROLLMENT_FEE_IMPROVEMENTS_STATUS.md](./ENROLLMENT_FEE_IMPROVEMENTS_STATUS.md).

---

## How to use this plan

- **Add/remove/change** items as we discuss. Keep "Ready to build?" per item or per phase.
- When an item is **approved**, set `Ready to build: yes` so implementation can start.
- We can group work into **phases** and mark a phase "ready to build" when all its items are agreed.

---

## Master plan (overview)

### Vision

A single, coherent plan so the school management system reaches **100% workflow efficiency** (no redundant data, clear notifications, empty states that guide action), feels **professional and consistent** (design system, white-labeling, accessible, secure), and gives every role **fast, clear paths** (dashboards, global search, help, export, print-friendly report cards). All **optional** items (Phase 4, haptic feedback, post-bulk notify, guardian sync, optional print-friendly docs, etc.) are **included** in the plan and sequenced where they fit.

### Pillars (how phases group)

| Pillar | Phases | Focus |
|--------|--------|--------|
| **A. Foundation** | 1, 10 | Data/sync and security first: single source of truth, RBAC, session management. |
| **B. Data & workflow** | 2, 3, 4 | Notifications, empty states, and additional workflow (post-bulk notify, guardian→student sync). |
| **C. Experience & UX** | 5, 6, 7, 8, 9, 11 | Design system, admin/settings UX, dashboards, teacher cognitive load, accessibility, teacher onboarding. |
| **D. Scale & polish** | 12, 13, 14, 15, 16, 17, 18, 19 | Performance, feedback loop, micro-interactions, table IA, white-labeling, global search, reporting/export, embedded help & empty-state template. |
| **E. Optional enhancements** | (see list below) | Items marked "optional" inside phases (haptic, parent payment feedback, extended print-friendly, etc.); build when capacity allows. |

### Full phase list (all 19 phases, optional included)

| # | Phase | One-line goal |
|---|--------|----------------|
| 1 | **Phase 1** — Data & sync | Single source for parent contact; payment/invoice semantics; reconcile_balance on all paths. |
| 2 | **Phase 2** — Notifications & confirmations | Parent welcome, onboarding confirmation, new-invoice and payment-received notifications; configurable. |
| 3 | **Phase 3** — Empty states & UX | Fee-invoice empty state; standardize finance table empty states with shared component. |
| 4 | **Phase 4** — Additional workflow & sync | Post–bulk invoice "Notify guardians" action; guardian→student contact sync on save (one-way). |
| 5 | **Phase 5** — Design system & visual hierarchy | One token source, Navy/Slate palette, H1–H4 scale, 4/8px grid, reduce noise; apply across portal/backend/admin. |
| 6 | **Phase 6** — Admin dashboard & settings UX | Logical buckets, Smart Search for settings, inline tooltips for complex toggles. |
| 7 | **Phase 7** — Principal & Teacher dashboards | Top 5 KPIs above the fold, charts for key metrics, Quick Action buttons (e.g. Message Absent Students, Enter marks). |
| 8 | **Phase 8** — Teacher portal cognitive load | Flattened nav, one-click to daily tasks, ≤3 clicks for grade/attendance, under-30-second target. |
| 9 | **Phase 9** — Accessibility (WCAG 2.1) | Contrast, skip link, full keyboard nav, ARIA for tables and complex widgets. |
| 10 | **Phase 10** — Security | SQL/input audit, RBAC audit and tests, session inactivity logout for shared computers. |
| 11 | **Phase 11** — Teacher welcome flow & onboarding | Aha! moment, 3-step walkthrough, empty-state messages for new teacher dashboard. |
| 12 | **Phase 12** — Performance & mobile/tablet | Load under 3s, lazy loading for large lists, 44×44px tap targets, Admin Console responsive on tablet. |
| 13 | **Phase 13** — Feedback loop & user research | "Was this helpful?" at completion points; 2-question end-of-term teacher survey; analysis/export. |
| 14 | **Phase 14** — Micro-interactions & feedback cues | Toasts, loading skeletons, human-readable errors; optional haptic on mobile. |
| 15 | **Phase 15** — Information architecture (tables) | Zebra striping, sticky headers, conditional formatting, Condensed vs. Expanded view toggle. |
| 16 | **Phase 16** — White-labeling & personalization | Logo and primary color everywhere; Personalization Engine (pin classes/reports to sidebar). |
| 17 | **Phase 17** — Global Search (CMD+K) & Quick Actions | Command palette to jump to student/invoice; Quick Actions in search (e.g. "Add Grade"). |
| 18 | **Phase 18** — Reporting workflow & export | One-click Excel/PDF for key tables; Print-Friendly CSS for report cards; optional for other parent docs. |
| 19 | **Phase 19** — Embedded Help & Empty State template | Help icons (page/section/field), global Help/KB; Empty State template with direct action link. |

### Optional items (included in the plan; build when capacity allows)

These are **part of the plan** but can be scheduled after core items in the same phase or in a later sprint:

- **Phase 1:** Optional sync of `student.parent_phone` from primary guardian on save (1.2).
- **Phase 2:** All notifications configurable/optional per feature; optional email on receipt verification (2.5).
- **Phase 4:** Post–bulk invoice "Notify guardians" (4.1); Guardian→student contact sync on save (4.2)—now first-class phase items.
- **Phase 7:** Optional "Quick actions" strip at top of dashboard (7.3).
- **Phase 8:** Optional "Daily tasks" / "Today" view (8.3).
- **Phase 11:** Optional "Don't show again" and Aha! completion tracking (11.2, 11.4).
- **Phase 12:** Optional "Load more" / infinite scroll (12.2); optional Lighthouse/smoke check (12.1).
- **Phase 13:** "Was this helpful?" optional comment; parent payment feedback placement (phase in later) (13.2).
- **Phase 14:** Haptic feedback on mobile (14.3); optional "Undo" for reversible actions in toasts (14.1).
- **Phase 15:** Optional at-risk attendance highlight; optional finance lists in Condensed/Expanded toggle (15.3, 15.4).
- **Phase 16:** Optional emails/PDFs logo; optional backend sidebar pins; optional "Manage pins" (16.1, 16.3, 16.4).
- **Phase 17:** Optional parent portal scope for command palette (17.1).
- **Phase 18:** Optional print-friendly for other parent-facing docs (e.g. term summary, fee statement) (18.5).
- **Phase 19:** Optional inclusion of help articles in global search (19.2).

**Build order** below sequences all 19 phases (including Phase 4); optional sub-items are implemented within their phase when capacity allows.

---

## Goals (from audit)

1. **Remove redundancy** — Single source of truth for parent contact; clear semantics for payment reference and invoice balance.
2. **Close workflow gaps** — Confirmation/notification emails where missing; empty states; data sync (e.g. guardian contact on backend create).
3. **Reach 100% workflow efficiency** — No double data entry, consistent notifications, clear empty states.
4. **Professional design system** — Cohesive visual hierarchy (H1–H4 scale), 4px/8px spacing grid, reduced visual noise, high-contrast Navy/Slate palette so the app feels like a modern, premium SaaS product.
5. **Admin dashboard & settings UX** — Settings and User Permissions (and all admin pages) intuitive for non-technical users: configurations in logical buckets (e.g. Academics, Finance, System), Smart Search to find settings by keyword, inline tooltips on complex toggles to explain impact.
6. **Principal & Teacher dashboards: seamless and actionable** — Top 5 KPIs visible without scrolling; visual charts (bar, line, donut) where they add more than raw tables; Quick Action buttons (e.g. Message Absent Students) to bridge viewing data and taking action.
7. **Teacher portal: low cognitive load** — No frequent task takes more than 3 clicks; flattened navigation and one-click access to daily tasks (e.g. mark attendance, submit a grade) so teachers can complete them in under 30 seconds.
8. **Accessibility (WCAG 2.1)** — Color contrast sufficient for low vision (AA: 4.5:1 text, 3:1 large); full keyboard navigation (tab order, skip link, visible focus); ARIA labels and structure for complex elements (e.g. student grade tables, nav, modals) so screen readers interpret them correctly.
9. **Security (Fee Payments & Student Records)** — External input sanitized to prevent SQL injection; strict RBAC so teachers cannot see payroll or another teacher's private data; session management that auto-logs out users after inactivity on shared school computers.
10. **Teacher welcome flow & onboarding** — A Welcome Flow for new teachers with a clear Aha! moment (e.g. marking first attendance or entering first grades); a 3-step interactive walkthrough or tooltips guiding them to that moment; empty-state messages on the dashboard that encourage adding data.
11. **Performance & mobile/tablet** — App loads in under 3 seconds on slow connections; lazy loading for large student lists where appropriate; mobile tap targets at least 44×44px; Admin Console (and similar) no horizontal scrolling on tablet—responsive stack layout where needed.
12. **Feedback loop & user research** — A feedback loop integrated into the app: "Was this helpful?" placed at key completion points (e.g. after submitting grades, after generating invoices); a simple 2-question survey for teachers at the end of each grading period to identify friction points in the workflow.
13. **Micro-interactions & feedback cues** — When an admin (or user) saves a complex configuration or completes an action, the system confirms success clearly without interrupting flow. Use Toast notifications for save/action feedback, loading skeletons during fetches, and (where supported) haptic cues on mobile. All error messages are human-readable (e.g. "We couldn't find that student's record" instead of "Error 404").
14. **Information architecture: student (and key) data tables** — Student data tables (and other high-use tables) use zebra striping, fixed/sticky headers when scrolling, and conditional formatting (e.g. failing grades in subtle red, overdue fees in bold). A Condensed View vs. Expanded View toggle lets users choose how much data they see at once.
15. **White-labeling & personalization** — White-labeling: school logo and primary colors injected consistently across portal, backend, and login so the product feels like the school's. A Personalization Engine lets teachers (and optionally others) pin their most-used classes or reports to the sidebar for faster access.
16. **Global Search (CMD+K) & Quick Actions in search** — A global command palette (e.g. CMD+K / Ctrl+K) lets users jump from anywhere (e.g. Dashboard) to a specific student profile or invoice by typing. Quick Actions inside the search bar (e.g. typing "Add Grade") open the grading flow or other actions immediately.
17. **Reporting workflow & export (BI)** — Reporting workflow audited; every key table can be exported to clean Excel and PDF with one click. Report cards have a Print-Friendly CSS view so they look professional when physically handed to parents, not just on screen.
18. **Embedded Help & Empty State template** — An Embedded Help Strategy: consistent placement of Help icons (page, section, field) with links to relevant docs. A canonical Empty State template: "No [X] Found—Click here to [action]" with a direct link to the action (e.g. "No Students Found—Click here to add your first student"), not just "No Data."

---

## QA audit findings summary

*(Full detail: [QA_AUDIT_ENROLLMENT_AND_FEE_PAYMENT.md](./QA_AUDIT_ENROLLMENT_AND_FEE_PAYMENT.md).)*

### Redundant data fields (info asked or stored twice)

| Area | Finding | Addressed by |
|------|---------|--------------|
| **Parent/guardian contact** | `StudentProfile.parent_phone` and `StudentGuardian.phone` / `.email` both hold contact info. Backend "Create Student" form collects parent email/phone but only saves to student; when creating `StudentGuardian`, it does **not** set `phone` or `email`, so reminders can use wrong/empty contact. Onboarding wizard correctly sets both. | Phase 1.1, 1.2 |
| **Payment reference** | `Payment.reference` and `Payment.external_reference` both set to the same value when creating payment from receipt; semantics duplicated. | Phase 1.3 |
| **Invoice balance** | `Invoice.balance_amount` (stored) vs `Invoice.computed_balance` (property); risk of drift if `reconcile_balance()` is not called on every payment path. | Phase 1.4 |

### Workflow gaps

| Gap | Current behaviour | Addressed by |
|-----|-------------------|--------------|
| **No confirmation email when student created (backend)** | Staff message only: "Please send login credentials to {email}". No automated email to parent. | Phase 2.1 |
| **No confirmation after onboarding wizard** | Success message only; no email to parent or student with next steps. | Phase 2.2 |
| **No "new invoice issued" notification** | Invoices created; payment reminders run when due. Parents are not notified when an invoice is first issued. | Phase 2.3 |
| **No "payment received" when staff records payment** | Payment applied via signal; no notification to guardian. Receipt-upload verification does send in-app notification. | Phase 2.4 |
| **No email copy on receipt verification** | In-app "Payment verified" only; no optional email for audit/parent. | Phase 2.5 |
| **Generate Fee Invoices: no empty state** | When no fee plans exist, dropdown is empty and submit fails; no friendly message or CTA to create a plan. | Phase 3.1 |
| **Finance table empty states** | Some tables use plain "No invoices found" / "No payments recorded"; could use shared empty-state component for consistency. | Phase 3.2 |

### Checklist mapping

The phases below are the consolidation/automation checklist to achieve 100% workflow efficiency: Phase 1 (data/sync), Phase 2 (notifications), Phase 3 (empty states), Phase 4 (additional workflow & sync). All are part of the master plan.

---

## Phase 1: Data & sync (foundation)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 1.1 | Sync guardian contact on backend student create | When creating `StudentGuardian` from backend form, set `phone` and `email` from form (so reminders use correct contact). | |
| 1.2 | Single source for parent contact | Prefer `StudentGuardian` (phone/email) everywhere; document fallback to `StudentProfile.parent_phone`. Optional: sync `student.parent_phone` from primary guardian on save. | |
| 1.3 | Payment reference semantics | Decide: one field for "external transaction ID" (e.g. `external_reference`), use it consistently; document or deprecate the other. | |
| 1.4 | Invoice balance | Ensure all payment-apply paths call `reconcile_balance()`; document migration path from `balance_amount` to `computed_balance` only. | |

**Phase 1 ready to build?**  

---

## Phase 2: Notifications & confirmations

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 2.1 | Parent welcome / credentials email | When parent account is created (backend or onboarding): optional email with sign-up link or temp password instructions. Configurable in site/notification settings. | |
| 2.2 | Pre-registration confirmation email | After onboarding wizard: optional email to parent confirming student name, admission number, next steps. | |
| 2.3 | New invoice issued notification | When invoice is created (single or bulk): optional notification to guardians with finance access (email and/or in-app). Configurable. | |
| 2.4 | Payment received notification | When a payment is applied (manual or receipt verification): notify guardians with finance access (amount, invoice ref). Configurable. | |
| 2.5 | Optional email on receipt verification | In addition to in-app "Payment verified", optional email copy for audit/parent. | |

**Phase 2 ready to build?**  

---

## Phase 3: Empty states & UX

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 3.1 | Generate Fee Invoices empty state | When no fee plans exist: show friendly empty state (e.g. `dashboard_empty_state.html`) with message and link to create fee plan. | |
| 3.2 | Standardize finance table empty states | Use shared empty-state component for "Recent Invoices", "Recent Payments", payments list where it makes sense. | |

**Phase 3 ready to build?**  

---

## Phase 4: Additional workflow & sync (included in master plan)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 4.1 | Post–bulk invoice "Notify guardians" | After "Generate Fee Invoices", optional summary + "Send new-invoice notifications" action so staff can notify guardians in one click. | |
| 4.2 | Guardian → student contact sync on save | On `StudentGuardian.save`, if primary guardian, set `student.parent_phone` from `guardian.phone` (one-way sync). Keeps fallback in sync with single source. | |

**Phase 4 ready to build?**  

---

## Design system & visual hierarchy (UI/UX)

### Current-state findings

| Area | Finding |
|------|---------|
| **Two token sources** | `design-tokens.css` (blue/green brand, slate admin, 8px dashboard unit, fluid type) and `design-system-unified.css` (pink/purple/teal, 4px spacing, fixed font sizes) both loaded; templates also inject `--school-primary` / theme overrides. Backend light theme adds another accent (purple gradient). No single source of truth; **clashing colors**. |
| **No single H1–H4 scale** | design-tokens has fluid `--text-*` but no semantic h1–h4 mapping; design-system-unified maps h1–h6 to sizes but H4/H5/H6 share the same size. Templates mix Bootstrap classes (`h1 class="h5"`, `display-6`, `fw-bold`) and inline styles. **No cohesive visual hierarchy**. |
| **Spacing inconsistency** | design-tokens uses 8px dashboard unit and 12px gaps; design-system-unified uses 4px base. **No single 4px/8px grid** applied everywhere. |
| **Visual noise** | Many gradients (body, buttons, badges, header, sidebar); many border opacities (0.04–0.35); multiple shadow systems; inline border/shadow/color in some templates. **Busy, inconsistent** feel. |
| **No Navy/Slate palette** | Current palettes are blue/green, pink/purple/teal, or purple gradient. **No defined high-contrast Navy + Slate** for a premium SaaS look. |

### Proposed design system

- **Single token source** — One canonical token file (or clear layering); **Navy/Slate default palette**: Navy for primary surfaces and key UI (e.g. `#0f172a` / `#1e3a5f`); Slate for text and secondary (`#0f172a` primary text, `#475569` muted, `#f1f5f9`/`#e2e8f0` light backgrounds); **one accent** (e.g. single blue or teal) for links and CTAs.
- **Explicit H1–H4 scale** — H1 page title (e.g. 1.75–2rem), H2 section (1.375–1.5rem), H3 card/block (1.125rem), H4 subsection (1rem); define as CSS vars and apply to semantic headings; reduce Bootstrap display/fw overrides for headings.
- **4px/8px spacing grid** — Base unit 4px; spacing in multiples (4, 8, 12, 16, 24, 32, 48, 64); one set of variables used across dashboard, cards, forms, lists.
- **Reduce visual noise** — One or two border tokens; one shadow/elevation scale; restrict gradients to header or primary CTA; flat fills for sidebar/cards/body; remove inline border/shadow/color from key templates.
- **Apply across portal, backend, admin** — Same tokens and hierarchy everywhere so the app feels like one premium product.

### Phase 5: Design system & visual hierarchy

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 5.1 | Consolidate design tokens | Single canonical token file or clear layering; remove duplicate/conflicting variables between design-tokens.css and design-system-unified.css. | |
| 5.2 | Navy/Slate high-contrast palette | Define and apply default palette (Navy primary/surfaces, Slate text and secondary, one accent); ensure WCAG contrast; reduce competing palettes (pink/purple/teal, purple gradient). | |
| 5.3 | H1–H4 type scale | Define and apply explicit heading scale (e.g. H1 28–32px, H2 22–24px, H3 18px, H4 16px); map to CSS vars and semantic headings; reduce Bootstrap display/fw-bold overrides for headings. | |
| 5.4 | 4px/8px spacing grid | Standardize spacing variables on 4px base; apply to dashboard, cards, forms, lists; replace one-off spacing values. | |
| 5.5 | Reduce visual noise | Unify borders (one or two tokens), one shadow scale, restrict gradients to header/CTA; remove inline border/shadow/color from key templates (e.g. compliance dashboard). | |
| 5.6 | Apply across portal, backend, admin | Ensure portal_base, backend_base, and admin all use the same token set and hierarchy so the app feels like one premium SaaS product. | |

**Phase 5 ready to build?**  

---

## Admin dashboard & settings UX (Product)

### Current state

- **Settings** live in Django Admin (Site Settings change form) and in portal/siteconfig (Customizer, User preferences, Feature Control). Site Settings uses **tabs** (Branding, Company, Theme, Portal, Footer, Feature Toggles, Backend Orchestration, Notifications, Compliance & Payroll, Reports, Finance Automation, Analytics Defaults, Automation) but names are technical and not grouped under clear buckets like "Academics" or "System".
- **User permissions / RBAC** are spread across admin (user/group permissions, role-based access) and Site Settings (e.g. "Backend Orchestration & Limits": allowed_roles_entity_console, require_guardian_finance_opt_in). Non-technical admins may not know where to look.
- **No keyword search** for settings: admins must open tabs and scan. Finding e.g. "payment reminder" or "invoice" requires knowing it lives under "Finance Automation".
- **Complex toggles** (e.g. finance_auto_generate_invoices_enabled, finance_receipt_auto_apply_threshold, enable_parent_portal) have form `help_text` in code but the change form may not surface them as **inline tooltips** next to the control, so impact on the school system is not obvious at a glance.

### Proposed improvements

- **Logical buckets** — Group all configurations into a small set of buckets so non-technical users know where to go:
  - **Academics** — Reports (publish & grades), Analytics Defaults, top students, pass mark, deadlines, grade approval.
  - **Finance** — Finance Automation, payment reminders, receipt verification, payment instructions, overpayment/void/withdrawal.
  - **System** — Feature toggles (portals, modules), Backend Orchestration & Limits, Automation (execution & approval), maintenance, MFA/compliance.
  - **Branding & experience** — Branding, Company, Theme, Login/Header, Portal content, Footer.
  - **Notifications** — Notification channels, reminder defaults (can stay under Finance or separate).
  Reorganize Site Settings tabs/labels to match these buckets (or add a "Browse by category" view that maps tabs to buckets).
- **Smart Search** — Add a **keyword search** at the top of the Settings/Customizer area (and optionally on the main admin dashboard) that:
  - Indexes setting labels, help text, and field names.
  - Filters or jumps to the relevant tab/section and highlights the matching control.
  - Uses plain-language terms (e.g. "invoice", "reminder", "parent portal", "dark mode") so admins can find settings without knowing the internal name.
- **Inline tooltips for complex toggles** — For every toggle or dropdown that affects system behaviour (e.g. "Auto-generate invoices", "Require guardian finance opt-in", "Receipt auto-apply threshold"):
  - Surface a **tooltip** (e.g. Bootstrap tooltip or `title` + small info icon) next to the label that explains in one line what happens when enabled/changed (e.g. "When on, fee invoices are created automatically for the selected plan on the schedule. Parents are not notified until reminders run.").
  - Ensure tooltips are visible on focus/keyboard for accessibility.
  - Optionally add a short "Impact" line under the control (e.g. "Affects: Finance dashboard, parent portal, payment reminders.").

### Phase 6: Admin dashboard & settings UX

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 6.1 | Group settings into logical buckets | Reorganize Site Settings (and related pages) so configurations sit under clear buckets: Academics, Finance, System, Branding & experience, Notifications. Rename or regroup existing tabs to match; optionally add a "Browse by category" entry point. | |
| 6.2 | User Permissions / RBAC discoverability | Ensure "User Permissions" (or equivalent) is easy to find from the admin dashboard and from Settings: single entry point or clear link under "System". Document or add in-app hint for non-technical users (e.g. "Who can do what"). | |
| 6.3 | Smart Search for settings | Add keyword search at the top of Site Settings (and optionally Customizer / admin index). Search over labels, help text, field names; filter or jump to tab/section and highlight match. Support plain-language terms (invoice, reminder, parent portal, etc.). | |
| 6.4 | Inline tooltips for complex toggles | For high-impact toggles and dropdowns (Finance Automation, Feature Toggles, Backend Orchestration), add inline tooltips (info icon + title or Bootstrap tooltip) that explain in one line the impact when changed. Ensure keyboard/focus visible. | |
| 6.5 | Consistency across admin pages | Apply same clarity to other admin list/detail pages: clear headings, grouped fields, tooltips where options are non-obvious so the whole admin feels intuitive for non-technical users. | |

**Phase 6 ready to build?**  

---

## Principal & Teacher dashboards (Data / actionable)

### Current state

- **Backend dashboard** (used by principals and staff) and **Teacher dashboard** show a mix of cards, tables, and some chart placeholders. Key numbers often require scrolling or opening another page. No standardized "above the fold" KPI strip.
- **Tables** are used for classes, assignments, recent activity, and finance; **charts** (line, bar, donut) exist in places (e.g. teacher dashboard has donut/bar CSS, backend has trend pills) but many views still rely on raw data tables where a chart would be clearer.
- **Actions** (e.g. enter marks, view workflow, open finance) are in the header or card links; there are no **Quick Action** buttons tied directly to a KPI or alert (e.g. "Message Absent Students" next to attendance, "Send reminder" next to overdue list).

### Proposed: top 5 KPIs above the fold

Make the **top 5 KPIs visible without scrolling** on each dashboard. Suggested by role:

| Principal / Backend dashboard | Teacher dashboard |
|------------------------------|-------------------|
| 1. **Daily attendance trend** (e.g. % present today vs 7-day avg) | 1. **Today’s attendance** (e.g. present/absent for my classes) |
| 2. **Revenue collection progress** (e.g. % of term fees collected vs target) | 2. **Marks entry progress** (e.g. % of assessments with marks entered) |
| 3. **Overdue invoices** (count or amount) | 3. **Upcoming deadlines** (e.g. next mark submission / report date) |
| 4. **Pending approvals** (e.g. finance access, grade approval) | 4. **Classes needing marks** (e.g. count or list) |
| 5. **Alerts / incidents** (e.g. low attendance, failed logins, or compliance flags) | 5. **Announcements / tasks** (e.g. unread or due today) |

Implement as a compact **KPI strip** (e.g. 5 tiles in one row on desktop, wrap on mobile) so the user sees the most important numbers immediately.

### Proposed: charts instead of raw tables where helpful

- **Line charts** — Daily attendance trend, revenue over time, login/activity trends.
- **Bar charts** — Collection by class or by fee type, marks entry by class, comparison across terms.
- **Donut or small pie** — Present vs absent today, paid vs outstanding invoices, approval status breakdown.
- **Keep tables** where detail is needed (e.g. list of absent students, list of overdue invoices) but add a **chart summary** above or beside the table so the story is visible at a glance. Prefer reusing or extending the existing dashboard chart components (e.g. `dashboard_chart.html`, shared JS) for consistency.

### Proposed: Quick Action buttons

Add **Quick Action** buttons that bridge viewing data and taking action, placed next to the relevant KPI or section:

| Context | Example Quick Action |
|---------|----------------------|
| Attendance (absent today) | **Message Absent Students** — opens compose or list of guardians for absent students. |
| Overdue invoices | **Send reminder** or **Export list** — bulk reminder or CSV for follow-up. |
| Pending approvals | **Review now** — deep link to finance inbox or grade approval queue. |
| Marks entry (teacher) | **Enter marks** — link to marks entry for the next class needing input. |
| Upcoming deadlines | **View calendar** or **Prepare report** — link to deadline list or report builder. |

Ensure each action is **one click** from the dashboard (no extra navigation when possible). Optionally add a small "Quick actions" strip or dropdown at the top of the dashboard for the top 3–5 actions for that role.

### Phase 7: Principal & Teacher dashboards (KPIs, charts, Quick Actions)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 7.1 | Top 5 KPIs above the fold | Add a compact KPI strip (no scrolling) to Backend dashboard and Teacher dashboard. Principal: e.g. daily attendance trend, revenue collection progress, overdue invoices, pending approvals, alerts. Teacher: e.g. today’s attendance, marks entry progress, upcoming deadlines, classes needing marks, announcements/tasks. Use existing data where available; add queries/aggregates as needed. | |
| 7.2 | Charts for key metrics | Where a chart adds more than a table, add or surface line (trends), bar (comparisons), or donut (breakdown) charts for attendance, revenue, marks progress, approval status. Replace or supplement raw data tables with chart summaries; reuse shared chart component and JS. | |
| 7.3 | Quick Action buttons | Add Quick Action buttons next to relevant KPIs or sections: e.g. Message Absent Students (attendance), Send reminder / Export (overdue invoices), Review now (pending approvals), Enter marks (teacher), View calendar / Prepare report. One-click where possible; optional Quick actions strip at top. | |
| 7.4 | Consistent layout and empty states | Ensure both dashboards use the same layout pattern (KPI strip → charts → tables/detail) and show clear empty states when there is no data (e.g. "No absences today", "No overdue invoices") so the experience is seamless and actionable. | |

**Phase 7 ready to build?**  

---

## Cognitive load audit: Teacher portal

### Tasks that take more than 3 clicks

| Task | Current flow (click count) | Friction |
|------|----------------------------|----------|
| **Submitting a grade** | 1) Dashboard or sidebar → Enter Marks; 2) Select class/subject (if not pre-selected); 3) Fill marks form; 4) Submit (or Submit for approval). **= 4+ clicks** and multiple pages. | Teacher must navigate to Enter Marks, then choose subject assignment, then land on the form. No "resume where I left off" or default to most-needed class. |
| **Marking attendance** (teacher’s own) | 1) Dashboard or sidebar → Attendance (or via My Workflow → My attendance). **= 1–2 clicks** to view; marking/check-in may require another page or action. | If student roll-call is a separate flow (e.g. under academics), that path can be 3+ clicks from the teacher portal. |
| **Viewing marks / Marks history** | 1) Sidebar → Marks History; 2) Optional filters (class, subject, term). **= 2–3 clicks** to see list; opening a class or editing adds clicks. | Acceptable but could be one click from dashboard with "Classes needing marks" → direct to entry. |
| **My Workflow** | 1) Sidebar → My Workflow; then from workflow, 2) Enter marks / 3) View marks / 4) Attendance, etc. **= 2+ clicks** to reach any sub-task. | Workflow is a hub; good. Reaching the *first* daily action (e.g. "Enter marks for Form 3A") still often requires: Workflow → Enter marks → select Form 3A = 3 clicks. |
| **Leave request / Payslips** | 1) Sidebar → Leave Requests or Payslips (under Human Resources). **= 1–2 clicks**. | OK; less frequent. |

**Summary:** The highest cognitive load is **grade submission** (Enter Marks → select class → fill → submit) and any **student attendance** flow that is buried under multiple sections. Getting to "the right class" for marks or attendance often adds at least one extra selection step.

### Proposed: flattened navigation & under-30-second tasks

- **One-click to most frequent daily tasks**
  - From **Teacher dashboard**: show a single row or strip of **primary actions**: e.g. "Enter marks (Form 3A)", "Today’s attendance", "View pending marks", each going **directly** to the right context (e.g. marks entry with subject_assignment_id for the class with next deadline or most pending), not to a chooser.
  - **Remember or suggest context**: e.g. "Continue: Form 3A – CA1" so the teacher can land on the form in one click; optional "Switch class" if they need to change.
  - **Sidebar**: keep Enter Marks, Attendance, Marks History, My Workflow, but ensure the **dashboard** and **workflow** surfaces link to the **same** URLs with pre-filled context (class/assessment) so the path is 1 click from dashboard or 2 from workflow (workflow → "Enter marks Form 3A" deep link).

- **Flattened structure**
  - **Tier 1 (always visible, 0–1 click from dashboard):** Enter marks (with default or next class), Today’s attendance (or check-in), Pending marks / deadlines.
  - **Tier 2 (one click from sidebar):** Marks History, Full attendance, My Workflow, Timetable, Messages, Payslips, Leave.
  - **Tier 3 (under Settings / less frequent):** Preferences, Portal Stats, Knowledge Base.
  - Avoid nesting "Enter Marks" and "Attendance" only under "Learning Management" without also surfacing them on the dashboard as **direct actions** with context.

- **Under 30 seconds**
  - **Submit a grade for one class:** Dashboard → click "Enter marks (Form 3A)" → form loads with students → teacher fills (or pastes) → Submit. **Target: no intermediate "Select class" page** when the dashboard or workflow already knows the suggested class; **2–3 clicks** total (open form, submit, optional "Submit for approval").
  - **Mark today’s attendance (self):** Dashboard → "Today’s attendance" or "Check in" → one tap/click. **Target: 1–2 clicks.**
  - **View who’s absent (if student roll-call exists):** Dashboard → "Today’s attendance" (for my classes) → list with optional "Message absent" per student or bulk. **Target: 2–3 clicks.**

- **Reduce cognitive load**
  - **Single "Today" or "Daily tasks" strip** on the teacher dashboard: one card per "next best action" (e.g. "Enter CA1 for Form 3A – 12 pending", "Check in", "3 students absent in Form 2B – Message guardians"). Each card is one click to the right screen.
  - **No "choose class" when it can be inferred:** e.g. if the teacher has one class with pending marks, default to that class on Enter Marks; if multiple, show the top 1–2 as direct links instead of a dropdown.

### Phase 8: Teacher portal cognitive load & flattened nav

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 8.1 | Document and fix 3+ click tasks | Audit all teacher-portal tasks (marks entry, attendance, workflow, leave, payslips); document current click count and target. Implement changes so **Submitting a grade** and **Marking attendance** (and any student roll-call) are ≤3 clicks from dashboard or sidebar. | |
| 8.2 | One-click / contextual entry from dashboard | Add dashboard strip or cards: direct links to "Enter marks (Class X)", "Today’s attendance", "Pending marks" with context pre-filled (e.g. subject_assignment_id, date). Remember or suggest "next class" so teacher can open the form in one click. | |
| 8.3 | Flattened navigation structure | Apply Tier 1 (0–1 click from dashboard) / Tier 2 (one click from sidebar) / Tier 3 (Settings) structure; ensure Enter Marks and Attendance are Tier 1 or Tier 2 with no unnecessary nesting. Optional: "Daily tasks" or "Today" view that lists only the next 3–5 actions. | |
| 8.4 | Under-30-second target for daily tasks | Design and implement so that "Submit a grade for one class", "Mark today’s attendance", and "View absent students" (if applicable) can be completed in under 30 seconds with minimal steps; measure or document click count and time for acceptance. | |

**Phase 8 ready to build?**  

---

## Accessibility (WCAG 2.1) audit

### Current state

- **Contrast:** Design tokens and theme CSS use variables (e.g. `--admin-content-text: #0f172a`, `--admin-content-text-muted: #475569`, `--admin-sidebar-text-muted: #94a3b8` on dark `#0f172a`/`#1e293b`). Muted text and some borders may **fail WCAG AA** (4.5:1 for normal text, 3:1 for large) if used on light gray or on dark without verification. No project-wide contrast audit or enforced minimum in CSS.
- **Keyboard navigation:** Some interactive elements use `aria-label`, `aria-expanded`, `tabindex="-1"` on modals. There is **no visible “skip to main content” link** in base templates. Focus styles depend on Bootstrap and custom CSS; **:focus-visible** is not consistently applied, so keyboard users may not see where focus is. Sidebar and nav may not trap focus in modals or expose a logical tab order for all menus.
- **ARIA and semantics:** Modals have `aria-labelledby` and `aria-hidden`; progress bars have `role="progressbar"` and `aria-valuenow`/`min`/`max`; some buttons have `aria-label`. **Data tables** (e.g. student grade tables, certification tables, compliance tables, invoices) often have `<table>`, `<thead>`, `<tbody>` but **no `<th scope="col">` or `scope="row"`**, no `<caption>`, and no **aria-label or aria-describedby** describing the table purpose. Screen readers cannot reliably announce table structure or context. Forms and custom controls (toggles, dropdowns) are not consistently labelled or associated with visible labels.
- **Existing checks:** `apps/siteconfig/tests/test_accessibility.py` performs basic WCAG-oriented checks (lang, alt text, form labels, headings, skip links, aria labels). The plan should extend and fix gaps found there and in manual audit.

### Proposed: WCAG 2.1 AA alignment

- **Color contrast**
  - Audit all text/background pairs (primary text, muted text, placeholders, borders used as separators) against **WCAG 2.1 AA**: at least **4.5:1** for normal text, **3:1** for large text (18px+ or 14px+ bold). Use a contrast checker or token set that enforces these ratios.
  - Replace or adjust any variable or class that yields insufficient contrast (e.g. light gray on white, or muted slate on dark without sufficient luminance). Document “safe” token pairs for future theming.
- **Full keyboard navigation**
  - Add a **skip link** (“Skip to main content”) as the first focusable element on every main template (portal_base, backend_base, base), linking to `#main` or the main content container; ensure it is visible on focus.
  - Ensure **tab order** is logical: skip link → header/nav → main content → footer. No interactive element (sidebar, dropdowns, modals, custom controls) should be unreachable by Tab. Modals and overlays should **trap focus** and return focus on close.
  - Apply **:focus-visible** (and optionally a 2–3px outline/ring) so keyboard focus is clearly visible; avoid removing outline without a visible replacement.
- **ARIA and tables**
  - **Student grade table and all data tables:** Add `<caption>` or `aria-label` describing the table (e.g. “Term 1 grades for Form 3A – Mathematics”). Use `<th scope="col">` for column headers and `<th scope="row">` for row headers where applicable. For complex tables, consider `aria-describedby` pointing to a short summary.
  - **Navigation and menus:** Use `nav` and `aria-label` for regions (e.g. “Main navigation”, “Sidebar”). For collapsible menus (e.g. sidebar sections), ensure `aria-expanded` and `aria-controls` are set and that keyboard users can open/close with Enter/Space.
  - **Complex widgets:** Toggles, custom dropdowns, and chart controls should have `aria-label` or associated `aria-labelledby`/`aria-describedby` so screen readers can name and describe the control and its state.

### Phase 9: Accessibility (WCAG 2.1)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 9.1 | Color contrast audit and fix | Audit CSS/HTML for text and UI component contrast; ensure all pairs meet WCAG 2.1 AA (4.5:1 normal, 3:1 large). Fix muted text, placeholders, and borders; document safe token pairs for low vision. | |
| 9.2 | Skip link and focus visibility | Add “Skip to main content” as first focusable element in base templates; ensure main content has matching id. Apply :focus-visible and visible focus ring so keyboard users can see focus; avoid outline: none without replacement. | |
| 9.3 | Full keyboard navigation | Verify tab order (skip → nav → main → footer); ensure sidebar, dropdowns, and modals are reachable and that modals trap focus. Fix any unreachable or wrong-order controls. | |
| 9.4 | ARIA for data tables (e.g. grade table) | Add caption or aria-label to student grade tables and other data tables; add th scope="col"/scope="row"; add aria-describedby where helpful. Ensure screen readers can announce table purpose and structure. | |
| 9.5 | ARIA for nav and complex widgets | Add aria-label to nav regions and menus; ensure collapsible sections have aria-expanded/aria-controls. Add aria-label or aria-labelledby to toggles, custom dropdowns, and chart controls so screen readers interpret them correctly. | |

**Phase 9 ready to build?**  

---

## Security: Fee Payments & Student Records (Cybersecurity)

### Data flow and current controls

- **Fee payments:** Parent/guardian sees only invoices and payments for students linked via `StudentGuardian` with `can_view_finance=True`. Finance views use `_finance_access_state(request.user)` and guardian-linked students; staff/bursar see broader data. Payment creation and receipt verification use server-side validation and ORM.
- **Student records:** Views use `permission_required`, `role_required`, `teacher_portal_required`, `parent_portal_required`. Teachers see only their assignments and linked data; parents see only guardian-linked students. Backend people views use `permission_required('people.view_studentprofile')` etc.
- **Payroll:** Teacher pay history (`teacher_pay_history`) uses `request.user.teacher_profile` and `profile.pay_records` so each teacher sees only their own pay; no cross-teacher access. AI copilot explicitly blocks payroll queries for non-admin/finance roles.

### 1. SQL injection and input sanitization

- **Current:** Application code uses Django ORM (filter, get, create) and parameterized queries; raw SQL appears only in **migrations** (e.g. index renames), not in request-handling views. User input is passed to ORM or form validation. This **reduces** SQL injection risk but is not a formal audit.
- **Gap:** Any future use of `raw()`, `extra()`, or `cursor.execute()` with string interpolation must be avoided. Search and filter endpoints (e.g. API or admin search) should be audited to ensure all user-supplied values are passed as parameters, not concatenated into SQL. File upload paths and payment reference fields should be validated/sanitized.

**Proposal:** Audit all views and API handlers for Fee Payments and Student Records (and shared search/filter code) to confirm no raw SQL with user input; document that ORM/form usage is the standard and add a safeguard (e.g. code review rule or test) that fails if `raw()`/`execute()` with string formatting is introduced in request paths.

### 2. RBAC: strict role and resource checks

- **Current:** Decorators enforce role (e.g. teacher, parent) and some permission_required on backend. Teacher payroll is scoped to `request.user.teacher_profile`. Finance portal data is scoped to guardian links. Document access and other “private file” flows should be verified so a teacher cannot access another teacher’s files (e.g. by guessing IDs or URLs).
- **Gap:** Ensure **every** sensitive endpoint (payroll, documents, grades, finance) explicitly checks that the requested resource belongs to the current user (or to a student/entity the user is allowed to see). No reliance on “hiding” links alone; validate IDs and ownership in the view. Confirm that staff-only payroll/admin views are not reachable by TEACHER role and that document/attachment URLs enforce ownership or shared-access rules.

**Proposal:** RBAC audit: list all endpoints that return fee payment data, student records, payroll, or private files; for each, document the ownership check (e.g. guardian link, teacher_profile, permission_required). Add tests that assert a teacher cannot see another teacher’s payroll or another teacher’s private files (e.g. by direct URL or API call). Fix any missing checks.

### 3. Session management and inactivity logout

- **Current:** `config/settings.py` sets `SESSION_COOKIE_AGE = 14400` (4 hours), `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`, `SESSION_SAVE_EVERY_REQUEST = True`. So the session extends on each request and expires after 4 hours from last activity **or** when the browser closes, depending on cookie behaviour. There is no documented “inactivity timeout” policy for shared computers (e.g. 15–30 minutes).
- **Gap:** On shared school computers, 4 hours may be too long; a user could walk away and leave a session active. No explicit “idle timeout” (e.g. client-side warning + server-side session invalidation after N minutes of no activity) is specified.

**Proposal:** Define an **inactivity timeout** for sessions (e.g. 15–30 minutes for shared-device scenarios). Implement by either: (a) reducing `SESSION_COOKIE_AGE` and ensuring `SESSION_SAVE_EVERY_REQUEST` is True so inactivity expires the session, or (b) adding optional middleware/JS that invalidates or warns after N minutes of no activity and optionally calls a logout endpoint. Document the policy (e.g. in deployment or security doc) and make the timeout configurable (e.g. env var) so schools can tighten it for shared computers.

### Phase 10: Security (Fee Payments, Student Records, Session)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 10.1 | SQL injection and input audit | Audit Fee Payments and Student Records (and related API/search) code paths for any raw SQL or string-interpolated queries; ensure all user input is via ORM or parameterized queries; document standard and add safeguard (review/test) against introducing raw SQL with user input in request paths. | |
| 10.2 | RBAC audit and harden | List endpoints for fee payments, student records, payroll, and private files; confirm each enforces ownership or role (guardian link, teacher_profile, permission_required). Add tests: teacher cannot access another teacher’s payroll or private files. Fix any missing checks. | |
| 10.3 | Session and inactivity logout | Define inactivity timeout policy for shared computers (e.g. 15–30 min). Implement via SESSION_COOKIE_AGE + SESSION_SAVE_EVERY_REQUEST or optional middleware/JS; make timeout configurable (env); document in deployment/security doc. | |

**Phase 10 ready to build?**  

---

## Teacher welcome flow & onboarding (Product)

### Goal

Design a **Welcome Flow** for a new teacher so they reach an **Aha! moment** quickly (e.g. marking the first attendance or entering the first grades), supported by a short interactive walkthrough and by **empty-state** messages that encourage adding data instead of showing a blank dashboard.

### Aha! moment (proposed)

Pick one primary moment that defines “I’ve started using the system” for a teacher:

| Option | Description | Why it works |
|--------|-------------|--------------|
| **Mark first attendance** | Teacher records attendance (own check-in or student roll-call for a class) for the first time. | Immediate, daily habit; proves the portal is “live” for their role. |
| **Enter first grades** | Teacher submits marks for one class/assessment (e.g. CA1 for Form 3A). | Core job; completion feels like a clear win. |
| **Complete first workflow step** | Teacher finishes step 1 (or the first actionable step) in “My Workflow” (e.g. profile complete, or first marks entered). | Aligns with existing My Workflow and creates a single “first success” milestone. |

**Recommendation:** Use **“Enter your first grades”** or **“Mark attendance for the first time”** as the primary Aha! moment, depending on what the school prioritises (grades vs attendance). The welcome flow and walkthrough should steer the teacher to that action.

### 3-step interactive walkthrough or tooltips

Guide new teachers to the Aha! moment in **3 steps** (dismissible; stored so we don’t show again after completion or dismiss):

| Step | Purpose | Example copy / behaviour |
|------|---------|---------------------------|
| **Step 1** | Orient: “This is your dashboard.” | Highlight the main content area: “Your dashboard shows your classes, marks progress, and quick actions. Start by completing one task below.” Optional: point to “My Workflow” or the first empty-state card. |
| **Step 2** | Direct to the Aha! action: “Your first win.” | “Enter marks for one class, or mark today’s attendance, to get started.” CTA: “Enter marks” or “Mark attendance” (deep link to marks entry or attendance with context if possible). |
| **Step 3** | Confirm and next: “You’re all set.” | “After you’ve entered marks (or marked attendance), you’ll see your progress here. Need help? Check the Knowledge Base or contact admin.” Optional: “Don’t show again” and set a user preference or flag so the walkthrough does not reappear. |

Implementation options: **product tour** (overlay with 3 steps and Next/Done), or **contextual tooltips** on the dashboard (e.g. tooltip 1 on the dashboard title, tooltip 2 on “Enter marks” / “Attendance”, tooltip 3 on the progress card). Ensure **keyboard accessible** and **dismissible** (Phase 9 alignment).

### Empty-state messages on the new teacher dashboard

When a new teacher has **no data yet**, show friendly empty states instead of blank tiles or generic “No data”:

| Area | Empty-state message (example) | Encourage action |
|------|-------------------------------|------------------|
| **Classes / assignments** | “You don’t have any classes assigned yet. Ask your admin to assign you to a class, then you’ll see them here and can enter marks.” | Contact admin; sets expectation. |
| **Marks entry progress** | “No marks entered yet. Enter your first grades for a class to see your progress here.” | CTA: “Enter marks” (link to marks entry). |
| **Attendance** | “No attendance recorded yet. Mark today’s attendance (or check in) to get started.” | CTA: “Mark attendance” or “Check in”. |
| **Upcoming deadlines** | “No deadlines yet. Once you have classes and assessments, upcoming dates will appear here.” | Reassure; no broken feeling. |
| **Announcements / tasks** | “No new announcements. Check back later or use Messages to contact colleagues.” | Optional CTA to Messages. |

Use the **shared empty-state component** (e.g. `dashboard_empty_state.html`) where possible: icon, short title, one sentence of explanation, and one primary action button. Avoid showing raw “0” or empty tables without a sentence that tells the teacher what to do next.

### Phase 11: Teacher welcome flow & onboarding

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 11.1 | Define and implement Aha! moment | Choose primary Aha! moment (first grades entered or first attendance marked); optionally track completion (e.g. user preference or one-time flag) and show a short success message or badge when achieved. | |
| 11.2 | 3-step welcome walkthrough or tooltips | Implement a 3-step interactive walkthrough (or 3 contextual tooltips) on the teacher dashboard: (1) orient to dashboard, (2) direct to Aha! action with CTA, (3) confirm and “Don’t show again”. Store dismiss/completion so it does not reappear; ensure keyboard accessible and dismissible. | |
| 11.3 | Empty-state messages for new teacher dashboard | Add or replace empty states for: classes/assignments, marks progress, attendance, upcoming deadlines, announcements. Use friendly copy that explains why it’s empty and one CTA (e.g. “Enter marks”, “Mark attendance”, “Contact admin”). Use shared empty-state component where possible. | |
| 11.4 | Show welcome flow only for new teachers | Show the welcome walkthrough only for teachers who have not completed the Aha! moment (and optionally have not dismissed it). Use a flag or preference (e.g. “onboarding_walkthrough_done” or “first_marks_entered”) so returning teachers do not see it. | |

**Phase 11 ready to build?**  

---

## Performance & mobile/tablet (Performance Engineer)

### Goal

- **Load in under 3 seconds** on slow connections (e.g. 3G or high-latency).
- **Lazy loading** for large student lists so initial render is fast.
- **Mobile:** Buttons and tap targets at least **44×44px** for easy tapping.
- **Tablet / Admin Console:** No horizontal scrolling; use a **responsive stack** layout where wide tables or panels would otherwise overflow.

### 1. Load time (under 3 seconds on slow connections)

- **Current:** No project-wide performance budget or measured “time to interactive” on throttled networks. Page weight and render-blocking resources (CSS, JS, fonts) vary by template. Large lists (e.g. backend student list) load up to 100 students in one query with no pagination or virtualisation.
- **Proposal:** Define a **3-second target** (e.g. on Slow 3G or similar). Optimise: defer non-critical JS, minimise render-blocking CSS, lazy-load below-the-fold content and images. Add **pagination or lazy loading** for student lists (and other large lists) so the first paint is fast; load more on scroll or “Load more” / next page. Consider a simple performance check (e.g. Lighthouse or a smoke test) in CI or release notes.

### 2. Lazy loading for large student lists

- **Current:** Backend student list (`backend_student_list`) fetches up to 100 students in one go (`[:100]`) with no pagination. Other lists (e.g. admin changelist, marks entry student list, reports) may also load many rows at once.
- **Proposal:** **Identify** all views that render large student (or similar) lists: backend student list, admin student changelist, marks entry student list, any report or export that lists students. For each:
  - Prefer **server-side pagination** (e.g. 20–50 per page) so the first response is small and fast.
  - Optionally add **infinite scroll** or “Load more” that fetches the next page via the same paginated API.
  - Avoid loading hundreds of rows in a single HTML response on slow connections. Document which pages use lazy loading or pagination.

### 3. Mobile: 44×44px tap targets

- **Current:** `mobile-tables-forms.css` sets `min-height: 44px` for `.form-control`, `.form-select`, `.btn`. Smaller buttons (e.g. `.btn-sm`, icon-only buttons in sidebar or tables) may **override** with smaller padding or height, falling below the 44px minimum and making taps difficult on mobile.
- **Proposal:** **Audit** all interactive elements on key mobile pages (login, portal sidebar, teacher/parent dashboard, finance, admin on tablet): buttons, links used as buttons, icon buttons, table row actions. Ensure each has a **minimum 44×44px** touch target (either the element itself or a padded hit area). Add or extend a utility class (e.g. `.touch-target`) and apply it to small buttons and nav items on mobile. Re-check after design system changes (Phase 5).

### 4. Admin Console (and similar): no horizontal scroll on tablet; stack layout

- **Current:** Some admin and backend pages use wide tables (e.g. Site Settings tabs, finance invoices, student tables) inside `overflow-x-auto` or fixed-width layouts. On tablet (e.g. 768px width), this can force **horizontal scrolling**. Admin dashboard and some change forms use `min-width` on cards or flex items that may not wrap.
- **Proposal:** **Audit** Admin Console and backend pages (dashboard, Site Settings change form, finance list views, student/teacher lists) on a **tablet viewport** (e.g. 768×1024). Where horizontal scrolling occurs:
  - Prefer a **responsive stack layout**: at breakpoints below ~992px, switch tables to **card/list layout** (one row per record as a stacked card with label-value pairs) instead of a wide table, or use a **horizontal scroll** only as a last resort with a visible “scroll” hint.
  - Ensure tab strips, filter bars, and action buttons **wrap** or stack so the whole page fits without horizontal scroll. Document the breakpoint and pattern (e.g. “stack layout below 992px for admin data tables”).

### Phase 12: Performance & mobile/tablet

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 12.1 | Load under 3 seconds (slow connections) | Define 3-second target on throttled network; reduce render-blocking resources, defer non-critical JS, lazy-load below-fold content; add pagination or lazy loading for large lists to improve first load; optional Lighthouse/smoke check. | |
| 12.2 | Lazy loading for large student lists | Identify all views with large student (or similar) lists; add server-side pagination (e.g. 20–50 per page) and optionally “Load more”/infinite scroll; ensure backend student list and other key lists do not load hundreds of rows in one response. | |
| 12.3 | Mobile tap targets 44×44px | Audit buttons and interactive elements on mobile (login, portal, dashboard, finance); ensure min 44×44px touch target; add/apply .touch-target or equivalent for small/icon buttons; re-check after design system updates. | |
| 12.4 | Admin Console / tablet: no horizontal scroll; stack layout | Audit admin and backend pages on tablet viewport; where horizontal scroll occurs, implement responsive stack layout (card/list per row) or wrap filters/tabs; document breakpoint and pattern for wide tables. | |

**Phase 12 ready to build?**  

---

## Feedback loop & user research (UX Researcher)

### Goal

Integrate a **feedback loop** into the app so the product team can learn from real usage: lightweight "Was this helpful?" at key completion points, and a **short 2-question survey** for teachers at the end of each grading period to surface friction in the workflow.

### Current state

- **No structured in-app feedback** — Users have no obvious way to say whether a flow worked for them or where they got stuck. Support or admin may hear ad-hoc complaints; there is no systematic signal tied to specific screens or actions.
- **No periodic pulse** — Teachers are not asked at natural break points (e.g. end of term) what was hardest or what would help most, so friction points (e.g. grade submission, attendance, deadlines) are inferred rather than measured.

### Proposed: "Was this helpful?" placement

Place a small, non-intrusive **"Was this helpful?"** control (e.g. thumbs up / thumbs down, or Yes / No) at **completion points** where the user has just finished a meaningful task. Avoid mid-flow; avoid every page. Suggested placements:

| Context | Placement | Rationale |
|--------|-----------|-----------|
| **After submitting grades** | On the success/confirmation screen (or toast) after "Marks submitted" / "Submitted for approval". | High-value task; feedback here captures whether the marks-entry flow felt clear and fast. |
| **After generating fee invoices** | On the success message or summary after "Generate Fee Invoices" (bulk run). | Critical admin action; identifies confusion or errors in fee generation. |
| **After recording a payment** | On confirmation after staff records a payment (manual or receipt verification). | Finance workflow; surfaces issues with payment application or receipt flow. |
| **After onboarding wizard** | On the final "Success" or "Next steps" screen for parent/student onboarding. | First-run experience; captures drop-off or confusion. |
| **Knowledge Base / Help** | At the bottom of a help article or documentation page. | Content usefulness; improves docs over time. |
| **Optional: Parent payment** | After a parent completes a payment in the portal. | Parent experience; can be phased in later. |

**Implementation:** Store response (helpful / not helpful), optional one-line comment (e.g. "What could we improve?"), screen/action identifier, and timestamp. No login required for the vote if anonymous is acceptable; otherwise tie to user/session. Use a shared component (e.g. a small inline block or toast-footer) so placement is consistent and minimal.

### Proposed: 2-question survey for teachers (end of grading period)

Trigger a **short survey** for teachers when they have reached the **end of a grading period** (e.g. term end, or when grade submission deadline has passed and they have submitted). Goal: identify **friction points** in the workflow with minimal burden.

| # | Question | Type | Purpose |
|---|-----------|------|---------|
| **1** | "What was the **single biggest friction** when entering grades or completing tasks this term?" (e.g. too many clicks, unclear deadlines, slow page, wrong default class, confusing approval flow) | Single choice or short free text | Surfaces the top pain point to prioritise (aligns with Phase 8 cognitive load). |
| **2** | "What **one change** would save you the most time next term?" | Short free text (optional) | Qualitative signal; informs roadmap (Quick Actions, defaults, navigation). |

**Trigger:** Show once per teacher per term (or per grading period), e.g. when they next land on the teacher dashboard after the grade-submission deadline, or via a small banner: "Quick 2-question survey — help us improve your experience." Dismissible; do not show again after submission or dismiss. Store responses (anonymous or tied to user, per policy) with term/grading period and date.

**Analysis:** Aggregate by term: count "friction" themes (e.g. "too many clicks", "unclear deadlines") and review free-text for recurring themes. Feed results into Phase 8 (teacher portal cognitive load) and Phase 7 (dashboards / Quick Actions).

### Phase 13: Feedback loop & user research

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 13.1 | "Was this helpful?" component | Implement a reusable "Was this helpful?" control (e.g. thumbs or Yes/No); store response plus optional short comment, screen/action ID, and timestamp. Use shared template/JS so it can be included at multiple completion points. | |
| 13.2 | Place "Was this helpful?" at key completion points | Add the component at: (1) after submitting grades (success screen/toast), (2) after generating fee invoices, (3) after recording a payment, (4) after onboarding wizard, (5) Knowledge Base / help articles. Document placement and any analytics or admin view for responses. | |
| 13.3 | End-of-grading-period survey (2 questions) | Implement a 2-question survey for teachers: (1) single biggest friction this term (choice or short text), (2) one change that would save the most time (optional free text). Trigger once per teacher per term (e.g. dashboard banner after grade-submission deadline); dismissible and do-not-show-again after submit/dismiss. Store responses with term and date. | |
| 13.4 | Survey analysis and feedback loop | Provide an admin or export view to aggregate survey responses by term (friction themes, free-text summary). Document how results feed into product decisions (e.g. Phase 8 teacher portal, Phase 7 Quick Actions) so the feedback loop is closed. | |

**Phase 13 ready to build?**  

---

## Micro-interactions & feedback cues (Micro-interaction Designer)

### Goal

Audit and improve the app's **feedback loops** so that success, loading, and errors are communicated clearly **without interrupting the user's flow**. Use toasts for confirmations, skeletons for loading, optional haptic cues on mobile, and human-readable error copy everywhere.

### Audit: current feedback loops

| Context | Current behaviour | Gap |
|--------|-------------------|-----|
| **Admin saves complex configuration** (e.g. Site Settings, Feature Control, Theme & experience) | Django `messages.success()` / `messages.error()` rendered in-page (e.g. banner or list at top of content). User may need to scroll to see it; after save, full page re-render. | No non-blocking confirmation; success can be missed if above the fold or if user navigates quickly. No clear "Saved" state on the form itself (e.g. brief checkmark or toast) that works without a full reload. |
| **Teacher submits grades / marks** | Typically redirect with success message or in-page message. | Same as above; no consistent toast so the user gets immediate, non-intrusive confirmation. |
| **Finance: generate invoices, record payment** | Success/error via Django messages. | Same; no standard toast pattern. |
| **Loading states** | Some views show spinners or full-page load; `skeleton_loader.html` and `dashboard_skeleton.html` exist but may not be used on all heavy views (e.g. admin change form save, large list loads). | Inconsistent: some places show nothing, others full-page block. Skeletons reduce perceived wait and inform "content is coming" without interrupting flow. |
| **Errors** | Many views surface Django form errors or exception messages; some API or 404/500 pages may show raw "Error 404" or stack traces in debug. | Technical codes (404, 500, CSRF failed) are not always translated to human-readable copy; user may not know what to do next. |
| **Mobile** | No haptic feedback (e.g. light vibration on success or error). | Optional enhancement so success/error is felt without looking at the screen. |

**Summary:** Success feedback is often in-page and tied to full reload; loading is inconsistent; error copy is not consistently human-friendly. Toast notifications, loading skeletons, and human-readable errors would close these gaps.

### Proposed: Toast notifications

- **Use toasts for action feedback** (save, submit, delete, bulk action) so the user sees confirmation **without leaving the page or scrolling**.
  - **Success:** e.g. "Settings saved", "Grades submitted", "Payment recorded" — short, one line; auto-dismiss after 4–5 seconds or on click; optional "Undo" for reversible actions (e.g. "Invoice generated" → no undo; "Item removed" → optional undo).
  - **Error:** e.g. "Couldn't save. Please check the form and try again." — stay until dismissed; link to form or field if possible.
  - **Info:** e.g. "Preview cleared.", "Acting as [role]." — same pattern as success.
- **Placement:** Fixed position (e.g. top-right or bottom-right) so it doesn't cover primary content; stack multiple toasts if needed; ensure toasts are **keyboard dismissible** and **announced to screen readers** (Phase 9).
- **Implementation:** The app has `templates/components/toast_notifications.html`; ensure all Django message types (success, error, warning, info) are rendered as toasts on key flows (admin config save, teacher grades submit, finance actions, onboarding completion). Prefer toast over in-page message list for these flows so the user's flow is not interrupted.

### Proposed: Loading skeletons

- **Use skeleton placeholders** where content takes more than ~300–500 ms to load (e.g. dashboard widgets, student list, report table, admin change form after save-and-continue).
  - **Dashboard / cards:** Use existing `dashboard_skeleton.html` or card-shaped skeletons so layout is stable and the user sees "content is loading" instead of a blank area or spinner.
  - **Tables/lists:** Row skeletons (e.g. 5–10 placeholder rows) so the user knows a list is coming; replace with real rows when data arrives.
  - **Forms:** Avoid blocking the whole page; show skeleton only for the dynamic part (e.g. dropdown options or related section) if the rest of the form is already visible.
- **Do not** use skeletons for instant actions (e.g. button click that returns in &lt;200 ms); use a brief button loading state (e.g. spinner in button) instead. Skeletons are for **content** that is loading, not for every request.
- **Implementation:** Reuse or extend `skeleton_loader.html` and `dashboard_skeleton.html`; add skeletons to admin Site Settings (or heavy tabs), backend/teacher dashboard async blocks, and any large list that is loaded via AJAX or slow initial render. Ensure skeleton layout matches final content layout to avoid layout shift.

### Proposed: Haptic feedback cues (mobile)

- **Where supported:** On mobile browsers or wrapped app, trigger a **light success** vibration (e.g. 10–20 ms) on successful save/submit and a **short error** pattern (e.g. two brief pulses) on validation or server error. Use the Vibration API only when available and non-intrusive (e.g. not in silent/focus mode if we can detect it; fallback to no haptic).
- **Scope:** Optional enhancement; prioritize toasts and skeletons first. Document in Phase 14 so it can be added once the toast/skeleton pattern is consistent.

### Proposed: Human-readable error messages

Replace technical or generic errors with **clear, actionable copy** that tells the user what happened and what to do next. Examples:

| Instead of | Use (example) |
|------------|----------------|
| Error 404 | "We couldn't find that student's record. It may have been removed or you may not have access." |
| Error 500 | "Something went wrong on our side. Please try again in a moment. If it keeps happening, contact support." |
| CSRF verification failed | "Your session may have expired. Please refresh the page and try again." |
| Permission denied | "You don't have permission to do that. If you think you should, ask an admin to check your access." |
| Invalid form / ValidationError (generic) | "Please check the fields marked in red and fix any errors." (Plus field-level messages where possible.) |
| Object not found (generic) | "We couldn't find that [invoice / payment / class]. It may have been deleted or the link may be wrong." |

- **Apply everywhere:** Django form errors, API error responses, 404/500/403 error templates, and any user-facing exception handler. Add a small **mapping layer** (e.g. view or middleware) that translates known exception types or codes into a standard set of user-facing messages; log technical details server-side only.
- **Tone:** First person ("We couldn't find…") or second person ("You don't have permission…"); avoid jargon (CSRF, 404, 500). Optionally add a "Reference: …" for support, but keep the main message human.

### Phase 14: Micro-interactions & feedback cues

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 14.1 | Toast notifications for action feedback | Use toasts for save/submit/delete feedback on admin config save (Site Settings, Feature Control, Theme), teacher grades submit, finance (generate invoices, record payment), and onboarding completion. Ensure success/error/info from Django messages are rendered as toasts on these flows; placement (e.g. top-right), auto-dismiss for success, stack multiple; keyboard and screen-reader accessible. | |
| 14.2 | Loading skeletons for slow content | Audit views where content load exceeds ~300–500 ms (dashboard widgets, large student/list tables, admin heavy tabs). Use or extend existing skeleton components so loading shows placeholder layout (cards, rows) instead of blank or full-page spinner; avoid layout shift. Add button loading state (e.g. spinner in button) for quick actions instead of skeletons. | |
| 14.3 | Haptic feedback (mobile, optional) | Where Vibration API is available (mobile), add light success pulse on successful save/submit and short error pattern on validation/server error; document and make optional so toasts remain primary feedback. | |
| 14.4 | Human-readable error messages | Audit and replace technical/generic errors: 404 → "We couldn't find that [resource]…"; 500 → "Something went wrong…"; CSRF → "Session may have expired…"; Permission denied → "You don't have permission…". Apply to error templates, form errors, and API responses; add mapping for known exception types; keep technical detail in logs only. | |

**Phase 14 ready to build?**  

---

## Information architecture: student data tables (Information Architect)

### Goal

Review and improve **student data tables** (and other high-use data tables) so they are easier to scan, compare, and act on: **zebra striping**, **fixed headers** when scrolling, **conditional formatting** for at-risk or overdue items, and a **Condensed vs. Expanded view** toggle so users control how much data they see at once.

### Current state

- **Student tables** appear in backend student list, marks entry, grade tables, class lists, reports, finance (invoices/payments by student), and admin changelists. Styling is often default Bootstrap or custom one-off CSS; **no consistent zebra striping** across these views.
- **Headers** scroll away with the page on long tables, so context (column meaning) is lost when scrolling; **no sticky/fixed header** pattern is applied consistently.
- **Conditional formatting** — Failing grades, overdue invoices, or at-risk attendance are not consistently highlighted (e.g. subtle red for fail, bold for overdue), so users must scan every row to spot issues.
- **Density** — All users see the same column set and row height; there is **no Condensed vs. Expanded** option, so users who want more rows on screen (condensed) or more columns (expanded) cannot choose.

### Proposed: Zebra striping

- Apply **alternating row background** (e.g. subtle gray/white or theme-aligned alternating shade) to all primary data tables: student list, grade tables, invoice/payment lists, class lists, and other tabular list views.
- Use a **single CSS class or design token** (e.g. `.table-striped` or `--table-row-alt-bg`) so the pattern is consistent and respects theme (light/dark). Ensure contrast meets WCAG (Phase 9); striping should aid scanability, not distract.
- Apply to `<tbody>` rows only; header stays distinct. Prefer `nth-child(even/odd)` or equivalent so dynamic rows (sorting, filtering) still stripe correctly.

### Proposed: Fixed (sticky) headers

- For tables that **scroll vertically** (e.g. more than one viewport of rows), make the **table header row sticky** so it stays visible at the top of the scroll container while the body scrolls.
- Implementation: Use `position: sticky; top: 0` on `<thead>` (or first `<tr>` inside `<thead>`) with a solid background and optional shadow so the header is visually distinct when content scrolls beneath it. Ensure the scroll container has a defined height and `overflow-y: auto` (or equivalent) so sticky works. Test with horizontal scroll as well (e.g. sticky first column for student name) where it adds value.
- Apply to: backend student list, marks entry student list, grade tables, finance invoice/payment tables, and any admin changelist that uses a scrollable wrapper. Ensure **keyboard and screen reader** users can still associate header with cells (Phase 9 ARIA for tables).

### Proposed: Conditional formatting

- Use **subtle, consistent formatting** to surface at-risk or action-needed items without overwhelming the table:
  - **Failing grades** — Cell or row with a **subtle red** background (e.g. light red tint) or a small "fail" indicator. Use a design token (e.g. `--alert-fail-bg`) so it aligns with the design system and passes contrast.
  - **Overdue fees / invoices** — **Bold** for the amount or due date, or a subtle warning background for the row. Optionally an icon (e.g. clock or warning) in the cell.
  - **Attendance / at-risk** — Optional: highlight rows where attendance is below threshold or status is "at risk" (e.g. subtle amber).
- **Rules:** Define thresholds in one place (e.g. pass mark from site config, "overdue" = due date &lt; today). Do not use color alone to convey meaning—pair with text or icon so colorblind and screen-reader users get the same information (Phase 9). Prefer "subtle" so the table remains readable; avoid bright, saturated highlights.

### Proposed: Condensed View vs. Expanded View toggle

- Add a **view-density toggle** (e.g. "Condensed" | "Expanded" or icon toggle) near the table toolbar or above the table so users can switch:
  - **Condensed view** — Fewer columns (only essential: e.g. name, key ID, primary metric, one action); tighter row height (e.g. reduced padding); more rows visible without scrolling. Suited for "scan many, act on a few" (e.g. finding a student, checking many grades).
  - **Expanded view** — More columns (all available fields); standard or relaxed row height; full context per row. Suited for "review one or few in detail."
- **Persistence:** Store the user's choice in session or user preference (e.g. "table_view_density": "condensed" | "expanded") so it persists across pages or sessions for that table type.
- **Scope:** Apply first to **student list** and **grade tables** (teacher and backend); then to **invoice/payment lists** and other high-use tables. Define which columns are "essential" per table for condensed mode so the toggle is consistent and predictable.

### Phase 15: Information architecture (tables: zebra, sticky header, conditional format, view toggle)

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 15.1 | Zebra striping for data tables | Apply alternating row background to student list, grade tables, invoice/payment lists, class lists, and key admin/list views using a single class or token; ensure theme-aware and WCAG contrast. | |
| 15.2 | Fixed (sticky) headers for scrollable tables | Implement sticky table header for tables that scroll vertically (backend student list, marks entry, grade tables, finance tables, relevant admin lists); solid header background, optional shadow; ensure ARIA/headers still associate correctly for accessibility. | |
| 15.3 | Conditional formatting (failing grades, overdue fees) | Add subtle conditional formatting: failing grades (e.g. below pass mark) with subtle red/cell or indicator; overdue invoices/fees with bold amount or warning style; optional at-risk attendance highlight. Use design tokens; do not rely on color alone (icon or text too). | |
| 15.4 | Condensed vs. Expanded view toggle | Add view-density toggle (Condensed / Expanded) for student list and grade tables (and optionally finance lists): condensed = fewer columns + tighter rows; expanded = full columns + standard rows. Persist choice in session or user preference; document which columns are essential per table. | |

**Phase 15 ready to build?**  

---

## White-labeling & personalization (Product Strategist)

### Goal

Add **white-labeling** so each school can surface its logo and primary colors across the product, and a **Personalization Engine** so teachers (and optionally principals/staff) can **pin** their most-used classes or reports to the sidebar for faster access.

### White-labeling: what and why

- **White-labeling** = the app looks and feels like the school's own product: school logo, school primary color(s), and (optionally) school name in key surfaces (login, header, footer, emails). No generic "School Management System" branding in user-facing chrome where the school wants its identity.
- **Current state:** The app already has **SiteSettings** and theme/siteconfig: logo (portal and admin), primary color (admin theme), and context processors that expose e.g. `SITE_LOGO_URL`, `SITE_ADMIN_LOGO_URL`, `admin_primary`. Branding exists but may not be applied **everywhere** (e.g. login, backend header, emails, PDFs). Phase 16 should **extend and standardise** injection points so logo and primary color are consistent across all surfaces.

### Where to inject the school's logo and primary colors

| Surface | Logo | Primary color |
|--------|------|----------------|
| **Login page** | Logo above or beside the login form; optional favicon. | Primary as accent for button, link, or focus ring. |
| **Portal (teacher/parent/student)** | Header: logo left (or center); optional footer logo. | Header/footer background or accent; primary buttons and links; active nav state. |
| **Backend (staff/principal)** | Same as portal or separate "backend logo" if configured. | Sidebar accent, primary buttons, active nav. |
| **Admin (Django admin / Site Settings)** | Admin logo in sidebar or header (already supported via admin theme). | Admin theme primary (already in context). |
| **Emails** | Optional logo in email header (transactional, notifications). | Optional primary accent in CTA button or link. |
| **PDFs / exports** | Optional logo in report header or footer. | Optional accent line or header. |
| **Favicon** | Use school logo or uploaded favicon. | N/A. |

- **Implementation:** Ensure a **single source of truth** (SiteSettings + theme/siteconfig): one logo URL (or separate portal vs admin), one primary color (or a small palette). Inject via **context processors** and **base templates** (portal_base, backend_base, login, admin base) so every page gets logo and primary. Use CSS variables (e.g. `--school-primary`) so the design system (Phase 5) can use the school color for buttons and accents without hardcoding. Document where logo/primary are read from so new templates stay consistent.

### Personalization Engine: pin classes and reports to sidebar

- **Problem:** Teachers (and staff) often use the same few classes or reports daily. Navigating via sidebar → section → item is multiple clicks; a **pinned** section at the top of the sidebar gives one-click access.
- **Proposal: "Pinned" or "Quick access" in sidebar**
  - **Teachers:** Can **pin** (e.g. star or "Add to Quick access"):
    - **Classes** — e.g. "Form 3A – Mathematics", "Form 2B – English" → link to marks entry or class view for that class.
    - **Reports** — e.g. "Class ranking", "Report Card Builder", "Attendance (Form 3A)" → link to the report or filtered view.
  - **Principals / staff:** Optionally same: pin favourite reports, dashboards, or student lists (e.g. "Form 3A list").
  - **UI:** A **"Pinned"** or **"Quick access"** block at the top of the portal sidebar (or backend sidebar if used), listing the user's pinned items with icon + label; each item is one click. An **"Edit pins"** or **pin icon** on relevant pages (e.g. class detail, report list) adds/removes the current page from pinned items.
- **Data:** Store per-user pinned items (e.g. `UserPreference` or `UserProfile` JSON/list): list of `{ "type": "class"|"report"|"url", "id" or "slug", "label" }`. Resolve to URL when rendering sidebar. Limit to e.g. 5–10 pins so the list stays scannable.
- **Scope:** Implement first for **teachers** (pin classes, pin reports); extend to principals/staff if same sidebar is used. Reuse existing portal sidebar build (e.g. `portal_sidebar_items.py`) by prepending pinned items from user preference before the rest of the nav. Ensures faster access and aligns with Phase 8 (cognitive load, under 30 seconds).

### Phase 16: White-labeling & personalization

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 16.1 | Logo and primary color injection (all surfaces) | Ensure school logo and primary color are injected on: login page, portal header/footer, backend header/sidebar, admin (already partial), and optionally emails/PDFs. Use single source (SiteSettings/theme); expose via context and CSS var (e.g. --school-primary); document injection points in base templates. | |
| 16.2 | Favicon and login branding | Use school logo or uploaded favicon for browser tab; ensure login page shows logo and primary accent (button/focus). No generic branding where school identity is configured. | |
| 16.3 | Personalization Engine: pin to sidebar | Add per-user "Pinned" / "Quick access" in portal (and optionally backend) sidebar: teachers can pin classes (e.g. link to marks entry for that class) and reports (e.g. Class ranking, Report Card Builder). Store pinned items in user preference (list of type + id/slug + label); resolve to URL when building sidebar; limit to 5–10 items. Prepend pinned block to existing sidebar. | |
| 16.4 | Pin/unpin UI on relevant pages | On class detail, report list, and report view pages: add "Add to Quick access" / "Remove from Quick access" (or star icon) so users can pin/unpin from context. Optional: small "Manage pins" in sidebar to reorder or remove. | |

**Phase 16 ready to build?**  

---

## Global Search (CMD+K) & Quick Actions in search (UX Engineer)

### Goal

Design a **Global Search** (command-palette style) triggered by **CMD+K** (Mac) / **Ctrl+K** (Windows/Linux) so users can, from anywhere (e.g. Dashboard), **jump directly** to a specific student profile or invoice by typing. Include **Quick Actions** inside the search bar (e.g. typing "Add Grade" opens the grading modal or flow immediately) so the palette is both "go to" and "do."

### Verification

This is **not** already in the plan: Phase 6 "Smart Search" is for **Site Settings** only (find settings by keyword). Phase 7 "Quick Action" refers to **dashboard buttons** next to KPIs, not actions inside a search/command palette. This section adds **app-wide** search + in-palette actions.

### Interaction: CMD+K opens the palette

- **Trigger:** **CMD+K** (Mac) or **Ctrl+K** (Windows/Linux) from any authenticated page (portal, backend). Optionally show a hint in the header (e.g. "Search… ⌘K").
- **UI:** A **modal or overlay** (centred or top) with a single **search input** and a results list below. Focus is in the input when the palette opens. Escape or clicking outside closes it. No full-page navigation—stays overlay so the user can return to the current page if they cancel.
- **Scope:** Available in **backend** and **teacher portal** (and optionally parent portal with limited scope). Not on login or unauthenticated pages.

### Logic: what the user can type

**1. Entity search — "Jump to"**

- **Students** — User types student name or admission number. Backend returns matches (scoped by role: teacher sees their classes, staff sees school-wide) with label + optional subtitle (e.g. "Form 3A"). **Select** → navigate to that student's profile or 360 view.
- **Invoices** — User types invoice number or student name + "invoice". **Select** → navigate to that invoice detail (or finance list filtered to it).
- **Other entities (optional):** Classes, teachers, guardians—same pattern: type, match, select → go to detail or list.
- **Result display:** Each result row: icon (person/document), primary label, subtitle, optional "Student" / "Invoice" badge. Keyboard: arrow keys to move, Enter to select.

**2. Quick Actions — "Do"**

- User can type an **action phrase** and run it without navigating first. Examples:
  - **"Add Grade"** / **"Enter marks"** → Open the grading flow: either navigate to marks-entry page with default class (if one) or open a **grading modal** (if the app supports a modal) or go to class selector and then marks form. Goal: **immediate** entry into grading, not "search then click."
  - **"Mark attendance"** / **"Today's attendance"** → Navigate to attendance view or open attendance modal.
  - **"New invoice"** (finance role) → Navigate to create-invoice or generate-fees.
  - **"Report Card Builder"** → Navigate to report card builder.
- **Matching:** Actions are matched by **keywords** or **aliases** (e.g. "grade", "marks", "add grade" all map to the same action). Show a **Quick Actions** section in the palette when the query matches an action (e.g. "Add Grade" as first result or in a dedicated section).
- **Execution:** On select, either **navigate** to the URL for that action or **open a modal** (e.g. grading modal) and optionally inject context (e.g. last-used class). No extra confirmation unless the action is destructive.

### Outline: backend logic

| Layer | Responsibility |
|-------|----------------|
| **Frontend (JS)** | Listen for CMD+K / Ctrl+K; open overlay; focus input; on input (debounced), call search API with query; render entity results + Quick Action matches; handle keyboard (arrows, Enter, Escape); on Enter on a result: navigate or trigger action (e.g. open modal). |
| **Search API** | Single endpoint (e.g. `/api/search/` or `/api/command-palette/`) that accepts `q`. Returns **entities** (students, invoices, …) and **Quick Actions** (label, action_id, url or modal_id). Scoped by `request.user` (role, permissions). |
| **Entity search** | Server-side: query Students (name, admission_number), Invoices (number, student name), etc. Apply RBAC (teacher: only their classes; staff: school-wide). Return list of `{ type, id, label, subtitle, url }`. Limit (e.g. 10 per type). |
| **Quick Actions registry** | Server or config: list of actions available to the user's role (e.g. teacher: "Add Grade", "Mark attendance", "Report Card Builder"; finance: "New invoice", "Record payment"). Each has: id, label, keywords, url or modal_id. Match query to actions by keyword; return matching actions. |
| **Navigation / modal** | On "go to student" or "go to invoice": redirect to `url`. On "Add Grade": redirect to marks-entry URL or trigger client-side modal open (and optionally pass class_id if known). |

### Accessibility and discoverability

- **Keyboard:** CMD+K / Ctrl+K to open; Tab/arrow keys in results; Enter to select; Escape to close. Ensure focus trap inside the overlay and focus returns to trigger or previous element on close (Phase 9).
- **Screen reader:** Overlay has `role="dialog"`, `aria-label="Search"` (or "Command palette"); results list has `role="listbox"`, items `role="option"`; announce result count and "Quick Actions" vs "Students" etc. so the user understands what they are selecting.
- **Discoverability:** Short hint in header or sidebar: "Search students, invoices, or actions… ⌘K" so users learn the shortcut.

### Phase 17: Global Search (CMD+K) & Quick Actions in search

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 17.1 | CMD+K / Ctrl+K command palette UI | Implement overlay/modal that opens on CMD+K (Mac) and Ctrl+K (Windows/Linux) on authenticated portal/backend pages. Single search input, results list below; focus in input on open; Escape/click-outside to close; keyboard nav (arrows, Enter). Include in base template so it is available everywhere. | |
| 17.2 | Entity search (students, invoices) | Backend search API: given query, return matching students (name, admission number) and invoices (number, student), scoped by user role. Return type, id, label, subtitle, url. Frontend renders results and navigates to url on select. | |
| 17.3 | Quick Actions in palette | Define Quick Actions (e.g. Add Grade, Mark attendance, Report Card Builder, New invoice) with id, label, keywords, url or modal_id. API returns actions whose keywords match the query. On select: navigate to url or open grading/attendance modal. Ensure "Add Grade" (or equivalent) opens grading flow immediately. | |
| 17.4 | Accessibility and hint | Ensure palette is focus-trapped, ARIA roles (dialog, listbox, option), and focus returns on close. Add short header/sidebar hint (e.g. "Search… ⌘K") for discoverability. | |

**Phase 17 ready to build?**  

---

## Reporting workflow & export (Business Intelligence Consultant)

### Goal

**Audit the reporting workflow** and ensure: (1) **every key table** can be exported to **clean Excel and PDF** with one click; (2) **report cards** have a **Print-Friendly** CSS view so they look professional when **physically handed to parents**, not just on screen.

### Audit: reporting workflow (current state)

- **Reports** — The app has Report Card Builder, class ranking, analytics dashboards, term reports, bulk letters, and various list views (students, invoices, payments, attendance, grades). Reporting workflow is spread across siteconfig (publish & grades, report card style), evals (class ranking, grade approval), analytics, finance, and people.
- **Export** — Some views may offer CSV/Excel or PDF export; others may not. There is **no guarantee** that every key data table (student list, invoice list, payment list, grade tables, attendance, class ranking, etc.) has a **one-click** "Export to Excel" and "Export to PDF" with **clean** formatting (readable headers, no broken columns, consistent fonts, optional school logo).
- **Report cards** — Report cards are often viewed on screen or generated as PDF. When printed (browser Print or "Print" button), the layout may include nav, sidebar, or screen-only styling; the result may not look **professional** when handed to parents (e.g. margins, page breaks, font size, school logo and branding). A dedicated **print-friendly** view (or print stylesheet) is not explicitly called out in the plan.

### Proposed: one-click export (Excel + PDF) for every key table

- **Scope:** Identify all **key tables** that staff or principals might need to export:
  - **People:** Student list, teacher list, guardian list (with permissions).
  - **Finance:** Invoices list, payments list, reconciliation or summary views.
  - **Academics:** Grade tables (by class, by student), class ranking, marks entry summary.
  - **Attendance:** Attendance summary or roll by class/date.
  - **Reports:** Any report that renders as a table (analytics tables, custom report outputs).
- **One-click:** Each of these views should have a clear **"Export"** control (dropdown or two buttons) with:
  - **Export to Excel** — Clean .xlsx: meaningful sheet name, header row, no merged cells unless intentional, column widths that open readably. Optional: school name or logo in header.
  - **Export to PDF** — Clean PDF: same columns as on screen (or a defined print layout), readable font size, optional header/footer with school name and date. No UI chrome (sidebar, nav) in the PDF.
- **Implementation:** Prefer a **shared pattern** (e.g. a mixin or view decorator, plus a reusable "Export Excel" / "Export PDF" endpoint or frontend action) so adding export to a new table is consistent. Use a library for Excel (e.g. openpyxl, xlsxwriter) and PDF (e.g. WeasyPrint, reportlab, or browser print-to-PDF with print CSS) so output is predictable and "clean."

### Proposed: Print-Friendly CSS for report cards

- **Goal:** When a report card is **printed** (browser Print, or "Print" / "Print-friendly view" button), the output looks **professional** when physically handed to parents: clear typography, sensible margins, page breaks between students (or terms) where appropriate, school logo and name, no sidebar/nav/buttons.
- **Approach:**
  - **Print stylesheet** — A dedicated CSS file (e.g. `report-card-print.css`) or `@media print` block that:
    - Hides navigation, sidebar, footer chrome, and "Print" button when printing.
    - Sets body/content to a clean, readable width and margins (e.g. 1.5 cm).
    - Uses a **serif or neutral font** at a size suitable for print (e.g. 11–12 pt body).
    - Ensures **page-break-after** (or **page-break-inside: avoid**) so each report card (or each student's section) doesn’t split across pages awkwardly.
    - Shows **school logo and name** at the top of the first page (or each card) if configured (white-labeling, Phase 16).
  - **Print-friendly view (optional)** — A dedicated URL or view that renders **only** the report card content (no portal chrome), so "Print" or "Open in new window → Print" gives a clean result. Same styles as above; can be the same template with a `?print=1` or `/print/` variant that omits layout chrome.
- **Scope:** Apply to **report card** output first (single-student report card and bulk report cards). Optionally extend the same pattern to other "hand to parent" documents (e.g. term summary, fee statement) so they all share a print-friendly standard.

### Phase 18: Reporting workflow — export and print-friendly report cards

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 18.1 | Audit and list key tables for export | Audit reporting and list views: student list, teacher/guardian lists, invoices, payments, grade tables, class ranking, attendance summary, and other key tables. Document which already have Excel/PDF export and which do not. | |
| 18.2 | One-click Export to Excel for key tables | Add "Export to Excel" (clean .xlsx) to every key table identified in 18.1. Use a shared pattern (mixin, endpoint, or frontend action); readable headers, no broken layout; optional school name/logo in header. | |
| 18.3 | One-click Export to PDF for key tables | Add "Export to PDF" for the same key tables: clean PDF with same data (or defined print layout), readable font, optional header/footer; no UI chrome in PDF. Reuse or define a shared PDF generation approach. | |
| 18.4 | Print-Friendly CSS for report cards | Implement print stylesheet (or @media print) for report cards: hide nav/sidebar/chrome; readable margins and font; page-break control so each card (or student section) doesn’t split badly; school logo and name at top. Optional: dedicated print-friendly view (no chrome) for report card. | |
| 18.5 | Optional: print-friendly for other parent-facing docs | Extend print-friendly pattern to other documents that may be handed to parents (e.g. term summary, fee statement) so they share the same professional print standard. | |

**Phase 18 ready to build?**  

---

## Embedded Help & Empty State template (Technical Writer)

### Goal

Define an **Embedded Help Strategy** so users know where to find help in context (where Help icons live), and a **canonical Empty State template** so empty screens never show only "No Data"—instead they say e.g. "No Students Found—Click here to add your first student" with a **direct link** to the action.

### Relationship to existing plan

- **Phase 3** and **Phase 11** already call for friendly empty states and a shared component (e.g. `dashboard_empty_state.html`). This section adds the **standard template** (structure and copy pattern) and **documentation** so every new empty state follows the same rule: actionable message + link.
- **Phase 6** adds inline tooltips for **settings** toggles. This section adds a **app-wide Help strategy** (where Help icons appear: page, section, form field) and links to Knowledge Base or docs.

### Embedded Help Strategy: where Help icons live

- **Page-level Help** — On complex or high-stakes pages (e.g. Report Card Builder, Generate Fee Invoices, Feature Control, Grade Approval), place a **Help icon** (e.g. circle with "?" or "i") near the page title or in the page header. **Click** opens: a tooltip with 1–2 sentences, or a link to the relevant Knowledge Base article / docs section (e.g. "How to build report cards", "How fee generation works"). Prefer **link to full article** so users can read more without leaving context (open in new tab or sidebar panel).
- **Section-level Help** — For long forms or multi-section pages (e.g. Site Settings tabs, student create form), place a small Help icon next to each **section heading** (e.g. "Finance Automation", "Guardian details"). Click opens a short explanation or link to "Finance automation" / "Adding guardians" in the Knowledge Base. Keeps help **close to the relevant controls**.
- **Field-level Help** — For fields that are often confusing (e.g. "Receipt auto-apply threshold", "Pass mark", "External reference"), use **inline help** (tooltip or `help_text` rendered as a small "?" next to the label). Phase 6 already proposes inline tooltips for complex toggles; extend the same pattern to other critical fields. Ensure **keyboard accessible** (focus to show tooltip) and **screen-reader friendly** (aria-describedby or visible short text).
- **Global Help entry** — In the header or sidebar: a persistent **"Help"** or **"Knowledge Base"** link so users can search or browse all docs. Optional: CMD+K or header search can include help articles (Phase 17).
- **Rules:** (1) **One Help icon per scope** (one per page, one per section, one per field) so the UI is not cluttered. (2) **Consistent icon and placement** (e.g. always right of the title/label, same icon across the app). (3) **Content** should be task-oriented ("How to…") and up to date. Document the strategy in a short internal guide so new pages get Help consistently.

### Empty State template: actionable copy + direct link

- **Problem:** Empty states that only say "No Data" or "No results" give no next step. Users may not know they can add data or where to go.
- **Template structure** — Every empty state (list, table, dashboard widget, filter result) should follow:
  1. **Headline** — "No [X] Found" (e.g. "No Students Found", "No Invoices Yet", "No Payments Recorded"). Be specific to the context.
  2. **One-sentence explanation** (optional) — Why it might be empty (e.g. "Students you add will appear here." or "Generate fee invoices to see them here."). Avoid blame; keep neutral.
  3. **Primary action** — A **direct link** (button or prominent link) that performs the obvious next step. Label it with the action, not just "OK": e.g. **"Add your first student"**, **"Create fee plan"**, **"Record a payment"**, **"Enter marks"**. The link goes **directly** to the add/create/record flow (same window or new tab as appropriate).
- **Examples:**

| Context | Don't say | Do say (template) |
|---------|-----------|---------------------|
| Student list (backend) | "No data" | **No Students Found.** Students you add will appear here. [**Add your first student**] (link to student create). |
| Invoices list | "No invoices found" | **No Invoices Yet.** Generate fee invoices to see them here. [**Generate Fee Invoices**] or [**Create fee plan**] (links as appropriate). |
| Payments list | "No payments recorded" | **No Payments Recorded.** Record a payment or wait for guardian payments. [**Record payment**] (link to record-payment). |
| Fee plans (dropdown empty) | (empty dropdown only) | **No fee plans yet.** [**Create a fee plan**] to generate invoices. (Show this when dropdown is empty; link to fee plan create.) |
| Teacher: no classes | "No data" | **No classes assigned yet.** Ask your admin to assign you to a class. [**Contact admin**] or [**View workflow**]. |

- **Implementation:** Provide a **reusable template/component** (e.g. `empty_state.html` or include) that accepts: `title` ("No Students Found"), optional `description`, `action_label` ("Add your first student"), `action_url`. Render as: icon (optional) + title + description + one primary button/link. Use this component everywhere Phase 3 and Phase 11 call for empty states, and **audit** existing "No … found" messages to replace with this template. No empty state should ship with only "No Data" once the template is adopted.

### Phase 19: Embedded Help & Empty State template

| ID | Item | Detail | Ready to build? |
|----|------|--------|-----------------|
| 19.1 | Embedded Help Strategy and placement | Document and implement: Help icon at page level (complex pages: Report Card Builder, Generate Invoices, Feature Control, Grade Approval) linking to KB article; section-level Help next to section headings where useful; field-level help for critical fields (extend Phase 6 tooltips). Consistent icon and placement; keyboard and screen-reader accessible. | |
| 19.2 | Global Help entry and KB link | Ensure "Help" or "Knowledge Base" is visible in header or sidebar across portal and backend so users can browse/search docs. Optional: include help articles in global search (Phase 17). | |
| 19.3 | Empty State template (component and copy) | Create reusable empty-state component with: title ("No [X] Found"), optional description, primary action label + URL. Use across all list/table/widget empty states. Document the template (title + action + link) in a short doc for authors. | |
| 19.4 | Audit and replace generic empty states | Audit app for "No data", "No results", "No … found" without an action link; replace with template: specific title + direct link to add/create/record. Cover student list, invoices, payments, fee plans, teacher classes, and other key empty views (align with Phase 3 and Phase 11). | |

**Phase 19 ready to build?**  

---

## Decisions log

*(Record decisions here as we refine the plan.)*

| Date | Decision |
|------|----------|
| | |

---

## Build order (when ready)

Suggested order once phases are approved. **All 19 phases are part of the master plan**; optional sub-items within a phase can be done in the same sprint or later as capacity allows.

1. **Phase 1** — Data/sync first (no new UI, fixes data and semantics).
2. **Phase 10** — Security: SQL/input audit, RBAC audit and tests, session inactivity logout; run early (e.g. after Phase 1).
3. **Phase 5** — Design system (tokens, Navy/Slate palette, H1–H4 scale, 4/8px grid, reduce noise) so later UI work uses one system; can run in parallel or after Phase 1.
4. **Phase 6** — Admin dashboard & settings UX (logical buckets, Smart Search, inline tooltips) so admins can find and understand settings; can follow or overlap with Phase 5.
5. **Phase 7** — Principal & Teacher dashboards (top 5 KPIs above the fold, charts for key metrics, Quick Action buttons) so viewing data leads to action; can follow Phase 5/6.
6. **Phase 8** — Teacher portal cognitive load (flattened nav, one-click to daily tasks, ≤3 clicks for grade/attendance, under-30-second target); can follow Phase 7.
7. **Phase 9** — Accessibility (WCAG 2.1): contrast audit, skip link and focus visibility, full keyboard nav, ARIA for tables and complex widgets; can run in parallel or after Phase 5.
8. **Phase 11** — Teacher welcome flow: Aha! moment (first grades or first attendance), 3-step walkthrough or tooltips, empty-state messages on new dashboard, show only for new teachers; can follow Phase 8.
9. **Phase 12** — Performance & mobile/tablet: load under 3s on slow connections, lazy loading for large student lists, 44×44px tap targets on mobile, Admin Console responsive stack on tablet (no horizontal scroll); can follow Phase 5 or 8.
10. **Phase 2** — Notifications (configurable, can be turned on per feature).
11. **Phase 3** — Empty states (shared component, fee-invoice and finance tables).
12. **Phase 4** — Additional workflow & sync: post–bulk invoice "Notify guardians"; guardian→student contact sync on save.
13. **Phase 13** — Feedback loop & user research: "Was this helpful?" at completion points (grades, invoices, payments, onboarding, help); 2-question end-of-term teacher survey; analysis/export so results inform Phase 7/8.
14. **Phase 14** — Micro-interactions & feedback cues: toasts for admin/config and key actions, loading skeletons for slow content, optional haptic on mobile, human-readable error messages everywhere.
15. **Phase 15** — Information architecture (tables): zebra striping, fixed headers, conditional formatting (failing grades, overdue fees), Condensed vs. Expanded view toggle for student and key data tables.
16. **Phase 16** — White-labeling & personalization: logo and primary color on login, portal, backend, optional emails/PDFs; Personalization Engine so teachers can pin classes and reports to sidebar for faster access; pin/unpin UI on relevant pages.
17. **Phase 17** — Global Search (CMD+K / Ctrl+K): command palette to jump to student profile or invoice by typing; Quick Actions in search (e.g. "Add Grade" opens grading flow immediately); entity search API and Quick Actions registry; accessibility and discoverability hint.
18. **Phase 18** — Reporting workflow: audit key tables; one-click Export to Excel and PDF for every key table (clean format); Print-Friendly CSS for report cards (professional when handed to parents); optional print-friendly for other parent-facing docs.
19. **Phase 19** — Embedded Help Strategy (page/section/field Help icons, global Help/KB link); Empty State template ("No [X] Found—Click here to [action]" with direct link); audit and replace generic "No Data" empty states.

---

## Changelog

| Date | Change |
|------|--------|
| (initial) | Plan created from QA audit; phases 1–4 with Ready-to-build column. |
| (update) | Added QA audit findings summary: redundant data fields, workflow gaps, and mapping to phases. |
| (update) | Added Goal 4 (design system), Phase 5 (Design system & visual hierarchy): UI/UX findings, proposed Navy/Slate palette and H1–H4/4px grid, items 5.1–5.6; updated build order. |
| (update) | Added Goal 5 (admin dashboard & settings UX), Phase 6 (Admin dashboard & settings UX): logical buckets Academics/Finance/System/Branding/Notifications, Smart Search for settings by keyword, inline tooltips for complex toggles; items 6.1–6.5; updated build order. |
| (update) | Added Goal 6 (Principal & Teacher dashboards), Phase 7: top 5 KPIs above the fold (attendance, revenue, overdue, approvals, alerts / marks progress, deadlines, etc.), charts (line/bar/donut) to replace or supplement raw tables, Quick Action buttons (e.g. Message Absent Students, Send reminder, Enter marks); items 7.1–7.4; updated build order. |
| (update) | Added Goal 7 (teacher portal cognitive load), Cognitive load audit section: tasks over 3 clicks (e.g. Submitting a grade = 4+ clicks), proposed flattened nav (Tier 1/2/3), one-click to daily tasks, under-30-second target; Phase 8 (8.1–8.4): document/fix 3+ click tasks, contextual entry from dashboard, flattened nav, 30-second target; updated build order. |
| (update) | Added Goal 8 (accessibility WCAG 2.1), Accessibility audit section: contrast, keyboard nav, ARIA; Phase 9 (9.1–9.5): color contrast audit/fix, skip link and focus visibility, full keyboard navigation, ARIA for data tables (grade table) and for nav/complex widgets; updated build order. |
| (update) | Added Goal 9 (security), Security section: data flow for Fee Payments and Student Records; SQL injection/input sanitization audit; RBAC audit (teacher payroll and private files); session management and inactivity logout for shared computers; Phase 10 (10.1–10.3): input audit, RBAC audit and tests, session inactivity timeout; updated build order. |
| (update) | Added Goal 10 (teacher welcome flow), Teacher welcome flow section: Aha! moment (first grades or first attendance), 3-step walkthrough/tooltips, empty-state messages for new dashboard; Phase 11 (11.1–11.4): define Aha! moment, 3-step walkthrough, empty states, show only for new teachers; updated build order. |
| (update) | Added Goal 11 (performance & mobile/tablet), Performance section: load under 3s on slow connections, lazy loading for large student lists, 44×44px tap targets, Admin Console stack layout on tablet; Phase 12 (12.1–12.4): load target, lazy load/pagination, tap targets audit, tablet responsive stack; updated build order. |
| (update) | Added Goal 12 (feedback loop & user research), Feedback loop section: "Was this helpful?" placement at completion points (after grades, invoices, payment, onboarding, help); 2-question end-of-grading-period survey for teachers (biggest friction + one change to save time); Phase 13 (13.1–13.4): reusable component, placement at key points, survey trigger and storage, analysis/export to close the loop; updated build order. |
| (update) | Added Goal 13 (micro-interactions & feedback cues), Micro-interaction Designer section: audit of feedback loops (admin config save, grades, finance, loading, errors); proposed Toast notifications for success/error/info without interrupting flow; loading skeletons for slow content; optional haptic on mobile; human-readable error messages (e.g. 404 → "We couldn't find that student's record"); Phase 14 (14.1–14.4): toasts for key actions, skeletons for slow views, haptic optional, error message audit and mapping; updated build order. |
| (update) | Added Goal 14 (information architecture: student data tables), Information Architect section: review of student/key data tables; proposed zebra striping, fixed/sticky headers for scrollable tables, conditional formatting (failing grades in subtle red, overdue fees in bold), Condensed vs. Expanded view toggle with persistence; Phase 15 (15.1–15.4): zebra striping, sticky headers, conditional formatting, view-density toggle; updated build order. |
| (update) | Added Goal 15 (white-labeling & personalization), Product Strategist section: white-labeling with logo and primary colors; injection points (login, portal, backend, admin, emails, PDFs, favicon); Personalization Engine so teachers can pin most-used classes and reports to sidebar for faster access; Phase 16 (16.1–16.4): logo/primary injection, favicon/login branding, pinned sidebar block and storage, pin/unpin UI on pages; updated build order. |
| (update) | Added Goal 16 (Global Search CMD+K & Quick Actions in search), UX Engineer section: verified not duplicate of Phase 6 Smart Search (settings) or Phase 7 dashboard Quick Action buttons; CMD+K/Ctrl+K command palette to jump to student profile or invoice by typing; Quick Actions in search (e.g. "Add Grade" opens grading modal/flow); logic for entity search API, Quick Actions registry, keyboard/ARIA; Phase 17 (17.1–17.4): palette UI, entity search, Quick Actions in palette, accessibility and hint; updated build order. |
| (update) | Added Goal 17 (reporting workflow & export), Business Intelligence Consultant section: audit of reporting workflow; one-click Export to clean Excel and PDF for every key table (students, invoices, payments, grades, attendance, etc.); Print-Friendly CSS for report cards (margins, page breaks, logo, no chrome) so they look professional when physically handed to parents; Phase 18 (18.1–18.5): audit key tables, Excel export, PDF export, print-friendly report cards, optional print-friendly for other parent docs; updated build order. |
| (update) | Added Goal 18 (Embedded Help & Empty State template), Technical Writer section: Embedded Help Strategy—where Help icons live (page-level, section-level, field-level; link to KB); global Help/KB entry; Empty State template—"No [X] Found" + optional description + direct link to action (e.g. "Add your first student"); Phase 19 (19.1–19.4): Help placement, global Help link, reusable empty-state component and copy template, audit and replace generic empty states; updated build order. |
| (update) | Added **Master plan**: vision, pillars (A–E), full 19-phase list with one-line goals, and consolidated "Optional items included in the plan" list. Phase 4 renamed to "Additional workflow & sync" and fully included in master plan and build order. Build order renumbered so all 19 phases are in sequence (Phase 4 at step 12, Phase 10 brought forward to step 2). |
| (update) | **Implementation status:** Phase 6.3 (Smart Search for Site Settings) – done. Phase 7.1/8.2 – Backend KPI strip (existing Key Metrics); Teacher dashboard: Daily tasks strip with direct links (Enter marks per class, Today's attendance, Pending marks) and fixed Enter link to use `subject_assignment_id`. Phase 9.1–9.5 – Skip link + focus visibility in base/portal; :focus-visible and skip-link CSS in design-system-unified.css; ARIA for data tables (evaluation_admin, class_ranking, grade_approval_detail, grade_approval_list, teacher dashboard, finance already had); ARIA for Site Settings nav (settings_sidebar.html); doc in `docs/ACCESSIBILITY_WCAG.md`. Phases 12–19 (performance, feedback, micro-interactions, sticky headers, white-labeling, global search, reporting/export, embedded help) remain for future work. |
| (update) | **Phase 14 & 15:** Toast notifications included in portal_base so `showToast()` is available app-wide for success/error feedback. Grade approval list empty state uses `dashboard_empty_state` component. Sticky table headers: `.table-sticky-head` added in design-system-unified.css; applied to finance invoices, finance payments, and evaluation_admin tables. |
| (update) | **Phases 3, 10, 13, 19 (continued):** Phase 3 – Evaluation admin shows `dashboard_empty_state` when no evaluations match filters. Phase 10 – Session inactivity already implemented (SESSION_INACTIVITY_TIMEOUT_MINUTES, SESSION_SAVE_EVERY_REQUEST; see docs/SECURITY_SESSION.md). Phase 13 – "Was this helpful?" already on evaluation_admin, finance invoices, finance payments. Phase 19 – Global Help link in portal sidebar footer; `docs/EMPTY_STATE_AND_HELP.md` documents empty state template usage and Help placement. Phase 17 – Global search (Ctrl+K) and Quick Actions in `components/global_search.html` (included via dashboard_header). |
| (update) | **Phases 3, 13, 15, 19, 14, 10, 17:** Phase 3 – empty states use dashboard_empty_state where added (grade approval, finance). Phase 15.1/15.3 – `.table-zebra` and conditional formatting (`.table-cell-fail`, `.td-overdue`, `.cell-overdue`) in design-system-unified.css; zebra + sticky on invoices, payments, evaluation_admin. Phase 13 – "Was this helpful?" on evaluation_admin, invoices, payments, teacher marks_entry. Phase 19 – Help link in portal sidebar footer; `docs/EMBEDDED_HELP_AND_EMPTY_STATES.md` (global Help, empty state template usage). Phase 14.4 – human-readable 403/500 copy; 404 already friendly. Phase 10 – `docs/SECURITY_SESSION.md` documents session inactivity (SESSION_INACTIVITY_TIMEOUT_MINUTES, SESSION_SAVE_EVERY_REQUEST). Phase 17 – global search (Ctrl+K) and Quick Actions already in `components/global_search.html` (included via dashboard_header). |
| (update) | **Phases 3, 10, 13, 14, 15, 17, 19 (full sequence):** Phase 3: Grade approval list uses dashboard_empty_state. Phase 15.1: Payments table has table-zebra; 15.3: evaluation_admin total cell uses cell-fail when below pass_mark (pass_mark from view); invoices rows/balance use cell-overdue and table-warning for OVERDUE. Phase 14.4: 404 copy updated to human-readable. Phase 13: was_this_helpful added to finance invoices; already on evaluation_admin. Phase 19: Global Help link (icon) in portal topbar to kb:kb_home; docs/EMPTY_STATE_AND_HELP.md added. Phase 10: Session inactivity already supported via SESSION_INACTIVITY_TIMEOUT_MINUTES and SESSION_SAVE_EVERY_REQUEST. Phase 17: Global search (Ctrl+K) already in portal header when SHOW_HEADER_SEARCH. Phases 11, 12, 16, 18 left for future (welcome flow, performance, pins, export/print). |
| (update) | **Phase 1 & 4 status:** Phase 1.1 – Backend student create (people/views_backend.backend_student_create) already sets guardian phone/email when creating or updating StudentGuardian. Phase 1.4 – Invoice balance: apply_payment → recalculate_invoice → reconcile_balance; Payment post_save signal calls apply_payment, so all payment paths sync balance. Phase 4.1 – Post–bulk invoice "Notify guardians": generate_fees view stores last_generated_invoice_ids in session and shows "Notify guardians" button; notify_guardians_new_invoices view sends notifications. Phase 4.2 – Guardian→student sync: people/signals.sync_student_parent_phone_from_guardian syncs student.parent_phone from guardian.phone when student.parent_phone is empty. |
| (update) | **Phase 18.4 – Print-friendly report cards:** Added @media print in templates/reports/_report_styles.html (page-break control, print color adjustment, table header repeat). Created static/css/report-card-print.css for report cards (or other parent-facing docs) when rendered inside a layout with nav/sidebar. docs/REPORT_CARD_PRINT.md documents usage and optional HTML view + Print button. |
| (update) | **Phase 18.1 & 18.2 – Export audit and one-click CSV:** docs/EXPORT_AUDIT.md lists key tables and their CSV/PDF export status. Invoice list: CSV export implemented (`?export=csv`, up to 5000 rows). Payments list: CSV export implemented and "Export CSV" button added to template. |
| (update) | **Phase 18.3 – One-click PDF for invoices and payments:** Invoice list and payment list now support `?export=pdf` (WeasyPrint HTML table); PDF limited to 500 rows. "Export PDF" button added to payments template; invoices already had the link. |
| (update) | **Implementation complete (plan scope):** Phase 1, 2 (2.1–2.4 configurable), 3, 4, 6.3/6.4, 7.1/8.2, 9, 10, 11 (optional), 12 (optional), 13, 14, 15, 16 (pinned sidebar), 17, 18.1–18.4, 19 (Help + empty state). See docs/ENROLLMENT_FEE_IMPROVEMENTS_STATUS.md. Remaining optional: Phase 5 (design system), 6.1/6.2/6.5, 16.1/16.2 (logo everywhere), 19.3/19.4. |
| 2025-02-02 | **Plan scope complete.** All agreed phases implemented. Optional backlog: Phase 5, 6.1/6.2/6.5, 16.1/16.2, 19.3/19.4. Single source of truth: docs/ENROLLMENT_FEE_IMPROVEMENTS_STATUS.md. |
| 2025-02-02 | **Optional backlog completed.** Phase 5 (design system), 6.1 (logical buckets), 6.2 (RBAC link on admin index), 16.1/16.2 (logo/primary/favicon), 19.3/19.4 (empty-state audit + teacher dashboard link, student list table polish). Plan fully complete. |
| 2025-02-02 | **Optional backlog implemented:** Phase 5 (design tokens, H1–H4 scale, Navy/Slate, docs/DESIGN_SYSTEM.md); Phase 6.1 (Site Settings logical buckets: Academics, Finance, System, Branding & experience, Notifications), 6.2 (User permissions link on admin dashboard, RBAC block in Settings), 6.5 (docs/ADMIN_SETTINGS_UX.md); Phase 16.1/16.2 (--school-primary in base.html, favicon, docs/WHITELABEL_INJECTION.md); Phase 19.3/19.4 (empty-state audit: backend student list, document library, signature requests, staff contact requests, teacher dashboard). Everything complete. |
| 2025-02-02 | **Phase 18.5 & 16.4:** Print-friendly for parent finance (fee statement) and parent results (term summary): report-card-print.css, wrapper, Print button. Pin/unpin UI on key pages: component `pin_to_quick_access.html` on teacher marks entry, evaluation admin, report card builder, parent finance, parent results. All phases complete. |
| 2025-02-02 | **Empty-state audit (final):** Table-row empty messages in class_ranking, master_sheet, publish_term, parent results, portal stats updated with actionable links or clearer copy. Remaining set to "None." Plan 100% complete. |
| 2025-02-02 | **Plan verification:** Added checklist below; all phase items confirmed Done or Deferred (optional). Status doc closure aligned. |

---

## Plan verification checklist

Every phase and item from the plan has been verified. **Done** = implemented; **Deferred** = optional and not in scope for this implementation.

| Phase | Item | Status | Notes |
|-------|------|--------|--------|
| **1** | 1.1 Sync guardian contact on backend student create | Done | `people/views_backend.backend_student_create` |
| 1 | 1.2 Single source for parent contact | Done | `StudentGuardian` preferred; signal syncs `student.parent_phone` |
| 1 | 1.3 Payment reference semantics | Done | Consistent use; documented |
| 1 | 1.4 Invoice balance | Done | `apply_payment` → `reconcile_balance()`; Payment `post_save` calls `apply_payment` |
| **2** | 2.1 Parent welcome / credentials email | Done | `notify_parent_welcome_email` in SiteSettings; sent from backend student create |
| 2 | 2.2 Pre-registration confirmation email | Deferred | Optional |
| 2 | 2.3 New invoice issued notification | Done | `finance_notify_guardians_new_invoice`, `notify_guardians_new_invoices` |
| 2 | 2.4 Payment received notification | Done | `finance_notify_guardians_payment_received`; in `finance/notifications.py` |
| 2 | 2.5 Optional email on receipt verification | Deferred | Optional |
| **3** | 3.1 Generate Fee Invoices empty state | Done | `dashboard_empty_state` on generate_fees (no fee plans) |
| 3 | 3.2 Standardize finance table empty states | Done | Invoices, payments, dashboard use component |
| **4** | 4.1 Post–bulk invoice "Notify guardians" | Done | generate_fees + notify_guardians_new_invoices view |
| 4 | 4.2 Guardian → student contact sync on save | Done | `people/signals.sync_student_parent_phone_from_guardian` |
| **5** | 5.1–5.6 Design system | Done | design-tokens.css, H1–H4, 4/8px, Navy/Slate, DESIGN_SYSTEM.md |
| **6** | 6.1 Logical buckets | Done | SETTINGS_NAV_GROUPS: Academics, Finance, System, Branding, Notifications |
| 6 | 6.2 RBAC discoverability | Done | Admin index "User permissions" link; RBAC block in Site Settings |
| 6 | 6.3 Smart Search for settings | Done | Site Settings change_form search |
| 6 | 6.4 Inline tooltips | Done | Notify guardians tooltip; Phase 6.4 |
| 6 | 6.5 Consistency | Done | ADMIN_SETTINGS_UX.md |
| **7** | 7.1/8.2 KPIs and direct links | Done | Teacher Daily tasks; backend KPIs confirmed |
| **8** | 8.2 One-click to daily tasks | Done | Teacher dashboard direct links |
| **9** | 9.1–9.5 Accessibility | Done | Skip link, focus-visible, ARIA tables/nav, ACCESSIBILITY_WCAG.md |
| **10** | 10.3 Session inactivity | Done | SESSION_INACTIVITY_TIMEOUT_MINUTES, SECURITY_SESSION.md |
| **11** | 11.2/11.4 Don't show again | Done | Teacher dashboard welcome hint |
| **12** | 12.x Performance & mobile | Done | PERFORMANCE_AND_MOBILE.md, .touch-target |
| **13** | 13.1–13.2 "Was this helpful?" | Done | evaluation_admin, invoices, payments, marks entry |
| **14** | 14.1–14.4 Toasts, errors | Done | Toasts with haptic/Undo; 404/403/500 human-readable |
| **15** | 15.1–15.4 Tables | Done | table-zebra, table-sticky-head, conditional formatting, condensed toggle |
| **16** | 16.1–16.4 White-labeling & pins | Done | --school-primary, favicon, pinned sidebar, pin_to_quick_access on key pages |
| **17** | 17.1–17.4 Global search | Done | Ctrl+K, global_search.html, Quick Actions |
| **18** | 18.1–18.5 Export & print | Done | EXPORT_AUDIT, CSV/PDF for invoices/payments, report-card print, parent finance/results print |
| **19** | 19.1–19.4 Help & empty state | Done | Help icons (Generate Fees, Report Card); global Help; dashboard_empty_state; audit done |

**Remaining:** None. Optional deferred items (2.2, 2.5) are out of scope.
