# Coverage audit — 2026-05-14 (wave NS-6)

**Purpose.** End-to-end audit of waves NS-1 through NS-5, verifying every claim in every SOT against actual code. Drift found, drift fixed. This is the close-out for the 2026-05-14 series.

**Scope.** Five completed waves:

| Wave | SW version | Headline |
|---|---|---|
| NS-1 | `sms-v2.9.0-north-star-closeout-2026-05-14` | Roadmap drift correction, TODOs, bounded-context audit, WCAG contrast tightening, security harness, ML scaffold, AI media pipeline, model-relocation runbook, doc graveyard pass 1 |
| NS-2 | `sms-v2.10.0-ai-surfaces-closeout-2026-05-14` | NEW [`AI_PLATFORM_WIDE_STATUS_2026_05_14.md`](AI_PLATFORM_WIDE_STATUS_2026_05_14.md), ⌘K Ask AI fallback, RAG ingest admin endpoint |
| NS-3 | `sms-v2.11.0-everything-closeout-2026-05-14` | drf-spectacular cleanup, stone-theme WCAG, axe-CI 13-template matrix, [tenant-isolation scanner](TENANT_ISOLATION_SCANNER.md) + baseline, [SLO module](OBSERVABILITY_SLO_CODE.md) + burn-rate, marketplace/blueprint seed expansion, doc graveyard wave 2, bandit + pip-audit baselines |
| NS-4 | `sms-v2.12.0-seed-deep-expansion-2026-05-14` | [Deep platform-wide catalog growth](SEED_EXPANSION_2026_05_14.md): 73 marketplace apps, 50 scopes, 55 capabilities, 56 workflow packs, 38 dashboard packs, 34 policy bundles, 29 notification templates, 12 SLOs |
| NS-5 | `sms-v2.13.0-deferred-closure-2026-05-14` | Closed all 4 deferred items: `CommunicationTemplate` model + migration + resolver + admin + tests, onboarding step catalog (25 × 8), DynamicFieldDefinition recipes (87 × 12), tenant-isolation burn-down (769→742) + allowlist mechanism |

This wave (**NS-6**) is the audit + drift correction pass. SW bumped to `sms-v2.14.0-coverage-sweep-2026-05-14`.

---

## Verification matrix — every SOT claim against code

### A. Headline counts (all 10 verified by AST count)

| Surface | SOT claim | Code | Module |
|---|---:|---:|---|
| Marketplace apps | 73 | **73** | `apps/marketplace/management/commands/seed_marketplace_apps.py` |
| OAuth2 scopes | 50 | **50** | `apps/marketplace/scopes_catalog.py` |
| Capability registry | 55 | **55** | `apps/marketplace/management/commands/seed_capability_registry.py` |
| Workflow packs | 56 | **56** | `apps/siteconfig/management/commands/seed_workflow_dashboard_packs.py` |
| Dashboard packs | 38 | **38** | (same file) |
| Blueprint packs | 33 | **33** | `apps/policies/management/commands/seed_blueprint_policy_packs.py` (8 base + 7 regional + 18 extra) |
| Policy bundles | 34 | **34** | (same file: 10 base + 24 extra) |
| Notification templates | 29 | **29** | `apps/communication/template_catalog.py` |
| Onboarding steps | 25 | **25** | `apps/siteconfig/onboarding_step_catalog.py` |
| Onboarding blueprints | 8 | **8** | (same file, `STEPS_BY_BLUEPRINT_PACK`) |
| DynamicField recipes | 87 | **87** | `apps/metadata/management/commands/seed_dynamic_field_recipes.py` |
| Canonical SLOs | 12 | **12** | `apps/observability/slo.py` |

**Status:** all 12 surfaces match.

### B. Migrations vs models

| Migration | Claim | Verified |
|---|---|---|
| `apps/communication/migrations/0019_communicationtemplate.py` | Model fields = `school, key, subject_template, body_template, channels, audience, sensitivity, is_active, locale, notes, created_at, updated_at` | **MATCH** (12 fields, including school FK) |

### C. URL routing

