# Build Document: Module Audit Improvements — Implementation Guide

This document turns the [Module Audit & Improvement Plan](MODULE_AUDIT_AND_IMPROVEMENT_PLAN.md) into actionable build items. Use it as a sprint checklist: implement in P0 → P1 → P2 → P3 order; optional items can be scheduled as capacity allows. It includes all optional items from the module audit; the Portal section ensures parent/teacher portals are wired, RBAC-compliant, and auditable.

**Conventions:**
- **Priority:** P0 = critical, P1 = high value, P2 = quality/maintainability, P3 = nice-to-have.
- **Optional:** Marked where the item is desirable but not required for correctness or security.
- **Status:** Check off `[ ]` → `[x]` as you complete each item.

---

## P0 — Critical (Correctness & Consistency)

### BUILD-P0-1: Requests task → AutomationExecutionLog

| Field | Detail |
|-------|--------|
| **Priority** | P0 |
| **Optional** | No |
| **Module** | `apps.requests` |

**Description:** The Celery task `remind_pending_assignees_task` does not create an `AutomationExecutionLog` entry. Add logging so the automation hub and admin show "Requests reminder" runs alongside finance and analytics tasks.

**Acceptance criteria:**
- [ ] When `remind_pending_assignees_task` runs, it creates one `AutomationExecutionLog` record.
- [ ] Log status is SUCCESS when notifications are sent (or when disabled by interval 0); FAILED when an exception occurs.
- [ ] `task_name` identifies the task (e.g. `"requests.remind_pending_assignees"`).
- [ ] `records_processed` or `execution_summary` reflects count of assignees notified (or "disabled").
- [ ] Automation hub and admin Execution Log list show these runs.

**Implementation steps:**
1. In `apps/requests/tasks.py`, import `AutomationExecutionLog` from `apps.automation.models`.
2. At start of task (after checking `interval_hours <= 0` and returning early), create a log with `status=PENDING`, `task_name="requests.remind_pending_assignees"`, `execution_type=SCHEDULED`.
3. In the success path (including "disabled" and "notified N"), call `execution_log.mark_completed(..., records_processed=notified, execution_summary={"notified": N, "assignees": M, "pending_total": P})`.
4. In an `except` block, call `execution_log.mark_completed(..., status=FAILED, error_message=str(e))`.
5. When interval is 0 and you return early, optionally create a short log with status SUCCESS and summary `{"message": "Reminder disabled (interval 0)"}` so the run is visible.

**Files to touch:**
- `apps/requests/tasks.py`

**Tests:**
- [ ] Add or extend test: run task with interval > 0 and assert `AutomationExecutionLog` exists with SUCCESS and expected summary.
- [ ] Run task with interval 0 and assert log exists (if you log disabled runs).

---

### BUILD-P0-2: Finance — consolidate payment_processors_temp / payment_validators_temp

| Field | Detail |
|-------|--------|
| **Priority** | P0 |
| **Optional** | No |
| **Module** | `apps.finance` |

**Description:** Remove the "_temp" naming and have a single canonical module for payment processors and validators. Currently `payment_processors.py` imports from `payment_processors_temp`; consolidate so production code does not depend on "_temp" modules.

**Acceptance criteria:**
- [ ] No file named `payment_processors_temp.py` or `payment_validators_temp.py` in active use, OR they are clearly deprecated and all imports point to non-_temp modules.
- [ ] All references to `payment_processors_temp` / `payment_validators_temp` are updated (e.g. move contents into `payment_processors.py` / `payment_validators.py` and remove the _temp files, or rename _temp to the canonical name and remove the old file).
- [ ] Existing finance tests and payment flows still pass.

**Implementation steps:**
1. Identify every import of `payment_processors_temp` or `PaymentProcessorFactory` (and same for validators).
2. If the "_temp" file is the real implementation: rename `payment_processors_temp.py` → `payment_processors.py` (back up or merge the current `payment_processors.py` first), then update any imports. Same for validators.
3. If the non-temp file is canonical: move any missing symbols from _temp into the main file and delete _temp; update imports.
4. Run finance tests and a quick manual check (e.g. invoice creation, payment reminder).
5. Update docs (e.g. PHASE_8_ROADMAP.md, PHASE_2_0_ARCHITECTURE_SUMMARY.md) to remove references to _temp files.

**Files to touch:**
- `apps/finance/payment_processors.py`
- `apps/finance/payment_processors_temp.py` (remove or rename)
- `apps/finance/payment_validators.py`
- `apps/finance/payment_validators_temp.py` (remove or rename)
- Any other files that import from _temp (grep for `payment_processors_temp`, `payment_validators_temp`).
- Docs that mention these files.

**Tests:**
- [ ] Run `apps.finance.tests` and any payment-related smoke tests.

---

### BUILD-P0-3: Evals–reports documentation

| Field | Detail |
|-------|--------|
| **Priority** | P0 |
| **Optional** | No |
| **Module** | `apps.reports` / `apps.evals` / `apps.siteconfig` |

**Description:** Add a short, findable document (and optionally admin/siteconfig help text) explaining how report cards use grades and how staff can fix missing or unapproved grades.

**Acceptance criteria:**
- [ ] A document exists (e.g. in `docs/` or as admin help) that explains: (1) Report cards pull grades from Evaluations (evals). (2) SiteSettings "Reports use approved grades only" and "Require approved grades before publish" control what appears and when publish is allowed. (3) Where to fix missing grades (Evaluation Admin) and where to approve grades (Grade Approval).
- [ ] Document is linked or discoverable from the Publish Results page and/or Evaluation Admin (e.g. "How report cards use grades" link or help block).

**Implementation steps:**
1. Create `docs/REPORT_CARDS_AND_GRADES.md` (or add a section to an existing doc) with:
   - How report cards get data (term_report_context, annual_report_context from evals).
   - Meaning of "Reports use approved grades only" and "Require approved grades before publish."
   - Steps: enter grades → (optional) grade approval → publish term → parents can download reports.
   - Links to Evaluation Admin and Publish Results (URL names or paths).
