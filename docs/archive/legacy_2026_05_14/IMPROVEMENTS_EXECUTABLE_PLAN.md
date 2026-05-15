# Executable improvement plan

This plan has two parts:

- **Part A: Execute now** – Do these first; they do not depend on having real data and stay valid once data exists.
- **Part B: Execute when data exists** – Do these only after real data (invoices, students, payments, users) is present or when usage justifies them. They are in the plan so we execute them at the right time, not now.

---

## Part A: Execute now

### Phase 1: Behaviour & correctness (do first)

| # | Task | Where | What to do |
|---|------|--------|------------|
| 1.1 | **Split allocation – client-side sum check** | `templates/finance/split_allocation.html` | Add a small script: on input change in allocation amount fields, sum amounts and compare to total; show inline message "Sum: X / Total: Y" and disable submit or show warning if they don't match. Keep server-side validation as-is. |
| 1.2 | **Split allocation – loading state on submit** | `templates/finance/split_allocation.html` | On form submit: disable the submit button and show a spinner (e.g. `spinner-border spinner-border-sm` in button). Prevents double submit; works with 0 or many records. |
| 1.3 | **Preferences – loading state on submit** | `templates/siteconfig/user_preferences.html` | Same: on form submit disable "Save preferences" and show spinner. |
| 1.4 | **Access denied – loading state** | `templates/requests/access_denied.html` | On "Request access" button click: disable button and show spinner. |
| 1.5 | **Success/error messages on POST** | Finance + Portal + Siteconfig views | Audit: every POST that redirects should use `messages.success` or `messages.error` before redirect. Add where missing (e.g. split_allocation already has success; ensure invoice_detail upload, preference save, request access all have one). |
| 1.6 | **Test: preferences bypass** | `apps/accounts/tests/` or `apps/siteconfig/tests/` | Add test: authenticated non-admin user (e.g. parent or teacher) GET `/siteconfig/preferences/` returns 200 (not 403). |
| 1.7 | **Test: split allocation flow** | `apps/finance/tests/` | Add test: POST valid split allocation form → invoice created with lines, payment created, redirect to invoice detail; optional assert `apply_payment` called or balance updated. |

---

### Phase 2: Structure & consistency (templates and layout)

| # | Task | Where | What to do |
|---|------|--------|------------|
| 2.1 | **Reusable page header** | New partial or CSS class | Create a single pattern: e.g. `templates/components/page_header.html` with block for title, subtitle, primary action (right). Use it on Split allocation, Scan Teller, Preferences, Access denied, Finance payments, so all key pages share the same header layout. |
| 2.2 | **Button order on forms** | All form templates | Ensure every form: primary action (Submit/Save/Record) first, Cancel or Back second. Check: split_allocation, user_preferences, access_denied, any finance or portal form. Swap order where it's reversed. |
| 2.3 | **Form grouping – split allocation** | `templates/finance/split_allocation.html` | Wrap "Student, Total amount, Method" in a light box (e.g. `p-3 border rounded-3 bg-light-subtle` or `card mb-3`). Wrap the allocation table in its own card or section. Improves scan when form is used daily. |
| 2.4 | **Card style consistency** | Key list/detail templates | Use same card pattern where cards are used: `card shadow-sm` (or existing token), consistent `card-body` padding. Apply to split allocation card, preferences card, access denied card, finance list cards so they look one family. |
| 2.5 | **Access denied – icon and width** | `templates/requests/access_denied.html` | Add an icon above title (e.g. `bi-lock` or `bi-shield-exclamation`), wrap content in `col-lg-6 mx-auto` for max-width so layout doesn’t look stretched. |

---

### Phase 3: Queries & performance (code, not data-dependent)

| # | Task | Where | What to do |
|---|------|--------|------------|
| 3.1 | **Portal – parent finance** | `apps/portal/views.py` (parent_finance) | Already uses `select_related("student", "academic_year")` and `prefetch_related("payments")`. Confirm no other queryset in that view does N+1 (e.g. aggregates are on same qs). |
| 3.2 | **Finance – invoice list/detail** | `apps/finance/views.py` | For invoice_list and invoice_detail: ensure Invoice querysets use `select_related("student", "academic_year", "profile")` and `prefetch_related("payments", "lines")` where those relations are used. Add if missing. |
| 3.3 | **Finance – payment list** | `apps/finance/views.py` (payment_list) | Already uses `select_related("invoice", "invoice__student", "invoice__academic_year")`. No change if already present; otherwise add. |
| 3.4 | **Pagination – document limits** | `docs/` or code comments | Where we cap results (e.g. payments export 5000): add a one-line comment or doc note so future devs know the limit is intentional for "when we have data." **Done:** finance `invoice_list`/`payment_list` have inline comments (CSV 5000, PDF 500, paginator 25). |

---

### Phase 4: Aesthetics that scale (design tokens & a11y)

