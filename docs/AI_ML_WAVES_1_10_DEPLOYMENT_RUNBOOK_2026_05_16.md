# AI/ML Waves 1-10 — Deployment Runbook

**Status as of 2026-05-16:** Code merged through `sms-v3.02.0`. This runbook is
the SOT for the operator-side work required to take the new infrastructure live.

It assumes you have an existing at-risk artifact on disk (the
`AT_RISK_MODEL_PATH` env var has been working since Pass 13.D) — the runbook
brings the registry, shadow scoring, explainability, grade prediction,
semantic search, AI digest, multi-language support, pgvector, and SHAP into
active service.

## TL;DR — one-shot deploy

```
# 1. Apply migrations (six analytics + one carried-over siteconfig)
python manage.py migrate siteconfig 0175
python manage.py migrate analytics 0022
python manage.py migrate analytics 0023
python manage.py migrate analytics 0024
python manage.py migrate analytics 0025
python manage.py migrate analytics 0026
python manage.py migrate analytics 0027

# 2. Backfill the registry from the legacy env-var path
python manage.py bootstrap_at_risk_registry --operator-username <opr>

# 3. Index existing students for semantic search
python manage.py build_student_embeddings

# 4. Confirm everything is green
python manage.py verify_ai_ml_readiness
```

That's the minimum for the at-risk path. Grade prediction, the AI digest, and
the optional opt-ins (`shap`, `pgvector`) have their own short checklists
below.

---

## Step-by-step

### 1. Schema (required)

The six analytics migrations stack cleanly on `0021`. Run in order:

| Migration | Adds | Wave |
|---|---|---|
| `0022_at_risk_model_registry` | `AtRiskModelArtifact`, `AtRiskInferenceRun` | 1 |
| `0023_at_risk_shadow_run_and_comparison` | shadow scoring | 2 |
| `0024_riskfactor_feature_contributions` | per-prediction explanations | 3 |
| `0025_grade_prediction_models` | grade-prediction family | 4 |
| `0026_grade_prediction_shadow` | shadow for grade prediction | 7 |
| `0027_risk_digest_recipient` | digest delivery targets | 8 |

`siteconfig 0175` is the integrations-marketplace migration that's been
pending since v2.79; it's unrelated to AI/ML but bundled in the same deploy.

### 2. Backfill the registry

The `_load_model` precedence is `registry production row → settings → env`.
Without a row, the loader falls back to env so behaviour is unchanged — but
shadow scoring, drift, calibration, and the digest's `top driver` text all
need a registered artifact.

```
python manage.py bootstrap_at_risk_registry \
    --operator-username <username> \
    [--artifact var/at_risk_model.joblib] \
    [--model-version at_risk_v1_synthetic]
```

Idempotent. Running again is a no-op if the row already exists. The default
version slug is `legacy_<basename>_<sha8>` so re-running with a different
joblib creates a new row.

### 3. Build the semantic-search index

```
python manage.py build_student_embeddings
```

Idempotent (text hash dedupes). Schedule nightly via Celery beat below.

### 4. Wire Celery beat (recommended)

Six new schedule entries, each opt-in via env var so a fresh deploy doesn't
start scoring before step 2:

| Env var | Task | Suggested cadence |
|---|---|---|
| `ENABLE_AT_RISK_NIGHTLY_BEAT=1` | `analytics.compute_nightly_risk` | daily 02:00 |
| `ENABLE_GRADE_PREDICTION_NIGHTLY_BEAT=1` | `analytics.compute_nightly_grade_predictions` | daily 03:00 |
| `ENABLE_STUDENT_EMBEDDINGS_BEAT=1` | `analytics.build_student_embeddings` | daily 03:30 |
| `ENABLE_RISK_DIGEST_BEAT=1` | `analytics.send_risk_digest_all` | daily 06:00 |
| `ENABLE_AT_RISK_DRIFT_WATCHDOG_BEAT=1` | `analytics.check_at_risk_drift_watchdog` | daily 07:00 |

