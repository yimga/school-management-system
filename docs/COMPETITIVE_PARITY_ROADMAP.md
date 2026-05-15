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
| 6 | **Production observability** | **A.** Sentry + Celery integration + Prometheus + JSON logs + request-id middleware all wired. 8 canonical SLOs in `apps/observability/slo.py` with burn-rate code. Custom Sentry transactions on attendance / grade / parent dashboard / migration bundle apply. RUM gated only on `SENTRY_AUTH_TOKEN` (ops). | (settings.py review) |
| 7 | **OpenAPI / API surface** | **A.** drf-spectacular live with `/api/openapi.json` + Swagger + Redoc. CORS allowlist from `SiteConfig`. `IdempotencyKeyMiddleware` on all `/api/v1/` POSTs. RFC 7807 problem+json envelope. Cursor pagination default. 5 final `W002` placeholders closed in wave NS-3. SDKs are stubs; publishing is ops-blocked on tokens. | D→A |
| 8 | **Audit-log UI** | Backend audit infra is extensive; 5/6 compliance report templates missing from disk → views 500; login signals unwired; no per-record drill-down; PII-VIEW logging ~0% | E |
| 9 | **AI features** | **A.** Gateway + schemas + RAG store + prompt registry + audit + 27 productized endpoints + 6 bounded-context wrappers + Ollama-first tier policy + anthropic premium fallback + RAG ingest (CLI + admin endpoint) + ⌘K Ask-AI fallback + anomaly LLM enrichment. Only remaining gap is a trained at-risk joblib artifact (needs tagged dataset). See `AI_PLATFORM_WIDE_STATUS_2026_05_14.md`. | F→A |
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

## D-wave closures shipped 2026-05-11 (post-passes-7-14 follow-up)

The A → B → C waves of passes 8-14 shipped 2026-05-11 (see `STATE_OF_PLAY.md`).
Their D-tail items were closed in a single follow-up session:

- **8.D** — Importer Fees/Payments persistence ([apps/accounts/migration_importers.py](../apps/accounts/migration_importers.py)). `import_fees` writes to `Invoice` honoring Part F §25.1 immutability (re-imports of ISSUED rows are skipped, not mutated); `import_payments` writes to `Payment` with idempotency on `payment_reference` and best-effort `Invoice.balance_amount` recalc that uses `_recalculating=True` to bypass the immutability gate. Currency normalized to ISO 4217 (school region default as fallback). Roster importer now auto-creates `SubjectAssignment` (classroom × subject × term × specialty); the previous "create via Academics admin" note is gone. New CSV error-report endpoint at `GET /api/v1/migration-jobs/<job_id>/errors.csv` ([apps/api/views_migration_jobs.py](../apps/api/views_migration_jobs.py)) streams the job snapshot's errors as `row,message` for cleanup before re-import.
- **9.D** — Audit-log follow-up. `@audit_pii_view` applied to all four parent report-card download views (term/annual × pdf/csv) at [apps/reports/views.py](../apps/reports/views.py:220) — FERPA read-access decorator now covers the full PII surface. New `apps/compliance/tasks.py:mark_sla_breaches` Celery task stamps `sla_breach_at` on overdue Export/Erase rows; scheduled hourly via `CELERY_BEAT_SCHEDULE["compliance-mark-sla-breaches"]` ([config/settings.py](../config/settings.py:1147)). FERPA disclosure detail + evaluation drill-down still deferred (no canonical views yet — needs 9.E view-discovery first).
- **10.D** — A11y CI gate. Canonical [`inject_table_captions`](../apps/compliance/management/commands/inject_table_captions.py) management command upgraded with the layered heuristics from the duplicate `scripts/add_table_captions.py` (card-header/title, page_header includes, cp-mini-heading patterns, file-level title fallback) — the standalone script is deleted, one canonical source remains. `.github/workflows/a11y-axe.yml` now triggers on `static/js/**` and `apps/**/templatetags/**.py` in addition to templates/CSS/views, and the pytest `-k` filter that limited the run to a single class was removed.
- **Offline foundational** — Closed in full:
  - SMSOfflineDB read-binding wired via [static/js/attendance-offline-hydrator.js](../static/js/attendance-offline-hydrator.js); roll-call student + teacher templates now carry `data-attendance-offline-hydrator` so an offline page-load renders rows from the IndexedDB mirror. Script is loaded from `portal_base.html`.
  - Grades added to the SW write-allowlist in [static/js/service-worker.js](../static/js/service-worker.js) (previously commented out at `isApiWriteRequest` and `inferSyncType`).
  - Fresh CSRF on replay: new `GET /api/csrf-token/` endpoint ([apps/observability/views.py](../apps/observability/views.py)) returns a freshly-rotated token; `replayQueue()` in the service worker calls it once per batch and injects `X-CSRFToken` into every replayed POST, eliminating the 403s that occurred when the csrftoken cookie rotated while POSTs were queued.
  - PWA icons: `static/manifest-portal.json` was `icons: []` (uninstallable). Generated `static/images/icon-192.png` + `icon-512.png` (192/512 maskable, indigo background, centered logo) and wired both manifests; the portal is now a fully installable PWA.