| Route | SOT claim | Verified |
|---|---|---|
| `/api/ai/health/` | Wired in 4 URL configs | **OK** in `config/urls.py:451`, `config/tenant_urls.py:331`, `config/manager_urls.py:425`, `config/public_urls.py:100` |
| `/api/ai-copilot/audit/` | Staff-only feed | **OK** in `config/urls.py:448`, `config/tenant_urls.py:330` |
| `/siteconfig/console/ai/rag/ingest/` | NS-2 staff endpoint | **OK** in `apps/siteconfig/urls.py:437` (`siteconfig:ai_rag_ingest_policy_docs`) |

### D. CI workflows

| Workflow | Claim | Verified |
|---|---|---|
| `.github/workflows/security-self-audit.yml` | NS-1: weekly + per-PR security harness | **OK** |
| `.github/workflows/tenant-isolation-scan.yml` | NS-3: per-PR scanner gate | **OK** |
| `.github/workflows/a11y-axe.yml` | NS-3: 13 templates (was 9) | **OK** — header comment lists all 13 |

### E. SLO ↔ Sentry transaction alignment

`apps/observability/slo.py` declares 12 SLOs with `sentry_transactions=(...)`. Each named transaction must be wrapped somewhere. Audit + fix:

| SLO | Transaction name | Wrapped at | Status (before NS-6) |
|---|---|---|---|
| `web.availability` | `http.server` | Auto-captured by Sentry Django integration | OK |
| `attendance.submit` | `attendance.submit` | `apps/academics/api_views.py:160` `AttendanceViewSet.create` | OK |
| `grade.entry` | `grade.entry` | `apps/academics/api_views.py:562` `GradeViewSet.create` | OK |
| `parent.dashboard` | `parent.dashboard.render` | `apps/portal/views_parent.py:636` `parent_dashboard` | OK |
| `migration.bundle_apply` | `migration.bundle_apply` | `apps/migration_cloud/orchestrator.py` `apply_bundle` | OK |
| `ai.gateway.latency` | `ai.gateway.invoke` | `services/ai_gateway.py` `invoke` | **WIRED in NS-6** (was missing) |
| `webhook.delivery` | `webhook.deliver` | `apps/events/webhooks.py` `deliver_webhook_delivery` | **WIRED in NS-6** (was missing) |
| `sync.conflict_pending` | `sync.delta_apply` | `apps/api/sync_services.py` `apply_changes` | **WIRED in NS-6** (was missing) |
| `finance.invoice_create` | `finance.invoice.create` | `apps/finance/api_views.py:177` | OK |
| `finance.payment_record` | `finance.payment.record` | `apps/finance/api_views.py:373` | OK |
| `auth.login` | `auth.login` | `apps/accounts/views.py:2745` `login_view` | **WIRED in NS-6** (was missing) |
| `api.public_config` | `http.server` | Auto-captured | OK |

**4 transactions wired in this wave.** All 12 SLOs now have a real backing transaction.

Pattern adopted:
- Views: `@trace_view("name")` from `apps/observability/tracing.py`
- Tasks / service functions: `start_named_transaction("name") / set_transaction_status / finish_transaction` (also from `apps/observability/tracing.py`). Helpers extracted from the migration_cloud-specific pattern in NS-3.

### F. Tenant-isolation scanner

| Claim | Verified |
|---|---|
| Baseline finding count = 742 | **OK** (regenerated this wave; CommunicationTemplate now in tenant model count: 195 → +1 because school FK on the new model) |
| `# tenant-isolation-allow: <reason>` comment respected | **OK** (NS-5 mechanism intact) |
| `school__isnull` / `school_id__isnull` recognized as safe | **OK** |
| `.update()` / `.delete()` flagged on tenant models | **OK** (added NS-4) |

### G. Cross-document link audit

15 SOT docs scanned; 0 broken code-path links; 1 broken markdown link in `AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md` → `MARKETING_EDITORIAL_DIRECTION.md` (pre-existing drift, not from these waves; flagged for the marketing-doc owner).

### H. Created-files existence

All **28 files** created across NS-1 through NS-5 are present in the repo (see audit script in `scripts/scan_tenant_queryset_safety.py` for analogous pattern; full list in NS-1/NS-5 docket entries).

### I. Orphan check (created but unwired)

**Two orphans found and fixed in this wave:**

1. `apps/siteconfig/onboarding_step_catalog.py` was referenced only by its own SOT and the docket — no caller in app code. **Fix:** wired into `apps/platform_runtime/onboarding.py:get_onboarding_steps` to enrich each row with catalog metadata (label, description, audience, estimated_minutes, deep_link), and added a new `get_blueprint_recommended_onboarding_steps(blueprint_slug)` helper for wizard / setup-assistant views.

