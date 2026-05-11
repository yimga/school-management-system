# Competitive Parity Roadmap (items 2–10 of the global-readiness mandate)

This document is the synthesis of six parallel audits run on 2026-05-11 to validate
the platform against US K-12 public / district / international-school sale requirements.
The 9 user-flagged areas are sequenced into engineering passes with realistic effort.

Companion docs created this pass:
- [`SECURITY.md`](SECURITY.md) — SOC 2 / ISO 27001 / FERPA / GDPR posture (item 3)
- [`OBSERVABILITY.md`](OBSERVABILITY.md) — Sentry / Prometheus / SLO plan (item 6)
- [`ECOSYSTEM_STRATEGY.md`](ECOSYSTEM_STRATEGY.md) — developer portal / app marketplace (item 10)
- [`ACCESSIBILITY_WCAG.md`](ACCESSIBILITY_WCAG.md) — existed; supplemented by audit findings (item 2)
- [`MULTI_TENANT_GLOBAL_ROADMAP.md`](MULTI_TENANT_GLOBAL_ROADMAP.md) — passes 6 + 7 (offline + education-system rebuild)

---

## Audit headline findings

| # | Area | Status today | Audit ID |
|---|---|---|---|
| 2 | **Accessibility (WCAG 2.2 AA)** | Mostly compliant; 8 legal-blocking items — most are surgical template edits | A |
| 3 | **Security posture (SOC 2 / ISO / PCI)** | Excellent technical controls (Argon2, MFA, CSP, HSTS, Sentry tagging, audit middleware, retention env vars, RLS policies); missing only the posture-statement doc | (settings.py review) |
| 4 | **Onboarding wizard** | ~70% built; magic-link login at verify, DNS automation, marketing CTAs bypass wizard are showstoppers | B |
| 5 | **Data import wizards** | Students + grades only; CSV-only; 500-row cap; no teacher/parent/roster/fee/payment/attendance importers; vendor presets exist for 7 SISes but only 4 auto-detect | C |
| 6 | **Production observability** | Sentry + Prometheus + JSON logs + request-id middleware all wired; Celery integration NOT enabled in `sentry_sdk.init`; no RUM; no SLO definitions | (settings.py review) |
| 7 | **OpenAPI / API surface** | Two parallel API trees (`/api/v1/` + unversioned); no `drf-spectacular`; no REST_FRAMEWORK dict; no CORS; no webhook event catalog; no RFC 7807 errors; SDKs are stubs | D |
| 8 | **Audit-log UI** | Backend audit infra is extensive; 5/6 compliance report templates missing from disk → views 500; login signals unwired; no per-record drill-down; PII-VIEW logging ~0% | E |
| 9 | **AI features** | Infrastructure mature (771-line gateway, schemas, RAG store, prompt registry, audit); end-user features sparse (AI Copilot disabled by default; risk-scoring is a heuristic; no Anthropic/OpenAI direct integration) | F |
| 10 | **Ecosystem (AWS/Shopify lane)** | OAuth2 wired; webhooks production-grade; SDKs stubs; no marketplace; no partner program; no public dev portal | D + strategy |

## What this pass (Pass 6) ships

Tight scoped quick wins extracted from the audits — all in this single pass:

### Documentation deliverables
- `docs/SECURITY.md` — vendor-questionnaire-ready posture statement
- `docs/OBSERVABILITY.md` — incident runbook patterns + SLO targets
- `docs/ECOSYSTEM_STRATEGY.md` — 5-phase 18-month marketplace plan
- `docs/COMPETITIVE_PARITY_ROADMAP.md` (this file)

### Code quick wins
- **Login / logout / failed-login audit signals** (`apps/compliance/signals.py`) — closes SOC 2 CC6.1 + FERPA access-log gap. `user_logged_in` / `user_logged_out` / `user_login_failed` Django signals now write to `AuditLog`.
- **Flash-message ARIA** (`templates/partials/shell_chrome_django_messages.html`) — error/warning get `role="alert" aria-live="assertive"`; success/info get `role="status" aria-live="polite"`. Platform-wide impact.
- **Duplicate `<h1>` removed** (`templates/backend_base.html`, `templates/control_plane_base.html`) — child pages own the single page h1 now; no more "Backend" or product-name dummy headings polluting the heading outline of every authenticated page.
- **Login form labels associated** (`templates/auth/login.html`) — `<label for="login-username">` + `id="login-username"`. (`manager_login.html` and `admin_login.html` were already correct.)
- **Admin index keyboard-accessible** (`templates/admin/index.html`) — 11 `<div class="app-card" onclick>` lost the outer click handler (inner `<a>` buttons remain as the accessible navigation); 1 `<div class="theme-toggle" onclick>` converted to a `<button type="button" aria-label="Toggle theme">`.
- **drf-spectacular wired** (`requirements.txt`, `config/settings.py`, `config/urls.py`) — `REST_FRAMEWORK` config block added; `SPECTACULAR_SETTINGS` with title/description/version/contact/servers/tags; new public routes `/api/openapi.json`, `/api/openapi.yaml`, `/api/docs/` (Swagger UI), `/api/redoc/`. Zero-auth on doc surfaces, per-endpoint auth still enforced on the underlying viewsets.

