# apps/analytics

> Nightly at-risk scoring, grade prediction, the ML artifact registry, and the
> governed (never-raw-SQL) query layer.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 21 models · 31 migrations · 32 test modules · ~24.6k LOC

## What this app owns

Analytics turns tenant data into two things: a **risk signal** and a **governed
answer**. The risk side computes a nightly 0–100 at-risk score per student
(`RiskFactor`), mirrors it into an intervention workflow (`StudentAtRiskSignal`),
bands it against per-tenant thresholds, narrates it, and ships a digest. The
query side gives non-engineers a report builder that can only ever express
catalog-backed ORM queries.

The defining decision is that **every ML path is registry-resolved and
shadow-testable, and every fallback is observable**. `models_ml_registry` is the
single source of truth for which artifact is live: the legacy `AT_RISK_MODEL_PATH`
env var is now only a fallback, and the `is_production=True` row wins when both
are present. Promotion is an atomic flip (`promote_at_risk_artifact` archives any
prior production row), gated on drift and shadow-comparison evidence rather than
on someone copying a joblib file onto a box. The same pattern is duplicated
deliberately for grade prediction so a second model family plugs into one shape.

The second decision is that **the governed layer never constructs raw SQL**.
`governed_intent` maps natural language onto allowlisted intents and returns
catalog-backed definition dicts — not SQL strings, not querysets. `GovernedSavedReport.definition`
is a JSON blob whose allowed keys are fixed (`dataset_id`, `fields`, `filters`,
`group_by`, `aggregate`, `limit`). If a feature needs an expression the catalog
cannot express, the catalog is what changes.

## Key models

The 13 that matter most, of 21 declared. This table is not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `RiskFactor` | `analytics_riskfactor` | The nightly at-risk score per student (0–100) plus `reason_summary` (the explainable "why") and `model_version` (which artifact produced it). |
| `RiskThresholds` | `analytics_riskthresholds` | Per-tenant band cutoffs. `score >= red_min` → Red, `score >= amber_min` → Amber, else Green. Defaults 80 / 50. |
| `StudentAtRiskSignal` | `analytics_studentatrisksignal` | BR-06 EWS row driving the intervention workflow; mirrored from `RiskFactor` when the student has a linked portal user. |
| `StudentSignals` | `analytics_studentsignals` | Per-student time-series inputs (attendance ratio and friends) feeding the scorer. |
| `InterventionLog` | `analytics_interventionlog` | Audit trail for automated or manual Amber/Red interventions. |
| `AtRiskModelArtifact` | `analytics_atriskmodelartifact` | Registry row per trained artifact; `current_production()` resolves the live one. |
| `AtRiskInferenceRun` | `analytics_atriskinferencerun` | One row per nightly batch — cross-run observability. |
| `AtRiskShadowRun` / `AtRiskShadowComparison` | `analytics_atriskshadowrun` / `analytics_atriskshadowcomparison` | Candidate-vs-production scoring evidence gathered before a promotion. |
| `AtRiskOutcomeLabel` | `analytics_atriskoutcomelabel` | Retrospective ground truth for training — distinct from the forward-looking signal row. |
| `GradePrediction` | `analytics_gradeprediction` | One predicted grade per (student, subject, term). |
| `GradePredictionLabel` | `analytics_gradepredictionlabel` | The operator-supplied final grade at term close. |
| `GovernedSavedReport` | `analytics_governedsavedreport` | Tenant-scoped saved governed query definitions (ORM catalog only). |
| `BenchmarkAggregate` | `analytics_benchmarkaggregate` | Anonymized cross-tenant aggregates per region / sub_system / subject / term. |
| `RiskDigestRecipient` | `analytics_riskdigestrecipient` | Delivery target for the at-risk narrative digest. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `compute_nightly_risk_task`, `nightly_risk_factors_task`, `compute_risk_factors_task` | Nightly scoring. |
| Celery task | `compute_nightly_grade_predictions_task` | Grade-prediction batch. |
| Celery task | `check_at_risk_drift_watchdog` | Drift watchdog. |
| Celery task | `send_risk_digest_task`, `send_deadline_reminders_task` | Delivery. |
| Celery task | `build_student_embeddings_task` | Semantic-search index build. |
| Command | `register_at_risk_artifact` → `score_shadow_at_risk` → `check_at_risk_drift` / `check_at_risk_calibration` → `promote_at_risk_artifact` | The artifact promotion path; mirrored by the `*_grade_prediction` family. |
| Command | `verify_at_risk_readiness`, `verify_ai_ml_readiness`, `verify_ai_promotion_readiness` | Preflights. |
| Command | `bootstrap_at_risk_registry`, `train_at_risk_baseline`, `retrain_at_risk_pipeline`, `should_retrain_at_risk` | Registry + training lifecycle. |
| Command | `migrate_embeddings_to_pgvector`, `rebuild_pgvector_index`, `verify_pgvector_index` | pgvector migration path. |
| Command | `ai_narrate_risk_digest`, `send_risk_digest`, `compute_benchmark_aggregates`, `export_to_warehouse` | Narration / delivery / export. |
| URLs | `at_risk_dashboard`, `at_risk_intervention_action`, `governed_query_builder`, `governed_intent_preview` / `_execute`, `governed_saved_reports`, `executive_dashboard`, `decision_*_dashboard`, `master_sheet`, `forecaster_api` | |
| Module | `at_risk_readiness` | Preflight that distinguishes ML-artifact mode from silent heuristic fallback. |
| Module | `ai_narration_grounding` | `assert_grounded` entity guardrail. |