2. `apps/metadata/management/commands/seed_dynamic_field_recipes.py` was not in the canonical platform seed orchestrator. **Fix:** appended `("seed_dynamic_field_recipes", "Platform-wide DynamicFieldDefinition recipes")` to `_PUBLIC_EXTRA_STEPS` in `apps/siteconfig/management/commands/seed_platform_complete.py`. Now runs as part of `python manage.py seed_platform_complete`.

### J. Documentation hierarchy (15 SOTs)

The full SOT graph after NS-1 through NS-6:

- **Top-level state:** [`STATE_OF_PLATFORM_2026_05_14.md`](STATE_OF_PLATFORM_2026_05_14.md), [`COMPETITIVE_PARITY_ROADMAP.md`](COMPETITIVE_PARITY_ROADMAP.md), [`CSS_RETIREMENT_DOCKET.md`](CSS_RETIREMENT_DOCKET.md)
- **AI:** [`AI_PLATFORM_WIDE_STATUS_2026_05_14.md`](AI_PLATFORM_WIDE_STATUS_2026_05_14.md), [`AI_DOMAIN_ASSISTANT_REGISTRY.md`](AI_DOMAIN_ASSISTANT_REGISTRY.md), [`AI_surface_audit.md`](AI_surface_audit.md), [`AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md`](AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md), [`ML_AT_RISK_TRAINING.md`](ML_AT_RISK_TRAINING.md)
- **Security & isolation:** [`PENTEST_SOW_2026_05_14.md`](PENTEST_SOW_2026_05_14.md), [`TENANT_ISOLATION_SCANNER.md`](TENANT_ISOLATION_SCANNER.md), [`MODEL_RELOCATION_RUNBOOK.md`](MODEL_RELOCATION_RUNBOOK.md), [`BOUNDED_CONTEXT_AUDIT_2026_05_14.md`](BOUNDED_CONTEXT_AUDIT_2026_05_14.md)
- **Observability:** [`OBSERVABILITY_SLO_CODE.md`](OBSERVABILITY_SLO_CODE.md)
- **Accessibility:** [`CONTRAST_AUDIT_2026_05_14.md`](CONTRAST_AUDIT_2026_05_14.md)
- **Platform expansion:** [`SEED_EXPANSION_2026_05_14.md`](SEED_EXPANSION_2026_05_14.md), this audit doc

---

## What changed in this wave (NS-6)

| # | Track | Artifact |
|---|---|---|
| 1 | SLO ↔ transaction alignment | 4 missing Sentry transactions wired: `services/ai_gateway.py:invoke` (`ai.gateway.invoke`), `apps/events/webhooks.py:deliver_webhook_delivery` (`webhook.deliver`), `apps/api/sync_services.py:apply_changes` (`sync.delta_apply`), `apps/accounts/views.py:login_view` (`auth.login`) |
| 2 | Tracing helper extraction | Refactored `_start_named_transaction` / `_txn_set_status` / `_txn_finish` from `migration_cloud/orchestrator.py` into shared `apps/observability/tracing.py` exports (`start_named_transaction`, `set_transaction_status`, `finish_transaction`). Migration_cloud now consumes the shared helpers. |
| 3 | Orphan wiring — onboarding | `apps/platform_runtime/onboarding.py:get_onboarding_steps` now enriches each row with catalog metadata (label/description/audience/estimated_minutes/deep_link). New helper `get_blueprint_recommended_onboarding_steps(blueprint_slug)`. |
| 4 | Orphan wiring — dynfield seed | `seed_dynamic_field_recipes` added to `_PUBLIC_EXTRA_STEPS` in `seed_platform_complete.py`. |
| 5 | Audit doc | This file. |
| 6 | Wave close | SW bump to `sms-v2.14.0-coverage-sweep-2026-05-14`, docket entry, MEMORY.md + standalone memory file. |

## Net result after waves NS-1 through NS-6

- Every SOT count claim verified.
- Every cross-doc link valid (1 pre-existing broken link flagged for marketing-doc owner).
- Every created file present and (now) wired to a caller.
- Every SLO has a real backing Sentry transaction.
- Every CI workflow declared in docs is on disk.
- Every URL declared in docs is wired in `urls.py`.

The 2026-05-14 series can be closed.
