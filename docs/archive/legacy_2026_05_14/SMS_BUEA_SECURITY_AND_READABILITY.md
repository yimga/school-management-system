# SMS: Security, Workflow, and Readability (Buea-Ready)

Checklist for code review and deployment: security, workflow, architecture, Buea context, Django pitfalls, and admin readability.

---

## 1. Critical Code-Level Vulnerabilities

| Issue | Impact | Mitigation |
|-------|--------|------------|
| SQL Injection | Unauthorized data access | Parameterized queries only. Never pass user dict into `.filter(**request.GET)` (CVE-2025-64459). Use explicit keys, e.g. `request.GET.get('q')`. |
| XSS | Session theft | Templates auto-escape. Serve uploaded media from separate domain; do not serve user uploads as same-origin HTML. |
| Hardcoded credentials | Full compromise | SECRET_KEY, DATABASE_URL, API keys from environment (os.getenv / .env). Never commit secrets. |
| Broken auth/session | Impersonation | MFA (django_otp), RequireMFAMiddleware, role timeouts, secure cookies in production. |
| Sensitive data exposure | Leaks | No passwords in logs; DEBUG=False in production. |

**Django-specific:** Never do `Model.objects.filter(**request.GET.dict())`. Extract and validate specific parameters, then pass as keyword args.

---

## 2. Workflow Inefficiencies

- **Manual data entry:** Use online forms, bulk uploads (e.g. bulk grade entry), automated admissions.
- **Onboarding/offboarding:** Clear RBAC; revoke access on role change.
- **Siloed data:** Centralized models and APIs; avoid ad-hoc spreadsheets for core data.
- **Communication:** Central announcements and notifications.

---

## 3. Architectural and Technical Debt

- **Modularity:** Loosely coupled apps; services layer for business logic.
- **Scalability:** Use `select_related()` / `prefetch_related()` to avoid N+1; index hot columns (student_id, term).
- **Separation of concerns:** Views delegate to services; no business logic in templates.
- **Testing and docs:** Unit/integration tests for critical paths; keep this doc updated.

---

## 4. Buea / Cameroon Context

| Challenge | Technical response |
|-----------|--------------------|
| Unstable internet | Offline-first where possible; queue writes; bulk operations. |
| Power cuts | Auto-save; bulk_create/bulk_update so work commits in fewer transactions. |
| Overcrowded classes | Bulk attendance and bulk grade entry; efficient list views. |
| Manual admissions | Online registration; validation to reduce ghost records. |

**Config:** No hardcoded DB paths or credentials. **TIME_ZONE**: set to `Africa/Douala` (or via env). **Payments:** Support MTN/Orange Mobile Money; do not rely only on Stripe/PayPal. **Assets:** Minimize JS/CSS and images for expensive mobile data.

---

## 5. Django Checklist (Buea-Ready)

- SECRET_KEY and DEBUG from environment; DEBUG=False in production.
- ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS set for production.
- TIME_ZONE = Africa/Douala (or env); USE_TZ = True.
- No `.filter(**request.GET)` or user dict unpacking in ORM.
- Media/uploads from separate domain or storage.
- select_related / prefetch_related on list/detail views.
- bulk_create / bulk_update for mass grade/attendance entry.
- Celery (or similar) for heavy tasks (report cards, notifications).
- Audit/history (e.g. django-simple-history) for grades and sensitive edits.
- Mobile Money–ready user fields (e.g. phone) and local payment integration.

---

## 6. Admin UI: Theme-Proof Visibility (Light/Dark)

Use classes from `theme-proof-visibility.css` and variables from `design-tokens.css`:

- **Stroke:** `text-theme-proof` or `text-theme-proof-strong` on critical labels.
- **Shadow:** `shadow-theme-proof` on cards/panels.
- **Backplate:** `backplate-theme-proof` for text on variable backgrounds.
- **Safe colors:** `text-safe-muted`, `text-safe-accent`; avoid pure #000/#FFF without outline.
- **Glass:** `glass-theme-proof` for overlays.

---

## 7. Site Settings: Information Architecture

- **Grouping:** Settings in clear categories (Account, Appearance, Notifications, etc.).
- **Labels:** Plain language; no jargon.
- **Layout:** Persistent side nav for categories; options in main content.
- **Search:** Search settings (e.g. Site Settings sidebar search).
- **Breadcrumbs:** Where hierarchy exists (breadcrumb_context).
- **Responsive:** Sidebar collapses to mobile nav on small screens.

---

## 8. Unfold Admin Polish

- SIDEBAR: show_search, show_all_applications; optional navigation for custom links.
- Custom CSS via base_site.html extrastyle (theme-proof, sidebar, dashboard).
- Custom dashboard index and widgets.
- Light/Dark/System toggle; use theme-proof classes where needed.

---

## Summary Table

| Category | Risk | Mitigation |
|----------|------|------------|
| Security | SQLi (CWE-89) | Parameterized queries only; no **request.GET in ORM. |
| Security | Hardcoded secrets (CWE-259) | Env vars only. |
| Workflow | Manual admissions | Online registration; bulk ops. |
| Architecture | Design debt | Modular design; indexes; tests. |
| Buea | Connectivity | Offline-friendly; bulk ops; background jobs. |
| Buea | Power | Auto-save; atomic bulk transactions. |
| Buea | Payments | Mobile Money APIs. |
| Buea | Grades | Server-side validation; audit logs. |
