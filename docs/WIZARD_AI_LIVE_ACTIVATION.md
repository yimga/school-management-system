# Wizard AI Smart-Defaults — LIVE Activation Procedure

Activation procedure for the Unified Wizard Framework's AI smart-default
suggestions. Until LIVE mode is activated, every wizard step still works
end-to-end through the deterministic fallback registry (22/22 prompt keys
have a registered fallback per v3.93.0 acceptance criteria) — LIVE just
replaces "good default" with "context-personalized recommendation".

## How to verify current posture

```bash
python scripts/verify_wizard_ai_live_smoke.py
```

Outcomes:

* `WIZARD_AI_LIVE_PASS` — gateway reachable, real model response with
  registry-valid suggestions
* `FALLBACK_PASS` — gateway unreachable / unconfigured; deterministic
  rule fallback exercised cleanly. Default posture today.
* `FAIL` — registry/fallback parity broken (regression of the v3.93.0
  boundary contract). NOT a deployment-posture issue.

Add `--strict` to require LIVE mode for CI gates.

Evidence lands at `docs/generated/wizard_ai_live_smoke.json`.

## Activation prerequisites

Two layers of activation:

### Layer 1 — platform posture (operator decision)

Set in deployment env (Render / Docker / k8s):

```bash
RMC_DEPLOYMENT_PROFILE=online       # cloud-first posture
LITELLM_BASE_URL=https://litellm.your-deploy.example.com
LITELLM_API_KEY=sk-...               # provisioned via the LiteLLM admin UI
```

The resolver lives in `services.ai_deployment_posture` per
`docs/AI_DEPLOYMENT_POSTURE.md`. For edge / on-prem appliances, set
`RMC_DEPLOYMENT_PROFILE=edge` and use the Ollama bridge instead — same
verifier reports honest posture either way.

### Layer 2 — per-tenant AI policy (tenant decision)

A tenant whose `school.settings["ai_policy"]["wizard_smart_defaults"]`
explicitly resolves to `False` (or whose feature flag denies it) gets
fallback even on a LIVE platform posture. This is enforced inside
`services.ai_helpers.invoke_with_request` via the `require_available`
flag the wizard_ai bridge passes (already wired).

## What LIVE mode changes for users

For each step with `ai_recommend.enabled: true` in its JSON spec, the
operator sees a "Suggest defaults" affordance. Clicking it calls
`POST /api/wizards/ai/recommend/` which routes through
`apps.setup_studio.wizard_ai.request_smart_defaults`. The response shape is:

```json
{
  "suggestions": {"palette_key": "kerala_heritage_emerald", ...},
  "confidence": {"palette_key": 0.82, ...},
  "rationale_text": "Optional 1-2 sentence why",
  "used_fallback": false,
  "latency_ms": 612
}
```

Per the wizard_ai contract, every code path (LIVE or FALLBACK) returns the
same shape; the operator UI rendering doesn't change. Only
`used_fallback` flips.

## Activation rollout suggestion

1. Configure LITELLM env on staging.
2. Run `verify_wizard_ai_live_smoke.py --strict` against staging — expect
   `WIZARD_AI_LIVE_PASS` and capture the JSON evidence.
3. Walk one wizard end-to-end in the browser with a tenant that has
   `ai_policy.wizard_smart_defaults: true` — verify the "Suggest defaults"
   call returns model-generated values, not fallback values.
4. Confirm `apps.observability.metrics.emit_counter("setup_studio.wizard_ai.live_call")`
   shows traffic in your metrics backend (Prometheus / StatsD).
5. Flip production env to match staging.
6. Monitor `setup_studio.wizard_ai.fallback_used` counter for elevated
   fallback rate (>10% sustained = LiteLLM availability issue).

## Rollback

Set `RMC_DEPLOYMENT_PROFILE=offline` OR remove `LITELLM_API_KEY` from env
and redeploy. Every wizard immediately falls back to deterministic
defaults with no UI degradation. No data loss — wizard state is
independent of AI suggestions.

## Why this isn't shipped as default

`services.ai_helpers` charges per call against the platform's LiteLLM budget.
Enabling LIVE without per-tenant AI policy + rate limits would let any tenant
exhaust budget by hammering "Suggest defaults". The activation requires:

1. Platform-level LiteLLM cost guardrails configured.
2. Per-tenant `ai_policy` defaults reviewed.
3. `apps.observability.metrics` Prometheus scrape verified in production
   so cost overruns trigger alerts.

These are operator decisions, not engineer decisions. The framework is
ready; the activation is intentionally externally-gated.
