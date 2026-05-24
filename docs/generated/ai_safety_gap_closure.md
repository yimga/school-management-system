# AI Safety + Inventory Redaction (Phase 17)

**Batch:** 1488 · **Verdict:** AI_SAFETY_REPO_SCOPE_PASS

## Floor
- AI Gateway boundary: app code MUST use [services/ai_helpers.py](../../services/ai_helpers.py) — NEVER `services.ai_gateway` directly
- Boundary scanner: `scripts/scan_ai_gateway_boundary.py` CI baseline **0**
- [services/ai_deployment_posture.py](../../services/ai_deployment_posture.py) — RMC_DEPLOYMENT_PROFILE → cloud/edge tiers
- [docs/AI_GOVERNANCE_CLASSROOM.md](../AI_GOVERNANCE_CLASSROOM.md)
- [apps/portal/help_governance.py](../../apps/portal/help_governance.py)
- [apps/observability/metrics.py](../../apps/observability/metrics.py) — `_sanitize_labels` drops sensitive VALUES (password/secret/token/signature_text/private_key/email/slug)
- [apps/brand_experience/template_ai_recommender.py](../../apps/brand_experience/template_ai_recommender.py) — registry-validated; refuses operator-only leaks
- `scan_pii_logging_smell` baseline **0**

## AI Safety Status

| Property | Status |
|---|---|
| No raw prompt logging with PII | ✓ |
| No tenant data crossing into platform AI context | ✓ |
| No secrets in inventory | ✓ |
| No source credentials in migration prompts | ✓ (Rust ZeroizeOnDrop + constant-time compare) |
| No tenant-visible code oracle | ✓ |
| Tenant-safe AI answers | ✓ (per-tenant `invoke_with_request`) |
| Missing context → `DATA DEFAULTER` | ✓ |
| Missing feature → `FEATURE CODESPACE DISCONNECT` | ✓ |
| KB drafts review-gated | ✓ |
| No homework cheating answer leakage | ✓ (Phase 13 contract) |
| No template recommendation stereotyping | ✓ (registry-validated + deterministic fallback) |

## Tests Added (Phase 18)
- `apps/apicenter/tests/test_ai_context_tenant_safety.py`
- `apps/apicenter/tests/test_ai_inventory_redaction.py`
- `apps/apicenter/tests/test_ai_missing_context_fallbacks.py`
- `apps/migration_cloud/tests/test_migration_ai_credential_redaction.py`
- `apps/academics/tests/test_homework_ai_guardrails.py`
- `apps/platform_runtime/tests/test_ai_local_template_recommendation_safety.py`

## External Blockers (Honest)
- Production LiteLLM keys for live AI probe (Lane 2)
- Operator counsel signoff for tenant-visible KB auto-publish (currently review-gated by design)

**Verdict:** AI_SAFETY_REPO_SCOPE_PASS
