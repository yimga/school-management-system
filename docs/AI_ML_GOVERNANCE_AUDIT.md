# AI / ML Governance Audit (P8)

**Audit date:** 2026-05-17
**Pillar:** P8 — 12-pillar platform audit
**Authority:** [docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4

This document is the **synthesis of governance controls already implemented** for the AI/ML inference boundary. It is honest scaffolding for operator audit — every claim cites a file path you can grep.

---

## 1. Model lifecycle registry

| Stage | Model | Storage | Promotion gate |
|---|---|---|---|
| ARTIFACT registered | `AtRiskModelArtifact` | [apps/analytics/models_ml_registry.py](../apps/analytics/models_ml_registry.py) | Operator runs `bootstrap_at_risk_registry` |
| CANDIDATE → PRODUCTION | `AtRiskModelArtifact.status` | same | **Manual** (operator runs `promote_at_risk_artifact`) — gated by shadow-run evidence |
| Shadow runs | `AtRiskShadowRun` | same | Recorded by `score_shadow_at_risk` against PRODUCTION baseline |
| Inference runs | `AtRiskInferenceRun` | same | Logged on every production inference for drift detection |

**Promotion-readiness verifier:** [`apps/analytics/management/commands/verify_ai_promotion_readiness.py`](../apps/analytics/management/commands/verify_ai_promotion_readiness.py) (memory `bug-hygiene-sweep-v3.23.1`). Verdict ladder (severity-ordered): `no-candidate` → `no-shadow-evidence` → `insufficient-sample` (default min students = 100) → `failing-agreement` (default min = 0.85) → `failing-psi` (default max = 0.25 over 10 bins) → `ready`. Weighted-by-students-scored aggregation defends against single-tiny-run skew.

**Tests:** [apps/analytics/tests/test_at_risk_model_registry.py](../apps/analytics/tests/test_at_risk_model_registry.py) (5 classes, 15 methods), [apps/analytics/tests/test_verify_ai_promotion_readiness.py](../apps/analytics/tests/test_verify_ai_promotion_readiness.py) (11 tests).

---

## 2. Inference boundary

App code routes AI through [`services/ai_helpers.py`](../services/ai_helpers.py) — never `services.ai_gateway` directly. Enforced by:

- [`scripts/scan_ai_gateway_boundary.py`](../scripts/scan_ai_gateway_boundary.py) — AST scanner, **baseline 0**.
- Allowlisted infrastructure exceptions (the only paths permitted to import the gateway directly): `apps/portal/ai_provider.py`, `apps/portal/views_ai_gateway.py`, `apps/migration_cloud/ai_bridge.py`, `apps/platform_runtime/ai_providers.py`, `apps/siteconfig/management/commands/aggregate_ai_metrics.py`.

The helper enforces single-entry-point metadata normalization via `normalize_gateway_metadata` — every gateway call carries school + tenant + country + user + role context.

---

## 3. PII boundary

| Control | Implementation | Today's behavior |
|---|---|---|
| **Detection** | `services.ai_helpers.looks_like_pii` | Heuristic: substring hints (`ssn` / `email` / `phone` / `dob` / `address` / `national_id` / `passport` / `date_of_birth` / `social_security`) + regex (US SSN, RFC-5322-ish email, phone-like). |
| **Sensitivity tagging** | Callers pass `content_sensitivity="high_pii"` when detection fires (see [apps/people/ai_dedup.py:54](../apps/people/ai_dedup.py), [apps/finance/ai_categorize.py:71](../apps/finance/ai_categorize.py), [apps/migration_cloud/ai_bridge.py:135](../apps/migration_cloud/ai_bridge.py)) | Gateway routes high-PII tasks under tighter retention. |
| **Redaction** | `services.ai_helpers.redact_pii` (v3.23.4 2026-05-17 follow-up) | Replaces SSN / email / phone shapes with `[REDACTED-<kind>]` markers. Available for callers who want masking before send; **opt-in**, does not retroactively change existing high-PII tagging callers. |

**Honest carve-out:** detection is heuristic, not exhaustive — names alone, free-text addresses, and culturally-specific identifiers may pass through. Operator-facing surfaces (advisor dashboards, prompts that quote student records) should additionally gate on `User.role` rather than on heuristic redaction alone.

---

## 4. Vector search integrity

| Control | Verifier |
|---|---|
| pgvector extension installed | [`verify_pgvector_index --strict`](../apps/analytics/management/commands/verify_pgvector_index.py) check 1 |
| Embedding column present | same check 2 |
| IVFFLAT index present | same check 3 |
| EXPLAIN uses index | same check 4 (real EXPLAIN ANALYZE on test query) |
| Row stats sane | same check 5 |
| Index rebuild | [`rebuild_pgvector_index`](../apps/analytics/management/commands/rebuild_pgvector_index.py) — drops + recreates with `lists = ceil(sqrt(rows)) clamped [50, 5000]`; ANALYZE outside txn |
| Backfill | [`migrate_embeddings_to_pgvector`](../apps/analytics/management/commands/migrate_embeddings_to_pgvector.py) — batched 1000/batch, dim-mismatch refusal |

**Sized for:** 5k+ rows (memory `pgvector_production_hardening_v3.05`).

---

## 5. Explainability (SHAP)

- Optional dep declared in [`requirements_optional.txt`](../requirements_optional.txt) (the `shap` package).
- 10 files reference `shap` (search: `grep -r shap apps/analytics/`); used via `method="shap"` parameter on inference paths.
- **Soft-fallback when library missing** (memory `ai_ml_waves_6_10_followups_v2_98_to_v3_02`): if `import shap` fails, the inference path falls back to a deterministic feature-importance proxy and logs a single warning rather than 500-ing the surface.

---

## 6. Inference quota + rate limits

Per-tenant API rate limits are enforced via [`apps/api/rate_limit.py`](../apps/api/rate_limit.py) (`DEFAULT_TENANT_MAX_PER_MINUTE = 600`; per-school override via `school.settings["webhook_rate_limit_per_minute"]` — memory `integrations_marketplace_v3_5_ten_residuals`). AI gateway calls inherit the same caller-side limits; gateway-side per-tenant cost metering lives in [apps/billing/middleware_metering.py](../apps/billing/middleware_metering.py) tracking `db_sessions` per `(school, browser-session, utc_day)` triple.

---

## 7. Hallucination guardrails on AI narration

| Surface | Mitigation |
|---|---|
| At-risk explain endpoint ([apps/portal/views_ai_gateway.py](../apps/portal/views_ai_gateway.py)) | Returns model + version + confidence + features; UI must render numbers from the structured response, not from free-text narration. |
| Risk drivers UI ([templates/portal/ai_risk_drivers.html](../templates/portal/ai_risk_drivers.html)) | Driver list is rendered from `AtRiskInferenceRun.feature_contributions` (structured), not from generated prose. |
| Grade outlook ([templates/portal/ai_grade_outlook.html](../templates/portal/ai_grade_outlook.html)) | Prediction + confidence interval rendered from `GradePredictionInferenceRun`, not from prose. |

**Honest carve-out:** any AI-generated *narration* (the human-readable explanation) is still a generative-model output. Operators must treat it as draft copy, not authoritative text. The structured fields are the source of truth.

---

## 8. End-to-end health verifier

[`verify_ai_ml_readiness`](../apps/analytics/management/commands/verify_ai_ml_readiness.py) — 9 checks: schema, registry, production artifact, inference recency, embeddings, digest, SHAP, pgvector, Celery beat. Modes: `--json` / `--strict` (exit 1 when any check fails).

Daily operator drill:

```bash
python manage.py verify_ai_ml_readiness --strict
python manage.py verify_pgvector_index --strict
python manage.py verify_ai_promotion_readiness --strict
```

All three must exit 0 before promoting CANDIDATE → PRODUCTION.

---

## 9. What is intentionally NOT in scope here

- Model **training infrastructure** — lives outside the repo; the registry records what was produced, not how.
- Model **bias / fairness audit** — separate process (data science, not platform engineering).
- **A/B testing of AI outputs** — handled by the shadow-scoring path; statistically-significant comparison runs are an operator decision, not an automated gate.