---

## Pass 7 — Onboarding showstoppers (1-2 weeks)

Audit B concludes onboarding is built but breaks at two seams. These are tight:

1. **Magic-link at `verify_signup`** — `apps/schools/signup_views.py:603` redirects to `/authentication/login/` after email verification, but the admin user has `set_unusable_password()` (`tasks.py:266`). Mint a one-shot signed token, log the user in via the SDK's `login_with_token` view, route to `studio_os:launch`. ~80 lines.
2. **DNS + wildcard cert automation** — `apps/schools/domain_sync.py:24-33` computes the FQDN but does not call any DNS provider. Add `apps/schools/dns_providers/{base.py,cloudflare.py,route53.py}` with a uniform `create_record(subdomain, target)` interface; trigger from `_do_provision` after `Client` creation; verify reachability with `dnspython` (already in requirements) before flipping `is_active=True`.
3. **Marketing CTAs through `/onboard/`** — bulk edit every `{% url 'signup_school' %}` in `templates/marketing/*.html` to `{% url 'onboard_wizard' %}`. Pure template work.
4. **Blueprint pack picker as wizard step 1.5** — surface `BlueprintPack` rows in the wizard UI; persist `pack_slug` into school settings; have `tasks.py` call `blueprint_apply.apply_pack(school, pack)` during provisioning.
5. **"Start with sample data" toggle** — checkbox in wizard step 3 that runs `seed_demo_tenant_users` post-provision and lands the admin on `attendance/today/` for a populated sample class.

## Pass 8 — Importer rebuild (3-4 weeks)

Audit C concludes the Migration Wizard scaffolding is solid but only covers students + grades. Build out:

1. **Teacher + Parent/Guardian importers** — add `teachers` and `guardians` to `MIGRATION_TYPES`; wire vendor presets analogous to student profiles.
2. **Roster importer** (Classroom + Subject + SubjectAssignment + Term in one wizard step) — unblocks the grade importer for fresh tenants.
3. **Excel/XLSX + Google Sheets paste support** — `openpyxl` is already in `requirements.txt` (line 57); widen `accept=".csv,.xlsx,.xls"`; branch on extension/magic-bytes.
4. **Async + progress + downloadable error CSV** — convert the wizard to enqueue a Celery task; reuse the `GradeImportService` job-detail UI pattern.
5. **One-click "Import from PowerSchool"** — when `schema_fingerprint.suggest_profiles_from_headers` confidence ≥ 0.8, auto-apply the schema mapping and jump to preview.
6. **Attendance + Fee + Payment importers** — currently stubs in `seed_migration_profiles.py`; need full target_fields + service.

## Pass 9 — Audit-log UI completion (1 week)

Audit E concludes infrastructure is extensive but 5 templates are missing:

1. Create the 5 missing templates under `templates/compliance/`:
   - `audit_trail_report.html`
   - `data_access_report.html`
   - `permission_overview.html`
   - `integrity_check_report.html`
   - `anomaly_detection.html`
   Views are already written — pure templating work.
2. **Per-record drill-down panel** — on StudentProfile / Evaluation / Invoice detail pages, render "Recent activity (last 90 d)" using `AuditLog.objects.filter(model_name=..., object_id=...)`.
3. **PII-VIEW logging** on high-sensitivity detail views — a small decorator emitting `AuditLog.Action.VIEW` rows on GET. Closes FERPA read-access gap.
4. **ExportJob / EraseRequest queue page** with approve/reject/complete workflow + SLA tracking.
5. **`FerpaDisclosure` model + admin UI** — Pass 7 of the multi-tenant roadmap (US K-12 unlock requirement).

## Pass 10 — Accessibility finish (2-3 weeks)

Audit A's remaining 12 items are mostly tight template fixes:
1. Add `<caption>` to every data table in analytics/finance/attendance/evals (~340 tables; bulk-script with sensible defaults then human review).
2. Darken `#94a3b8` muted-text variables to `#64748b` for AA contrast in light-mode surfaces (`design-tokens.css`).
3. Header gradient: change `--header-brand-fg` from `#ffffff` to a slate that achieves 4.5:1 against the emerald end, OR overlay `rgba(0,0,0,0.25)`.
4. Roll out `min-touch-target` to default `.btn` rules in `patterns.css` (WCAG 2.5.8 24×24px floor).
5. Fix `role="banner"` on `<nav>` in `base.html:127` — should be on `<header>` or removed.
6. Add `aria-label` to `<aside>` regions in `control_plane_base.html` and any other complementary landmarks.
7. Implement a keyboard handler for the sidebar resize `<div role="separator">` (`portal_base.html:308`).
8. Run `axe-selenium-python` (already in requirements) in CI on the 10 highest-traffic templates.