- **Education-system rebuild — phase 1** — De-Cameroonized `evals.Evaluation`. The hard `MaxValueValidator(20)` was stripped from `seq1_score`/`seq2_score`/`exam_score`/`mock_score`/`practical_score`/`internship_score`; schools now declare their max via the `GradingScale` bound to their region (US 0-100, UK 0-100, Cameroon 0-20, IB 0-7). Migration `evals/0030_evaluation_decameroonize_validators.py` records the change for schema-diff tooling (no-op at the DB level). Forms/views remain responsible for enforcing the tenant-resolved max; the model only enforces `>= 0` and the column width.

## Second-pass closures (E-wave + phase 2) shipped 2026-05-11

After the D-wave landed, the previously-deferred "needs in-repo work" items closed in a follow-up pass. Most of the multi-quarter remainder is now bones-on-disk plus a real interface; the only gaps that survive are genuinely external (credentials, training data, vendor agreements, product decisions).

- **9.E — Audit-log follow-up complete.** New [`apps/compliance/views_ferpa.py:ferpa_disclosure_detail`](../apps/compliance/views_ferpa.py) — operator-only FERPA §99.32 single-disclosure view at `/compliance/ferpa/disclosure/<pk>/`, decorated with `@audit_pii_view` so reads land in `AuditLog`. New [`apps/evals/views_drilldown.py:evaluation_drilldown`](../apps/evals/views_drilldown.py) — per-evaluation detail at `/evals/evaluation/<pk>/` with the full `GradeAudit` trail (before/after for every score component). Both templates land in `templates/compliance/ferpa_disclosure_detail.html` and `templates/evals/evaluation_drilldown.html`.
- **Education-system phase 2 — IEP + LMS spine + content.**
  - New [`apps.people.SpecialEducationPlan`](../apps/people/models.py) model (US K-12 unlock requirement) with IEP / 504 / Gifted / ELL types, status enum, accommodations JSON, IDEA primary-disability field, case-manager FK, FERPA-sensitive plan document upload, and a `next_review_at` field that surfaces in SLA queues. Migration `people/0046_specialeducationplan.py` + admin registration via `SpecialEducationPlanAdmin`.
  - New [`apps.academics.LMSAssignment` + `LMSSubmission`](../apps/academics/models_lms.py) — minimal LMS spine (Google Classroom-style): teacher creates an assignment for a classroom; students submit; teacher grades. Names prefixed `LMS*` to avoid collision with the pre-existing `SubjectAssignment` (roster row) and `TeacherAssignment` (teacher↔subject_assignment link). Migration `academics/0045_lms_assignment_submission.py`. Future surfaces (gradebook v2, plagiarism, peer review) hang off these two roots.
  - Country `policy_snapshot` content populated for WAEC (Nigeria + Ghana WASSCE), KCSE (Kenya CBC), CBSE (India), ACARA (Australia), Cambridge IGCSE (UK/Cambridge), and IB Diploma. Previously bare slugs in [`seed_blueprint_policy_packs`](../apps/policies/management/commands/seed_blueprint_policy_packs.py); now each pack carries `examination_board`, `exit_certificate`, `term_system`, full `grading_scale` band table, reporting locale, and currency. The IB pack also names the three core components (TOK / EE / CAS) and `diploma_total_max=45`.