2. Optionally add a help block or "Learn more" link on `reports/publish_term.html` and/or evals evaluation_admin template that points to this doc.
3. Optionally add a short help line in SiteSettings (admin) for `reports_use_approved_grades_only` and `reports_require_approved_grades_before_publish` fields (e.g. "See docs/REPORT_CARDS_AND_GRADES.md").

**Files to touch:**
- `docs/REPORT_CARDS_AND_GRADES.md` (new or existing)
- `templates/reports/publish_term.html` (optional link)
- `templates/evals/evaluation_admin.html` (optional link)
- `apps/siteconfig/admin.py` (optional help_text for report-related fields)

**Tests:**
- [ ] Doc builds and link is valid; no automated test required.

---

## P1 — High Value (UX & Observability)

### BUILD-P1-1: Report "ready" status in evaluation admin / publish page

| Field | Detail |
|-------|--------|
| **Priority** | P1 |
| **Optional** | No |
| **Module** | `apps.evals`, `apps.reports` |

**Description:** Show a clear "Report card status" for the selected term (e.g. Ready / Pending approval / Missing grades) on the Evaluation Admin and/or Publish Term Results page so staff know when it's safe to publish or when to fix grades.

**Acceptance criteria:**
- [ ] On Evaluation Admin (and/or Publish Term page), for the current or selected year/term, users see a status such as: "Report card status: Ready" | "Pending approval (N subjects)" | "Missing grades (N subjects)" or similar.
- [ ] Status is derived from existing logic (e.g. `grade_approval_publish_readiness` in reports.services, or equivalent evals data).
- [ ] Wording is consistent with docs (BUILD-P0-3).

**Implementation steps:**
1. In `apps.reports.services` ensure `grade_approval_publish_readiness(academic_year_id, term_id)` (or a small wrapper) returns a structure suitable for display (e.g. ready_for_publish, pending_count, missing_count).
2. In the view that renders Evaluation Admin (`apps.evals.views`), get active year/term (or from request), call the reports readiness helper (avoid circular imports: keep helper in reports or a shared place), and pass a `report_readiness` or `report_card_status` variable to the template.
3. In the view that renders Publish Term Results (`apps.reports.views.publish_term_results`), you already have year/term; add the same readiness data to the context.
4. In `templates/evals/evaluation_admin.html` and/or `templates/reports/publish_term.html`, add a small block (e.g. alert or info box) that shows the report card status and, if not ready, a short hint (e.g. "Complete grade approval or add missing grades" with link to grade approval list or evaluation admin).

**Files to touch:**
- `apps/reports/services.py` (expose or reuse readiness helper)
- `apps/evals/views.py` (or views that serve evaluation_admin)
- `apps/reports/views.py` (publish_term_results context)
- `templates/evals/evaluation_admin.html`
- `templates/reports/publish_term.html`

**Tests:**
- [ ] Test that when all grades are approved (and no missing), status shows "Ready" (or equivalent); when pending/missing, correct counts or labels show.

---

### BUILD-P1-2: Portal — fix N+1 when building report context for multiple students

| Field | Detail |
|-------|--------|
| **Priority** | P1 |
| **Optional** | No |
| **Module** | `apps.portal` |

**Description:** Where the portal builds report context for multiple students (e.g. listing children or prefilling report data), avoid calling `term_report_context(student, year, term)` in a loop; prefetch evaluations and related data per term and build context without N+1 queries.

**Acceptance criteria:**
- [ ] No view or service in portal performs one query per student (e.g. per child) when building term report context for the same year/term.
- [ ] Either: (a) report context is built in bulk (e.g. one query for all evaluations for the term filtered by student_id__in=children), then mapped to each student, or (b) report list/dashboard only shows summary or links and loads full context on demand (single student).
- [ ] Existing parent report download and list behavior preserved; performance improves where N students were previously causing N+1.

**Implementation steps:**
1. Find all call sites of `term_report_context` or `annual_report_context` in `apps/portal` (views, services). Identify any loop over students that calls these.
2. If there is a "list of reports" or "report status per child" view: fetch all relevant evaluations for the term (and year) for the set of student IDs (e.g. children of the parent), with `select_related` for subject_assignment, subject, classroom, etc. Build a dict keyed by student_id with precomputed rows/summaries, or build minimal summary (e.g. "has report", "average") without full term_report_context in the loop.
3. If full context is needed per student only on "download" or "view", keep calling `term_report_context` once per request (single student) — that's acceptable.
4. Add a test or manual check with multiple children to ensure query count does not scale with number of children for the list view.

**Files to touch:**
- `apps/portal/views.py` and/or `apps/portal/services.py`
- Any template that triggers the loop (if backend change only, no template change may be needed)

**Tests:**
- [ ] Test parent dashboard or report list with 2+ children; assert query count is bounded (e.g. assertNumQueries or manual inspection).

---

### BUILD-P1-3: Payroll run → AutomationExecutionLog

| Field | Detail |
|-------|--------|
| **Priority** | P1 |
| **Optional** | No |
| **Module** | `apps.payroll` |

**Description:** When a payroll run is executed (management command or any future Celery task), create an `AutomationExecutionLog` record so payroll appears in the automation hub and is auditable.

**Acceptance criteria:**
- [ ] Executing a payroll run (e.g. `run_payroll_cycle` command or equivalent) creates one `AutomationExecutionLog` entry.
- [ ] Log includes task_name (e.g. `"payroll.run_cycle"`), status SUCCESS/FAILED, and summary (e.g. records_processed, run id).
- [ ] Automation hub and admin Execution Log list show payroll runs.

