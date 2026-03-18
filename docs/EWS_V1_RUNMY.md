# Early Warning System v1 (BR-06)

## Implemented

- **Risk model:** `apps.analytics.models.RiskFactor` (score, band, reason_summary).
- **API:** `GET /api/v1/intervention/red-flags?threshold=80`, `POST /api/v1/intervention/calculate-risk`.
- **UI:** `analytics:at_risk_dashboard` — per-row **Log intervention** (amber/red), **Resolve** / **Dismiss** on ongoing list; POST `analytics:at_risk_intervention_action`.
- **Event:** `ews_intervention_started` on new intervention.
- **Command palette:** At-risk dashboard, Intervention action center.
- **Trigger on attendance change:** After attendance save, async `compute_risk_factors_task` for school (debounced).

## Ops

- Nightly or on-demand risk job remains valid.
- **InterventionLog** + action center for workflows.
