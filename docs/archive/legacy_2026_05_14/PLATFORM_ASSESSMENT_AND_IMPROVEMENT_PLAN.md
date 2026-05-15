# Platform Assessment & Improvement Plan

**Goal:** A well-built, professional, seamless platform with no bugs and minimal redundancy.

---

## 1. How We Are Looking (Current State)

### ✅ Already in Good Shape

| Area | Status |
|------|--------|
| **GradingDeadline** | Fixed: all logic uses `SubjectAssignment.grading_deadline_at`. |
| **Dashboard context** | Consolidated: all dashboard views use `get_dashboard_context(user, page)`. |
| **Layout normalization** | API reuses `_normalize_dashboard_settings` from dashboard_views. |
| **Portal alias auth** | `@login_required` on `student_portal_grades`, `admissions_application_status`, `teacher_dashboard_alias`, `teacher_workflow_alias`. |
| **Role helper** | `get_user_role(user)` exists in `apps/accounts/utils.py` and is used in dashboard_views and AvailableWidgetsAPI. |
| **View auth** | Most portal/evals/finance/accounts views use `@login_required`, `@staff_member_required`, or `@role_required`. |
| **Tests** | ~51 test files across apps (portal, finance, evals, compliance, api, siteconfig, etc.). |
| **Django check** | Passes with no issues. |

### ⚠️ Remaining Gaps & Redundancies

---

## 2. Remaining Gaps (Bugs & Missing Behavior)

### 2.1 Security & Consistency

| Issue | Location | Risk | Fix |
|-------|----------|------|-----|
| **Unused `csrf_exempt` import** | `apps/compliance/views_api.py` | Dead code; if ever applied later, would weaken CSRF protection. | Remove the unused import. |
| **Role check duplication** | `DashboardLayoutAPI.get_user_role` (line 286) still inlines `(getattr(user, "role", "") or "").upper()` | Inconsistent with rest of codebase; future role logic changes could be missed here. | Use `get_user_role(user)` from `apps.accounts.utils` (same as AvailableWidgetsAPI). |
| **Role check in get_layout_for_page** | `apps/siteconfig/dashboard_views.py` line 169 | Same pattern repeated instead of using `get_user_role(user)`. | Replace with `get_user_role(user)`. |

### 2.2 Inconsistent Use of `get_user_role`

**Still using inline role checks (should use `get_user_role` where it’s “normalized role string”):**

- `apps/portal/services.py` (line 173)
- `apps/siteconfig/admin.py` (lines 327, 878, 899)
- `apps/siteconfig/portal_sidebar_items.py` (line 52)
- `apps/accounts/context_processors.py` (line 46)
- `apps/requests/views.py` (line 20)
- `apps/portal/views_ai_copilot.py` (lines 94, 134, 475, 506)
- `apps/evals/approval.py` (line 44)
- `apps/api/entity_api.py` (multiple)
- `apps/api/search_api.py` (multiple)
- `apps/api/permissions.py` (line 119)
- `apps/academics/api_views.py` (multiple)

**Note:** Some of these need “role in list” or “role == X” semantics; for those, calling `get_user_role(user)` and then comparing is the consistent pattern.

### 2.3 Placeholder / Incomplete Code

| Location | Issue | Action |
|----------|--------|--------|
| `apps/academics/scheduling.py:415` | `# TODO: Attempt to redistribute` + `pass` | Implement or document and leave a clear TODO. |
| **Bare `pass` in logic** | Several views (accounts, portal, evals, siteconfig) use `pass` in except or conditional branches | Replace with explicit no-op comment or real handling so intent is clear. |
| **Broad `except Exception`** | 402 matches across 122 files; some with `# noqa: BLE001` | Review: keep where intentional (e.g. top-level safety), narrow or log elsewhere. |

### 2.4 Frontend / Dashboard JS

| Issue | Location | Impact |
|-------|----------|--------|
| **Two dashboard JS entry points** | `dashboard-layout.js` (Sortable-based) and `dashboard-customizer.js` | Templates only load `dashboard-layout.js`; customizer exists but isn’t loaded in main dashboards. Clarify: is customizer obsolete or should it be included for “settings only” (Option B from CODE_REVIEW_GAPS_REDUNDANCIES)? |
| **dashboard_customize_ui.html** | References “dashboard-layout.js” only | Matches current loading; ensure any “Add widget” / “Reset” behavior is fully in dashboard-layout.js. |

### 2.5 Error Handling & Resilience

- **Exception handling:** Many `except Exception` blocks. Prefer:
  - Specific exceptions where possible.
  - Logging (with traceback) where catching broadly.
  - Re-raise or clear user-facing message so bugs aren’t silently swallowed.
- **User-facing errors:** Standardize messages (and optionally codes) for “not found”, “forbidden”, and “validation error” so the front end and support have a consistent story.

---

## 3. Redundancies to Reduce

### 3.1 Role Normalization