**Implementation steps:**
1. In the payroll code that performs the run (e.g. `apps/payroll/management/commands/run_payroll_cycle.py` or the service it calls), import `AutomationExecutionLog`.
2. Before starting the run, create a log with status=PENDING, task_name e.g. `"payroll.run_cycle"`, execution_type=MANUAL or SCHEDULED.
3. On success, call `mark_completed(SUCCESS, records_processed=..., execution_summary={...})`.
4. On failure, call `mark_completed(FAILED, error_message=...)`.
5. If payroll is later moved to a Celery task, keep the same logging pattern inside the task.

**Files to touch:**
- `apps/payroll/management/commands/run_payroll_cycle.py` and/or `apps/payroll/services.py`

**Tests:**
- [ ] Run payroll (or mock) and assert `AutomationExecutionLog` exists with expected task_name and status.

---

### BUILD-P1-4: Single MFA helper (middleware + login)

| Field | Detail |
|-------|--------|
| **Priority** | P1 |
| **Optional** | No |
| **Module** | `apps.accounts` |

**Description:** Extract a single source of truth for "user must have MFA" and "user has MFA verified this session" so middleware and login redirect don't duplicate logic and stay in sync.

**Acceptance criteria:**
- [ ] A small helper (e.g. in `apps/accounts/utils.py` or `views_mfa.py`) provides: `must_have_mfa(user, site)` (bool) and optionally `is_mfa_verified(request)` (bool).
- [ ] `RequireMFAMiddleware` and the login/post-login redirect in `accounts.views` (or equivalent) both use these helpers instead of inlining the same logic.
- [ ] Behavior unchanged: users in require_mfa_roles (or all staff when require_mfa_all_staff) are still forced to setup/verify MFA.

**Implementation steps:**
1. Add `must_have_mfa(user, site)` that returns True when site.require_mfa_all_staff and user.is_staff, or when user.role in (site.require_mfa_roles or []). Use getattr for backward compatibility.
2. Add `is_mfa_verified(request)` that checks request.session.get("mfa_verified") and optionally "mfa_verified_until" (time window).
3. In `apps/accounts/middleware.py`, replace the inlined MFA checks with calls to these helpers (pass request.user and site).
4. In the login/post-login flow (e.g. in `apps/accounts/views.py` where MFA redirect happens), use the same helpers.
5. Add unit tests for `must_have_mfa` (role in list, all staff, no requirement) and for `is_mfa_verified` (session set, expired, not set).

**Files to touch:**
- `apps/accounts/utils.py` or `apps/accounts/views_mfa.py`
- `apps/accounts/middleware.py`
- `apps/accounts/views.py` (login/MFA redirect block)

**Tests:**
- [ ] Unit tests for `must_have_mfa` and `is_mfa_verified`; existing MFA middleware and redirect tests still pass.

---

## P2 — Quality & Maintainability

### BUILD-P2-1: Centralize active year/term usage

| Field | Detail |
|-------|--------|
| **Priority** | P2 |
| **Optional** | No |
| **Module** | `apps.academics`, cross-app |

**Description:** Ensure all key flows use the same service for "current" academic year and term (e.g. `get_active_year_and_term()` from academics) so backend, reports, evals, and portal behave consistently.

**Acceptance criteria:**
- [ ] No critical path uses a different way to get "active" year (e.g. raw `AcademicYear.objects.filter(is_active=True).first()`) where `get_active_year_and_term()` (or a single wrapper) would be appropriate.
- [ ] Term ordering (e.g. by order or start_date) is consistent wherever terms are listed (reports, evals, publish).

**Implementation steps:**
1. Grep for `is_active=True` on AcademicYear and for `get_active_year_and_term` / `get_active_year` across apps (academics, portal, reports, evals, accounts).
2. Replace ad hoc "active year" / "active term" resolution with a call to `academics.services.get_active_year_and_term(request)` or equivalent where a request is available; otherwise a function that returns (year, term) from settings or cache.
3. In academics, ensure Term model has a stable ordering (Meta.ordering or default ordering in queries) and document it in REPORT_CARDS_AND_GRADES or a small dev doc.
4. Run tests and spot-check backend dashboard, publish term, and report download to ensure correct year/term.

**Files to touch:**
- `apps/academics/services.py` (ensure single canonical function)
- `apps/portal/views.py` or services
- `apps/reports/views.py`
- `apps/evals/views.py`
- `apps/accounts/views.py` (backend dashboard if it uses year/term)
- Any other call sites found by grep

**Tests:**
- [ ] Test get_active_year_and_term with no year, one year, multiple years (if applicable); test term order in report context.

---

### BUILD-P2-2: Single source for staff console URLs and dashboard widget metadata

| Field | Detail |
|-------|--------|
| **Priority** | P2 |
| **Optional** | No |
| **Module** | `apps.siteconfig`, `apps.accounts` |

**Description:** Reduce duplication between accounts and siteconfig for "staff console URLs" (backend, admin, RBAC, etc.) and dashboard widget metadata; use one source of truth (e.g. siteconfig or a shared helper).

**Acceptance criteria:**
- [ ] Staff console URLs (backend_dashboard, admin index, RBAC, workflow center, etc.) are built in one place (e.g. a function in siteconfig or accounts that returns a dict of named URLs).
- [ ] Dashboard widget metadata (get_dashboard_widget_metadata, widget types) is defined in one place and reused by portal and accounts dashboard.
- [ ] No duplicate definitions of the same URL or widget type in two apps.

**Implementation steps:**
1. Identify where staff URLs are built: e.g. `_admin_context()` in accounts, dashboard context in accounts, and any siteconfig usage.
2. Introduce a small module or extend an existing one (e.g. `apps.accounts.utils.get_staff_console_urls(user, request=None)`) that returns backend_url, admin_url, rbac_url, workflow_center_url, etc., and use it from _admin_context and from backend dashboard context.
3. Ensure dashboard widget metadata (e.g. get_dashboard_widget_metadata) lives in siteconfig (or one app) and is imported by portal and accounts where needed; remove duplicate widget type lists if any.
4. Run tests and check profile page, backend dashboard, and portal dashboard for correct links and widgets.