The scoring tasks (`compute_nightly_*`) must run **before** the digest so the
digest pulls fresh `RiskFactor` rows.

### 5. Configure digest recipients

For each school, add at least one `RiskDigestRecipient`:

```
# Django admin: /admin/analytics/riskdigestrecipient/add/
# Or via shell:
RiskDigestRecipient.objects.create(
    school=school,
    channel="email",
    target="principal@<school>.com",
    label="principal",
)
```

For Slack, use a [Slack incoming webhook URL][1] as `target` and
`channel="slack_webhook"`.

[1]: https://api.slack.com/messaging/webhooks

### 6. Verify

```
python manage.py verify_ai_ml_readiness
```

Output:

```
AI/ML readiness:
  ✓ schema                 — all 10 tables present
  ✓ registry               — 1 artifact(s) registered
  ✓ production             — production='at_risk_v1_synthetic'
  ✓ inference_recency      — 12 run(s) in last 7d
  ✓ embeddings             — 8400 student embedding(s) indexed
  ✓ digest_recipients      — 4 enabled recipient(s) across tenants
  ○ shap_optional          — not installed — install with `pip install shap`
  ○ pgvector_optional      — PGVECTOR_ENABLED=False (JSON cosine path active)
  ✓ celery_beat            — 5 analytics beat entries: ...
```

`✓ = green`, `✗ = required & failing`, `○ = optional & off`. Add `--strict`
to make required failures exit non-zero (CI gate).

---

## Optional: grade prediction in production

Wave 7 added the full MLOps loop for grade prediction. The blocker is **operator data collection** — the model needs end-of-term labels to train on.

When you have ≥500 labelled (student × subject × term) rows:

```
# Export training data
python manage.py export_at_risk_training_data ...  # not yet implemented for grade prediction
# Operator-built CSV with the schema in train_grade_prediction.py docstring

# Train
python apps/analytics/ml/train_grade_prediction.py \
    --csv var/grade_training_2026_q1.csv \
    --out var/grade_prediction_v1.joblib

# Register + promote
python manage.py register_grade_prediction_artifact \
    var/grade_prediction_v1.joblib \
    --model-version grade_v1_2026_q1 \
    --registered-by-username <opr>

python manage.py promote_grade_prediction_artifact \
    grade_v1_2026_q1 \
    --promoted-by-username <opr> \
    --max-mae 6.0 --max-rmse 8.0 --min-r2 0.40
```

The nightly scorer (`compute_nightly_grade_predictions`) automatically
picks up the production artifact on the next run.

## Optional: SHAP per-prediction values (Wave 10)

```
pip install shap
```

Then `predict_at_risk_with_explanation` or `explain_score(model, features,
method="shap")` produces true Shapley values instead of the fast
importance × direction proxy. Cost: ~10-100× the fast path per
prediction. Default `method="fast"` is unchanged.

## pgvector for sub-millisecond search (Wave 9 + v3.x scale hardening)

Required at or beyond ~5k embeddings per tenant. The JSON cosine loop
falls over past that and the search latency tail starts to bite.

### Initial setup

Step 1 is the only manual action — the rest is wired into the Render
predeploy script (`scripts/release/render_predeploy.sh`) and runs on
every deploy. Both commands are idempotent and refuse on non-Postgres,
so they're safe to leave on permanently.

```bash
# 1. On the DB (one-time, requires DB superuser):
psql -c "CREATE EXTENSION vector;"

# 2-3. Handled by predeploy when RUN_PGVECTOR_MIGRATE=1 (default).
#      To skip (pre-5k tenants or no-extension DBs): RUN_PGVECTOR_MIGRATE=0
#
#      The predeploy block runs, in order:
#         python manage.py migrate_embeddings_to_pgvector --write-env-flag
#         python manage.py verify_pgvector_index --strict
#      `--strict` makes the deploy fail-loud if the index isn't being
#      picked up by the planner, so a silent fallback to JSON cosine
#      can never reach production unnoticed.

# 4. Restart workers so the new PGVECTOR_ENABLED env flag is read.
#    Render does this automatically on every deploy; nothing to do.
```