- **8.E — Vendor fee + payment schema packs.** New `POWERSCHOOL_FEES_HINTS` / `POWERSCHOOL_PAYMENTS_HINTS` / `SKYWARD_FEES_HINTS` / `SKYWARD_PAYMENTS_HINTS` / `VERACROSS_FEES_HINTS` / `VERACROSS_PAYMENTS_HINTS` in [`seed_migration_profiles`](../apps/automation/management/commands/seed_migration_profiles.py); union-merged into the generic `finance_import` + `payments_import` profile `schema_hints` so a typical export from any of the three vendors crosses the 0.8 auto-detect floor without operator field-mapping.
- **13.D — In-product AI surfaces.** New [`apps/portal/views_ai_draft.py`](../apps/portal/views_ai_draft.py) with `POST /portal/ai/draft/parent-message/` and `POST /portal/ai/draft/report-card-comment/` — both gated by `AI_TEACHER_COMMS` / `AI_REPORT_CARD` entitlement, both fail-closed when the entitlement is off. The existing `templates/portal/partials/ai_draft_inline.html` partial is wired into [`templates/accounts/direct_compose.html`](../templates/accounts/direct_compose.html); the compose view now resolves `AI_TEACHER_COMMS` entitlement at render time. (The structured ML at-risk path landed in parallel — see commit `0d931b66` for `apps/analytics/ml/at_risk_features.py` + `at_risk_model.py`.)
- **12.D — SDK packaging.** [`sdk/pyproject.toml`](../sdk/pyproject.toml) gained license (Apache-2.0), authors, classifiers, project URLs, and a `dev` optional-extras for the test harness. [`sdk/js/package.json`](../sdk/js/package.json) was `private:true UNLICENSED`; now public-publishable with author, license (Apache-2.0), homepage / repo / bugs URLs, and `publishConfig.access=public`. New [`.github/workflows/sdk-release.yml`](../.github/workflows/sdk-release.yml) — workflow_dispatch with `target ∈ {python, npm, both}`, builds artifacts on every run (so PRs can verify), publishes only when `PYPI_API_TOKEN` / `NPM_TOKEN` repo secrets are set (fail-closed otherwise). Operators flip a switch — no code change — to ship the first public release.

The rest of pass 13 (real ML risk model), pass 14 (publisher dashboard + Stripe Connect onboarding), and the deeper education-system rebuild (`Assignment`/`Submission` LMS spine, admissions pipeline, country policy_snapshots) remain multi-quarter product tracks. See "Ops-credentialed + multi-quarter remainder" below.

## Pass 10 — Accessibility finish (2-3 weeks)

Audit A's remaining 12 items — status refreshed 2026-05-14 against actual code:
1. ~~Add `<caption>` to every data table in analytics/finance/attendance/evals~~ **DONE 2026-05-11**.
2. Darken `#94a3b8` muted-text variables to `#64748b` for AA contrast — **PARTIAL.** `--text-muted` is `#86868b` (light) / `#8e8e93` (dark); `--admin-sidebar-text-muted: #94a3b8` still ships; addressed in the WCAG re-audit pass on `docs/CONTRAST_AUDIT_2026_05_14.md`.
3. Header gradient — **PARTIAL.** `--header-brand-fg: #f8fafc` (slate-50) at `design-tokens.css:161`. Needs final 4.5:1 verification against `--brand-gradient` endpoints; tracked in contrast audit.
4. ~~Roll out `min-touch-target` to default `.btn`~~ — **DONE.** `min-height: 24px` in `patterns.css:430`; aesthetic-v2 `.btn` rule at `design-tokens.css:429+`.
5. ~~Fix `role="banner"` on `<nav>` in `base.html:127`~~ — **DONE.** No matching `role="banner"` in any base template.
6. ~~Add `aria-label` to `<aside>` regions in `control_plane_base.html`~~ — **DONE.** `control_plane_base.html:76` has `aria-label="{% trans 'Control plane navigation' %}"`.
7. ~~Keyboard handler for sidebar resize `<div role="separator">`~~ — **DONE.** `static/js/portal-resize-keyboard.js` shipped (Pass 10 WCAG 2.1.1 compliance).
8. ~~Run `axe-selenium-python` in CI on the 10 highest-traffic templates~~ — **DONE 2026-05-14 wave NS-3.** Explicit 13-template matrix (1 homepage + 6 public + 6 auth) in `apps/compliance/tests/test_a11y_axe_smoke.py` covers all 4 dashboard shells + finance invoices + configure hub + login + forgot-password.

## Pass 11 — Observability finish (1-2 weeks) — STATUS REFRESHED 2026-05-14