**Files to touch:**
- `apps/accounts/utils.py` or new `apps/accounts/url_helpers.py`
- `apps/accounts/views.py` (_admin_context, backend_dashboard context)
- `apps/siteconfig/models_dashboard.py` or equivalent
- `apps/portal/views.py` (if it builds its own widget list)

**Tests:**
- [ ] Test that profile and backend dashboard show correct URLs; test dashboard layout still loads widgets.

---

### BUILD-P2-3: Add tests (evals–reports, finance log, requests log, portal, accounts)

| Field | Detail |
|-------|--------|
| **Priority** | P2 |
| **Optional** | No |
| **Module** | Multiple (tests) |

**Description:** Add the tests listed in the audit so regressions are caught and the new behavior (ExecutionLog, report status, etc.) is covered.

**Acceptance criteria:**
- [ ] Evals–reports: test that `term_report_context` excludes unapproved evaluations when `reports_use_approved_grades_only` is True; test publish_term when `reports_require_approved_grades_before_publish` is True/False.
- [ ] Finance: at least one key task (e.g. send_payment_reminders) is tested to create an AutomationExecutionLog (or already covered).
- [ ] Requests: after BUILD-P0-1, test that remind_pending_assignees creates an AutomationExecutionLog.
- [ ] Portal: test parent report download is allowed only for own children and for published terms; optionally assert query count for report list with multiple children.
- [ ] Accounts: test backend recommended_next_steps (workflow_center vs admin); test MFA redirect when MFA required but user has no device.

**Implementation steps:**
1. Add or extend tests in `apps/reports/tests/` for term_report_context with approved-only and for publish_term with require_approved_grades.
2. Add or extend test in `apps/finance/tests/` for one task creating AutomationExecutionLog.
3. Add test in `apps/requests/tasks` or a test module for remind_pending_assignees → AutomationExecutionLog.
4. Add or extend test in `apps/portal/tests/` for parent report download permission and published term.
5. Add or extend tests in `apps/accounts/tests/` for recommended_next_steps and MFA redirect.

**Files to touch:**
- `apps/reports/tests/test_publish_term.py` or new test file
- `apps/reports/tests/test_cameroon_report_context.py` or new
- `apps/finance/tests/` (e.g. test_services.py or new)
- `apps/requests/tests/` (new if needed)
- `apps/portal/tests/`
- `apps/accounts/tests/`

**Tests:**
- [ ] All new tests pass; existing test suite still passes.

---

### BUILD-P2-4: Compliance / MFA zero-cost documentation

| Field | Detail |
|-------|--------|
| **Priority** | P2 |
| **Optional** | No |
| **Module** | docs / compliance |

**Description:** Document that MFA is TOTP + backup codes (zero cost), where it's configured (SiteSettings), and how to run compliance commands (cron/Celery) for audit and threat detection.

**Acceptance criteria:**
- [ ] A short doc (e.g. in docs/ or compliance app) states: MFA is implemented with django_otp (TOTP + otp_static); no extra cost; configuration is under SiteSettings (require_mfa_roles, require_mfa_all_staff).
- [ ] Same or another doc lists recommended cron or Celery Beat entries for compliance commands (e.g. archive_old_audits, detect_threats, generate_compliance_reports) and any relevant env vars (e.g. GeoIP).

**Implementation steps:**
1. Create `docs/COMPLIANCE_AND_MFA.md` (or add to existing compliance doc) with: MFA stack (django_otp, TOTP, backup codes), zero cost, SiteSettings fields, and link to admin MFA KPIs.
2. Add a "Running compliance commands" section: list management commands (apps.compliance.management.commands) and suggest schedule (e.g. daily for detect_threats, weekly for archive).
3. If GeoIP or external threat data is used, document free vs paid limits (e.g. MaxMind GeoLite2).

**Files to touch:**
- `docs/COMPLIANCE_AND_MFA.md` or `docs/COMPLIANCE.md`

**Tests:**
- [ ] N/A (documentation).

---

### BUILD-P2-5: API search — return backend URLs when request is from backend (optional)

| Field | Detail |
|-------|--------|
| **Priority** | P2 |
| **Optional** | Yes |
| **Module** | `apps.api` |

**Description:** When the search API returns "edit" or "view" links for students/teachers, optionally return backend URLs (e.g. backend student/teacher list or edit) when the request is from the backend (e.g. Referer or custom header) so links keep the user in the backend flow.

**Acceptance criteria:**
- [ ] Search API accepts an optional hint (e.g. Referer containing `/backend` or header `X-Backend-Context: true`) and, when set, returns backend URLs for students and teachers (e.g. backend_student_list, backend_teacher_list or deep link) instead of admin change URLs where applicable.
- [ ] When hint is not set, behavior unchanged (e.g. admin URLs or existing behavior).
- [ ] API docs or schema note the optional header/behavior.

**Implementation steps:**
1. In `apps/api/search_api.py` (or equivalent), where entity links are built (student, teacher, etc.), add a check: request Referer path contains `/backend` or request header `X-Backend-Context` is truthy.
2. If true, use reverse for backend URLs (e.g. accounts:backend_student_list, or backend_student_create) or deep link to backend edit if available; otherwise keep current admin links.
3. Document in API schema or docs that clients can send `X-Backend-Context: true` to get backend-oriented links.

**Files to touch:**
- `apps/api/search_api.py`
- API schema or doc file if present

**Tests:**
- [ ] Test search with and without backend hint; assert link format differs as expected.

---

## Portal (Parent and Teacher) — wiring, RBAC, compliance

### BUILD-PORTAL-1: Portal (parent and teacher) wiring and RBAC verification (required)

| Field | Detail |
|-------|--------|
| **Priority** | P1 (Portal) |
| **Optional** | No |
| **Module** | `apps.portal`, `apps.reports`, `templates` |

