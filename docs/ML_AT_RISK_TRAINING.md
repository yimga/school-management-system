# At-Risk Model — Training Pipeline (2026-05-14)

Closes the "no trained model artifact" gap in `docs/COMPETITIVE_PARITY_ROADMAP.md`
Pass 13.1.

## What landed in this wave

| File | Role |
|---|---|
| [`apps/analytics/ml/at_risk_features.py`](../apps/analytics/ml/at_risk_features.py) | 9-feature extractor. *Existed.* |
| [`apps/analytics/ml/at_risk_model.py`](../apps/analytics/ml/at_risk_model.py) | Joblib loader + heuristic fallback. *Existed.* |
| [`apps/analytics/ml/synthetic_at_risk_dataset.py`](../apps/analytics/ml/synthetic_at_risk_dataset.py) | **New.** Synthetic dataset generator using a research-grounded latent-wellness kernel + Bernoulli noise. Default 5,000 rows, ~30% positive class. |
| [`apps/analytics/ml/train_at_risk.py`](../apps/analytics/ml/train_at_risk.py) | **New.** End-to-end training entry point — fits a `CalibratedClassifierCV(GradientBoostingClassifier)` on synthetic *or* real CSV, evaluates on a 20% stratified holdout, writes the joblib artifact at `settings.AT_RISK_MODEL_PATH` (or `var/at_risk_model.joblib`). |

## Run the synthetic baseline

```bash
pip install scikit-learn joblib   # one-time
python apps/analytics/ml/train_at_risk.py
```

Expected output: ROC AUC ≈ 0.93 on the synthetic holdout (the kernel is
learnable by design; a real-data run will be lower).

## Switch to real labeled data

Once a tenant accumulates real outcomes (year-end retention, course failure,
disciplinary referral, etc.), produce a CSV with the schema:

```
attendance_rate,absence_count,late_count,avg_evaluation_score,evaluation_count,eval_score_trend,open_invoice_count,open_balance_amount,days_since_last_login,label
0.83,7,3,68.2,11,-2.3,2,420.0,1,1
0.96,2,0,89.0,12,1.5,0,0.0,0,0
...
```

`FEATURE_ORDER` in `synthetic_at_risk_dataset.py` is the canonical schema —
both `at_risk_features.extract_features()` (live inference) and this CSV (training)
must use the same column order.

Then:

```bash
python apps/analytics/ml/train_at_risk.py --csv path/to/labeled.csv \
    --out var/at_risk_model.joblib
```

The trained joblib carries metadata (`feature_order`, training source,
holdout metrics, version string) so observability + audit can show *which*
artifact is in production at any time.

## Inference path

`apps/analytics/ml/at_risk_model.py` loads `settings.AT_RISK_MODEL_PATH` lazily,
caches the artifact for the process lifetime, and exposes `predict()` returning
`(score_0_100, reason_summary, model_version)`. When no artifact is present,
it falls back to the rule-based heuristic — so the platform never goes blind.

## Calibration choice

We use isotonic calibration (`CalibratedClassifierCV(method="isotonic", cv=3)`)
because the platform exposes the *raw probability × 100* to operators as a
0..100 "at-risk score." Raw gradient-boosting probabilities are not calibrated;
isotonic regression on a held-out fold lands the output where a 70 actually means
~70% probability of the at-risk outcome. Without calibration the score-tier
buckets (e.g. "≥80 alert") would mean different things across tenants.

## Reason summary (LLM-explained)

`at_risk_model.predict()` already returns a `reason_summary` string. The
production path can swap that for an Anthropic Claude call against the
feature vector:

```python
from apps.analytics.ml.at_risk_features import AtRiskFeatures

features = AtRiskFeatures(...)
# Existing heuristic reason:
reason = features.heuristic_reason()
# Optional AI upgrade (entitlement-gated):
if AI_RISK_EXPLAINER_entitlement_for(school):
    reason = ai_gateway.explain_at_risk(features, model_version=model.version)
```

The `ai_gateway.explain_at_risk` call is gated by tenant entitlement and falls
back to the heuristic when the entitlement is off (per the wider AI-gateway
"degrade gracefully" pattern).

## Why synthetic data is acceptable as a v1 baseline

1. **Schema fidelity.** The features are identical to the live inference path.
2. **Kernel is documented.** The latent-wellness kernel + Bernoulli noise is
   in `synthetic_at_risk_dataset.py` and reproducible from `seed=42`.
3. **Calibration discipline.** Isotonic + stratified holdout means we don't
   ship a high-AUC-but-overconfident model.
4. **Reason transparency.** The platform shows the *feature vector* and the
   *reason summary* to the operator, not just a black-box score. Operators
   can sanity-check.
5. **Easy replacement.** Day-1 deploy ships the synthetic-trained joblib.
   Day-N (real data available) reruns `train_at_risk.py --csv` and the file
   swaps in place; no code change required.

## What's still needed for the real-data swap

| Need | Owner |
|---|---|
| Year-end retention labels per student (positive/negative) | School operations |
| Optional course-failure / disciplinary labels | Academics + DSO |
| Anonymization + minimum tenant-size threshold (avoid identifiable predictions on tiny schools) | Compliance + ML |
| Cross-tenant federated learning (eventually) | Platform engineering |

Tracked in `docs/COMPETITIVE_PARITY_ROADMAP.md` Pass 13 item 1.

## CI gate (recommended)

Add a step that runs the training script on synthetic with `--no-write` and
fails the build if ROC-AUC regresses below 0.85. This catches accidental
regressions to the feature extractor or the kernel.
