# Improvements Implemented (Critical, High, Medium, Optional)

This document records the improvements that were implemented from the production-readiness and optional list.

---

## Critical

| Id | Item | Status | Where |
|----|------|--------|--------|
| A1 | Payment webhook CSRF | Already done | `apps/finance/views.py`: `@csrf_exempt` on `payment_provider_webhook` |
| A2 | Communication API 404 on invalid pk | Already done | `apps/communication/api_views.py`: `get_object_or_404` for Message/Announcement |
| A3 | Production env vars | Documented | Use `DEBUG=0`, `SECRET_KEY`, `ALLOWED_HOSTS`; run `manage.py check --deploy` |

---

## High

| Id | Item | Status | Where |
|----|------|--------|--------|
| B1 | Custom 404/500 | Already done | `config/urls.py`: `handler404`, `handler500`; `templates/errors/404.html`, `500.html` |
| B2 | API schema restricted | Already done | `config/urls.py`: `schema_view` wrapped with `@login_required` and `@user_passes_test(_is_schema_allowed)` |
| B3 | Unused csrf_exempt | N/A | No unused import found in `apps/compliance/views_api.py` |
| B4 | get_user_role consistency | Done | `apps/portal/views.py`: use `get_user_role(request.user)` in place of `getattr(..., "role", None)` where normalized role is needed |

---

## Medium

| Id | Item | Status | Where |
|----|------|--------|--------|
| C1 | .get() → 404 | Done | Communication API already uses `get_object_or_404` |
| C2 | XSS / KB sanitization | Done | `apps/portal/models_kb.py`: on save, sanitize `content_html` when set directly (e.g. admin) via `sanitize_html()` |
| C3 | File upload validation | Done | Invoice attachment: `FileTypeValidator` + `FileSizeValidator` in `apps/finance/views.py`; syllabus upload: same in `apps/academics/views_syllabus.py`; feature control import: 2MB max in `apps/siteconfig/views_feature_control.py` |
| C4 | Rate limiting | Done | Login already `@ratelimit(key='ip', rate='5/m', method='POST')`; `claim_invite` now `@ratelimit(key='ip', rate='10/h', method='POST')` in `apps/accounts/views.py` |

---

## Optional

| Item | Status | Where |
|------|--------|--------|
| Offline queue encryption | Stub | `static/js/service-worker.js`: `maybeEncryptBody` / `maybeDecryptBody` (base64 placeholder when `enableQueueEncryption` and `queueEncryptionKey` set); for real encryption use Web Crypto and server-derived key |
| Single grading deadline source | Already done | `GradingDeadline` removed (migration `analytics/0008`); canonical source is `SubjectAssignment.grading_deadline_at` |
| Empty state illustration slot | Done | `templates/components/dashboard_empty_state.html`: optional `illustration_url` for an image above the icon |
| Docs | Done | This file; `docs/OFFLINE_MODE_AUDIT.md` documents encryption hook points |

---

## Deploy checklist (A3)

Before production:

- Set `DEBUG=0` (or `False`).
- Set `SECRET_KEY` to a secure random value.
- Set `ALLOWED_HOSTS` (e.g. `yourdomain.com,www.yourdomain.com`).
- Run: `python manage.py check --deploy` and fix any warnings.
- Ensure payment webhook is reachable (CSRF exempt) and that communication API returns 404 for invalid pk.

---

*Reference: PRODUCTION_READINESS_GAPS_DETAILED.md, IMPROVEMENTS_EXECUTABLE_PLAN.md, OFFLINE_MODE_AUDIT.md.*