**Description:** Ensure every parent/teacher portal entry point is correctly wired, RBAC-protected, and data-scoped. Fix report download links in parent UI to use the `reports:` URL namespace so they resolve correctly.

**Acceptance criteria:**
- [ ] Every parent view has `@parent_portal_required` and/or `@role_required(PARENT)`; data (students, invoices, reports) is scoped to linked children via StudentGuardian.
- [ ] Every teacher view has `@teacher_portal_required` and/or `@role_required(TEACHER)`; data (pay, attendance, timetable, evals) is scoped to the current user's TeacherProfile / assignments.
- [ ] Sidebar shows parent/teacher items only when role matches and (for portal tools) `has_feature_permission` and site feature flags allow it.
- [ ] Report download links from parent UI use `reports:parent_download_term_report`, `reports:parent_download_annual_report`, etc., and resolve without 404.

**Implementation steps:**
1. Audit all views in `apps/portal/views.py`, `apps/portal/views_contact_requests.py`, and report download views in `apps/reports/views.py` that serve parents or teachers: confirm decorators and data filtering (guardian link, teacher profile).
2. In `templates/parent/results.html`, use the `reports:` namespace for all report download/share URLs (e.g. `reports:parent_download_term_report`, `reports:parent_download_term_report_csv`, `reports:parent_download_annual_report`, `reports:parent_download_annual_report_csv`, `reports:parent_share_report`).
3. Grep templates for any other `{% url 'parent_download_...' %}` or `parent_share_report` and fix to namespaced names.
4. Confirm `apps/siteconfig/portal_sidebar_items.py` does not expose backend/admin-only links to PARENT/TEACHER roles (spot-check).

**Files to touch:**
- `templates/parent/results.html`
- Any other templates using report download URLs

**Tests:**
- [ ] Existing `apps/portal/tests/test_rbac_teacher_pay.py`; add or extend test that parent can only access report download for a linked child and that unlinked child returns 403; test that report download URL from parent results page resolves (e.g. URL reverse test).

---

### BUILD-PORTAL-2: Portal compliance and audit coverage (optional)

| Field | Detail |
|-------|--------|
| **Priority** | P3 (Portal) |
| **Optional** | Yes |
| **Module** | `apps.portal`, `apps.compliance` |

**Description:** Ensure sensitive parent/teacher actions (report download, link child, view finance, teacher pay) are auditable via PortalAuditLog, AccessLog, or ReportCardAudit.

**Acceptance criteria:**
- [ ] Report downloads: already logged via ReportCardAudit; no change required.
- [ ] Link child / claim invite: optionally log to PortalAuditLog or compliance AccessLog so "parent linked to student X" is auditable.
- [ ] Parent finance view: optional log on first load or on sensitive action (e.g. "viewed finance for student X").
- [ ] Teacher pay history: optional log (or confirm existing payroll/compliance logging covers it).

**Implementation steps:**
1. Review `apps/portal/portal_services.py` `log_portal_action` usage; ensure it is called from link_child, claim_invite, and optionally parent_finance.
2. If compliance AccessLog is preferred for these actions, add a small helper and call it from the same views; avoid duplicate logging (choose one: PortalAuditLog or AccessLog per action type).
3. Document in the build doc or in `docs/COMPLIANCE_AND_MFA.md` which portal actions are audited and where.

**Files to touch:**
- `apps/portal/views.py` (link_child, claim_invite, parent_finance)
- `apps/portal/portal_services.py`
- Optional: `apps/compliance` if using AccessLog

**Tests:**
- [ ] Optional test that link_child or claim_invite creates an audit record.

---

### BUILD-PORTAL-3: Seamless flow and UX checks (optional)

| Field | Detail |
|-------|--------|
| **Priority** | P3 (Portal) |
| **Optional** | Yes |
| **Module** | `apps.portal`, docs |

**Description:** Confirm parent and teacher flows are consistent and professional (no dead links, correct back links, feature flags respected).

**Acceptance criteria:**
- [ ] Parent: dashboard → results (per child) → report download; finance; link child; claim invite. All links use correct namespaces and work when feature flags (enable_parent_portal, report_downloads_enabled, etc.) are on.
- [ ] Teacher: dashboard (evals) → workflow, attendance, pay, leave, timetable. No staff-only links in sidebar when role is TEACHER.
- [ ] "Back" and "Home" links from child pages return to parent dashboard or teacher dashboard as appropriate.

**Implementation steps:**
1. Manually or via a simple test walk: parent login → dashboard → results for a child → download term PDF; teacher login → dashboard → pay history. Verify no 404s and correct scoping.
2. With enable_parent_portal or enable_teacher_portal disabled, verify 403 or redirect and that sidebar does not show portal entry for that role.
3. Document in build doc a short "Portal flow checklist" (parent path, teacher path) for future releases.

**Files to touch:**
- Build doc only (checklist); fix any broken links found during walk.

**Tests:**
- [ ] Manual or automated flow test; no new unit test required.

---

## P3 — Nice to Have (Optional)

### BUILD-P3-1: Session list / revoke (accounts) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.accounts` |

**Description:** Add a small UI where a user can see active sessions (e.g. current session + others if stored) and revoke them for security and compliance.

**Acceptance criteria:**
- [ ] Authenticated user can open a "Sessions" or "Active sessions" page (e.g. under profile or security).
- [ ] Current session is indicated; other sessions (if any) show device/location or "other" and a "Revoke" action.
- [ ] Revoking a session invalidates that session (e.g. remove from session store or mark invalid); current session cannot be revoked without logging out.
- [ ] Session storage supports listing (e.g. use database or cache backend that stores session key and optional metadata); if using default cache/db sessions, extend to store user_id and optional label for "other" sessions.

