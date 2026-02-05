# Master Plan – Build Order

**Purpose**: One plan to build from. **Site Settings redesign is very important** and is Phase 1. Everything else is ordered by dependency and impact.

**Related docs**:  
- [SITE_SETTINGS_REDESIGN_PLAN.md](SITE_SETTINGS_REDESIGN_PLAN.md) – Site Settings UX and navigation  
- [AUTOMATION_ALL_MODULES_WORKFLOW.md](AUTOMATION_ALL_MODULES_WORKFLOW.md) – **Automation for ALL modules**: what to automate / what not, admin role, single workflow, redundancy removal  
- [ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md](ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md) – Modules, dependencies, automation, gaps  
- [AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md](AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md) – Guardrails, Eval–Reportcard, MFA  

---

## Overview

| Phase | Focus | Outcome |
|-------|--------|--------|
| **1** | **Site Settings redesign** (very important) | Fewer tabs → one Finance tab with subsections; then vertical sidebar; scalable nav. |
| **2** | Evals–Reports & critical gaps | Publish guard, approved-grades-only option, single grading-deadline source. |
| **3** | **Automation** (all modules, workflow, admin role, no redundancy) | One workflow; can/cannot automate per module; admin config/approve/override; redundancy removed. |
| **4** | Guardrails & compliance | Finance overrides audited; MFA-for-role; optional request reminders. |
| **5** | Scale & polish | New settings in Site Settings sidebar; API/permissions; EMIS/evals consistency. |

---

## Phase 1 – Site Settings redesign (very important)

**Goal**: Settings page that fits many more options and stays easy to use. No long horizontal tab row.

### 1.1 Quick win (ship first)

- [x] **Fix breadcrumb**  
  Ensure breadcrumb shows “Site Settings” (not “Site Settingss”). Check Unfold change_form breadcrumb and any custom title for `siteconfig.sitesettings`.
- [x] **Merge Finance Automation into one tab**  
  In `apps/siteconfig/admin.py` `SiteSettingsAdmin.fieldsets`:
  - Replace the 7+ separate “Finance Automation - …” fieldsets with **one** fieldset: `("Finance Automation", { "classes": ("tab",), "fields": (...) })`.
  - Put all finance automation fields in one tuple, in logical order (Fee invoice → Fee plan → Reminders → Invoice status → Receipt verification → Bank verification → Payment instructions → Real-world).
  - Add **in-tab structure**: for each subsection use a **readonly field** that renders only a subheading (e.g. “Fee invoice generation”, “Payment reminders”) so the one tab has clear blocks. Reuse the pattern from `theme_color_tools_block` (readonly field that renders a fragment) or use fieldset `description` for each block if you split into multiple fieldsets inside the same tab (Django/Unfold may allow nested or sequential fieldsets in one tab).
- [x] **Verify**  
  Open Site Settings: you should see fewer tabs; “Finance Automation” is one tab with all finance settings and visible subheadings.