## Before you change this

- **The embedding store is in the PUBLIC schema even though this app is TENANT.**
  `semantic_search` wraps `siteconfig.AIEmbeddingStore`, where `school_id` is a
  plain UUID column that gets filtered on directly. The search call deliberately
  does **not** join to `StudentProfile` — the caller does that after ranking, so
  tenant isolation is enforced on the caller side too. Keep both halves: dropping
  the caller-side check because "the query already filters by school_id" removes
  the second lock on cross-tenant student data.
- **Never hardcode 80 / 50 as the risk bands.** Those are the `RiskThresholds`
  *defaults*, and the model docstring on `RiskFactor` quotes them for
  illustration only. Tenants override them, so resolve bands through
  `RiskThresholds` for the school or you will label a student Red on a dashboard
  that the tenant configured to call it Amber.
- **The registry outranks the env var.** `AT_RISK_MODEL_PATH` is a fallback; an
  `is_production=True` `AtRiskModelArtifact` wins. Do not "fix" a wrong model in
  production by editing the env var — promote an artifact, which archives the
  previous production row atomically and leaves evidence.
- **The dangerous predictor state is "configured but broken", not "unconfigured".**
  Per `at_risk_readiness`: with no path set the predictor runs heuristic-only and
  reports `ready=True` (the platform is not broken, it just is not using ML). With
  a path set but the artifact missing, unloadable, or the wrong shape, the
  predictor logs a warning and silently falls back to the heuristic while ops
  believes ML is on — nobody notices until someone audits `RiskFactor.model_version`.
  That is what the preflight exists to catch; keep it wired.
- **The AI-narration guardrail is wired into exactly one path.** `assert_grounded`
  is called from `ai_narrate_risk_digest` today. Any new narrative endpoint must
  call it explicitly — it is a caller-invoked check, not middleware. The check is
  intentionally conservative (proper-noun shaped tokens, consecutive capitals
  merged into one name) and the caller's failure mode is to drop the narrative
  and fall back to bullets, never to ship an ungrounded name.
- **The governed layer must not learn to emit SQL.** `governed_intent` returns
  catalog-backed definition dicts only, and `GovernedSavedReport.definition` has a
  fixed allowed-key set. Widening that to accept an expression string turns a
  governed report builder into an injection surface reachable by any tenant user
  who can save a report.
- **`ews_signals` runs off `AnalyticsConfig.ready()`.** The nightly `RiskFactor` →
  `StudentAtRiskSignal` mirror only fires for students with a linked portal user,
  so a tenant with unlinked students will see dashboard rows without EWS rows.
  That is by design, not a sync bug.