**Implementation steps:**
1. Decide session backend: if using database sessions (django.contrib.sessions), you can list sessions for the current user (match by user_id stored in session data or by custom session model).
2. Add a view that lists sessions for request.user (excluding or marking the current session_key) and render a simple template with "Revoke" buttons.
3. Add a view that accepts session_key (and CSRF), verifies it belongs to the user, and deletes that session; then redirect back to sessions list.
4. Add a link to this page from profile or account settings.
5. Optional: store "last IP" or "user agent" in session for display.

**Files to touch:**
- `apps/accounts/views.py` (new views) or new file
- `apps/accounts/urls.py`
- New template(s)
- Profile or settings template (link)

**Tests:**
- [ ] Test listing sessions and revoking another session; test that revoked session can no longer be used.

---

### BUILD-P3-2: Notify parents when term is published — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.reports`, `apps.portal` / notifications |

**Description:** When a term is published (school or class level), create an in-app notification for parents whose children are affected so they know a new report is available.

**Acceptance criteria:**
- [ ] When publish_term_results view (or equivalent) sets TermPublishStatus to published for a scope (school or classroom), notifications are created for parents linked to students in that scope.
- [ ] Notification points to the report download or parent report list (portal URL).
- [ ] Uses existing Notification model (e.g. finance or a shared one); no new paid service.

**Implementation steps:**
1. In publish_term_results, after updating TermPublishStatus, determine the set of students in scope (all students in year/term if school-wide; else students in the selected classrooms).
2. For each student, get linked guardians (e.g. StudentGuardian with user_id); for each guardian user, create a Notification (or use existing in-app notification channel) with title/message like "Report card available for [Term]" and link to portal report page or download.
3. Deduplicate by user so one notification per parent even if multiple children.
4. Consider batching (e.g. bulk_create) for large schools.

**Files to touch:**
- `apps/reports/views.py` (publish_term_results)
- Notification model (finance or shared) and its creation API

**Tests:**
- [ ] Publish term for a classroom; assert linked parent(s) receive one notification with correct link.

---

### BUILD-P3-3: Pre-generate term report PDFs (nightly) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.reports` |

**Description:** Optional Celery task that pre-generates term report PDFs for the most recently published term (or a given year/term) so the first parent download is fast; use chunking for large schools.

**Acceptance criteria:**
- [ ] A Celery task (e.g. `reports.pregenerate_term_report_pdfs`) accepts year_id and term_id (or "latest published") and generates ReportCard PDFs for students in scope (published classrooms/school).
- [ ] Task creates or updates ReportCard records and stores pdf_file; uses existing term_report_context and PDF rendering.
- [ ] Task is chunked (e.g. 50–100 students per chunk) to avoid timeouts and memory spikes; progress can be logged to AutomationExecutionLog.
- [ ] Optional: schedule in CELERY_BEAT_SCHEDULE (e.g. nightly after publish is typically done).

**Implementation steps:**
1. Add `apps/reports/tasks.py` (or equivalent) with a shared_task that: resolves year/term (e.g. latest published or by id), gets students in scope (from TermPublishStatus and classroom membership), and loops in chunks.
2. For each chunk, for each student, call existing term report context and PDF generation (reuse logic from parent_download_term or similar), save to ReportCard.pdf_file, and optionally update ReportCard.generated_at.
3. Log to AutomationExecutionLog (task_name e.g. "reports.pregenerate_term_pdfs", records_processed, status).
4. Add to CELERY_BEAT_SCHEDULE if desired (e.g. 2am daily).
5. Document in REPORT_CARDS_AND_GRADES or deploy doc.

**Files to touch:**
- `apps/reports/tasks.py` (new or existing)
- `config/settings.py` (CELERY_BEAT_SCHEDULE)
- `apps/reports/views.py` or services (reuse PDF generation)

**Tests:**
- [ ] Test task with small dataset; assert ReportCard records have pdf_file set and ExecutionLog entry exists.

---

### BUILD-P3-4: MFA recovery path (lost device + no backup codes) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.accounts` |

**Description:** Document or implement a minimal recovery path when a user loses their MFA device and has no backup codes (e.g. superuser reset of TOTP devices or time-limited bypass with audit).

**Acceptance criteria:**
- [ ] Either: (a) documentation for admins: "Superuser can remove user's TOTP devices in Django admin (otp_totp.TOTPDevice) so user can log in and re-setup MFA", or (b) a dedicated "MFA recovery" flow: superuser (or IT_ADMIN) can trigger a one-time bypass or reset for a user, with an audit log entry.
- [ ] No insecure backdoor; any bypass is logged and time-limited or one-time.

**Implementation steps:**
1. Option A: Add `docs/MFA_RECOVERY.md` describing how to remove TOTP devices via admin for a user, and that the user will be prompted to set up MFA again on next login if required.
2. Option B: Add a view (superuser-only) that lists users with MFA required and allows "Reset MFA" (delete TOTP devices for that user) and write to AuditLog or AccessLog; then redirect user to MFA setup on next login.
3. If Option B, add a link from Configuration Engine or compliance dashboard to this tool (with appropriate permission).

**Files to touch:**
- `docs/MFA_RECOVERY.md` (Option A)
- `apps/accounts/views_mfa.py` or admin (Option B)
- `apps/accounts/urls.py` (if new view)
- Compliance or audit logging

**Tests:**
- [ ] If Option B: test that only superuser can access; test that reset removes devices and next login prompts setup.

---

### BUILD-P3-5: Remind users without MFA (when require_mfa_roles set) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.accounts`, `apps.siteconfig` |

**Description:** Optional periodic task or one-time nudge: send an in-app notification (or email) to staff who are in require_mfa_roles but do not yet have a confirmed TOTP device, encouraging them to set up MFA.

**Acceptance criteria:**
- [ ] A task or management command finds users in require_mfa_roles (or all staff when require_mfa_all_staff) who have no confirmed TOTP device, and creates an in-app Notification (or sends email) with a link to MFA setup.
- [ ] Rate-limited so the same user is not spammed (e.g. once per week or once until dismissed).
- [ ] No external cost (use existing Notification model and email backend).

