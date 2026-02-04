# Production Readiness – Detailed Gaps & Test Plan

**Purpose:** Before sending to production, fix these gaps and run the suggested tests so the platform is professional, secure, and stable.

---

## Part A: Critical (Must Fix Before Prod)

### A1. Payment webhook will 403 in production (CSRF)

**Location:** `apps/finance/views.py` – `payment_provider_webhook`

**Issue:** External payment providers (MTN MoMo, Orange Money, etc.) POST to `/finance/payments/webhook/<provider_slug>/` without a Django CSRF token. Django’s `CsrfViewMiddleware` will reject these with **403 Forbidden**, so real payment callbacks will never be accepted.

**Fix:** Exempt the webhook view from CSRF (security is already enforced by signature, IP whitelist, and rate limit):

- In `apps/finance/views.py`: add `@csrf_exempt` above `payment_provider_webhook` (and keep `@require_http_methods(["POST"])`).
- Import: `from django.views.decorators.csrf import csrf_exempt`.

**Test:** With DEBUG=0 and CSRF enabled, send a signed POST to the webhook URL and confirm 200/4xx from your logic (e.g. “unknown provider”), not 403 from CSRF.

---

### A2. Communication API returns 500 on invalid `pk` (uncaught DoesNotExist)

**Location:** `apps/communication/api_views.py`

**Issue:**

- **Lines 126 and 144:** `message = Message.objects.get(pk=pk)` – if `pk` is invalid or the message was deleted, `Message.DoesNotExist` is raised → **500**.
- **Line 340:** `announcement = Announcement.objects.get(pk=pk)` – same for announcements.

**Fix:** Use `get_object_or_404(Message, pk=pk)` (and same for `Announcement`), or wrap in `try/except Model.DoesNotExist` and return 404 with a clear JSON body.

**Test:** Call `mark_read`, `archive`, and `deactivate` with invalid or non-existent `pk`; expect 404 JSON, not 500.

---

### A3. Production environment variables

**Location:** `config/settings.py` and deployment env

**Checklist:**

| Variable | Required in prod | Notes |
|----------|-------------------|--------|
| `SECRET_KEY` | Yes | Must be set when DEBUG=0; otherwise ImproperlyConfigured. |
| `DEBUG` | Yes | Must be `0` or `False` in production. Default in code is `"1"` from env. |
| `ALLOWED_HOSTS` | Yes | Must be set when DEBUG=0; e.g. `yourdomain.com,www.yourdomain.com`. |
| `DATABASE_URL` | If not SQLite | Use for production DB (e.g. PostgreSQL). |
| `SITE_URL` / `BASE_URL` | Recommended | For emails and links (password reset, receipts). |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | Recommended | Already default to secure when not DEBUG. |

**Test:** Run with `DEBUG=0`, `SECRET_KEY=test`, `ALLOWED_HOSTS=testserver` and run test suite; then run `manage.py check --deploy` and fix any warnings.

---

## Part B: High (Should Fix Before Prod)

### B1. No custom 404 / 500 handlers

**Location:** `config/urls.py`, `config/settings.py`

**Issue:** Only `handler403` is set. For 404 and 500, Django uses default debug pages in DEBUG mode and generic “Not Found” / “Server Error” in production. No custom branded 404/500 templates.

**Fix:**

- Add `handler404` and `handler500` in `config/urls.py` (or a small views module) that render `templates/errors/404.html` and `templates/errors/500.html`.
- Create those templates (e.g. same layout as `errors/403.html`).

**Test:** With DEBUG=0, trigger 404 (e.g. `/nonexistent/`) and 500 (e.g. force an exception in a test view); confirm custom pages and no stack trace leakage.

---

### B2. API schema possibly public

**Location:** `config/urls.py` – `path('api/schema/', ...)`

**Issue:** `get_schema_view()` is wrapped only in `cache_page(60)`; there is no `login_required` or permission check. So `/api/schema/` may be publicly accessible (depends on DRF default).

**Fix:** If the schema must be restricted, wrap the schema view with the same pattern as `api_schema_ui` (e.g. `@login_required` and `@user_passes_test(_is_schema_allowed)`), or ensure `get_schema_view` uses DRF permission classes that require auth.

**Test:** With an unauthenticated client, GET `/api/schema/`; if it should be private, expect 401/403, not 200.

---

### B3. Unused `csrf_exempt` import

