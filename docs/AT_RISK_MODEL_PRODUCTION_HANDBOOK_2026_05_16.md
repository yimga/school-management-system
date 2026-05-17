# At-Risk Model — Production Handbook

**Status as of 2026-05-16:** A synthetic-data-trained baseline model
(`at_risk_v1_synthetic`, ROC AUC ≈ 0.874 on synthetic holdout) is the
production artifact today. This handbook documents the procedure for
replacing it with a model trained on real labeled outcomes.

## Component map

| Component | Path | Role |
|---|---|---|
| Feature extractor | `apps/analytics/ml/at_risk_features.py` | Computes the row vector for one student |
| Synthetic generator | `apps/analytics/ml/synthetic_at_risk_dataset.py` | Cold-start labeled data |
| Trainer | `apps/analytics/ml/train_at_risk.py` | Fits + calibrates + writes joblib |
| Inference loader | `apps/analytics/ml/at_risk_model.py` | Wraps artifact with stable `predict()` |
| Readiness preflight | `apps/analytics/at_risk_readiness.py` | Catches silent heuristic-fallback |
| Label collection model | `apps.analytics.models.AtRiskOutcomeLabel` | Operator-labeled ground truth |
| Label export cmd | `export_at_risk_training_data` | `AtRiskOutcomeLabel` → CSV |
| Baseline train cmd | `train_at_risk_baseline` | Wrapper around `train_at_risk.py` |
| Evaluation cmd | `evaluate_at_risk_model` | Holdout metrics + deploy gate |
| Drift detector | `check_at_risk_drift` | PSI vs reference distribution sidecar |
| Calibration audit | `check_at_risk_calibration` | ECE of predicted vs observed positive rate |
| Retrain trigger | `should_retrain_at_risk` | Distinct exit codes for label-volume / age gates |
| **Registry — artifacts** | `apps.analytics.AtRiskModelArtifact` | SOT for which artifact is live |
| **Registry — runs** | `apps.analytics.AtRiskInferenceRun` | Per-batch capacity / drift telemetry |
| **Shadow run** | `apps.analytics.AtRiskShadowRun` | Aggregate prod-vs-candidate evidence per batch |
| **Shadow comparison** | `apps.analytics.AtRiskShadowComparison` | Per-student production vs candidate score row |
| **Pipeline orchestrator** | `retrain_at_risk_pipeline` | Chains should_retrain→export→train→eval→register |
| **Register cmd** | `register_at_risk_artifact` | Joblib → candidate registry row (with metrics) |
| **Promote cmd** | `promote_at_risk_artifact` | Atomic flip candidate→production; archives prior |
| **Shadow cmd** | `score_shadow_at_risk` | Score every student with prod AND candidate; write comparison rows |
| Nightly scorer | `compute_nightly_risk` | Writes `RiskFactor` rows + `AtRiskInferenceRun` summary |
| EWS bridge | `apps/analytics/ews_signals.py` | Mirrors `RiskFactor` ≥50 → `StudentAtRiskSignal` |

## End-to-end retraining procedure

### 1. Gather labels

Operator picks a cohort that has reached a clear outcome
(graduated / withdrawn / repeated). The `/portal/at-risk/labeling/` queue
captures per-student `AtRiskOutcomeLabel` rows. **Minimum dataset for a
production retrain:** 500 labeled students with at least 15% positive rate.
Lower volume or extreme class imbalance produces models that look great on
holdout but generalize poorly.

### 2. Export training data

    python manage.py export_at_risk_training_data \
        --school <slug> \
        --out var/at_risk_training_2026_q1.csv

This script joins `AtRiskOutcomeLabel` to the same `extract_features()` the
inference path uses — so training and serving see identical feature vectors.

### 3. Train

    python apps/analytics/ml/train_at_risk.py \
        --csv var/at_risk_training_2026_q1.csv \
        --out var/at_risk_v2_candidate.joblib

The script prints holdout ROC AUC and average precision computed on a
20% stratified split inside the same CSV. Treat these numbers as
optimistic — the held-out 20% is i.i.d. with training data; production
drift will be worse.

### 4. Evaluate against an independent holdout

Reserve a separate labeled CSV that the trainer never saw, then:

    python manage.py evaluate_at_risk_model \
        var/at_risk_v2_candidate.joblib \
        --csv var/holdout_independent.csv \
        --json var/eval_v2_candidate.json \
        --min-roc-auc 0.75 \
        --min-average-precision 0.45

The command exits non-zero if either gate fails. Use this as a CI step
before promoting an artifact to production.

### 5. Promote

Three paths, in order of preference:

**a) Registry (current — v2.92+):** Register the candidate, then promote
atomically through the registry. The loader consults
`AtRiskModelArtifact.current_production()` first; the new path takes
effect on the next inference call without a worker restart.

    python manage.py register_at_risk_artifact \
        var/at_risk_v2_candidate.joblib \
        --model-version at_risk_v2_2026_q1 \
        --registered-by-username <operator> \
        --eval-json var/eval_v2_candidate.json

    python manage.py promote_at_risk_artifact at_risk_v2_2026_q1 \
        --promoted-by-username <operator> \
        --min-roc-auc 0.70 --min-average-precision 0.40

The promote command atomically archives the previously-production row;
rolling back is `promote_at_risk_artifact <previous_version>`.

**b) Path-pinned env (legacy):** Set `AT_RISK_MODEL_PATH` env var to
the new artifact and roll the workers. Loader cache is keyed by path
string, so promote takes effect on the next inference call.
Use only when the registry is unavailable.

**c) In-place (avoid):** Overwrite `var/at_risk_model.joblib`, restart
workers. Hardest to roll back; only justified during cold-start.

Always tag the artifact's `model_version` field with a date or commit:
`at_risk_v2_2026_q1` is more useful than `at_risk_v1_real` in audit logs
six months later.

### 6. Verify in production

After promotion, run:

    python manage.py verify_at_risk_readiness

This is the preflight from `at_risk_readiness.py`. It asserts the
ML-artifact path is firing (not silently falling back to heuristic) and
the bundle shape is valid.

Also spot-check `RiskFactor.model_version` on the next nightly run —
rows should carry the new version string, not the previous one.

## Quality bar for promotion

The defaults in `evaluate_at_risk_model` are deliberately conservative:

| Metric | Floor | Why |
|---|---|---|
| ROC AUC | 0.70 | Below this, the model adds noise to operator triage |
| Average precision | 0.40 | At ~15% base rate, AP=0.40 means precision dominates random by ~2.7x |
| Calibration error | n/a in v1 | Add this gate when artifacts include `calibration_curve` output |

Tighten the floors as the dataset grows. With 5000+ labels we'd expect to
hold AUC ≥ 0.78 and AP ≥ 0.55.

## Heuristic baseline contract

When no artifact path is set, `predict()` falls back to a rule-based
heuristic in `at_risk_model.py`. This is **the day-zero contract** for
new tenants: the platform always produces reason-summaries even before
labels exist. The heuristic is intentionally aggressive on a small number
of high-signal features (attendance, recent grade trend, late
assignments) — operators see explainable scores and start labeling.

The readiness preflight reports `mode=heuristic` and `ready=True` in this
state. That is **not a bug**; it's the supported "early days" mode.

## Operator playbook for slow rollouts

- Run `evaluate_at_risk_model` against the **current production artifact**
  every quarter using fresh labels. If metrics drift down, the model is
  decaying and needs retraining — don't wait for a complaint.
- When promoting a new artifact, run the heuristic in parallel for one
  nightly cycle by setting `AT_RISK_MODEL_PATH=` (empty) on a single
  worker. Compare `RiskFactor.score` distributions. A 10+ point shift in
  the median score is worth a manual review before full rollout.
- Keep three most-recent artifacts on disk so rollback is one env-var
  flip away.

## Continuous monitoring loop (v2.90+)

Three commands form the daily/weekly observability loop. They are
idempotent and tenant-scoped, so they are safe to run unattended.

### Drift — `check_at_risk_drift`

Compares the live `RiskFactor.score` distribution to a sidecar
reference captured at training time:

    # First run after a clean retrain — capture the reference.
    python manage.py check_at_risk_drift \
        --artifact var/at_risk_model.joblib \
        --window-days 30 \
        --write-reference

    # Daily watchdog — compute PSI vs reference.
    python manage.py check_at_risk_drift \
        --artifact var/at_risk_model.joblib \
        --window-days 7 \
        --max-psi 0.25 \
        --json var/drift_$(date +%F).json

PSI bands (industry convention): `<0.10 stable`, `0.10–0.25 moderate`,
`>=0.25 significant`. The `--max-psi` gate makes the watchdog crashable
in CI so alerting can hang off the exit code.

### Calibration — `check_at_risk_calibration`

Joins `AtRiskOutcomeLabel` to the most recent `RiskFactor` per student and
computes Expected Calibration Error:

    python manage.py check_at_risk_calibration \
        --school <slug> \
        --min-samples-per-bin 10 \
        --max-ece 0.15 \
        --json var/calibration_$(date +%F).json

Bins with fewer than `--min-samples-per-bin` labels are excluded from
the ECE so a single noisy bucket doesn't flip the gate. Treat ECE >0.15
as a recalibration signal (`CalibratedClassifierCV(method="isotonic")`).
`RECOVERED` labels count as positive — the prediction correctly flagged
a student before the intervention worked.

### AI surfaces — semantic search + narrated digest (v2.96+)

Two operator-facing AI surfaces sit on top of the predictive base:

**Semantic search over student records.** `apps.analytics.semantic_search`
embeds each active student's summary card (name + grade + recent risk
band) into `AIEmbeddingStore` (public schema, JSONField vectors).
The search function cosine-ranks stored embeddings against a query
embedding, school-filtered. Nightly cron:

    python manage.py build_student_embeddings   # all active schools

Search is exposed as `search_students(query, school_id=, top_k=)` —
no HTTP surface yet; callers should be portal views authorised on
the school. Pluggable backend via `services.embeddings.get_embedding_provider`
(Ollama by default, OpenAI-compatible via env). Stored vectors are
JSON — switch to `pgvector.VectorField` when available without
changing the function contract.

**AI-narrated risk digest.** `ai_narrate_risk_digest --school <slug>
--top-n 5` picks today's highest-risk students, formats them into a
prompt with band + top driver, and asks the AI gateway for a 2-3
sentence intervention-shaped narrative. Falls back to the plain
bullet list when the gateway is unavailable — never crashes the
batch. Send to stdout by default; `--out path.txt` for cron file
delivery.

Future homes for the digest text: `CommunicationTemplate` (v2.13) so
it can be scheduled as an email; Slack webhook via existing
integrations connectors (v2.79).

### Per-prediction explainability (v2.94+)

`RiskFactor.feature_contributions` (JSONField) now stores the top-3
feature attributions for every ML-served prediction. Format:

```json
[
  {"name": "attendance_rate", "value": 0.62, "importance": 0.31, "direction": "elevates"},
  {"name": "avg_evaluation_score", "value": 54.0, "importance": 0.22, "direction": "elevates"},
  {"name": "eval_score_trend", "value": -8.5, "importance": 0.10, "direction": "elevates"}
]
```

The `reason_summary` column is now derived from these contributions
when the ML path serves the score, replacing the canned heuristic
sentence. Heuristic-served scores still use the heuristic reason.

Direction tag (`elevates` / `lowers`) is computed against a per-feature
neutral baseline (e.g. `attendance_rate=0.95`); inverse-direction
features (attendance, evaluations) are flipped so the tag reads
correctly to operators. Importance comes from
`model.feature_importances_` (tree models) with `abs(coef_)` fallback
for linear models. Estimators exposing neither emit an empty list and
the heuristic reason text is used.

This is **local importance, not full SHAP** — for true Shapley values
add the `shap` library and write a `--full` variant of the explainer.

### Shadow scoring — `score_shadow_at_risk` (v2.93+)

Run AFTER an artifact has been registered as candidate but BEFORE
promote. Scores every active student against both the current
production artifact and the candidate, writes one
`AtRiskShadowComparison` row per student, and aggregates into an
`AtRiskShadowRun` summary with:

    agreement_pct       — share of students with identical bands
    band_changes        — total band differences
    promotions          — candidate moved student to HIGHER-risk band
    demotions           — candidate moved student to LOWER-risk band
    mean/median/p95     — distribution of |score_delta|
    psi_score_distribution — PSI between prod and candidate score
                             distributions over 10 bins

Operator decision matrix:

| Agreement | Promotions/demotions | Recommended |
|---|---|---|
| ≥ 0.92  | Few, distributed across bands | Promote |
| 0.80-0.92 | Mostly correct direction | Spot-check disagreements |
| < 0.80  | Pattern of demotions of true positives | Reject |
|        | PSI > 0.25                              | Investigate before promote |

Usage:

    python manage.py score_shadow_at_risk \
        --school <slug> \
        --candidate-version at_risk_v2_2026_q1   # optional override

Shadow scores are NEVER written back to `RiskFactor` — they live only
in `AtRiskShadowComparison`. The production read path stays clean.

Promotion from shadow row: the Django admin's
`AtRiskShadowRun` change-list has a "Promote candidate to PRODUCTION"
bulk action that performs the registry promote in one click. Refuses
on `SKIPPED` / `FAILED` runs.

### Retrain decision — `should_retrain_at_risk`

Exits with distinct codes so orchestrators can branch:

| Exit | Meaning |
|------|---------|
| 0    | not due |
| 10   | label-volume threshold crossed since `trained_at` |
| 11   | artifact older than `--max-age-days` |

    python manage.py should_retrain_at_risk \
        --artifact var/at_risk_model.joblib \
        --threshold 100 \
        --max-age-days 180

`trained_at` is read from the joblib bundle when present; otherwise it
falls back to the file mtime so legacy bundles still get an honest age
read. Disable either gate during commissioning with `--threshold-only`
or `--max-age-only`.

## Out of scope for v1

Tracked separately, not gated on the operator labeling effort:

- Multi-school transfer learning (one tenant's model boosting another).
- Per-grade-level models — current model treats Grade 7 and Grade 12
  the same; signal probably differs.
- Per-region calibration (US vs EU vs LATAM behavioral patterns).
- Live SHAP explanations on each prediction (artifacts emit
  reason-summary from `at_risk_features.explain()`, which is good
  enough for operator triage).
