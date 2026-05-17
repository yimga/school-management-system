# Operator Runbook — Where to Run Every Command

**Last updated:** 2026-05-16 (`sms-v3.6.2`)

This is the source-of-truth for every operator-facing management command on the
platform. The question this document answers: **"For each command, do I run it
locally, on the Render shell, or does it run on its own?"**

## TL;DR — the mental model

| Category | Who runs it | Where |
|---|---|---|
| **Predeploy** | Render, automatically | Nowhere (you do nothing) |
| **Celery beat** | Celery worker, automatically | Nowhere (you do nothing) |
| **One-time setup** | You, once per fresh DB | Render shell |
| **Verification / preflight** | You, before risky operations | Either local or Render shell — both work |
| **On-demand maintenance** | You, when there's a reason | Render shell (it has prod DB) |
| **Destructive** | You, with `--dry-run` first | Render shell, after explicit approval |
| **Developer / local-only** | You, during dev | Local — NEVER on Render |

The rule of thumb: **if it reads or writes the production DB, run it on Render shell.
If it builds local fixtures or diagrams, run it locally.**

---

## A. Predeploy — runs automatically on every Render deploy

You do nothing. These are wired into `scripts/release/render_predeploy.sh` and
gated by env vars. The deploy fails-loud if any of them fail.

```bash
# Order matters; this is what the predeploy script runs every time:
migrate_schemas --shared --noinput
ensure_tenant_schemas
migrate_schemas --tenant --noinput
migrate_schools_to_tenants
migrate_schemas --tenant --noinput              # 2nd pass for new schemas
backfill_schooldomain                            # if RUN_BACKFILL_SCHOOLDOMAIN=1 (default)
check_tenant_runtime                             # if RUN_STARTUP_SCHEMA_CHECK=1 (default)
seed_admin_dashboard_palettes
import_ui_config fixtures/ui_config.json         # if APPLY_UI_FIXTURE_ON_DEPLOY=1 (default)
normalize_ui_config
migrate_embeddings_to_pgvector --write-env-flag  # if RUN_PGVECTOR_MIGRATE=1 (default) AND Postgres
verify_pgvector_index --strict                   # if RUN_PGVECTOR_MIGRATE=1 (default) AND Postgres
integration_preflight                            # if RUN_INTEGRATION_PREFLIGHT=1 (default)
verify_residency_readiness --quiet               # if RUN_VERIFY_RESIDENCY_READINESS=1 (default 0)
seed_render_users
seed_demo --reset                                # if SEED_DEMO=1 (default 0)
bootstrap_platform_catalog [--all]               # if RUN_BOOTSTRAP_PLATFORM_CATALOG=1 (default 0)
collectstatic --noinput --clear
```

Env-var levers you control in the Render dashboard:
- `SKIP_DB_MIGRATIONS=1` — skip migrate (almost never want this)
- `RUN_PGVECTOR_MIGRATE=0` — skip pgvector path (for tenants pre-5k embeddings)
- `RUN_VERIFY_RESIDENCY_READINESS=1` — block deploy on residency misalignment
- `SEED_DEMO=1` — re-seed demo data on deploy (not for prod)
- `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` — re-seed registries on every deploy

---

## B. One-time setup — Render shell, once per fresh environment

Run once after the very first migration on a new DB. **Order matters** —
foundations first, then platform, then per-tenant.

Connect to Render shell:
```
Render Dashboard → web service → Shell tab → bash
```

Then run, in order:

```bash
# 1. Foundations (regions, country profiles, brand registry)
python manage.py seed_global_data --with-profiles

# 2. Platform-wide registries (terminology, providers, capabilities)
python manage.py seed_platform_registries

# 3. Marketplace + integrations catalogs
python manage.py seed_marketplace_apps
python manage.py seed_marketplace_scopes

# 4. Compliance + governance baseline
python manage.py seed_compliance_baseline

# 5. Finance defaults
python manage.py seed_finance_defaults

# 6. AI/ML registry — register the legacy heuristic baseline as PRODUCTION
python manage.py bootstrap_at_risk_registry

# 7. Digest recipients (after at least one ADMIN user exists)
python manage.py seed_default_digest_recipients

# 8. Grade prediction labels backfill (if grade history exists)
python manage.py seed_grade_prediction_labels_from_history

# 9. Superuser (only needed if seed_render_users didn't already make one)
python manage.py ensure_superuser --username admin

# 10. (Postgres only, requires DB superuser) pgvector extension
# This is the ONE thing you can't do from Python:
psql $DATABASE_URL -c "CREATE EXTENSION vector;"
# Next deploy's predeploy will auto-migrate JSON → pgvector + verify.
```

All commands above are idempotent — safe to re-run if you're unsure whether
they completed.

---

## C. Periodic — Celery beat handles automatically

