# State of Play

**Last updated:** 2026-05-11 (passes 7 → 14: A + B + C waves all code-shippable items closed; only ops-credentialed items remain)
**Maintained by:** Hycinth Yimga + Claude (Opus 4.7) collaboration sessions

This is the canonical project source-of-truth. If you're picking up the project
after a break or in a new session, **start here**.

---

## TL;DR

RunMyCampus is a multi-tenant school-management SaaS being built to compete with
PowerSchool / Veracross / Schoology globally, with the longer-horizon ambition to
become the "AWS / Shopify / Salesforce of education" (developer-loved API, app
marketplace, partner ecosystem).

The product is **globally shippable today** to African / European / international-
private markets (passes 1-5 closed all the multi-tenant residue gaps). The
enterprise-readiness program (US K-12 public, district sales, SOC 2, accessibility
finish, AI parity, marketplace) is sequenced as **passes 6-14** in
[`COMPETITIVE_PARITY_ROADMAP.md`](COMPETITIVE_PARITY_ROADMAP.md).

---

## Passes shipped (committed to `main`)

| # | Commit | Date | Scope | Diff |
|---|---|---|---|---|
| 1 | `4f680d57` and earlier waves | 2026-05-10 | Aesthetic foundation (indigo+emerald+Inter, design-tokens.css ~100KB), config service, brand cascade | — |
| 2 | `cde27eed` | 2026-05-10 | runtime_constants.py, TenantPaginationMixin, 60 role-string sites → `User.Role.*` enum, 46 pagination magic-numbers → settings refs, email_palette.py + 11 email templates | — |
| 3 | `4b43ebb7` | 2026-05-10 | `fa_to_bi` icon templatetag, exam-pack BlueprintPack accessor, `/sw-asset-manifest.json` endpoint, grade-weight env vars | — |
| 3.5 | `b02ebdc1` | 2026-05-10 | Multi-tenant safety pass: pass threshold via settings, hemisphere-aware academic year, email signoff via site_settings, neutral signup example | — |
| 4 | `c4d3ba72` | 2026-05-10 | Multi-tenant blocker remediation (17 files, +617/−87): parent-dashboard `$`, certificate `get_grade_letter` tenant-aware, payment-gateway whitelists fixed, RegionConfig defaults XAF→USD, Certification Board enum +9 entries, ComplianceProfile labor defaults zeroed, +237 placeholders neutralized, OCR currency regex, tax_engine 40+ jurisdictions, RiskFactor.band tenant-aware | +617/−87 |
| 5 | `8800b237` | 2026-05-11 | Global-tenant residue (19 files, +253/−131): 3 hardcoded `$` template literals, 3 DD/MM/YYYY fallback defaults, RISK_BAND/PAYMENT_MAX_AMOUNT settings, Ed-Fi/CEDS adapter grade-thresholds, seed_finance_defaults neutralized, Gender enum +NON_BINARY/PREFER_NOT_TO_SAY, 80 flash messages wrapped in `_()` | +253/−131 |
| 6 | `fc82e1f0` | 2026-05-11 | Enterprise-readiness kickoff (13 files, +847/−22): 4 strategy docs (SECURITY/OBSERVABILITY/ECOSYSTEM_STRATEGY/COMPETITIVE_PARITY_ROADMAP) + 6 code quick wins (login audit signals, flash ARIA, duplicate h1 removed, login labels, admin index keyboard access, drf-spectacular wired with `/api/openapi.json` `/api/docs/` `/api/redoc/`) | +847/−22 |
| 8.C | `2c71913c` | 2026-05-11 | Importer rebuild wave 3 — `static/js/migration-job-poll.js` drop-in async progress UI activated by `data-migration-job-id="<uuid>"`, polls `/api/v1/migration-jobs/<id>/` every 2.5s, renders progress bar + status badge + counts + first-50 errors collapsible, terminal-status detection, ~25min runaway-poll giveaway. `apps/automation/management/commands/seed_migration_profiles.py` — FACTS/Skyward/Alma student + grades schema_hints widened with vendor-specific column names (Student_DCID, FactsID, Other ID, Alpha Key, Alma_ID, section, advisor, primary_teacher, marking_period, quarter, trimester) so a typical export crosses the 0.8 auto-detect floor without manual mapping. |
| 9.C | `2095c39a` | 2026-05-11 | Audit-log UI wave 3 — ExportJob + EraseRequest gain `due_at` + `sla_breach_at` columns via migration `0014_exportjob_eraserequest_sla.py`. New `apps/compliance/views_queue.py:data_rights_queue` operator view + 4 POST action endpoints (approve_erase / reject_erase / complete_erase / complete_export). `templates/compliance/data_rights_queue.html` shows two stacked tables with status filter + "overdue only" toggle; rows past due_at get `.table-warning` highlight. Mounted under `/compliance/data-rights/queue/` + 4 action paths. Gate: superuser / staff / `compliance.manage_data_rights`. |
| 10.C | `a0d665a9` | 2026-05-11 | A11y wave 3 — authenticated-route axe coverage. New `_login_via_session()` helper in `apps/compliance/tests/test_a11y_axe_smoke.py` builds a Django session via SESSION_ENGINE and drops the cookie into the Chrome driver. New `test_authenticated_routes_have_no_severe_violations` scans `/portal/`, `/portal/teacher/`, `/portal/parent/`, `/backend/`. Both new tests inherit the `RUN_A11Y_TESTS=1` opt-in gate. The 333-table `<caption>` sweep stays operator-driven via the 10.B `inject_table_captions --write` command (template-author review per subdirectory). |
| 11.C | `df74e338` | 2026-05-11 | Observability wave 3 — `apps/observability/tracing.py:trace_view(name, op)` decorator wraps a view in `sentry_sdk.start_transaction` with status-on-exception bookkeeping. No-op when `sentry_sdk` is absent. Applied to 3 hot views: `teacher_attendance_view` → `teacher.attendance.view`, `parent_dashboard` → `parent.dashboard.render`, `grade_approval_detail` → `grade.approval.detail`. Operators can boost the per-op sample rate in Sentry to get full coverage on one path without paying for everything else. |
| 12.C | `7498ed05` | 2026-05-11 | API maturity wave 3 — `apps/api/middleware_tenant_cors.py:TenantCorsAllowlistMiddleware` mounted directly before `CorsMiddleware`. Reads `request.school.settings["cors_allowed_origins"]` (JSON list), normalizes each entry (strips trailing slash, requires http/https scheme, drops `*`), and union-merges into `settings.CORS_ALLOWED_ORIGINS` just before the upstream middleware reads it. Marketplace integrators can be added per-tenant without a redeploy. Static regex allowlist (`*.runmycampus.com`) untouched; broad-except wrapper so CORS bugs can't fail user requests. |
| 13.C | `c54017b3` | 2026-05-11 | AI differentiation wave 3 — per-tenant premium spend caps via new `_check_and_consume_premium_budget()` in the gateway, separate from the request budget; reads `school.settings["ai_premium_daily_cap"]` → `settings.AI_PREMIUM_DAILY_CAP_PER_TENANT` → env. Exhausted cap → tier skipped, falls through to Ollama (preserves availability). New `apps/siteconfig/management/commands/ingest_policy_documents.py` walks tenant policy directory, chunks .txt/.md/.pdf into 1500-char overlapping windows, embeds via `services.embeddings.get_embedding_provider()`, persists to `AIEmbeddingStore` with `scope="policy"` + sha256-keyed idempotence. Optional pypdf for PDF text extraction. New `templates/portal/partials/ai_draft_inline.html` drop-in "Generate AI draft" button next to any textarea — POSTs to a teacher-controlled endpoint, fills + dispatches input event, status via aria-live polite. |
| 14.C | `041dc780` | 2026-05-11 | Marketplace wave 3 — `POST /api/v1/marketplace/submissions/` (`apps/api/views_marketplace_submissions.py:MarketplaceSubmissionView`). Auto-provisions a `PublisherOrganization` for `request.user` if email doesn't match an existing one. Required body: {slug, name, version}. Optional: kind, manifest, description, category, short_description, preview_image_url, screenshot_urls (capped at 10). `update_or_create` on MarketplaceApp (by slug) + MarketplaceListing (one-to-one). New apps land DRAFT; updates land PENDING_REVIEW + `security_review_status=PENDING` so the existing review queue picks them up. Spectacular-tagged Marketplace. |
| 8.B | `ccfe57df` | 2026-05-11 | Importer rebuild wave 2 — async Celery wrapper for the Migration Wizard. New `apps/accounts/migration_async.py` (`enqueue_migration_run` → uuid job_id, `@shared_task name="accounts.run_migration_async"` body, cache-backed snapshots under `migration_job:<id>` with 24h TTL). Inline fallback when Celery isn't installed. New `GET /api/v1/migration-jobs/<job_id>/` (`apps/api/views_migration_jobs.py:MigrationJobStatusView`) returns the live snapshot for UI polling. Snapshot fields: status (queued/running/completed/completed_with_errors/failed), row_count, processed, created, updated, skipped, error_count, first 50 errors, timestamps. |
| 9.B | `6e62d570` | 2026-05-11 | Audit-log UI wave 2 — FERPA §99.32 disclosure log lands. New `FerpaDisclosure` model in `apps/compliance/models.py` (school + student cascades, disclosed_by SET_NULL, recipient_name + optional org, 10-value Purpose enum covering all §99.32 exceptions, parent_consent_obtained, record_types_disclosed JSON, disclosed_at + notes + 3 indexes). Migration `0013_ferpa_disclosure.py`. `FerpaDisclosureAdmin` registered via `@admin.register` with list_display + list_filter + date_hierarchy + autocomplete on FKs so K-12 auditors can sample by purpose / student / date range. |
| 10.B | `3dbb899b` | 2026-05-11 | A11y wave 2 — `apps/compliance/management/commands/inject_table_captions.py` walks `templates/**/*.html`, finds `<table class="table…">` without a `<caption>` within 400 chars, and injects `<caption class="visually-hidden">{% trans "..." %}</caption>` derived from `aria-label` / nearest `<h1>`/`<h2>` / fallback. DRY-RUN by default; `--write` mutates; `--path` scopes by subdirectory. Axe-selenium scaffold extended with `test_public_routes_have_no_severe_violations` covering `/onboard/`, `/marketing/`, `/authentication/login/`, `/healthz/`. Still opt-in via `RUN_A11Y_TESTS=1`. |
| 11.B | `61efcc2c` | 2026-05-11 | Observability wave 2 — `POST /api/observability/client-event/` (`apps/observability/views.py:client_event_capture`) accepts sanitized error payloads and forwards through server-side `sentry_sdk` under tagged scope. New `static/js/sentry-browser-bridge.js` hooks `window.error` + `unhandledrejection` + service-worker `message` (sw-error type) with a 16-event ring buffer and `keepalive: true` fetches. Wired into `portal_base.html`. `static/js/service-worker.js` broadcasts errors via `clients.matchAll() + postMessage(type=sw-error)`. No CDN dependency. |
| 12.B | `193c3c22` | 2026-05-11 | API maturity wave 2 — `apps/api/middleware_idempotency.py:IdempotencyKeyMiddleware` mounted globally after CorsMiddleware. Stripe / GitHub / Twilio semantics: `Idempotency-Key` header on `/api/v1/` POST/PUT/PATCH/DELETE caches the 2xx JSON response for 24h (tunable via `API_IDEMPOTENCY_TTL_SECONDS`); replays add an `Idempotent-Replay: 1` header. Cache key sha256-hashed across (tenant, user, method, path, key) so two tenants never collide. Broad-except on every cache op so cache failures can't break writes. |
| 13.B | `48061041` | 2026-05-11 | AI differentiation wave 2 — two new draft-and-approve AI surfaces. `TaskType.TEACHER_COMMS_DRAFT` + `TaskType.REPORT_CARD_COMMENT` added to gateway with same tier policy as RISK_EXPLAIN. New `services/teacher_comms.py:draft_parent_message` (80-120 word warm, factual parent draft; refuses speculation about home life / medical / protected attributes) and `draft_report_card_comment` (40-60 word per-term comment from a small evaluation snapshot list). Both fail closed — caller owns the entitlement gate via `can(school, "AI_TEACHER_COMMS")` / `"AI_REPORT_CARD"`. |
| 14.B | `bad9dde9` | 2026-05-11 | Marketplace wave 2 — `apps/marketplace/management/commands/seed_marketplace_scopes.py` upserts AppPermissionScope rows from `MARKETPLACE_SCOPES` (shipped in 14.A). Idempotent; `--dry-run` available. Run from the deploy hook to keep the DB-side catalog in lockstep with the code-side. |
| 14.A | `53d595b7` | 2026-05-11 | Marketplace wave 1 — first concrete slice. Surprise finding: all 4 roadmap models (MarketplaceApp / AppInstallation / MarketplaceReview / TenantMarketplaceSubscription) **already exist** in `apps/marketplace/models.py` from prior work, plus 11 supporting models (PublisherOrganization, AppPermissionScope, MarketplaceListing, AppScope, ScopeGrant, AppBillingLedger, PlatformMarketplaceEarning, AppAuditLog, MarketplaceMonetizationLedgerEntry, AppVersionCompat, CapabilityRegistry). Scope of pass 14.A narrowed to the actual gaps: code-backed scope vocabulary + public catalog endpoints. New `apps/marketplace/scopes_catalog.py:MARKETPLACE_SCOPES` declares 15 OAuth2-style scopes (students/guardians/attendance/grades/finance/webhooks/files/users/tenant × read/write/admin) with `domain`, `access`, `sensitivity` (mirrors AuditLog.Sensitivity), and approval-ready descriptions for the install dialog. New `apps/api/views_marketplace_catalog.py` exposes two public endpoints: `GET /api/v1/marketplace/apps/` (lists active apps with manifest projection, optional `?kind=` filter, 200-item cap) and `GET /api/v1/marketplace/scopes/` (full scope vocabulary). Both AllowAny, 5-minute Cache-Control. `SPECTACULAR_SETTINGS["TAGS"]` extended with `"Marketplace"` so the public docs render the section. |
| 13.A | `dc439fc0` | 2026-05-11 | AI differentiation wave 1 — first concrete slice. `anthropic>=0.39.0` added to requirements (optional dep; absent SDK falls back transparently). New `_call_anthropic()` provider in `services/ai_gateway.py` reading `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL` (default `claude-haiku-4-5-20251001`) from env/settings. `TaskType.RISK_EXPLAIN` added; default tier list `["anthropic", "ollama", "rules"]`. Premium gate in `invoke()` also covers `anthropic` (drops to ollama when data tier disallows premium). `_cost_class_for_tier` now classifies anthropic as `"premium"`. New `services/risk_explanation.py:explain_risk` builds a deterministic, 1-2-sentence prompt (60-word cap, PII-aware, no chain-of-thought) and returns either the LLM text or the heuristic fallback. Wired into `apps/analytics/management/commands/compute_nightly_risk.py`: only fires per school when `apps.billing.entitlements.can(school, "AI_RISK_EXPLAIN")` is true, otherwise the canned heuristic text persists unchanged. Nightly batch never raises on AI error — fallback paths are belt-and-suspenders. Cost class flows through to the existing audit log so per-tenant Anthropic spend is observable from day one. |
| 12.A | `c01c845d` | 2026-05-11 | API maturity wave 1. `django-cors-headers>=4.3.1` added to requirements; `corsheaders` registered in INSTALLED_APPS; `CorsMiddleware` mounted directly after `SecurityMiddleware` per upstream docs. `CORS_ALLOWED_ORIGINS` reads from env CSV, `CORS_ALLOWED_ORIGIN_REGEXES` allows `*.runmycampus.com`. `REST_FRAMEWORK` now sets `DEFAULT_PAGINATION_CLASS = CursorPagination` + tunable `PAGE_SIZE` (env `API_DEFAULT_PAGE_SIZE`, default 50). New `apps/api/exception_handler.py:rfc7807_exception_handler` wraps every DRF error in an RFC 7807 problem+json envelope (`type`/`title`/`status`/`detail`/`instance`/`errors`); content-type `application/problem+json`. Wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]`. New `GET /api/v1/webhooks/event-types/` (`apps/api/views_webhook_catalog.py:WebhookEventTypesView`) — public, unauth, serializes every entry in `apps/events/catalog.py:EVENT_CATALOG` with required + optional payload keys, retry policy, schema version. 5-min cacheable, tagged for Spectacular's `Webhooks` group. |
| 11.A | `c01c845d` | 2026-05-11 | Observability wave 1. `sentry_sdk.init` now ships `CeleryIntegration()` alongside `DjangoIntegration()` (lazy-imported so non-Celery deploys are unaffected) — every background task error becomes visible to Sentry. New `sentry/alerts.yml` declares 6 P1/P2/P3 alert rules: web 5xx fast-burn (1h, 5%), web 5xx slow-burn (6h, 2%), Celery failure spike (15min, 10+), browser JS errors (1h, 50+), `/healthz/` flapping, provisioning daily digest. Three SLO envelopes encoded (web availability 99.5%, latency p95 < 800ms, background-job success 99%). `/healthz/` extended with best-effort Redis (cache) liveness — degraded does not fail the response so load-balancer probes stay reliable, but operators see `"cache": "degraded"` in payload. |
| 10.A | `aaea04ff` | 2026-05-11 | Accessibility wave 1. Color tokens darkened from slate-400 → slate-500 on 4 light-surface variables (`--footer-text-muted`, `--chart-axis-muted`, `--admin-content-text-muted`, `--portal-text-muted`) for WCAG 1.4.3 AA contrast (4.5:1). New `--header-brand-fg = #f8fafc` + `--header-brand-overlay` for indigo→emerald gradient legibility. `.btn` default rule now carries `min-height/min-width: 24px` (WCAG 2.5.8 floor) on all viewports, not just mobile. `base.html` line 127 — `role="banner"` removed from `<nav>` and replaced with descriptive `aria-label` (banner role is invalid on nav anyway). `control_plane_base.html` desktop sidebar `<aside>` now carries `aria-label="Control plane navigation"`. `portal_base.html` resize separator now has `tabindex="0"`, `aria-orientation`, `aria-controls`, `aria-valuemin/max/now`, and a new `static/js/portal-resize-keyboard.js` adds Arrow/Home/End key handling (WCAG 2.1.1). New `apps/compliance/tests/test_a11y_axe_smoke.py` — opt-in (`RUN_A11Y_TESTS=1`) axe-core LiveServerTestCase scanning `/` for serious/critical violations. |
| 9.A | `52afb670` | 2026-05-11 | Audit-log UI wave 1. 5 missing compliance report templates created (audit_trail_report.html / data_access_report.html / permission_overview.html / integrity_check_report.html / anomaly_detection.html) — views in `apps/compliance/views_reporting.py` no longer 500. New `apps/compliance/decorators.py:audit_pii_view` decorator emits `AuditLog.Action.VIEW` rows on 2xx GETs (closes FERPA read-access gap). New `compliance_tags.recent_activity_for` template tag + `templates/compliance/partials/recent_activity_panel.html` drop-in drill-down panel; wired into `templates/people/backend_student_detail.html` (StudentProfile) and `templates/finance/invoice_detail.html` (Invoice). Evaluation drill-down deferred to 9.B (no canonical evaluation detail template — needs view discovery first). |
| 8.A | `8facb3d5` | 2026-05-11 | Importer rebuild — wave 1. XLSX/.xlsm upload support via openpyxl with magic-byte/extension branching in new `_read_uploaded_table()` helper; legacy `.xls` rejected with a clear message. Hard-coded 500-row cap replaced by `settings.IMPORT_MAX_ROWS` (default 10000, clamped 100-100000). 6 new MIGRATION_TYPES (teachers, guardians, roster, attendance, fees, payments) with full target_fields + required arrays. New `apps/accounts/migration_importers.py` (~430 lines) with functional importers for teachers (User+TeacherProfile+SchoolMembership), guardians (User+SchoolMembership+StudentGuardian × N students), roster (Classroom+Subject+Term, SubjectAssignment deferred), and attendance (Attendance + classroom auto-resolution); fees and payments are row-count scaffolds pending pass 8.B. One-click vendor auto-detect: when `schema_fingerprint.suggest_profiles_from_headers` returns ≥0.8 confidence the wizard auto-applies the profile and tells the user. New `seed_migration_profiles` entries for teachers_import / guardians_import / roster_import / payments_import; finance_import and attendance_import stubs now have real target_fields. Wizard view also widened to surface ALL generic profiles (not just students/grades) and to read `config.migration_type` so non-Domain-enum types route correctly. |
| 7 | `7b0fb960` | 2026-05-11 | Onboarding showstoppers — magic-link auto-login at `verify_signup` (no more password trap on `set_unusable_password()` admins) routes to `studio_os:launch`; DNS auto-provision via Cloudflare/Route53 providers (`apps/schools/dns_providers/{base,cloudflare,route53}.py`, opt-in by `DNS_PROVIDER` setting) called from `_do_provision`, reachability verified through `dns_verification.hostname_resolves`; 8 marketing CTAs rerouted from `signup_school` → `onboard_wizard`; BlueprintPack picker added as wizard step 1.5 (ranked by country relevance, applied through `apply_blueprint_pack` post-provision); "Start with sample data" toggle in step 3 seeds demo.admin/teacher/parent via `seed_demo_users_for_school` | pending |