**Implementation steps:**
1. Add a Celery task or management command (e.g. `accounts.remind_mfa_setup`) that: loads SiteSettings, gets require_mfa_roles and require_mfa_all_staff, builds list of user IDs who must have MFA (same logic as must_have_mfa), filters to those without TOTPDevice confirmed, and for each creates a Notification with link to accounts:mfa_setup.
2. Optionally track "last MFA reminder at" in User or UserPreference to avoid sending more than once per week.
3. Schedule in CELERY_BEAT_SCHEDULE (e.g. weekly) or run manually.
4. Log to AutomationExecutionLog (optional but recommended).

**Files to touch:**
- `apps/accounts/tasks.py` (new or existing)
- `apps/accounts/utils.py` (reuse must_have_mfa)
- `config/settings.py` (Beat schedule)
- Optional: UserPreference or similar for "last_reminder_at"

**Tests:**
- [ ] Test that only users in require_mfa_roles without MFA get a notification; test no duplicate within cooldown if implemented.

---

### BUILD-P3-6: Guardian link reminder (students without guardian) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.people`, `apps.portal` |

**Description:** Optional report or notification to remind staff to complete guardian links for students who have no linked guardian (e.g. internal report or weekly digest).

**Acceptance criteria:**
- [ ] A report (backend or Configuration Engine) or a periodic notification lists (or counts) students with no linked guardian for the current academic year, with a link to fix (e.g. backend student list or invite flow).
- [ ] Optional: weekly in-app notification to staff with "N students without guardian" and link.

**Implementation steps:**
1. Add a query: StudentProfile.filter(academic_year=current_year).exclude(guardians__isnull=False) or equivalent (students with no StudentGuardian link).
2. Expose in backend dashboard as a small widget or "Data quality" section, or as a CSV/PDF report from reports or people app.
3. Optional: Celery task that creates a Notification for staff with link to this report or to student list filtered by "no guardian".

**Files to touch:**
- `apps/people` or `apps/accounts` (dashboard widget or report)
- Optional: `apps/accounts/tasks.py` or `apps/portal` for notification

**Tests:**
- [ ] Test query returns correct students; test report or widget displays.

---

### BUILD-P3-7: EMIS export as Celery task + "download when ready" — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `emis` |

**Description:** Run EMIS export as a Celery task for large datasets; provide a "download when ready" link and log to AutomationExecutionLog.

**Acceptance criteria:**
- [ ] Export can be triggered asynchronously (e.g. "Start export" button enqueues task); user sees "Export in progress" and later "Download" when the task has finished and file is stored.
- [ ] Task creates AutomationExecutionLog entry (task_name e.g. "emis.export", status, records_processed or file size).
- [ ] Export file is stored (e.g. in media or a dedicated store) and linked from EMISExport model; download URL is valid for the user who requested (or for admins).

**Implementation steps:**
1. Add a Celery task in emis (e.g. `emis/tasks.py`) that takes year_id, term_id, user_id, and optional format; runs EMISExportService.export (or equivalent); saves output to a file and attaches to EMISExport; updates status; creates AutomationExecutionLog.
2. In the view that currently does synchronous export, add an option to "Export in background": create EMISExport row with status "pending", enqueue task, return page with "Export started; refresh to download when ready."
3. List or detail view shows "Download" when status is completed and file exists.
4. Optional: expiry for old export files (e.g. delete after 7 days) to save space.

**Files to touch:**
- `emis/tasks.py` (new)
- `emis/views.py`
- `emis/models.py` (if need status/file field)
- `config/settings.py` (Celery autodiscover or include emis)
- `config/celery.py` (if app not auto-discovered)

**Tests:**
- [ ] Test export task creates ExecutionLog and file; test download link works for completed export.

---

### BUILD-P3-8: Compliance — health degraded → compliance alert — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.observability`, `apps.compliance` |

**Description:** When the health check reports "degraded" or "unavailable", optionally create a compliance alert or log so security/ops can track incidents.

**Acceptance criteria:**
- [ ] When /healthz or /health returns non-200 or a "degraded" payload, an optional hook runs that creates an AlertDigest or AuditLog entry (e.g. "Health check failed at YYYY-MM-DD HH:MM").
- [ ] Configurable (e.g. only in production or via a setting) to avoid noise in dev.
- [ ] No tight coupling: observability can call a compliance helper or send a signal; compliance listens and logs.

**Implementation steps:**
1. In observability views (healthz/health), when status is not healthy, call a small helper (e.g. compliance.alerts.record_health_degraded(reason)) or send a Django signal.
2. In compliance, handle the signal or helper: create AlertDigest or AuditLog with message and timestamp.
3. Add a setting (e.g. SiteSettings or env) to enable/disable this (default False in dev).
4. Document in COMPLIANCE_AND_MFA or observability doc.

**Files to touch:**
- `apps/observability/views.py` or monitoring
- `apps/compliance/alerts.py` or equivalent
- Optional: Django signal in compliance
- Settings or SiteSettings

**Tests:**
- [ ] Test that when health returns degraded, compliance record is created (when enabled).

---

### BUILD-P3-9: Warn when term end date passed and not published — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.academics`, `apps.reports` |

**Description:** Optional dashboard widget or Celery task: warn staff when a term's end date has passed but the term is not yet published (e.g. "Term 1 ended on X; publish results so parents can see reports").

**Acceptance criteria:**
- [ ] Backend dashboard or a scheduled task detects terms (for active year) where end_date < today and TermPublishStatus is not published for that term; show a warning in UI or send one in-app notification to staff.
- [ ] At most one notification per term (or per week) to avoid spam.

**Implementation steps:**
1. Add a small service function: get terms for active year where term.end_date < today and not TermPublishStatus.is_published for that term.
2. In backend dashboard context, add "unpublished_past_terms" and render a small alert or widget if non-empty.
3. Optional: Celery task (e.g. weekly) that creates a Notification for admins with list of such terms and link to Publish Results.
4. Log to AutomationExecutionLog if implemented as task.

