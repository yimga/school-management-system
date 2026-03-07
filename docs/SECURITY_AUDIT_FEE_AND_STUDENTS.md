# Security audit: Fee Payments & Student Records (Phase 10)

**Plan:** [PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md](./PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md)

## 1. SQL injection and input sanitization

**Audit result:** Application code uses Django ORM (`filter`, `get`, `create`, `update_or_create`) and parameterized queries. **Raw SQL appears only in migrations** (e.g. index renames in `apps/finance/migrations/`), not in request-handling views. User input is passed to ORM or form validation.

**Safeguard:**
- Do **not** introduce `raw()`, `extra()`, or `cursor.execute()` with string interpolation (e.g. f-strings or `%` with user input) in views, API handlers, or services that handle requests.
- Search and filter endpoints: ensure all user-supplied values are passed as ORM parameters (e.g. `filter(id=request.GET.get("id"))`) or form `cleaned_data`.
- File upload paths and payment reference fields: use ORM and form validation; avoid concatenating user input into SQL.

**Code review:** Reject patches that add raw SQL with user input in request paths.

## 2. RBAC: fee payments, student records, payroll

**Fee payments:** Parent/guardian sees only invoices and payments for students linked via `StudentGuardian` with `can_view_finance=True`. Views use `_finance_access_state(request.user)` and guardian-linked students. Staff/bursar see broader data. Use `can_view_invoice(user, invoice_id)` (accounts.permissions) where applicable.

**Student records:** Views use `permission_required`, `role_required`, `teacher_portal_required`, `parent_portal_required`. Teachers see only their assignments and linked data; parents only guardian-linked students. Use `can_view_student_data(user, student_id)` where applicable.

**Payroll:**
- **Staff-only:** `payroll:dashboard`, `payroll:run_detail`, `payroll:create_run`, `payroll:generate_run` are protected by `@staff_member_required`. Teachers cannot access run details or other employees’ payslips.
- **Employee (self):** `payroll:employee_payslips` and `payroll:employee_leave` use `_employee_for_user(request.user)` and filter by that employee only; no `run_id` or `employee_id` in URL for employee views. Teachers see only their own payslips and leave.

**Tests:** See `apps/finance/tests/test_phase0_security.py` (InvoicePermissionTest, can_view_invoice) and payroll RBAC test (teacher cannot access run_detail).

## 3. Session management and inactivity logout

**Current:** `config/settings.py` uses:
- `SESSION_COOKIE_AGE`: from `SESSION_INACTIVITY_TIMEOUT_MINUTES` (env) × 60, or `SESSION_COOKIE_AGE` (seconds), default 14400 (4 hours).
- `SESSION_SAVE_EVERY_REQUEST = True`: session expiry extends on each request, so expiry is effectively **inactivity** timeout.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE`: configurable via env.

**For shared computers:** Set `SESSION_INACTIVITY_TIMEOUT_MINUTES=15` or `30` in `.env` so sessions expire after 15–30 minutes of inactivity. Document in deployment/security doc.

**Optional:** `ROLE_SESSION_TIMEOUTS` in settings allow per-role overrides (e.g. shorter for ADMIN) if enforced by custom middleware; current behaviour relies on global `SESSION_COOKIE_AGE`.
