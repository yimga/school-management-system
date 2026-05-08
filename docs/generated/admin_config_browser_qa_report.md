# Admin/config Browser QA Report

Generated: 2026-05-07

Scope: repo/local checklist.

Superseded by: `docs/generated/live_browser_ux_certification_report.json` for local browser UX certification.

Current truth: this remains a stale checklist artifact only. Local browser UX is certified in the later live-browser report; Render/custom-domain parity remains partial in `docs/generated/render_parity_certification_report.json`.

Live Render/browser automation status: not executed in this run.

Limitation: no live target or browser session was exercised. This artifact defines the browser/live QA contract and records the route checklist; screenshots, console inspection, and mobile visual review remain planned depth.

| Route | Status | Notes |
| --- | --- | --- |
| `/super` | checklist_ready | Platform Command Center remains verifier-covered; browser screenshot not captured. |
| `/configuration` | checklist_ready | Platform Configuration Center targeted-test and verifier-covered; browser screenshot not captured. |
| `/configuration/blueprints` | checklist_ready | Blueprint route targeted-test covered. |
| `/configuration/workflow-packs` | checklist_ready | Pack route targeted-test covered. |
| `/configuration/dashboard-packs` | checklist_ready | Pack route targeted-test covered. |
| `/configuration/policy-bundles` | checklist_ready | Pack route targeted-test covered. |
| `/configuration/change-requests` | checklist_ready | Governance route targeted-test covered. |
| `/configuration/registries` | checklist_ready | Registry center targeted-test covered. |
| `/configuration/registries/health` | new_repo_surface | Registry health contract test covered; browser screenshot not captured. |
| `/configuration/migrations` | checklist_ready | Migration depth contract covered; browser screenshot not captured. |
| `/configuration/integrations` | checklist_ready | Developer/app catalog contracts covered; browser screenshot not captured. |
| `/configuration/billing` | checklist_ready | Package/billing impact contracts covered; browser screenshot not captured. |
| `/configuration/experience` | checklist_ready | Configuration facade remains verifier-covered; browser screenshot not captured. |
| `/school/settings` | checklist_ready | Tenant configuration targeted-test covered. |
| `/school/setup/blueprints` | checklist_ready | Tenant blueprint setup targeted-test covered by prior slice. |
| `/school/setup/packs` | checklist_ready | Tenant pack setup targeted-test covered. |
| `/school/setup/imports` | planned_browser_depth | Migration contract covered; live tenant import UI QA remains planned depth. |
| `/internal-admin` | checklist_ready | Internal admin alias targeted-test covered. |

Checks required for certification: status code, auth redirect behavior, premium shell, primary action, no dummy href/action, no 404/500/502, mobile layout, console errors, tenant boundaries, external honesty, and density/spacing.

Verdict: `BROWSER_LIVE_QA_NOT_CERTIFIED_REPO_CHECKLIST_CREATED`.