**Files to touch:**
- `apps/academics/services.py` or `apps/reports/services.py`
- `apps/accounts/views.py` (backend dashboard context)
- `templates/accounts/backend_dashboard.html` (widget/alert)
- Optional: `apps/reports/tasks.py` and CELERY_BEAT_SCHEDULE

**Tests:**
- [ ] Test with a term whose end_date is in the past and not published; assert warning appears or notification created.

---

### BUILD-P3-10: Classroom capacity / overflow check (people) — Optional

| Field | Detail |
|-------|--------|
| **Priority** | P3 |
| **Optional** | Yes |
| **Module** | `apps.people`, `apps.academics` |

**Description:** Optional: when enrolling a student in a classroom, check classroom capacity (if a capacity field exists) and warn or block if at or over capacity.

**Acceptance criteria:**
- [ ] If Classroom has a capacity field (or you add one), backend student create/edit and any bulk import show a warning or validation error when assigning would exceed capacity.
- [ ] Existing behavior preserved when capacity is not set (unlimited).

**Implementation steps:**
1. Add optional `capacity` (PositiveIntegerField, null=True, blank=True) to Classroom if not present; run migration.
2. In backend student create/edit (and bulk import if applicable), when setting classroom: count current active students in that classroom; if capacity is set and count >= capacity, add validation error or warning ("Classroom at capacity").
3. Show message in template or form validation.
4. Document in people/academics doc.

**Files to touch:**
- `apps/academics/models.py` (Classroom)
- Migration
- `apps/people/forms_backend.py` or views_backend (validation)
- Templates if showing warning

**Tests:**
- [ ] Test that assigning a student to a full classroom (when capacity set) fails or warns; test that capacity=null means no check.

---

## Build order summary

| Phase | Item ID | Title | Optional |
|-------|---------|--------|----------|
| P0 | BUILD-P0-1 | Requests task → AutomationExecutionLog | No |
| P0 | BUILD-P0-2 | Finance: consolidate _temp payment modules | No |
| P0 | BUILD-P0-3 | Evals–reports documentation | No |
| P1 | BUILD-P1-1 | Report "ready" status in evaluation admin / publish page | No |
| P1 | BUILD-P1-2 | Portal: fix N+1 for report context | No |
| P1 | BUILD-P1-3 | Payroll run → AutomationExecutionLog | No |
| P1 | BUILD-P1-4 | Single MFA helper | No |
| P2 | BUILD-P2-1 | Centralize active year/term | No |
| P2 | BUILD-P2-2 | Single source staff URLs & dashboard metadata | No |
| P2 | BUILD-P2-3 | Add tests (evals–reports, finance, requests, portal, accounts) | No |
| P2 | BUILD-P2-4 | Compliance / MFA zero-cost documentation | No |
| P2 | BUILD-P2-5 | API search backend URLs | Yes |
| Portal | BUILD-PORTAL-1 | Portal (parent/teacher) wiring and RBAC verification | No |
| Portal | BUILD-PORTAL-2 | Portal compliance and audit coverage | Yes |
| Portal | BUILD-PORTAL-3 | Portal seamless flow and UX checks | Yes |
| P3 | BUILD-P3-1 | Session list / revoke | Yes |
| P3 | BUILD-P3-2 | Notify parents when term published | Yes |
| P3 | BUILD-P3-3 | Pre-generate term report PDFs (nightly) | Yes |
| P3 | BUILD-P3-4 | MFA recovery path | Yes |
| P3 | BUILD-P3-5 | Remind users without MFA | Yes |
| P3 | BUILD-P3-6 | Guardian link reminder | Yes |
| P3 | BUILD-P3-7 | EMIS export as Celery task | Yes |
| P3 | BUILD-P3-8 | Health degraded → compliance alert | Yes |
| P3 | BUILD-P3-9 | Warn when term end passed and not published | Yes |
| P3 | BUILD-P3-10 | Classroom capacity check | Yes |

---

## Tracking template (copy for your sprint)

```markdown
## Sprint / Build tracking

- [ ] BUILD-P0-1  Requests → ExecutionLog
- [ ] BUILD-P0-2  Finance _temp consolidation
- [ ] BUILD-P0-3  Evals–reports doc
- [ ] BUILD-P1-1  Report ready status
- [ ] BUILD-P1-2  Portal N+1
- [ ] BUILD-P1-3  Payroll → ExecutionLog
- [ ] BUILD-P1-4  Single MFA helper
- [ ] BUILD-P2-1  Centralize year/term
- [ ] BUILD-P2-2  Single source staff URLs & widgets
- [ ] BUILD-P2-3  Add tests
- [ ] BUILD-P2-4  Compliance/MFA doc
- [ ] BUILD-P2-5  API search backend URLs (optional)
- [ ] BUILD-PORTAL-1  Portal wiring and RBAC verification
- [ ] BUILD-PORTAL-2  Portal compliance audit (optional)
- [ ] BUILD-PORTAL-3  Portal flow and UX checks (optional)
- [ ] BUILD-P3-1  Session list/revoke (optional)
- [ ] BUILD-P3-2  Notify parents when published (optional)
- [ ] BUILD-P3-3  Pre-generate report PDFs (optional)
- [ ] BUILD-P3-4  MFA recovery (optional)
- [ ] BUILD-P3-5  Remind MFA setup (optional)
- [ ] BUILD-P3-6  Guardian link reminder (optional)
- [ ] BUILD-P3-7  EMIS export as task (optional)
- [ ] BUILD-P3-8  Health → compliance alert (optional)
- [ ] BUILD-P3-9  Term end not published warn (optional)
- [ ] BUILD-P3-10 Classroom capacity (optional)
```

Use this document as the single build reference; link to `MODULE_AUDIT_AND_IMPROVEMENT_PLAN.md` for the full audit rationale.