Per `OBSERVABILITY.md`:
1. ~~Wire `sentry_sdk.integrations.celery.CeleryIntegration`~~ — **DONE.** `config/settings.py:1559-1568` with import guard.
2. ~~Forward Service Worker errors to Sentry-Browser~~ — **DONE.** `service-worker.js:75-76` bridges SW errors to `static/js/sentry-browser-bridge.js`.
3. ~~Commit Sentry alert rules~~ — **DONE.** `sentry/alerts.yml` shipped.
4. ~~Add health endpoint `/healthz/`~~ — **DONE.** Routed and tested (`apps/accounts/tests/test_smoke_urls.py:21`); referenced by 3 middlewares' allowlists.
5. RUM via Sentry-Browser SDK — **OPS-BLOCKED.** Push script `scripts/push_sentry_alerts.py` ready; needs `SENTRY_AUTH_TOKEN` + CSP allowlist decision.
6. ~~Custom traces around attendance submit, grade entry, parent dashboard render~~ — **DONE 2026-05-14 wave NS-3.** `@trace_view("attendance.submit")` + `@trace_view("grade.entry")` applied to `AttendanceViewSet.create` + `GradeViewSet.create`; `parent.dashboard.render` already wrapped; `migration.bundle_apply` added as a 4th named transaction in `apps/migration_cloud/orchestrator.py`.
7. ~~Define SLOs in code; burn-rate alerts~~ — **DONE 2026-05-14 wave NS-3.** `apps/observability/slo.py` — 8 canonical SLOs (web availability, attendance, grade, parent dashboard, migration bundle apply, AI gateway latency, webhook delivery, sync freshness) + `burn_rate()` + `burn_rate_severity()` helpers per Google SRE Workbook ch. 5. Test coverage at `apps/observability/tests/test_slo.py`. SOT: `docs/OBSERVABILITY_SLO_CODE.md`.

## Pass 12 — API maturity (3-4 weeks) — STATUS REFRESHED 2026-05-14

Per `ECOSYSTEM_STRATEGY.md` phase 1:
1. ~~drf-spectacular wired~~ — **DONE.**
2. ~~`django-cors-headers` allowlist~~ — **DONE.** `corsheaders` in INSTALLED_APPS:237, middleware:251, allowlist:1505-1511.
3. ~~Global `IdempotencyKeyMiddleware` for `/api/v1/` POST~~ — **DONE.** `apps/api/middleware_idempotency.py:100`.
4. ~~RFC 7807 problem+json error envelope~~ — **DONE.** `apps/api/exception_handler.py` + `EXCEPTION_HANDLER` at `settings.py:1499`.
5. ~~Webhook event catalog at `/api/v1/webhooks/event-types/`~~ — **DONE.** `apps/api/views_webhook_catalog.py`.
6. ~~Cursor pagination as `DEFAULT_PAGINATION_CLASS`~~ — **DONE.** `settings.py:1496`.
7. SDK packaging — **OPS-BLOCKED.** `sdk/pyproject.toml` + `sdk/js/package.json` public-publishable; `.github/workflows/sdk-release.yml` waits on `PYPI_API_TOKEN` + `NPM_TOKEN`.
8. `docs.runmycampus.com` — **DNS-BLOCKED.**

## Pass 13 — AI differentiation — STATUS REFRESHED 2026-05-14

Per `audit F` top 5:
1. Real ML at-risk scoring + LLM-explained `reason_summary` — **SCAFFOLD DONE, ARTIFACT PENDING.** `apps/analytics/ml/at_risk_features.py` + `at_risk_model.py` shipped; tagged training dataset + training notebook output now shipped in `docs/ML_AT_RISK_TRAINING.md` + `apps/analytics/ml/synthetic_at_risk_dataset.py` + `apps/analytics/ml/train_at_risk.py` (2026-05-14 wave).
2. ~~Teacher communication assistant~~ — **DONE.** `apps/portal/views_ai_draft.py` shipped 13.D.
3. ~~Policy + handbook RAG~~ — **DONE.** `apps/siteconfig/management/commands/ingest_policy_documents.py` (CLI) + `apps/siteconfig/views_console_ai_rag.py` (`POST /console/ai/rag/ingest/`, staff-only, audited) shipped 2026-05-14 wave NS-2.
4. ~~Report-card comment AI~~ — **DONE 13.D.**
5. ~~Anthropic Claude client + entitlement gate~~ — **DONE.** `requirements.txt:45 anthropic>=0.39.0`.

**Wave NS-2 (2026-05-14) AI surfaces closeout:** see `docs/AI_PLATFORM_WIDE_STATUS_2026_05_14.md`. Every AI surface verified end-to-end (27 endpoints + 6 bounded-context wrappers + RAG ingest CLI + admin endpoint + ⌘K Ask-AI fallback + governance + audit + safety). No remaining repo-deliverable AI gap.

## Pass 14 — Marketplace + partner program — STATUS REFRESHED 2026-05-14

