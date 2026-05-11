# State of Play

**Last updated:** 2026-05-11 (passes 7, 8.A, 9.A, 10.A, 11.A, 12.A, 13.A, 14.A closed; B-waves pending)
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
| 14.A | (pending push) | 2026-05-11 | Marketplace wave 1 — first concrete slice. Surprise finding: all 4 roadmap models (MarketplaceApp / AppInstallation / MarketplaceReview / TenantMarketplaceSubscription) **already exist** in `apps/marketplace/models.py` from prior work, plus 11 supporting models (PublisherOrganization, AppPermissionScope, MarketplaceListing, AppScope, ScopeGrant, AppBillingLedger, PlatformMarketplaceEarning, AppAuditLog, MarketplaceMonetizationLedgerEntry, AppVersionCompat, CapabilityRegistry). Scope of pass 14.A narrowed to the actual gaps: code-backed scope vocabulary + public catalog endpoints. New `apps/marketplace/scopes_catalog.py:MARKETPLACE_SCOPES` declares 15 OAuth2-style scopes (students/guardians/attendance/grades/finance/webhooks/files/users/tenant × read/write/admin) with `domain`, `access`, `sensitivity` (mirrors AuditLog.Sensitivity), and approval-ready descriptions for the install dialog. New `apps/api/views_marketplace_catalog.py` exposes two public endpoints: `GET /api/v1/marketplace/apps/` (lists active apps with manifest projection, optional `?kind=` filter, 200-item cap) and `GET /api/v1/marketplace/scopes/` (full scope vocabulary). Both AllowAny, 5-minute Cache-Control. `SPECTACULAR_SETTINGS["TAGS"]` extended with `"Marketplace"` so the public docs render the section. |
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
| **8.B** | Importer rebuild — wave 2: async Celery task wrapper with progress polling, downloadable error CSV (reuse `import_job_monitor.html` pattern), full Fees/Payments persistence to Invoice+Payment models, SubjectAssignment auto-create inside roster importer, vendor schema_hints for FACTS / Skyward / Alma to bring them to auto-detect parity with PowerSchool/Blackbaud/Veracross/InfiniteCampus | 2-3 wk | Full PowerSchool migration in <1 hour for 5k-student schools |
| **9.B** | Audit-log UI wave 2 — ExportJob / EraseRequest queue page with approve/reject/complete workflow + SLA tracking, FerpaDisclosure model + admin UI (US K-12 unlock), evaluation drill-down once the canonical detail view lands, sample @audit_pii_view applications on the top 5 PII detail views | 3-5 days | SOC 2 audit window; FERPA US K-12 public unlock |
| **10.B** | Accessibility wave 2 — bulk-script `<caption>` insertion across ~333 data tables (analytics/finance/attendance/evals) with sensible defaults + human review, widen axe-selenium scan from `/` to the 10 highest-traffic authenticated templates with fixtures, gate CI on `RUN_A11Y_TESTS=1` once Chromium runners are wired, optional dark-surface mode for slate-500 if any sidebar text regresses | 2-3 wk | US public-district sales (Section 508) hard requirement |
| **11.B** | Observability wave 2 — Service Worker error forwarding to Sentry-Browser, RUM via @sentry/browser on the portal shell, custom traces around attendance.submit / grade.publish / parent dashboard render, SLO burn-rate alert rules promoted from `sentry/alerts.yml` to the live Sentry project | 3-5 days | Production incident MTTR; SLO enforcement |
| **12.B** | API maturity wave 2 — global `IdempotencyKeyMiddleware` for `/api/v1/` POST/PATCH/DELETE (cache-backed, 24h dedupe), publish `runmycampus` to PyPI + `@runmycampus/sdk` to npm from `sdk/`, host the public reference at `docs.runmycampus.com`, dynamic per-tenant CORS allowlist from SiteConfig | 2-3 wk | First external integrators; marketplace foundation |
| **13.B** | AI differentiation wave 2 — replace `pct_absent * 0.4 + 20` (and grade-only baseline) with a real ML at-risk model (`apps/analytics/ml_inference.py`), teacher communication assistant on the draft-message-and-approve pattern from `narrative_feedback.py`, policy + handbook RAG via existing `AIEmbeddingStore` with a policy-PDF ingestion task, report-card AI (one LLM call per term per class), Anthropic budget controls + per-tenant spend caps | Multi-quarter | 2026 ed-tech AI parity (Schoology, MagicSchool) |
| **14.B** | Marketplace + partner program wave 2 — `seed_marketplace_scopes` mgmt command to upsert AppPermissionScope rows from the catalog, app submission flow + automated security/compliance checks, sandbox tenant infrastructure for app developers, tenant-facing `/admin/apps/` install/uninstall UI on top of the existing AppInstallation model, Stripe Connect revenue share wiring through PlatformMarketplaceEarning, partners.runmycampus.com + certification + portal | Multi-quarter | "AWS-of-education" positioning |

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
