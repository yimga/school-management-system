# RunMyCampus Premium UX Standard

This standard governs public marketing, authenticated role homes, and operational centers. It is intentionally product-facing: backend architecture can be strong while the visible experience still fails trust, clarity, and buyer confidence.

## Core Rules

1. One primary action per screen.
2. Every page must answer: what is happening, what needs attention, what should I do next, and can I solve it here?
3. No passive dashboards; use Command Center, Workspace, Home, or Center labels.
4. No dead-end empty states.
5. No equal-weight CTA clusters.
6. No dummy links or fake actions.
7. No fake payment or PSP readiness.
8. Use premium spacing, restrained density, and clear typography.
9. Every page needs a clear identity and purpose marker.
10. Mobile behavior must stack controls without hiding the next action.
11. Every risk must show an action or an honest blocker.
12. Every operational table needs a clear next step.

## Required Shell Markers

Shared shells must expose these markers so tests, audits, and browser QA can verify the premium contract:

- `data-rmc-premium-shell`
- `data-rmc-primary-action` or `data-rmc-primary-action-slot`
- `data-rmc-page-purpose`
- `data-rmc-action-rail` where a contextual rail or drawer exists

## Product Labels

Use active operating-system labels:

- Founder Command Center
- School Command Center
- Teacher Workspace
- Family Home
- Money Center
- Insights Center
- App Marketplace
- Offline Sync Center
- Trust & Security Center
- Configuration Center
- Automation Studio

## Payment Truth

Payment pages may show `ready`, `degraded`, `missing credentials`, `external required`, and `manual fallback`. They must not imply live PSP readiness unless credentials and external provider status are verified.