Per `ECOSYSTEM_STRATEGY.md` phases 2-5:
1. ~~OAuth2 scope vocabulary~~ — **DONE.** `apps/marketplace/scopes_catalog.py`.
2. Generate Python + Node SDKs from OpenAPI; publish — **OPS-BLOCKED** (see 12.7).
3. ~~`MarketplaceApp`, `AppInstallation`~~ — **DONE.** `apps/marketplace/models.py:53, 427`. `AppReview` + `AppSubscription` still optional; submission flow handles validation today.
4. App submission flow + automated checks — **OPEN.** No `AppSubmission` model on disk; review queue handled via `MarketplaceApp.status` enum + manifest validators.
5. ~~Sandbox tenant infrastructure~~ — **DONE.** `apps/marketplace/management/commands/create_sandbox_tenant.py`.
6. ~~Tenant-facing `/marketplace/apps/` directory~~ — **DONE.** Routed via `apps/schools/super_urls.py:414-419`.
7. ~~Stripe Connect revenue share~~ — **DONE in code.** `apps/billing/processors.py:248 StripeConnectProcessor`; live execution still needs a Stripe platform account.
8. `partners.runmycampus.com` — **DNS-BLOCKED.**

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

---

## Ops-credentialed + multi-quarter remainder (after the D + E waves)

The repo-deliverable items through Pass 14 wave D **and** the second-pass
E-wave / phase-2 follow-up are now closed. What remains cannot be completed
inside this git repository alone — it needs external credentials, vendor
relationships, training data, or product decisions:

### Ops-credentialed (cannot run from this repo without secrets / DNS)

- **11.D — RUM via `@sentry/browser`.** Push code already shipped (`scripts/push_sentry_alerts.py`, commit `8b4fe931`); page-level `@sentry/browser` init still requires CSP decision (CDN allowlist vs vendored bundle). The push script + alerts.yml + SW error bridge are all ready — operator runs the script with **`SENTRY_AUTH_TOKEN` + `SENTRY_ORG_SLUG`** and the live Sentry project is wired.
- **12.D — SDK publish.** Packaging is ready: `sdk/pyproject.toml` Apache-2.0 + classifiers + URLs; `sdk/js/package.json` public-publishable with full metadata; `.github/workflows/sdk-release.yml` manual-trigger with target ∈ {python, npm, both}, fail-closed when secrets are missing. Operators add **`PYPI_API_TOKEN` + `NPM_TOKEN`** repo secrets and trigger the workflow. Hosting the public reference at **`docs.runmycampus.com`** still needs DNS + hosting decisions.
- **14.D — Publisher dashboard + Stripe Connect.** Publisher dashboard shipped (commit `0a9d85c7`) at `apps/marketplace/views_publisher.py` + 2 templates. Sandbox tenant provisioning shipped via `create_sandbox_tenant.py`. **Stripe Connect onboarding** still needs a Stripe platform account; **`partners.runmycampus.com`** still needs DNS.
- **SOC 2 Type II / ISO scope.** Audit-log read coverage is now complete (9.D + 9.E); auditor RFP + evidence room + audit kickoff still require **Compliance lead + exec sponsor**.
- **Clever / ClassLink prod district.** Needs **district prod creds + named sponsor**.
- **WOPI / Collabora live.** Needs **production DNS + Collabora service stand-up**.
- **iOS / Android store releases.** Needs **Mobile release owner + Apple/Google developer accounts**.
- **24/7 NOC.** Needs **Ops lead + pager rotation contract**.

### Multi-quarter product work (deferred — needs decisions / data / training)

- **13.D — Real trained ML at-risk model.** The scaffold is in place: `apps/analytics/ml/at_risk_features.py` (9-feature dataclass), `at_risk_model.py` (joblib loader + heuristic fallback), AI draft inline wired into direct_compose. The remaining gap is genuinely off-repo: **a tagged training dataset + the training notebook** that produces the joblib artifact at `settings.AT_RISK_MODEL_PATH`.
- **Education-system rebuild — phases 3-N.** Phase 2 shipped (IEP/504 model + LMS spine + 6 country policy_snapshots). Future phases: admissions pipeline upgrade, the FERPA disclosure *log* read-surface (a list view on top of the model + admin we already have), pluggable curriculum standards alignment, US state-specific reporting packs (Ed-Fi alignment goes deeper).
- **Pass 10 items 2-8** (contrast token swap, header gradient legibility, touch-target rollout, `role="banner"` fix, complementary-landmark labels, sidebar-resize keyboard handler). All sub-day changes once design tokens are settled — not blocked, just queued behind UX review.
- **Pass 11 items 4, 7** (`/healthz/` deeper dependency check, SLO burn-rate alerts in code). Shape established; gap is calibration data.

Every item that could be built without external coordination is now built; what remains is genuinely external work or product decisions.