You do nothing. Make sure `celery -A config worker` and `celery -A config beat`
are both running on Render (or any worker host). The schedule is in
`config/settings.py::CELERY_BEAT_SCHEDULE`.

**Currently scheduled (enabled by default):**
- `compute_nightly_grade_predictions` — daily
- `compute_nightly_risk` — daily
- `nightly_risk_factors` — daily
- `send_deadline_reminders` — daily
- `build_student_embeddings` — daily
- `send_payment_reminders` — hourly
- `process_event_outbox` — every 2 min
- `process_outbound_message_queue` — every 2 min
- `refresh_due_oauth_tokens` — every 5 min
- `renew_due_subscriptions` — hourly
- `fetch_due_mailboxes` — every 5 min

**Opt-in (set env flag to enable):**
- `ENABLE_RISK_DIGEST_BEAT=1` — `send_risk_digest_all` daily at 07:00
- `ENABLE_AT_RISK_DRIFT_WATCHDOG_BEAT=1` — `check_at_risk_drift` weekly
- `ENABLE_OLLAMA_MODEL_SYNC_BEAT=1` — `sync_ollama_models` weekly
- `ENABLE_BACKLOG_UNLOCK_BEAT=1` — `evaluate_backlog_unlocks` daily

---

## D. Verification / preflight — either local or Render shell

Read-only or near-read-only. Run anytime you want to know the state of things.

| Command | What it checks |
|---|---|
| `verify_ai_ml_readiness` | All AI/ML waves: schema, registry, production, inference, embeddings, digest, SHAP, pgvector, Celery |
| `verify_pgvector_index --strict` | pgvector extension + IVFFLAT index health (5 checks) |
| `verify_residency_readiness --quiet` | Data residency alignment; exit 1 if any tenant misaligned |
| `verify_data_residency` | Per-tenant residency report |
| `verify_platform_readiness` | High-level snapshot (waves, critical features, migrations) |
| `verify_rls_readiness` | Multi-tenant Row-Level Security policy validation |
| `verify_tenant_rls --school=<slug>` | Per-tenant RLS check |
| `verify_custom_domains` | DNS CNAME records for tenant custom domains |
| `verify_registry_coverage [--fix]` | Required entries in role/grade/status registries |
| `verify_region_coverage` | Regional config completeness (timezones, holidays, curricula) |
| `verify_access_control` | RBAC matrix vs. expected role/permission pairs |
| `verify_data_integrity [--fix]` | Orphan audit trails, missing FK, cardinality violations |
| `check_integrations [--json]` | Slack / email / SMS connectivity + auth |
| `check_payment_gateways` | Stripe / PayFast / MOZ API connectivity |
| `check_email_signing` | DKIM + SPF configuration for outbound mail |
| `synthetic_probe [--db] [--ready]` | External SRE health probe (healthz, ready, optional DB) |
| `db_health_check` | DB connectivity, replication lag, query baseline |
| `tenant_health_check [--school=<slug>]` | Per-tenant DNS / TLS / connectivity heartbeat |

Run locally if you just want a quick state check on a copy of the DB. Run on
Render shell if you need the live production state.

---

## E. On-demand maintenance — Render shell

These mutate the production DB. Use `--dry-run` first where supported.

| Command | When you'd run it |
|---|---|
| `rebuild_pgvector_index --vacuum` | Monthly maintenance; pgvector IVFFLAT recall degrades as data grows |
| `score_shadow_at_risk --school=<slug> --candidate-version=<v>` | Compare candidate ML artifact against production before promoting |
| `promote_at_risk_artifact <version> --promoted-by-username=<u> --min-roc-auc=0.75` | Flip a CANDIDATE artifact to PRODUCTION after shadow-scoring evidence |
| `retrain_at_risk_pipeline --dry-run` | Retrain ML model from historical data |
| `evaluate_at_risk_model var/model.joblib --json` | Test model on holdout set |
| `score_student_risk --school=<slug> --top=5 --reload` | Debug: shows score/band/inference-path/model_version per student |
| `build_student_embeddings` | Backfill missing student embeddings (also runs daily via beat) |
| `import_grades file.csv --dry-run` | Bulk import grades from CSV |
| `import_curriculum_nodes file.csv --dry-run` | Load curriculum from CSV |
| `claim_suspense_payment --school=<slug> --dry-run` | Allocate unidentified payments |
| `import_bank_statement bank.csv --dry-run` | Ingest bank statement |
| `export_config > backup.json` | Dump SiteSettings + RuntimeDefaults |
| `import_config backup.json --dry-run` | Restore SiteSettings + RuntimeDefaults |
| `export_ui_config > fixtures/ui_config.json` | Export current UI fixture |
| `migrate_dashboard_layouts --dry-run` | Transform deprecated dashboard layouts |
| `clone_region --from=US_CA --to=US_TX --dry-run` | Duplicate region config |
| `run_auto_promotion --dry-run --year=<y>` | Auto-advance students to next grade |
| `solve_timetable --school=<slug> --term=<t>` | Generate class timetable (CP-SAT) |
| `create_teacher_parent_accounts users.csv --dry-run` | Bulk-create users from CSV |
| `generate_compliance_reports --region=GDPR --school=<slug>` | On-demand compliance evidence |
| `export_compliance_evidence_pack --school=<slug>` | Audit ZIP for SOC2/GDPR |
| `process_erase_requests --limit=50 --dry-run` | Execute APPROVED GDPR EraseRequest rows |
| `cleanup_photo_upload_tokens --dry-run` | Delete expired photo upload tokens |
| `replay_domain_events --stream=<s> --from-date=<d>` | Re-run domain event handlers (backfill) |
| `replay_platform_event --event-id=<id>` | Reprocess a single platform event |
| `index_ai_knowledge --rebuild` | Rebuild RAG knowledge base index |
| `seed_default_digest_recipients` | Add risk-digest recipients for new admins |
| `apply_platform_migration --schema=a,b,c --target=<m>` | Bulk per-tenant migration apply |