- **Current:** `get_user_role(user)` used in dashboard_views and API’s AvailableWidgetsAPI; many other places still use `(getattr(user, "role", "") or "").upper()` or `getattr(user, "role", None)`.
- **Target:** Use `get_user_role(user)` everywhere a normalized role string is needed (and keep `getattr(user, "role", None)` only where you explicitly need “no role” vs “empty string”).
- **Files to update:** See list in 2.2; plus `dashboard_views.get_layout_for_page` and `DashboardLayoutAPI.get_user_role`.

### 3.2 Unused Imports

- Run `ruff` or `flake8` with “unused import” checks (e.g. `F401`) and remove or use imports.
- Known: `apps/compliance/views_api.py` – `csrf_exempt` imported but not used.

### 3.3 Duplicate “admin/staff” Checks

- Patterns like `user.is_superuser or user.is_staff or user.role in ['ADMIN', 'LEADERSHIP']` appear in compliance, finance, communication.
- Consider a small helper, e.g. `is_admin_or_staff(user)` or reuse from a single place (e.g. `apps/accounts/permissions` or `apps/compliance/views_api`) so the allowed list is defined once.

---

## 4. Professional & Seamless Improvements

### 4.1 Logging & Observability

- Ensure important actions (login failures, permission denials, layout save, payment attempts) are logged with enough context (user id, endpoint, outcome) for support and auditing.
- Avoid logging sensitive data (passwords, tokens, full request bodies).

### 4.2 Validation & Messages

- Use Django forms and serializers consistently; avoid ad-hoc `request.POST.get` without validation.
- Standardize success/error message keys or formats so the front end can show consistent, user-friendly text (and optionally i18n later).

### 4.3 i18n Readiness

- Portal and many views use hard-coded English strings.
- For a “professional and seamless” multi-locale platform: wrap user-facing strings in `gettext`/`gettext_lazy` and use a consistent strategy (e.g. per-app or per-feature) so translation coverage can grow over time.

### 4.4 Tests & Regression

- Keep adding tests for:
  - New or changed features (dashboard context, grading deadlines, portal aliases).
  - Permission boundaries (role-based access, staff-only views).
  - Critical flows (payment, grade submission, invite/claim).
- Run the full test suite in CI so regressions are caught before release.

### 4.5 Documentation & Onboarding

- Keep CODE_REVIEW_GAPS_REDUNDANCIES.md and this plan updated as items are done.
- Document:
  - How dashboard layout and role-based widgets work.
  - Where grading deadlines live (SubjectAssignment.grading_deadline_at) and how reminders work (send_deadline_reminders command).
  - Any env-specific or deployment notes so new devs can run a “well-built” setup easily.

---

## 5. Prioritized Action Plan

### Phase 1 – Quick wins (low risk, high consistency)

1. Remove unused `csrf_exempt` import in `apps/compliance/views_api.py`.
2. In `DashboardLayoutAPI`, make `get_user_role(self, user)` call `get_user_role(user)` from `apps.accounts.utils`.
3. In `get_layout_for_page` (dashboard_views), use `get_user_role(user)` instead of inline role expression.
4. Run linter (e.g. ruff/flake8) for unused imports and fix reported files.

### Phase 2 – Consistency & maintainability

5. Replace remaining inline “role string” logic with `get_user_role(user)` in the files listed in 2.2 (portal/services, siteconfig/admin, portal_sidebar_items, context_processors, requests/views, views_ai_copilot, evals/approval, api/entity_api, api/search_api, api/permissions, academics/api_views).
6. Optionally introduce a single `is_admin_or_staff(user)` (or similar) and use it in compliance/finance/communication where the same list is repeated.
7. Resolve dashboard JS: either remove `dashboard-customizer.js` if unused, or document and wire it for “settings only” (Option B) so behavior is clear and non-redundant.

### Phase 3 – Robustness & clarity

8. Replace bare `pass` in non-migration code with a one-line comment or proper handling.
9. Review broad `except Exception` blocks: add logging, narrow exceptions, or document why broad catch is required.
10. Address `apps/academics/scheduling.py` TODO: either implement “redistribute” or document and leave a clear, tracked TODO.

### Phase 4 – Polish & scale

11. Add or extend i18n for user-facing strings in high-traffic areas (portal, auth, dashboard).
12. Standardize API error responses and user-facing error messages (format/codes).
13. Ensure critical paths have tests and that CI runs them on every change.

---

## 6. Summary Table

| Category | Count / Scope | Priority |
|----------|----------------|----------|
| Unused / dead code (e.g. csrf_exempt) | 1 file | P1 |
| Role helper not used everywhere | ~15+ call sites | P2 |
| Placeholder / TODO / bare pass | Several files | P2–P3 |
| Broad exception handling | 402 in 122 files (review, not all bad) | P3 |
| Dashboard JS (customizer vs layout) | 2 files, loading unclear | P2 |
| i18n | Many views | P4 |
| Test coverage | Add for new/changed features | P3–P4 |

---

**Document version:** 1.0  
**Last updated:** 2026-02-02  
**Status:** Ready for implementation (Phase 1 can start immediately).
