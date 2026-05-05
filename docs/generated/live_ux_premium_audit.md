# Live UX Premium Audit

**Verdict:** repo fixes applied; live certification pending deployed recheck.

This audit records code-controlled findings plus the known live Render blocker from the previous recheck. It does not claim the live manager deployment has picked up these changes until a fresh deployed browser pass confirms it.

| Page | URL/template | Priority | Main issue | Primary action | Fix plan |
| --- | --- | --- | --- | --- | --- |
| Homepage | `templates/schools/marketing_landing.html` | high | Story is strong but still dense. | Book demo | Keep hero direct, Book Demo primary, Product Tour secondary, no fake PSP/certification claims. |
| Manager `/super/` | `templates/schools/super_dashboard.html` | critical | Control plane density can overwhelm buyers/operators. | Setup Studio | Keep executive pulse above fold and collapse the detailed operating board. |
| Offline Sync Center | `templates/platform_runtime/manager_offline_sync_center.html` | critical | Live manager route was a 404. | Select school | Render manager-safe tenant-scoped explainer and school selection action. |
| Payment Readiness Center | `templates/finance/payment_readiness_dashboard.html` | high | Must preserve PSP honesty. | Resolve missing credentials | Keep ready/degraded/missing-credentials/external-required/manual fallback states visible. |

## Manager Density

Before live audit: 202 links, 217 buttons, 106 card/panel-like elements.

Repo after above-fold fix: 9 links, 0 buttons, 16 card/panel-like elements before the disclosed detailed operating board.

Top five above-fold items:

- Platform health/status
- North Star/revenue posture
- Operational risk
- System health
- One primary setup/action

Secondary work is collapsed into progressive disclosure, sidebar groups, search, command center links, and the action rail.