**Location:** `apps/compliance/views_api.py` line 8

**Issue:** Import is unused. If someone later applies it to a view by mistake, that view would lose CSRF protection.

**Fix:** Remove the unused import.

---

### B4. Role helper not used everywhere

**Locations:** See PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN.md §2.1 and §2.2.

**Issue:** `get_user_role(user)` exists but is not used in:

- `apps/siteconfig/dashboard_views.py` – `get_layout_for_page` (line 169)
- `apps/api/dashboard_layout_api.py` – `DashboardLayoutAPI.get_user_role` (line 286)
- Plus portal/services, siteconfig/admin, portal_sidebar_items, context_processors, requests/views, views_ai_copilot, evals/approval, api/entity_api, api/search_api, api/permissions, academics/api_views.

**Fix:** Use `get_user_role(user)` wherever a normalized role string is needed (and keep `getattr(user, "role", None)` only where you explicitly need None vs "").

**Test:** After refactor, run tests and smoke-check dashboard layout, RBAC, and API access by role.

---

## Part C: Medium (Stability & Consistency)

### C1. `.objects.get()` without try/except in other views

**Locations (already safe – use try/except or get_object_or_404):**

- evals/views.py: SubjectAssignment, Evaluation, OfflineMarkEntry – handled.
- finance/views.py: Invoice, WebhookLog – handled.
- accounts/views_mfa.py: TOTPDevice – handled.
- academics/api_views.py: Classroom – handled.

**Gap:** communication/api_views.py (see A2) – fix as above.

**Test:** For any view that takes `pk` or `id` in URL or body, call with invalid/non-existent id; expect 404 or 400, never 500.

---

### C2. Template `|safe` and XSS

**Locations:** Templates that use `|safe`:

- `SITE.custom_css` (base.html, portal_base.html) – admin/site-config editable; ensure only staff can set it and consider sanitizing or restricting to CSS.
- `article.content_html` (portal/kb_article.html) – user/editor content; ensure it’s sanitized on save (e.g. bleach or a safe HTML field).
- `report_style.css_snippet` (reports) – admin-controlled; lower risk.
- `dashboard_settings.sidebar_items`, `custom_links`, `widget_meta` – from DB/layout; ensure only trusted roles can write and values are validated.
- `AI_PERMISSIONS`, `current_json`, `bulk_presets_json` – from server; ensure not directly user-input.
- `req.details` (requests/detail.html) – could contain user/submitted data; prefer escaping unless intentionally safe.

**Fix:** Audit each: either keep `|safe` only for trusted/sanitized content, or remove `|safe` and escape. For KB articles, enforce a sanitizer (e.g. bleach) on `content_html` before save.

**Test:** As a non-superuser, try to submit HTML/script in KB article, custom CSS, or request details; confirm it’s escaped or stripped in output.

---

### C3. File upload validation

**Locations:** Views that use `request.FILES`:

- evals: marksheet upload, grade import CSV.
- accounts: profile photo.
- finance: invoice attachment, payment receipt.
- portal: document upload, contact request attachment.
- siteconfig: feature control import.

**Issue:** Some flows may not enforce file type/size in the view (only in form or model). Ensure every upload path validates type and size server-side.

**Fix:** Use Django form validation and/or model validators (e.g. `FileTypeValidator`, `FileSizeValidator` like in finance migrations) for all uploads; reject invalid files with 400 and a clear message.

**Test:** Upload oversized file, wrong extension, or non-upload file (e.g. .exe); expect 400 or validation error, not 500.

---

### C4. Rate limiting coverage

**Current:** Login 5/m, compliance views 30/m, compliance mute_threats 10/m, AI copilot custom limit, webhooks per-provider limit, mobile API throttle.

**Gaps to consider:**

- Password reset / forgot password (if any) – should be rate limited.
- Signup / claim invite – rate limit by IP or email.
- Finance request access – already behind auth; optional per-user limit.
- High-value APIs (e.g. grade import, bulk actions) – consider per-user throttling.

**Test:** Hammer login, password reset, and signup endpoints; confirm 429 or equivalent after limit.

---

## Part D: Pre-Production Test Matrix

Run these before tagging for production.

### D1. Security & auth