| # | Task | Where | What to do |
|---|------|--------|------------|
| 4.1 | **Focus ring consistency** | `static/css/` (e.g. design-tokens or a small utility) | Add or confirm: `:focus-visible` outline using `--school-primary` (or existing token) for buttons and form controls. Ensures keyboard users and full pages stay consistent. |
| 4.2 | **Tables – use existing tokens** | List templates (finance, portal, evals) | Ensure table headers/cells use design tokens (e.g. `--admin-content-thead-bg`, `--admin-content-text`) so when rows are many, tables stay readable in light/dark. Add token classes where tables are plain Bootstrap. |
| 4.3 | **Form labels** | Forms in finance, siteconfig, portal | Ensure every visible form field has a `<label for="id_...">` with class `form-label`. Fix any form that uses only placeholders. Helps when data is present and with a11y. |
| 4.4 | **Preferences – base template** | `templates/siteconfig/user_preferences.html` | If it extends `base.html` instead of `portal_base.html`, consider extending `portal_base.html` so header/sidebar/theme match the rest of the portal. Only if it’s the only page on a different base. |

---

### Phase 5: Security & validation (already mostly done; verify)

| # | Task | Where | What to do |
|---|------|--------|------------|
| 5.1 | **Safe redirects** | Views that use `next` or `redirect` after POST | Confirm no view redirects to user-controlled `next` without validation (e.g. _safe_next_url or allowlist). Quick grep for `redirect(request.GET.get("next"))` and similar. |
| 5.2 | **Split allocation – validation** | `apps/finance/forms.py` | Already validates sum = total and at least one line. No change; just confirm it’s there. |

---

### Checklist summary – Part A (execute in order)

- [x] **1.1** Split allocation – client-side sum check  
- [x] **1.2** Split allocation – loading state on submit  
- [x] **1.3** Preferences – loading state on submit  
- [x] **1.4** Access denied – loading state  
- [x] **1.5** Audit success/error messages on POST  
- [x] **1.6** Test: preferences bypass  
- [x] **1.7** Test: split allocation flow  
- [x] **2.1** Reusable page header component  
- [x] **2.2** Button order on forms  
- [x] **2.3** Form grouping – split allocation  
- [x] **2.4** Card style consistency  
- [x] **2.5** Access denied – icon and width  
- [x] **3.1–3.3** Queries (portal finance, finance invoice/payment)  
- [x] **3.4** Document pagination/limits where applicable  
- [x] **4.1** Focus ring consistency  
- [x] **4.2** Tables – design tokens  
- [x] **4.3** Form labels  
- [x] **4.4** Preferences base template (if needed)  
- [x] **5.1** Safe redirects audit  
- [x] **5.2** Split allocation validation (verify only)  

---

## Part B: Execute when data exists

Part B is **planned and partially implemented** so that when data becomes available, lists and reports populate without further structural work. Full plan, dependencies, and hook points: **`docs/IMPROVEMENTS_PART_B_PLAN.md`**.

| # | Task | When to execute | What to do |
|---|------|------------------|------------|
| B.1 | **Fancy empty-state illustrations or long copy** | After launch, only if needed | Keep empty states minimal. Revisit only if user feedback or analytics show empty states are confusing. See Part B plan. |
| B.2 | **Dashboard fill / placeholder content** | Do not do | No placeholders or fake widgets. When we have data, show real data. Documented in Part B plan. |
| B.3 | **Layouts only for 0–3 items** | Do not do | Build for 0, 10, and 100+ items. Documented in Part B plan. |
| B.4 | **List UX when data exists** | When lists are in use | Part A already added table tokens and structure. Part B plan lists hook points for sort/actions when needed. |
| B.5 | **Analytics/reports caching** | When usage/data justify | Part B plan documents hook points (e.g. `apps/analytics/views.py` dashboard). Add cache when slow. |
| B.6 | **Extra filters/sorting UI** | Done (data-agnostic) | Payment list: method + date range + sort order. Invoice list: sort order (date, due date, amount). Export and pagination preserve filters and order. |

### Checklist summary – Part B

- [ ] **B.1** Fancy empty-state illustrations (only if needed after launch)
- [x] **B.2** Dashboard fill/placeholder content – **do not do** (documented)
- [x] **B.3** Layouts only for 0–3 items – **do not do** (documented)
- [x] **B.4** List UX – tokens and structure in place; Part B plan has hook points for when data exists
- [x] **B.5** Caching – optional analytics dashboard cache implemented (off by default; set backend_feature_flags["analytics_dashboard_cache_seconds"] to enable)
- [x] **B.6** Filters – payment list filters (method, date from/to) implemented; invoices already had filters

---

*Reference: IMPROVEMENTS_DATA_AGNOSTIC.md for the "why" behind Part A vs Part B. Full Part B details: IMPROVEMENTS_PART_B_PLAN.md.*
