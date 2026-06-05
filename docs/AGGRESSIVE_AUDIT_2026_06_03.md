# Aggressive Platform Audit — 2026-06-03

Multi-perspective audit (security, reliability/SRE, architecture/dead-code) +
static analysis (`ruff` F-rules) of `beta/school-management-system/`. Driven by
the recurring "nothing works" symptoms (no activation email, provisioning,
offboarding). Three specialist sub-agents + a static undefined-name/dead-code
sweep. **All fixes below verified: `manage.py check` clean, `ruff` re-run,
every touched file AST-parses.**

## A. FIXED — runtime crash bugs (undefined names → `NameError`/`UnboundLocalError`)

Same bug class as the earlier provisioning `resolve_profile_for_school` crash:
a name used at runtime but never imported/defined. `ruff --select F` found 20
F821 + 1 F823; after excluding harmless string annotations, these were real:

| # | File | Bug | Trigger / impact |
|---|------|-----|------------------|
| 1 | `apps/finance/services.py` | `logger` used but never defined | NameError on the invalid-decimal-setting path (finance) |
| 2 | `apps/siteconfig/views.py` | `except (DatabaseError, OperationalError, …)` — neither imported | The `except` itself raises NameError → grading-scale error handling broken |
| 3 | `apps/portal/views_documents.py` | `except NoReverseMatch` not imported | Documents view crashes if a URL name is missing |
| 4 | `apps/schools/domain_sync.py` | `log_exception_with_context` not imported | Domain-sync error path crashes instead of logging |
| 5 | `apps/reports/management/commands/generate_regional_reports.py` | `smtplib` used at module top, not imported | **Import-time crash** — the command can't run at all |
| 6 | `apps/payroll/management/commands/run_payroll_cycle.py` | `period_start_str`/`period_end_str` undefined in `except` | Payroll-failure handler crashes (masks the real error) |
| 7 | `apps/evals/ocr.py` | `_EVALS_OCR_PARSE_ROW_ERRORS` never defined | OCR per-row `except` raises NameError |
| 8 | `apps/evals/models.py` | `_EVALS_MODEL_SAVE_FINAL_SCORE_ERRORS` / `_NORMALIZED_ERRORS` never defined | `Evaluation.save()` error path crashes (grades) |
| 9 | `apps/migration_cloud/landers/guardian_lander.py` | `external_id` undefined (should be `student_external_id`) | Caught by a broad `except` → **every guardian silently quarantined** during migration |
| 10 | `apps/accounts/mfa_setup_flow.py` | `_` (gettext) shadowed by a later local `_` assignment → `UnboundLocalError` | **MFA enablement crashes** at the success/error messages (security-relevant) |

The 3 remaining `ruff` F821 hits (`import_services.py:436`, `middleware.py:588`,
`models_support.py:848`) are **string forward-ref annotations** (never evaluated
at runtime) — not crashes; left as-is.

## B. FIXED — shadowing / duplicate-definition bug

| File | Bug | Impact |
|------|-----|--------|
| `apps/evals/importers.py` + `apps/accounts/views_migration.py` | Two `apply_import` defs (preview-based + csv-based); the 2nd silently shadowed the 1st | The **migration grade-import** path passed a `GradeImportPreview` into the csv-rows function → broken. Fixed by renaming the preview one to `apply_import_from_preview` and updating the caller. |

## C. FIXED — CRITICAL broker-down crash class (free-tier "nothing works")

On the free tier there is often **no Celery broker**, and
`CELERY_TASK_ALWAYS_EAGER` is only set under tests. So `.delay()` raises
`kombu.exceptions.OperationalError` — which is **not** a `DatabaseError`, so the
signal handlers' `except` tuples missed it. It then propagated out of the
`post_save` signal and **rolled back the business write**.

| File | Fix |
|------|-----|
| `apps/platform_runtime/event_bus.py` | Wrapped the webhook-enqueue `.delay()` loop in try/except. Deliveries are already persisted PENDING, so a broker outage no longer rolls back the **attendance-save / student-create** that triggered the event — they're retried later. |
| `apps/academics/signals.py`, `apps/people/signals.py` | Added `KombuOperationalError`, `ConnectionError`, `OSError` to the signal `except` tuples so EWS-recompute / student-created dispatch can't roll back their write when the broker is down. |

> Impact before fix: any tenant with ≥1 webhook subscription could not mark
> attendance or create students on the free tier (500 + rollback).

## D. FIXED — email diagnostic was misleadingly "HEALTHY"

