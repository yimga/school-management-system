# AI Recommendation Audit

Generated: 2026-05-23T14:35:23.651549+00:00

## Boundary

- Gateway path: `services.ai_helpers.invoke_with_request`
- Forbidden imports: `services.ai_gateway` (enforced by `scan_ai_gateway_boundary` + `verify_template_ai_recommender_boundary`)

## Fallback

deterministic rules path scoring role↔category + country + language + connectivity

## Registry validation

Refuses any AI-proposed key not in OVERLAYS; refuses operator-only proposals

## Live smoke verifier

`scripts/verify_template_ai_recommender_live_smoke.py`
