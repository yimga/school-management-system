# Security audit: Fee Payments & Student Records (Phase 10)

**Plan:** [PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md](./PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md)

## 10.1 SQL injection and input sanitization

**Audit result:** Application code uses Django ORM (`filter`, `get`, `create`, `update_or_create`) and parameterized queries. Raw SQL appears only in **migrations** (index renames, schema), not in request-handling views. User input is passed to ORM or form validation.

**Safeguard:** Do not introduce `raw()`, `extra()`, or `cursor.execute()` with string formatting in views, API handlers, or any code path that receives user input. Use ORM or parameterized queries only. Search/filter endpoints must pass user values as parameters.

**File upload / payment reference:** Receipt upload paths use validated file fields and `transaction_reference` as stored strings; no SQL concatenation.

## 10.2 RBAC (Fee, Student Records, Payroll, Private Files)

- **Fee payments:** Scoped by `_finance_access_state(request.user)` and guardian-linked students; staff see broader data. Payment creation uses server-side validation.
- **Student records:** Views use `permission_required`, `role_required`, `teacher_portal_required`, `parent_portal_required`. Teachers see only their assignments; parents only guardian-linked students.
- **Payroll:** Teacher pay uses `request.user.teacher_profile` and `profile.pay_records`; no URL parameter for another teacher. `apps/portal/tests/test_rbac_teacher_pay.py` asserts teacher sees only own pay records.

## 10.3 Session and inactivity logout

- **Configurable inactivity:** Set `SESSION_INACTIVITY_TIMEOUT_MINUTES` (e.g. `15` or `30`) in env to limit session to that many minutes of inactivity. When set, it overrides `SESSION_COOKIE_AGE`. With `SESSION_SAVE_EVERY_REQUEST=True`, the session expires after that many minutes with no requests.
- **Fallback:** If `SESSION_INACTIVITY_TIMEOUT_MINUTES` is not set, `SESSION_COOKIE_AGE` (default 14400 = 4 hours) applies. See `config/settings.py`.