`apps/schoolops/management/commands/test_email_health.py`: when run with
`--send-to` against a non-SMTP backend (console), it reported `[HEALTHY]`. Now a
live-send request against a backend that can't deliver is always `[CRITICAL]
non_smtp_backend` → verdict `[DEGRADED]`, `deliverable:false`. (This is why the
Render test "passed" while no mail was sent — the env vars weren't applied; see
§F.)

## E. FIXED — dead code removed (724 lines + 1 duplicate)

Each proven zero-reference (sub-agent AST scan + manual grep across
`.py`/`.html`/`.json`), `manage.py check` clean after removal:

- `apps/evals/advanced_evaluations.py` (~360) — "Phase 8" scaffold, imported nowhere
- `apps/evals/performance_optimization.py` (~250) — `@receiver`s in a module never imported (signals never connected)
- `apps/evals/stats.py` (49)
- ~~`apps/academics/fractional_capacity.py` (43)~~ **RESTORED 2026-06-05** — Phase 4E gate kernel; protected by `verify_global_operational_blind_spots --granular-ops` + `verify_poly_institution_governance_stack.py` (do not delete)
- `apps/finance/payment_dispute_local_copy.py` — orphaned copy
- `apps/schoolops/sms_templates.py` — removed a **verbatim duplicate** of `render_payment_received_sms` + its locale dict

## F. OPERATIONAL (your action on Render — not code)

- **`ProgrammingError: ...emaildeliveryevent... does not exist`** — confirmed NOT
  a missing migration (`makemigrations --check` is clean; the migration file
  exists). It's **migrate-not-applied on the live service**. Run
  `python manage.py migrate` on Render. Ensure the Pre-Deploy Command is set to
  `./scripts/release/render_predeploy.sh` so every deploy migrates.
- **Activation email** — `$EMAIL_BACKEND`/`$EMAIL_HOST` were **empty** on the
  running web service (confirmed via `echo`), so it fell back to the console
  backend. Set the Brevo `EMAIL_*` env vars on **both** web + worker and
  redeploy; verify with `test_email_health --send-to you@…`. See
  `docs/RENDER_EMAIL_SETUP.md`.

## G. RECOMMENDED (not auto-applied — need review / tests / are higher-risk)

Security agent: **no critical/high vulnerabilities** (mature codebase; prior
applicant-PII bug confirmed fixed; protocol endpoints auth via Bearer;
schema-per-tenant isolation; no injection/secret-logging). One defense-in-depth
nit: rate-limit `operator_invite_accept` POST.

Reliability agent (email reliability, free tier):
- **H2** `notify_low_meal_plan_balance.delay()` has no sync fallback → low-balance emails silently never send when broker is down. Mirror the `notification_intent` try-delay-then-sync pattern.
- **H3** `dispatch_notification_intent` returns `queued:True` when the broker is up but the worker is asleep (free-tier worker is a separate sleepy service) → mail never delivered. Prefer `send_transactional(async_send=True)` for transactional intents, or add a dead-letter sweep.
- **M1** `welcome_email.py` uses raw `EmailMessage.send()` — bypasses the hardened sender's timeout ceiling + audit row; route through `send_transactional`.
- **M2** `EmailDeliveryEvent.save()` does a wasted SELECT per insert (uuid PK makes the append-only guard always query); use `self._state.adding`.
- **M3** SendGrid webhook accepts unverified bounces (needs `pynacl` Ed25519); gate behind a flag until verified.
- **Global option:** set `CELERY_TASK_ALWAYS_EAGER = True` when `CELERY_BROKER_URL` is empty so every `.delay()` runs inline instead of raising (matches the settings docstring intent). Deferred — changes task-execution semantics platform-wide; needs a test pass first.

Architecture agent:
- **B023 latent bugs** — closures capturing a loop variable: `apps/accounts/views_certification.py:259,359,449`, `academics/management/commands/export_certification_pack.py:125`. Worth a targeted look.
- **C2** duplicated OAuth plumbing (`_record_audit`, `_retry_with_backoff`) across `lms_connector_d2l.py` / `lms_connector_schoology.py` — lift into `oauth_live_path_helpers.py` (low risk).
- **C3** circular-import smell — heavy function-level imports; worst on the hot path `schools/middleware.py` (46). Introduce `selectors.py` interfaces; one module at a time.
- **C4** god objects — `_marketing_context` (1,382 lines), `site_settings` context processor (887, runs every request), `backend_dashboard` (1,283). High blast radius; split behind snapshot tests.
- **Section B "likely dead, verify"** — ~250 zero-ref candidates that are plausibly dynamic (admin classes, signal handlers, templatetags, public service helpers, models-with-tables). NOT deleted — need a human glance / product confirmation; models need a migration decision.

## H. Round 2 — worked through the §G backlog (same session)

| Item | Outcome |
|------|---------|
| **B023** loop-closure "bugs" | **Verified FALSE POSITIVES** — all 9 are the `getattr(x, "method", lambda: …x…)()` idiom where the lambda is the getattr default, **invoked immediately** in-iteration. No fix needed (didn't blindly "fix" and churn them). |
| **M2** `EmailDeliveryEvent.save()` wasted SELECT | **FIXED** — now uses `self._state.adding` (zero queries) instead of a per-insert SELECT. |
| **H2** meal-balance notification no fallback | **FIXED** — `apps/schoolops/signals.py` now runs `notify_low_meal_plan_balance` inline when `.delay()` fails (broker down), idempotent via the 7-day cooldown. |
| **H3** notification-intent false `queued` when worker asleep | **FIXED** — `apps/schoolops/notification_intent.py` async path now uses the in-process daemon (`send_transactional(async_send=True)`) instead of a Celery task, so delivery no longer depends on the (free-tier, sleepy) worker. |
| **M1** route welcome_email via `send_transactional` | **SKIPPED (intentional)** — it changes the welcome email's MIME structure (plain body + html alt) and breaks the test pinning `content_subtype=="html"` + brand color in `msg.body`, for only a marginal gain (raw send already honors `EMAIL_TIMEOUT=10s`). Not worth the contract change. |
| **C2** OAuth plumbing dedup | **DEFERRED (intentional)** — pure cosmetic de-dup on the live OAuth outbound path (own 18+ smoke tests; one connector docstring says "duplicated by design"). No bug; not worth regression risk unsupervised. |

Round-2 verification: `ruff --select F` clean on all edited files; `manage.py check` clean; **email-infrastructure smokes 269/269** still green.

## I. Round 3 — dead-import cleanup + the M3 security fix

| Item | Outcome |
|------|---------|
| **F401 dead imports** | **15 removed** (apps/platform_runtime ×4, config/manager_* ×3, emis ×4, payment/admin, services ×2). Left `config/settings.py:3269-3297` (the `runtime_constants` re-export — verified load-bearing: `settings.DEFAULT_PAGE_SIZE` etc. used in 8 places; ruff false-positive) and `config/tenant_urls.py` `handler503` (deliberate). |
| **F811 redefinitions** | **2 cleaned** — `communication/forms_groups.py` redundant `User` import (shadowed by `get_user_model()`); `apicenter/views.py` duplicate `_` import (`gettext_lazy` shadowed by `gettext`). Left `siteconfig/models.py` `HolidayCalendar` (harmless dual re-export from two module paths; sensitive models file). |
| **M3 SendGrid webhook** | **FIXED PROPERLY** — implemented real **ECDSA P-256/SHA-256** verification (`_verify_sendgrid_ecdsa`) over `timestamp + body` against the operator's base64 public key, using the already-present `cryptography` lib (the old code's "Ed25519/pynacl" comment was wrong — SendGrid uses ECDSA). **Round-trip self-tested 5/5** (valid accepted; tampered body / wrong timestamp / garbage key / empty inputs all rejected). **Regression-proof:** a valid sig now returns verified=True; if verification can't run it falls back to today's accept-unverified UNLESS `SCHOOLOPS_SENDGRID_REQUIRE_VERIFIED_WEBHOOK=1` (then 401). So default behaviour is unchanged for existing users, but forged-bounce protection is now available and on by opt-in. |

## J. Remaining backlog — deliberately NOT auto-applied (need supervision / test scaffolding)

These are documented with a recommended approach; doing them unsupervised would be reckless:

- **God-object split** (`site_settings` context processor 887 lines, runs every request; `_marketing_context` 1,382; `backend_dashboard` 1,283) — **HIGH blast radius** (every page depends on `site_settings`' output dict). On inspection `site_settings` does a single cached settings read + dict assembly, not N queries, so there's no obvious safe targeted win. Needs context-snapshot tests before splitting. **Do with supervision + tests.**
- **Circular-import "smell"** (`schools/middleware.py` 46 function-level imports) — **low value** (Python caches imports in `sys.modules`, so deferred-import overhead after first call is ~a dict lookup) and **real cycle risk** to hoist. Not worth it; leave as-is.
- **CELERY_TASK_ALWAYS_EAGER when no broker** — a behavioural decision (would make deferred tasks like EWS-recompute run inline on attendance saves). Your call, not a silent flip. The targeted broker-guard fixes (§C, H2, H3) already prevent the crashes/silent-drops without changing task timing.
- **~250 "verify-dead" candidates** (admin classes, signal handlers, templatetags, public service helpers, models-with-tables) — need a human/product glance; models need a migration decision. Not safe to bulk-delete.
- **C2 OAuth plumbing dedup** — cosmetic; lives on the live OAuth path with its own smoke tests; one connector says "duplicated by design". Defer.

## Verification
- `ruff --select F` (final): F823 **0** (was 1), F811 **1** (was 9 — only the harmless HolidayCalendar re-export left), F821 runtime **0** (3 harmless annotations), F401 **32** (≈29 are the intentional settings re-export + deliberate skips; 15 real ones removed).
- `python manage.py check` → "System check identified no issues" after every round.
- Email-infrastructure smokes **269/269** green after Rounds 2 & 3.
- SendGrid ECDSA verifier self-test **5/5**.