| Test | How | Expected |
|------|-----|----------|
| Login with wrong password | POST login with bad creds | 200 + “Invalid username or password” (no user enumeration). |
| Access staff URL as anonymous | GET e.g. /finance/, /analytics/ | Redirect to login or 403. |
| Access parent-only URL as teacher | e.g. /portal/parent/dashboard/ | 403 or redirect. |
| CSRF on POST form | Submit a critical form without CSRF token | 403. |
| Webhook without signature | POST to payment webhook without valid signature | 403. |
| Webhook with valid signature (test provider) | POST with correct HMAC/signature | 200 or 4xx from app logic, not 403 CSRF. |

### D2. Critical user flows

| Flow | Steps | Expected |
|------|--------|----------|
| Parent: claim invite, link child | Use valid invite token, link child | Success; child appears in parent dashboard. |
| Parent: view fees, request access | View finance, request access | Request created; notification to staff. |
| Teacher: enter marks, submit for approval | Enter marks, submit | Grades saved; approval request created. |
| Staff: approve grades, publish term | Approve, publish | Term published; parents see results. |
| Finance: create invoice, record payment | Create invoice, record payment (and webhook if applicable) | Invoice and payment recorded; receipt available. |
| Admin: extend grading deadline | Extend deadline for subject assignment | `grading_deadline_at` updated; visible in analytics deadlines. |

### D3. APIs

| Endpoint / area | Test | Expected |
|------------------|------|----------|
| Dashboard layout API | GET/PUT /api/dashboard/layout/backend/ as allowed role | 200; layout saved. |
| Dashboard layout API | GET as disallowed role | 404. |
| Communication API | mark_read with invalid pk | 404 JSON, not 500. |
| Communication API | mark_read with valid pk, as recipient | 200; message marked read. |
| Payment webhook | POST with invalid provider_slug | 403. |
| Payment webhook | POST with valid provider + signature (test config) | 200 or 4xx from logic. |
| Health | GET /health/ | 200 {"status": "healthy"}. |
| Observability | GET /metrics/ without auth | 401/403. |

### D4. Error pages & logging

| Test | Expected |
|------|----------|
| GET /nonexistent/ with DEBUG=0 | Custom 404 page, no stack trace. |
| Trigger 500 with DEBUG=0 | Custom 500 page, no stack trace; error logged server-side. |
| 403 (e.g. non-staff on admin) | Custom 403 page (already implemented). |

### D5. Configuration & deploy

| Check | Command / action |
|-------|-------------------|
| Deploy checks | `python manage.py check --deploy` |
| Migrations | `python manage.py migrate` (no unapplied migrations). |
| Static files | `python manage.py collectstatic --noinput` (e.g. for Whitenoise). |
| Env in prod | DEBUG=0, SECRET_KEY set, ALLOWED_HOSTS set, DATABASE_URL if not SQLite. |

---

## Part E: Summary Checklist

**Must fix before prod**

- [x] A1: Add `@csrf_exempt` to payment webhook view. **DONE**
- [x] A2: Use get_object_or_404 or try/except in communication API (Message, Announcement). **DONE**
- [ ] A3: Confirm production env (DEBUG=0, SECRET_KEY, ALLOWED_HOSTS).

**Should fix before prod**

- [x] B1: Add handler404 and handler500 and templates. **DONE**
- [x] B2: Restrict API schema if required. **DONE** (schema_view now uses login_required + _is_schema_allowed).
- [x] B3: Remove unused csrf_exempt import (compliance). **DONE**
- [x] B4: Use get_user_role in dashboard_views (get_layout_for_page) and DashboardLayoutAPI. **DONE**

**Test before prod**

- [ ] D1: Security & auth (login, staff/parent/teacher access, CSRF, webhook).
- [ ] D2: Critical flows (claim invite, fees, marks, approval, publish, finance, deadlines).
- [ ] D3: APIs (dashboard layout, communication 404, webhook, health).
- [ ] D4: 404/500 pages with DEBUG=0.
- [ ] D5: `check --deploy`, migrations, collectstatic, env.

**Medium (can be soon after launch)**

- C1: Audit remaining .get() in views (already mostly done).
- C2: Audit |safe and sanitize KB / custom_css / request details.
- C3: Enforce file type/size on all uploads.
- C4: Add rate limits on password reset / signup / claim invite if not already present.

---

**Document version:** 1.0  
**Last updated:** 2026-02-02  
**Use with:** CODE_REVIEW_GAPS_REDUNDANCIES.md, PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN.md