`--write-env-flag` appends `PGVECTOR_ENABLED=True` to `.env` (replaces
any existing `PGVECTOR_ENABLED=False` line in place). On a deploy that
manages env vars outside `.env`, set the flag in your config instead.

### Behaviour at scale

The migrate command was hardened in v3.x for production load:

- **Batched backfill** — `--batch-size 1000` (default) so the
  `JSON → vector` UPDATE doesn't hold a row-level lock for the entire
  duration of a multi-minute migration. Progress is reported per batch.
- **Auto-tuned `lists`** — IVFFLAT's `lists` parameter is set to
  `ceil(sqrt(row_count))`, clamped to `[50, 5000]`. For 5k rows that's
  71; for 50k rows it's 224. Override with `--index-lists N` if you have
  a measured better value.
- **Dim-mismatch refusal** — if `embedding_vec` exists with a different
  dim than the current embeddings (e.g. you switched embedding models),
  the command refuses unless `--force-drop-column` is passed.
  Irreversible loss of previously-backfilled vectors — required when
  legitimate, never silent.

### Periodic maintenance

IVFFLAT recall degrades as data grows past the `lists` value it was
built with. Convention: rebuild monthly during a low-traffic window.

```bash
python manage.py rebuild_pgvector_index --vacuum
```

- Reads current `embedding_vec` row count, auto-tunes new `lists`.
- Drops + recreates the index inside one transaction.
- `--vacuum` runs `VACUUM ANALYZE` afterwards (outside the transaction
  so it can run at all — Postgres refuses VACUUM inside a txn).

When you've grown 4× or more since the last rebuild, schedule one
sooner — the cost is one index scan worth of latency for ~30 seconds.

### Post-deploy verification

`verify_pgvector_index --json` is safe to run any time:

| Check | What it confirms |
|---|---|
| `extension_loaded` | `vector` is `CREATE EXTENSION`-ed in this DB |
| `vector_column` | `embedding_vec` column present + dim reported |
| `ivfflat_index` | `aiembedding_vec_ivfflat` index exists |
| `explain_uses_index` | Query planner picks Index Scan (not Seq Scan) |
| `row_stats` | Row count + null-vector-with-json count (should be 0) |

`--strict` makes it exit non-zero on any required failure for CI use.

### Rollback

`PGVECTOR_ENABLED=False` (or remove the line and restart workers).
The `search_students` function falls back to the JSON cosine loop.
No data loss — the JSON `embedding` column is never modified.

---

## Rollback

Each wave's data is additive — rolling back a migration drops the new
table but leaves existing data intact. Recommended rollback order
(deepest first):

```
python manage.py migrate analytics 0021  # before any Wave 1-8 migration
```

Loader will degrade to env-var path automatically. Operators don't
have to redeploy code.

## Common pitfalls

* **Heuristic-served scores during cutover.** Until step 2 runs, every
  `RiskFactor.feature_contributions` will be empty (heuristic served).
  The portal "Why" column shows the heuristic reason. This is correct
  behaviour — bootstrap the registry, then the next nightly batch
  populates contributions.
* **Empty digest body.** If `ai_narrate_risk_digest` shows
  `"Narrative unavailable"`, the AI gateway is off for that tenant or
  the day's RiskFactor batch hasn't run. Verify with
  `verify_ai_ml_readiness`.
* **Slack 4xx.** The webhook URL needs to accept JSON POSTs; some
  proxies block. `send_risk_digest` retries once per run but doesn't
  exponentially back off — flaky webhooks should be moved to a
  different channel.

## Related SOTs

- `docs/AT_RISK_MODEL_PRODUCTION_HANDBOOK_2026_05_16.md` — model
  lifecycle, retrain procedure, quality bars
- `apps/analytics/celery_tasks.py` — task name registry
- Memory entries `ai-ml-wave-{1..10}-*` — per-wave change log