**Reference**: [SITE_SETTINGS_REDESIGN_PLAN.md – Option B](SITE_SETTINGS_REDESIGN_PLAN.md#22-option-b--fewer-top-level-tabs--in-tab-subsections-quicker-win).

### 1.2 Full redesign – vertical sidebar (main deliverable)

- [x] **Custom change_form for Site Settings only**  
  - New template (e.g. `templates/admin/siteconfig/sitesettings/change_form.html`) that **does not** output Unfold’s default tab list for this page (override the block that renders `{% tab_list "changeform" opts %}` for this model only, or use a custom `change_form_template` that wraps content in a sidebar layout).
- [x] **Sidebar structure**
  - Left sidebar with **groups** and **sub-items**:
    - **General**: At a glance, Company details, Login & header, Theme & experience, Footer.
    - **Portal & content**: Portal & content, Feature toggles.
    - **Backend**: Backend orchestration & limits, Notifications & analytics, Compliance & payroll.
    - **Finance automation**: Fee invoice, Fee plan, Reminders, Invoice status, Receipt verification, Bank verification, Payment instructions, Real-world scenarios.
    - **Automation** (optional in Phase 1.2; expand in Phase 3): Execution logs & approval; schedules and thresholds for all automations (finance, evals deadlines, reminders, etc.).
    - **Analytics**: Analytics defaults.
    - **Metadata**: Updated at, etc.
  - Each sub-item maps to one fieldset (or one block of fields). Clicking a sub-item shows only that section in the main area.
- [x] **Behavior**  
  - Single form; all fields in DOM; only the active section is visible (toggle visibility by `data-section` or class). Save submits the whole form.
  - Optional: persist active section in `sessionStorage` so the last-opened section is restored.
- [x] **Mobile**  
  - Sidebar becomes a drawer or a “Sections” dropdown on small screens so the “different site setting links” don’t overflow.
- [x] **Breadcrumb**  
  - Still “Site Settings” (fixed in 1.1).

**Reference**: [SITE_SETTINGS_REDESIGN_PLAN.md – Option A](SITE_SETTINGS_REDESIGN_PLAN.md#21-option-a--vertical-sidebar-recommended-for-fit-as-many-as-possible).

### 1.3 UX polish (same phase or right after)

- [x] **Sticky save bar**  
  Keep; optional “Unsaved changes” indicator when form is dirty (you already have dirty tracking in the template).
- [x] **Replace raw JSON where possible**  
  Identify settings that are currently big JSON text areas (e.g. portal config, backend flags). Add structured widgets (e.g. key/value, checkboxes, multi-select) and keep raw JSON only for “Advanced” or export. Do at least one high-impact one (e.g. `portal_features` or `backend_feature_flags`) as a pattern.

**Deliverable**: Site Settings with vertical sidebar, scalable for Evals, Reports, Payroll, etc., and no crowded horizontal tab row.

---

## Phase 2 – Evals–Reports & critical gaps

**Goal**: Report cards tied to approved grades when the school uses approval; single source for grading deadlines; no broken references.

### 2.1 Reports – publish and approved grades

- [ ] **SiteSettings flags** (in Site Settings – can live under a new “Reports” or “Evals & reports” section in the sidebar once Phase 1.2 is done):
  - `reports_require_approved_grades_before_publish` (bool): when True, block or strongly warn on “Publish term” if there are pending `GradeApprovalRequest` for that term.
  - `reports_use_approved_grades_only` (bool): when True, report context (term/annual) only includes evaluations that are tied to an approved GradeApprovalRequest (or no approval required).
- [x] **Publish-term view**  
  In `apps/reports/views.py` (publish_term_results): when `reports_require_approved_grades_before_publish` is True, check pending grade approvals for the selected term/classrooms; if any, show a clear message and either block publish or require explicit “Publish anyway”.
- [x] **Report context**  
  In `apps/reports/services.py` (`term_report_context`, `annual_report_context`): when `reports_use_approved_grades_only` is True, filter `Evaluation` so only “approved” (or non-approval) grades are included. Document logic next to the query.
- [x] **Publish page UX**  
  On the publish-term page, show a short “Eval status” line (e.g. “All grades approved” / “N subjects pending approval”) so the person publishing is informed even when not blocking.

**Reference**: [AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md – EVAL and Reportcard](AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md#3-eval-and-reportcard-tie-in-and-gaps).

### 2.2 Evals – single source for grading deadline

- [x] **Canonical deadline**  
  Use one source for “grading deadline” everywhere (e.g. `SubjectAssignment.grading_deadline_at` or a small evals deadline model). Remove or redirect any remaining references to the old `GradingDeadline` model.
- [x] **Analytics / portal**  
  Ensure deadline reminders and any “grading deadlines” UI use this single source (see CODE_REVIEW_GAPS_REDUNDANCIES.md).

### 2.3 Reports – audit

- [x] **Publish action audit**  
  Ensure “Publish term” is logged (e.g. ReportCardAudit or compliance AuditLog) with user and timestamp.

**Deliverable**: Publish guarded by approval when configured; report cards optionally show only approved grades; one grading-deadline source; publish audited.

---

## Phase 3 – Automation (app + config + guardrails)

**Goal**: **Automation** is a first-class part of the plan. All scheduled and high-impact tasks use `apps.automation` (ExecutionLog, ApprovalQueue); schedules and thresholds live in Site Settings; admin can see runs and override.

### 3.1 Centralize automation in the plan

- [x] **Use automation app for all automations**  
  Ensure every Celery/scheduled task that creates or changes data (invoice generation, payment reminders, receipt processing, deadline reminders, retry failed reminders, bank verification, etc.) logs to **AutomationExecutionLog** (task name, status, records_processed, error_message, triggered_by). High-impact ones (e.g. bulk invoice generation) use **AutomationApprovalQueue** when Site Settings say “require approval”.
- [x] **Config in Site Settings, not code**  
  All automation thresholds, schedules, and “require approval” flags live in Site Settings (or env that Site Settings reads). No hardcoded limits for production behavior. Finance automation already does this; extend pattern to evals (deadline reminder schedule/channels), analytics (deadline mode), and any new automations.
- [x] **Site Settings – Automation section**  
  In the Site Settings sidebar (Phase 1.2), add an **Automation** group with sub-items, e.g.:
  - **Execution & approval**: Link or embed “Recent runs” (from AutomationExecutionLog), “Pending approvals” (from AutomationApprovalQueue), and toggles like “Require approval for invoice generation”.
  - **Schedules & thresholds**: One place to see/edit schedules for payment reminders, deadline reminders, fee generation, receipt verification retries, etc. (Either link to existing finance/evals fields or add a dedicated “Automation schedules” subsection.)
- [x] **Admin visibility**  
  Staff with permission can open **Automation** in admin: AutomationExecutionLog (list filters: task_name, status, date), AutomationApprovalQueue (pending/approved/rejected). Optional: “Run now” or “Retry” for safe tasks, with dry-run where applicable.

**Reference**: [ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md – automation](ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md#216-appsautomation--automation--background-tasks), [AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md](AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md).

### 3.2 Evals & analytics automation

- [x] **Deadline reminders**  
  Ensure evals/analytics deadline reminder task uses the single grading-deadline source (Phase 2) and logs to AutomationExecutionLog. Channels and schedule configurable via Site Settings (e.g. `deadline_reminder_channels`, reminder window).
- [x] **Payroll / report batch (future)**  
  When adding “payroll reminder” or “scheduled report batch”, implement with ExecutionLog and optional ApprovalQueue from the start; add settings to Site Settings and to the Automation section in the sidebar.

**Deliverable**: Automation is explicit in the plan; all automations log and optionally queue for approval; config in Site Settings; Automation section in Site Settings sidebar; admin can see and override.

---

## Phase 4 – Guardrails & compliance

**Goal**: Automation cannot do things admin can’t override; critical overrides are audited; zero-cost MFA for compliance.

### 4.1 Finance overrides

- [x] **Void invoice / reject receipt**  
  Ensure every such action in admin requires a reason (or dropdown) and is written to AuditLog (or equivalent). No silent overwrites.
- [x] **Review**  
  Confirm all “override” actions (reassign receipt, bypass approval, etc.) have mandatory reason + audit.

**Reference**: [ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md – finance](ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md#25-appsfinance--financial-management).

### 4.2 MFA for compliance (zero cost)

- [x] **SiteSettings**  
  Add `require_mfa_roles` (e.g. JSON list of role codes: `["ADMIN","BURSAR","IT_ADMIN"]`) in Site Settings (e.g. under “Compliance & security” or new “Security” section).
- [x] **Enforcement**  
  In login flow or middleware: if user’s role is in `require_mfa_roles` and they have no TOTP device, redirect to MFA setup (django_otp) before allowing access. Rely on **TOTP only** (no SMS cost).
- [x] **Docs**  
  Short note in compliance docs: MFA available; recommended/required for admin/finance; TOTP = zero marginal cost.

**Reference**: [AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md – Zero-cost MFA](AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md#5-zero-cost-mfa-for-compliance).

### 4.3 Requests

- [x] **Requests**  
  Optional: Celery task “remind assignee of pending AccessRequest” (configurable interval); document how to add new request types that sync to AccessRequest.

**Deliverable**: Finance overrides audited; MFA can be required for chosen roles (TOTP); request reminders in place.

---

## Phase 5 – Scale & polish

**Goal**: New settings and modules fit into the new Site Settings; API and EMIS aligned with the rest.

### 5.1 Site Settings – new groups

- [x] **Evals & grading**  
  When adding evals/report-related settings (e.g. grading deadline source, approval defaults), add a sidebar group “Evals & reports” with sub-items in the Site Settings template and in `fieldsets`.
- [x] **Reports**  
  Put `reports_require_approved_grades_before_publish`, `reports_use_approved_grades_only`, and any report-style options under “Evals & reports” or “Reports”.
- [x] **Payroll / Compliance**  
  New settings for payroll or compliance get their own sidebar group or sub-item under “Backend” or “Compliance”.

No new horizontal tabs; everything goes into the sidebar.

### 4.2 API & permissions

- [x] **API**  
  Audit API_COMPLETE_GUIDE.md (or equivalent) vs implemented endpoints; fill critical gaps. Ensure permission classes match portal (e.g. guardian sees only own students). (Audit: `docs/API_AUDIT_VS_GUIDE.md`.)
- [x] **Dashboard context**  
  Ensure every dashboard view uses `get_dashboard_context()` (already done for main dashboards; verify any new ones).

### 5.3 EMIS & evals

- [x] **EMIS**  
  Document which fields come from evals (e.g. performance); ensure export uses same logic as report cards where relevant. Optional: approval step before “submit to government”.

**Deliverable**: New settings live in sidebar; API and EMIS consistent and documented.

---

## Build order summary

1. **Phase 1.1** – Breadcrumb fix + one Finance Automation tab with in-tab subsections (quick win).
2. **Phase 1.2** – Site Settings vertical sidebar (custom change_form, groups, sub-items). **Very important.**
3. **Phase 1.3** – Unsaved indicator; replace at least one JSON setting with structured widget.
4. **Phase 2** – Evals–reports: publish guard, approved-grades-only, grading deadline single source, publish audit.
5. **Phase 3** – **Automation (all modules)**: Single workflow; what to automate / what not for all 17 modules; admin role (config, approve, override, visibility); redundancy removal; ExecutionLog/ApprovalQueue; Automation section in Site Settings.
6. **Phase 4** – Finance override audit, MFA-for-role (TOTP), request reminders.
7. **Phase 5** – New settings in sidebar (including Automation), API/EMIS/docs.

---

## Checklist – “Ready to build”

- [ ] Phase 1.1 done → Site Settings has fewer tabs and correct breadcrumb.
- [ ] Phase 1.2 done → Site Settings has vertical sidebar; scalable for future settings.
- [ ] Phase 1.3 done (at least one JSON→widget) → Pattern for friendlier settings.
- [ ] Phase 2 done → Report publish safe; report cards optionally approved-only; deadlines fixed.
- [ ] Phase 3 done → **Automation (all modules)**: one workflow; can/cannot automate per module; admin config/approve/override/visibility; redundancy removed; Automation section in sidebar.
- [ ] Phase 4 done → Overrides audited; MFA-for-role available.
- [ ] Phase 5 done → New modules fit in; API/EMIS aligned.

**Master plan doc**: `docs/MASTER_PLAN.md` (this file).  
**Site Settings detail**: `docs/SITE_SETTINGS_REDESIGN_PLAN.md`.  
**Automation (all modules, workflow, admin, redundancy)**: `docs/AUTOMATION_ALL_MODULES_WORKFLOW.md`.
