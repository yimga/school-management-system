# State of Play

**Last updated:** 2026-05-11 (pass 7 closed; pass 8.A closed — 8.B pending async/Celery)
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
| 8.A | `8facb3d5` | 2026-05-11 | Importer rebuild — wave 1. XLSX/.xlsm upload support via openpyxl with magic-byte/extension branching in new `_read_uploaded_table()` helper; legacy `.xls` rejected with a clear message. Hard-coded 500-row cap replaced by `settings.IMPORT_MAX_ROWS` (default 10000, clamped 100-100000). 6 new MIGRATION_TYPES (teachers, guardians, roster, attendance, fees, payments) with full target_fields + required arrays. New `apps/accounts/migration_importers.py` (~430 lines) with functional importers for teachers (User+TeacherProfile+SchoolMembership), guardians (User+SchoolMembership+StudentGuardian × N students), roster (Classroom+Subject+Term, SubjectAssignment deferred), and attendance (Attendance + classroom auto-resolution); fees and payments are row-count scaffolds pending pass 8.B. One-click vendor auto-detect: when `schema_fingerprint.suggest_profiles_from_headers` returns ≥0.8 confidence the wizard auto-applies the profile and tells the user. New `seed_migration_profiles` entries for teachers_import / guardians_import / roster_import / payments_import; finance_import and attendance_import stubs now have real target_fields. Wizard view also widened to surface ALL generic profiles (not just students/grades) and to read `config.migration_type` so non-Domain-enum types route correctly. |
| 7 | `7b0fb960` | 2026-05-11 | Onboarding showstoppers — magic-link auto-login at `verify_signup` (no more password trap on `set_unusable_password()` admins) routes to `studio_os:launch`; DNS auto-provision via Cloudflare/Route53 providers (`apps/schools/dns_providers/{base,cloudflare,route53}.py`, opt-in by `DNS_PROVIDER` setting) called from `_do_provision`, reachability verified through `dns_verification.hostname_resolves`; 8 marketing CTAs rerouted from `signup_school` → `onboard_wizard`; BlueprintPack picker added as wizard step 1.5 (ranked by country relevance, applied through `apply_blueprint_pack` post-provision); "Start with sample data" toggle in step 3 seeds demo.admin/teacher/parent via `seed_demo_users_for_school` | pending |

**Aggregate (passes 4-7):** ~60 files, ~+2,100/−260, 4 new migrations, 4 strategy docs.

---

## Passes pending (queued in `COMPETITIVE_PARITY_ROADMAP.md`)

Sequenced in priority order. Effort estimates are realistic engineering weeks.

| # | Pass | Effort | What it unblocks |
|---|---|---|---|
| **8.B** | Importer rebuild — wave 2: async Celery task wrapper with progress polling, downloadable error CSV (reuse `import_job_monitor.html` pattern), full Fees/Payments persistence to Invoice+Payment models, SubjectAssignment auto-create inside roster importer, vendor schema_hints for FACTS / Skyward / Alma to bring them to auto-detect parity with PowerSchool/Blackbaud/Veracross/InfiniteCampus | 2-3 wk | Full PowerSchool migration in <1 hour for 5k-student schools |
| **9** | Audit-log UI — 5 missing compliance report templates, per-record drill-down, PII-VIEW decorator, ExportJob/EraseRequest queue, FerpaDisclosure model | 1 wk | SOC 2 audit + US K-12 public unlock |
| **10** | Accessibility finish — table captions, contrast tokens, header gradient text, touch-target 24×24 floor, axe-selenium in CI | 2-3 wk | US public-district sales (Section 508) |
| **11** | Observability finish — `CeleryIntegration` in `sentry_sdk.init`, SW errors → Sentry-Browser, SLOs in code, RUM | 1-2 wk | Enterprise SLAs |
| **12** | API maturity — CORS, Idempotency-Key middleware, RFC 7807 errors, webhook event catalog, SDK PyPI/npm publish | 3-4 wk | First external integrators; marketplace foundation |
| **13** | AI differentiation — real ML risk + LLM explanation, teacher comms assistant, policy/handbook RAG, report-card AI, Anthropic Claude direct integration | Multi-quarter | 2026 ed-tech AI parity (Schoology, MagicSchool) |
| **14** | Marketplace + partner program — MarketplaceApp models, OAuth scopes, Stripe Connect revenue share, partners.runmycampus.com | Multi-quarter | "AWS-of-education" positioning |

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

As of 2026-05-11 (post-pass-8.A), HEAD is on the `pass-7-marketing-bugs` feature
branch, **3 commits ahead of `origin/main`** (`9f3e9a1a`):

- `8facb3d5` — pass 8.A (importer rebuild — wave 1)
- `0f3c1f37` — docs: record pass-7 commit hash
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