---

## F. Destructive — Render shell, with approval

Always `--dry-run` first. Confirm impact. Coordinate with backup/compliance.

| Command | Effect |
|---|---|
| `tenant_purge --school=<slug> --confirm` | Complete tenant deletion (cascade all data) — IRREVERSIBLE |
| `tenant_wind_down --school=<slug> --dry-run` | Graceful tenant offboarding (archive then purge) |
| `purge_compliance_data --dry-run` | Delete audit logs / access logs per retention policy |
| `purge_thread_message_retention --dry-run` | Prune old communication threads |
| `process_erase_requests --dry-run` | Scrub PII for APPROVED GDPR erase requests |
| `rotate_audit_hmac_key --dry-run` | Rotate HMAC signing key (old entries become unverifiable) |
| `security_log_retention --dry-run --days=180` | Delete old security audit logs |
| `recover_database --backup-id=<id> --check` | Restore from backup / rollback DB (emergency only) |

---

## G. Local-only — NEVER on Render

These build local fixtures, diagrams, or demo data. They will pollute prod.

- `seed_demo --reset --keep-admin`
- `seed_buea_synthetic`
- `seed_testdata_2425`
- `seed_demo_tenant_users`
- `generate_models_diagram`
- `compile_translations`
- `audit_tenant_models`
- `test_core_workflows`
- `run_phase7_checks`
- `phase_i_gap_analysis`
- `apply_marketplace_migrations` (the dev variant; use `apply_platform_migration` on prod)

If a command's docstring says "developer-only", "local-only", "debugging",
"demo", "internal", or "smoke test" — it belongs here.

---

## Quick-start: I just provisioned a new Render environment

```bash
# 0. One-time, on the Postgres DB (requires DB superuser):
psql $DATABASE_URL -c "CREATE EXTENSION vector;"

# 1. Deploy. Predeploy script handles migrate + seed_render_users + pgvector path.
git push render main

# 2. Open Render shell, run one-time setup:
python manage.py seed_global_data --with-profiles
python manage.py seed_platform_registries
python manage.py seed_marketplace_apps
python manage.py seed_marketplace_scopes
python manage.py seed_compliance_baseline
python manage.py seed_finance_defaults
python manage.py bootstrap_at_risk_registry
python manage.py seed_default_digest_recipients

# 3. Verify everything's wired:
python manage.py verify_platform_readiness
python manage.py verify_ai_ml_readiness
python manage.py verify_pgvector_index --strict

# 4. Ensure Celery worker + beat are running. That's it.
```

## Quick-start: I just trained a new ML candidate

```bash
# Local — train on synthetic or real data:
python apps/analytics/ml/train_at_risk.py --samples 5000 --out var/cand.joblib
python manage.py evaluate_at_risk_model var/cand.joblib --json var/cand.eval.json

# Render shell — upload the artifact, register, shadow-score:
python manage.py register_at_risk_artifact var/cand.joblib \
    --model-version at_risk_v3_2026q3 \
    --registered-by-username admin \
    --eval-json var/cand.eval.json
python manage.py score_shadow_at_risk --school=<slug> --candidate-version at_risk_v3_2026q3

# Review the shadow run in Django admin (AtRiskShadowRun). If band-change
# rate is acceptable and PSI is low:
python manage.py promote_at_risk_artifact at_risk_v3_2026q3 \
    --promoted-by-username admin \
    --min-roc-auc 0.75
```

## Quick-start: GDPR erase request came in

```bash
# Render shell:
# 1. Find the request in admin, approve it (status=APPROVED).
# 2. Dry-run to inspect what will be scrubbed:
python manage.py process_erase_requests --limit=50 --dry-run
# 3. Execute:
python manage.py process_erase_requests --limit=50
# 4. Confirm via audit log + export for compliance pack:
python manage.py export_compliance_evidence_pack --school=<slug>
```
