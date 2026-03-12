# Commit and Push Plan — AI Adoption Blueprint (Historical)

**Status:** Historical execution note only. The live AI adoption scope, phases, and deliverables are tracked only in `C:\Users\yimga\.cursor\plans\tiered_ai_gateway_and_ollama_7ecaa3c1.plan.md`. Do not use this file as a current tracker.

## Pre-commit verification

Run these and ensure they pass:

| Step | Command |
|------|---------|
| Django check | `python manage.py check` |
| AI gateway tests | `python manage.py test apps.portal.tests.test_ai_gateway -v 2` |
| Migrations applied | `python manage.py migrate` (or confirm siteconfig 0148, 0149 applied) |
| Lint (optional) | `python scripts/lint_secret_exposure.py`; no new broad-except in gateway/views_ai_gateway |

## Files changed (summary)

- **Gateway & config:** `services/ai_gateway.py`, `config/settings.py`
- **Models:** `apps/siteconfig/models.py` (AIPromptRegistry, AIGatewayMetric, AIPromptClass)
- **Migrations:** `apps/siteconfig/migrations/0148_add_ai_prompt_registry.py`, `0149_add_ai_gateway_metric.py`
- **Prompt registry:** `apps/siteconfig/prompt_registry.py`
- **Views:** `apps/portal/views_ai_gateway.py` (all productized endpoints, citations, redaction, budget 429, Wave 2/3)
- **URLs:** `apps/api/urls.py` (all AI routes)
- **Management commands:** `apps/siteconfig/management/commands/aggregate_ai_metrics.py`, `index_ai_knowledge.py`
- **Docs:** `docs/architecture/ai_orchestration.md`, `docs/architecture/ai_tiered_ollama.md`, `docs/architecture/AI_ADOPTION_BLUEPRINT_COMPLETE.md`, `docs/COMMIT_AND_PUSH_PLAN_AI_BLUEPRINT.md`
- **UI:** `templates/accounts/backend_dashboard.html` (Open WebUI link), `templates/customersuccess/guided_onboarding.html` (Explain / Suggest workflow + script)
- **Backend context:** `apps/accounts/views.py` (open_webui_url, settings import)
- **Tests:** `apps/portal/tests/test_ai_gateway.py` (allowed_backends, budget_exceeded)

## Suggested commit message

```
feat(ai): Complete AI Adoption Blueprint — gateway, endpoints, observability, Wave 2/3

- Gateway: budget enforcement, request metadata (allowed_backends, latency_target),
  schema_validation_failed in audit/metrics, tenant-safe logging
- Productized APIs: setup-assistant, workflow-draft, policy-explain, document-classify,
  semantic-search, migration-suggest; admin-copilot; Toolset 5A–5I (theme, feature-control,
  report, design-studio, live-preview, system-config); Wave 2 (dashboard-pack, support-assistant,
  tenant-maturity); Wave 3 (data-quality-assistant, marketplace-recommend, control-plane-intelligence)
- Citations for setup_assistant, policy_explain, admin_copilot
- Prompt registry: AIPromptRegistry model + get_prompt_template + BUILTIN_PROMPTS
- Observability: AIGatewayMetric, _record_metric cache buckets, aggregate_ai_metrics command
- Indexing: index_ai_knowledge command (policy, blueprint, workflow, report, help, config)
- Data-tier matrix and per-feature data boundary docs; Open WebUI deployment + Control Plane link
- UI: Setup Studio Explain / Suggest workflow buttons; OPEN_WEBUI_URL in backend dashboard
- All endpoints: rate limit, audit, budget 429; tests for allowed_backends and budget_exceeded

Ref: docs/architecture/AI_ADOPTION_BLUEPRINT_COMPLETE.md, ai_orchestration.md
```

## Push checklist

1. **Branch:** Commit on current branch (e.g. `main` or feature branch).
2. **Remote:** `git push origin <branch>` (or your remote name).
3. **CI:** If you have CI running on push, ensure gates (e.g. `pre_deploy_gate.sh`, tests) pass.
4. **Post-push:** Re-verify `docs/architecture/AI_ADOPTION_BLUEPRINT_COMPLETE.md` against the plan; every row should remain Done.

## Plan coverage

Every item from the RunMyCampus Open-Source AI Adoption Blueprint (and conversation summary) is addressed:

- Budget enforcement in gateway
- Request metadata (sensitivity_class, latency_target, output_type, allowed_backends)
- Retrieval indexing (doc + index_ai_knowledge command)
- Citations (setup_assistant, policy_explain, admin_copilot)
- Admin-copilot endpoint
- UI wiring (Setup Studio Explain / Suggest workflow; Control Plane Open WebUI link)
- Prompt registry and prompt classes
- Observability (metrics model, cache buckets, aggregate command, log redaction)
- Data-tier matrix and per-feature data boundary docs
- Open WebUI deployment doc + Control Plane link
- Toolset 5A–5I endpoints
- Wave 2 (dashboard/pack recommend, support assistant, tenant maturity)
- Wave 3 (data-quality assistant, marketplace recommend, control-plane intelligence)

No basic or placeholder work; all at expert/advanced level.