**Aggregate (passes 4-7):** ~60 files, ~+2,100/−260, 4 new migrations, 4 strategy docs.

---

## Passes pending (queued in `COMPETITIVE_PARITY_ROADMAP.md`)

Sequenced in priority order. Effort estimates are realistic engineering weeks.

| # | Pass | Effort | What it unblocks |
|---|---|---|---|
| **8.D** | Importer rebuild — Fees/Payments full persistence to Invoice + Payment honoring Part F 25.1 invoice immutability + currency normalization (needs a dedicated audit window), SubjectAssignment auto-create inside the roster importer (needs a Specialty-resolution helper that the platform doesn't currently expose), CSV-export error report from the migration_job snapshot | 1-2 wk | Schools migrating fee schedules + historical payments from PowerSchool / Skyward |
| **9.D** | Audit-log UI follow-up — evaluation drill-down once the canonical detail view lands (still no canonical evaluation detail template); apply `@audit_pii_view` to the top 5 PII detail views (student / invoice / disclosure / evaluation / report-card); Celery beat job `compliance.tasks.mark_sla_breaches` to populate `sla_breach_at` automatically | 2-3 days | SOC 2 audit window readiness |
| **10.D** (operator task) | Run `inject_table_captions --write` against each `templates/*` subdirectory in turn (analytics → finance → attendance → evals → portal → admin), template author reviews each batch's diff before merge. Wire CI to run `RUN_A11Y_TESTS=1 pytest apps/compliance/tests/test_a11y_axe_smoke.py` on every PR. | 1-2 wk | US public-district sales (Section 508) hard requirement |
| **11.D** (ops-credentialed) | RUM via `@sentry/browser` (decision: CSP allowlist + CDN copy, or self-host vendored bundle); push `sentry/alerts.yml` rules to the live Sentry project via the Sentry API (needs a Sentry org auth token) | 2-3 days | Production incident MTTR |
| **12.D** (ops-credentialed) | Publish `runmycampus` to PyPI + `@runmycampus/sdk` to npm from `sdk/` (needs registry tokens), host the public reference at `docs.runmycampus.com` (needs DNS + hosting) | 1 wk | First external integrators; marketplace foundation |
| **13.D** (product + data work) | Real ML at-risk model in `apps/analytics/ml_inference.py` (training pipeline + features + offline eval — needs a tagged dataset), in-product hookup of `draft_parent_message` (teacher comms inbox) + `draft_report_card_comment` (report-card editor) using the `ai_draft_inline.html` partial, `seed_policy_documents` per-tenant scheduler that runs `ingest_policy_documents` on a Celery beat | Multi-quarter | 2026 ed-tech AI parity (Schoology, MagicSchool) |
| **14.D** (ops + product work) | Publisher dashboard UI on top of the `/api/v1/marketplace/submissions/` endpoint (screenshot upload, version compat, revenue-share negotiation), sandbox tenant provisioning (per-app isolated tenant — needs ops VM strategy), tenant-facing `/admin/apps/` install/uninstall UI on top of AppInstallation, Stripe Connect onboarding (needs Stripe platform account), partners.runmycampus.com + certification + portal (needs DNS) | Multi-quarter | "AWS-of-education" positioning |

Also from [`MULTI_TENANT_GLOBAL_ROADMAP.md`](MULTI_TENANT_GLOBAL_ROADMAP.md):
- **Offline foundational** (4-6 weeks): SMSOfflineDB read-binding (currently dead code), POST `/api/attendance/` endpoint, grades in SW write list, fresh-CSRF-on-replay, installable PWA icons.
- **Education-system rebuild** (multi-quarter): De-Cameroonize `evals.Evaluation`, `SpecialEducationPlan` + `FerpaDisclosureLog`, `Assignment` + `Submission` LMS spine, admissions pipeline upgrade, populate empty country policy_snapshots (WAEC/KCSE/CBSE/ACARA/IGCSE/IB are bare slugs today).

---

## Canonical docs map

| File | Purpose |
|---|---|
| [`STATE_OF_PLAY.md`](STATE_OF_PLAY.md) | This file — start here in any new session |
| [`COMPETITIVE_PARITY_ROADMAP.md`](COMPETITIVE_PARITY_ROADMAP.md) | Synthesis of 6 audits; sequences passes 7-14 |
| [`MULTI_TENANT_GLOBAL_ROADMAP.md`](MULTI_TENANT_GLOBAL_ROADMAP.md) | Offline foundational + education-system rebuild |
| [`SECURITY.md`](SECURITY.md) | SOC 2 / ISO 27001 / PCI-DSS / FERPA / GDPR posture |
| [`OBSERVABILITY.md`](OBSERVABILITY.md) | Sentry + Prometheus + JSON logs + SLO targets |
| [`ECOSYSTEM_STRATEGY.md`](ECOSYSTEM_STRATEGY.md) | 5-phase 18-month marketplace + dev portal plan |
| [`CONFIGURABILITY.md`](CONFIGURABILITY.md) | 7-layer config decision tree |
| [`ACCESSIBILITY_WCAG.md`](ACCESSIBILITY_WCAG.md) | Pre-existing a11y status doc (a11y audit findings supplement it) |

---

## Push status

As of 2026-05-11 (post-pass-9.A), HEAD is on the `pass-7-marketing-bugs` feature
branch, **6 commits ahead of `origin/main`** (`9f3e9a1a`):

- `52afb670` — pass 9.A (audit-log UI wave 1)
- `88ed25fd` — pass 7.B (marketing-surface bug fixes from 2026-05-10 walkthrough)
- `7af09a94` — docs: record pass-8.A hash
- `8facb3d5` — pass 8.A (importer rebuild — wave 1)
- `0f3c1f37` — docs: record pass-7 hash
- `7b0fb960` — pass 7 (onboarding showstoppers)

Not yet deployed to manager.runmycampus.com.

Claude Code's auto-mode classifier blocks `git push origin main` directly
(treats it as bypassing PR review). To deploy:
1. Run `git push origin main` manually, OR
2. Add `Bash(git push origin main)` permission rule in `.claude/settings.json`, OR
3. Switch to a PR-based workflow (feature branch + `gh pr create`).

---

## Architecture quick facts

- **Stack:** Django 5.x, DRF, Celery + Redis, Postgres with RLS, WhiteNoise, django-tenants (optional schema-per-tenant via `USE_DJANGO_TENANTS=1`), GraphQL via graphene-django, Sentry, Prometheus, drf-spectacular (as of pass 6).
- **Active code lives in:** `beta/school-management-system/`. The top-level `Live Code/` folder is empty (legacy).
- **Multi-tenant resolution:** by host (subdomain) or session; tenant scope enforced at middleware + ORM + Postgres RLS (`apps/siteconfig/migrations/0129_rls_policy_default_deny.py`).
- **Deployment:** Render, single region (Oregon default; EU on request). Cross-region backup is a known SOC 2 pre-audit gap.
- **MFA:** django-otp TOTP + WebAuthn passkeys. Argon2 password hashing.
- **AI:** services/ai_gateway.py (771 lines) fronts Ollama → vLLM → LiteLLM → rules fallback. No direct Anthropic/OpenAI integration today (planned in pass 13).
- **Offline:** SW + IndexedDB outbox exist; read-side mirror is dead code (templates don't call `SMSOfflineDB`). `enable_offline_mode` defaults `null` per tenant.
- **Onboarding wizard:** `/onboard/` 3-step flow + `setup_studio` 8-step post-signup checklist. Two showstopper bugs in current flow (see pass 7).

---

## Conventions

- **No hardcoded values:** Per [`CONFIGURABILITY.md`](CONFIGURABILITY.md), every value must resolve through one of: tenant config (SiteSettings) / env var (settings.py) / user prefs (UserPreferences) / Django i18n / feature flag / DB fixture / platform constant.
- **No multi-tenant residue:** No Cameroon-, XAF-, FCFA-, `+237`-, DD/MM/YYYY-, or "Gilead"-specific assumptions in code paths. See passes 4 and 5 for the cleanup history.
- **Commits:** Conventional pass naming (`pass N: <scope>` or `refactor(config): pass N — <scope>`). Co-authored-by Claude in the commit body.
- **Style:** ruff via pre-commit. Tabs/spaces match existing files. No emoji in code or docs unless explicitly requested.
- **i18n:** All user-facing strings wrapped in `{% trans %}` / `gettext` / `gettext_lazy`. ~340 strings still pending wrap (see configurability contract memory).
- **A11y:** WCAG 2.2 AA targets. Skip-links + landmarks + focus-visible already in place; finish work in pass 10.

---

## Where to look if you need to ...

| ... | Path |
|---|---|
| Add a new currency | `apps/registries/currency.py` (symbol table); `settings.PLATFORM_DEFAULT_CURRENCY` |
| Add a new country/region | `RegionConfig` model + `seed_global_regions` mgmt command; `apps/siteconfig/education_profile_engine.py` for academic-year hemisphere logic |
| Add a new grading scale | `apps/evals/grading.py` `GRADING_SCALES` + `RegionConfig.GRADING_SCALE_CHOICES` |
| Add a new education system / board | `Certification.Board` enum in `apps/academics/models.py:345` + populated `policy_snapshot` in `seed_blueprint_policy_packs.py` |
| Touch the brand cascade | `static/css/design-tokens.css` (canonical foundation, ~100KB) |
| Wire a new audit-logged action | `AuditLog.Action` enum in `apps/compliance/models_audit.py:22` + signal/decorator |
| Wire a new webhook event | `WebhookSubscription.event_types` + `DomainEvent` emit in the relevant service |
| Add an API endpoint | `apps/api/urls_v1.py` (versioned) — drf-spectacular auto-generates OpenAPI |
| Read the multi-tenant config contract | `docs/CONFIGURABILITY.md` |
| Read the security posture | `docs/SECURITY.md` |
| Read the next-step roadmap | `docs/COMPETITIVE_PARITY_ROADMAP.md` |

---

## How to update this file

After each major commit or pass, append a row to the "Passes shipped" table with
the commit hash, date, and a 1-line scope summary. After each completed pass that
was in "Passes pending", move it to "Passes shipped" and re-rank what's next.

Keep this file under 250 lines; if it grows, factor specifics into the matching
roadmap doc and keep this as the index/orientation.