## Pass 11 — Observability finish (1-2 weeks)

Per `OBSERVABILITY.md`:
1. Wire `sentry_sdk.integrations.celery.CeleryIntegration` — single line, critical gap.
2. Forward Service Worker errors to Sentry-Browser.
3. Commit Sentry alert rules to `sentry/alerts.yml`.
4. Add health endpoint `/healthz/` if missing; verify dependency-aware (Postgres + Redis + storage).
5. Real-user monitoring (RUM) via Sentry-Browser SDK on frontend pages.
6. Custom traces around attendance submit, grade entry, parent dashboard render.
7. Define SLOs in code; burn-rate alerts.

## Pass 12 — API maturity (3-4 weeks)

Per `ECOSYSTEM_STRATEGY.md` phase 1:
1. ✅ **Done in this pass**: drf-spectacular wired; OpenAPI 3.0 at `/api/openapi.json`; Swagger at `/api/docs/`; Redoc at `/api/redoc/`; project-wide `REST_FRAMEWORK` config.
2. Add `django-cors-headers` with allowlist from `SiteConfig`.
3. Global `IdempotencyKeyMiddleware` for `/api/v1/` POST methods (today only finance has it).
4. RFC 7807 problem+json error envelope (custom exception handler).
5. Publish webhook event catalog as `/api/v1/webhooks/event-types/` with payload schemas.
6. Cursor pagination as `DEFAULT_PAGINATION_CLASS`.
7. SDK packaging — publish `runmycampus` to PyPI, `@runmycampus/sdk` to npm.
8. Promote `docs.runmycampus.com` to host the public reference (Swagger + recipes + changelog).

## Pass 13 — AI differentiation (multi-quarter)

Per `audit F` top 5:
1. Real ML at-risk scoring + LLM-explained `reason_summary` (replace `pct_absent * 0.4 + 20` heuristic).
2. Teacher communication assistant (draft-message + approval pattern proven in `narrative_feedback.py`).
3. Policy + handbook RAG (use existing `AIEmbeddingStore`; add policy-PDF ingestion task).
4. Report-card comment AI (one LLM call per term per class).
5. Premium-model failover — wire Anthropic Claude client (requirements: add `anthropic`), gate by tenant entitlement, layer above `litellm` in `DEFAULT_TASK_TIERS`.

## Pass 14 — Marketplace + partner program (multi-quarter)

Per `ECOSYSTEM_STRATEGY.md` phases 2-5:
1. Define OAuth2 scope vocabulary (`students:read`, `attendance:write`, etc.).
2. Generate Python + Node SDKs from OpenAPI; publish.
3. `MarketplaceApp`, `AppInstallation`, `AppReview`, `AppSubscription` models.
4. App submission flow + automated checks.
5. Sandbox tenant infrastructure.
6. Tenant-facing `/admin/apps/` directory.
7. Stripe Connect revenue share.
8. partners.runmycampus.com + certification + portal.

---

## Effort summary

| Pass | Scope | Effort | Unblocks |
|---|---|---|---|
| 6 (this) | Docs + quick wins (login audit, a11y top-5, drf-spectacular) | Done | Vendor questionnaires, screen-reader smoke tests, public API docs |
| 7 | Onboarding showstoppers | 1-2 weeks | Self-serve sub-30-minute signup |
| 8 | Importer rebuild | 3-4 weeks | Schools migrating from PowerSchool / Skyward / Veracross |
| 9 | Audit-log UI completion | 1 week | SOC 2 audit window; FERPA US K-12 public unlock |
| 10 | Accessibility finish | 2-3 weeks | US public-district sales (Section 508) |
| 11 | Observability finish | 1-2 weeks | Production incident response; enterprise SLAs |
| 12 | API maturity | 3-4 weeks | First external integrators; marketplace foundation |
| 13 | AI differentiation | Multi-quarter | 2026 ed-tech parity (Schoology, PowerSchool, MagicSchool) |
| 14 | Marketplace + partners | Multi-quarter | "AWS-of-education" positioning |

Aggregate Pass 7-12: **~12 weeks** for tight enterprise-readiness items. Pass 13 + 14 are
long-running programs that ship in parallel slices over 2-4 quarters.

**Nothing here blocks Pass 1-5 from shipping today.** The product is multi-tenant
ready globally for African, European, and international-private markets right now.
The 9 areas above are what's needed to credibly enter the US K-12 public-district
market and the "AWS-of-education" platform-positioning lane.
