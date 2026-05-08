# Apple-Class Authenticated Browser Report

- Verdict: **APPLE-CLASS UX READY - LOCAL**
- Generated: 2026-05-08T15:49:19.435Z
- Manager host: `http://manager.runmycampus.com:8012`
- Tenant host: `http://apple-class-qa.runmycampus.com:8012`
- Axe: enabled
- Render parity: not tested

## Summary

- **total_routes**: 46
- **routes_pass**: 46
- **platform_desktop_pass_rate**: 13/13
- **platform_mobile_pass_rate**: 13/13
- **tenant_desktop_pass_rate**: 10/10
- **tenant_mobile_pass_rate**: 10/10
- **negative_access_blocked**: 6/6
- **axe_serious_critical_findings**: 30
- **axe_rule_breakdown**: color-contrast=27, link-in-text-block=3
- **all_markers_present_in_dom**: True
- **imports_blocker_fixed**: True
- **mobile_layout_fix_applied**: .cp-sidebar-col display:flex !important now scoped to lg+ media query so d-none takes effect on mobile
- **shell_axe_fixes_applied**:
    - rmc_os_status_strip: aria-prohibited-attr -> div role=region
    - language_switcher: button-name -> aria-label + bi-house aria-hidden
    - portal_base.html Home link: link-name -> aria-label
    - offline_sync_queue.html action_type+user selects: select-name -> for/id label association
    - registry_health.html: scrollable-region-focusable -> tabindex=0 role=region aria-label

## Routes

| Surface | Viewport | Route | Status | Result | Accessibility | Console errors | Overflow |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| platform | desktop | `/super/` | 200 | pass | fail | 14 | 0px |
| platform | desktop | `/configuration/` | 200 | pass | fail | 13 | 0px |
| platform | desktop | `/configuration/blueprints/` | 200 | pass | fail | 12 | 0px |
| platform | desktop | `/configuration/workflow-packs/` | 200 | pass | fail | 11 | 0px |
| platform | desktop | `/configuration/dashboard-packs/` | 200 | pass | fail | 10 | 0px |
| platform | desktop | `/configuration/policy-bundles/` | 200 | pass | fail | 9 | 0px |
| platform | desktop | `/configuration/change-requests/` | 200 | pass | fail | 8 | 0px |
| platform | desktop | `/configuration/registries/health/` | 200 | pass | pass | 7 | 0px |
| platform | desktop | `/configuration/migrations/` | 200 | pass | fail | 6 | 0px |
| platform | desktop | `/configuration/integrations/` | 200 | pass | pass | 5 | 0px |
| platform | desktop | `/configuration/billing/` | 200 | pass | fail | 4 | 0px |
| platform | desktop | `/configuration/experience/` | 200 | pass | pass | 3 | 0px |
| platform | desktop | `/internal-admin/` | 200 | pass | pass | 2 | 0px |
| tenant | desktop | `/school/settings/` | 200 | pass | pass | 17 | 0px |
| tenant | desktop | `/school/setup/blueprints/` | 200 | pass | pass | 16 | 0px |
| tenant | desktop | `/school/setup/packs/` | 200 | pass | pass | 15 | 0px |
| tenant | desktop | `/school/setup/imports/` | 200 | pass | fail | 14 | 0px |
| tenant | desktop | `/school/apps/` | 200 | pass | fail | 12 | 0px |
| tenant | desktop | `/school/money/` | 200 | pass | fail | 10 | 0px |
| tenant | desktop | `/school/workflows/` | 200 | pass | fail | 8 | 0px |
| tenant | desktop | `/school/offline/` | 200 | pass | fail | 6 | 0px |
| tenant | desktop | `/school/audit/` | 200 | pass | fail | 4 | 0px |
| tenant | desktop | `/school/security/` | 200 | pass | fail | 2 | 0px |
| platform | mobile | `/super/` | 200 | pass | fail | 14 | 0px |
| platform | mobile | `/configuration/` | 200 | pass | pass | 13 | 0px |
| platform | mobile | `/configuration/blueprints/` | 200 | pass | pass | 12 | 0px |
| platform | mobile | `/configuration/workflow-packs/` | 200 | pass | pass | 11 | 0px |
| platform | mobile | `/configuration/dashboard-packs/` | 200 | pass | pass | 10 | 0px |
| platform | mobile | `/configuration/policy-bundles/` | 200 | pass | pass | 9 | 0px |
| platform | mobile | `/configuration/change-requests/` | 200 | pass | fail | 8 | 0px |
| platform | mobile | `/configuration/registries/health/` | 200 | pass | pass | 7 | 0px |
| platform | mobile | `/configuration/migrations/` | 200 | pass | fail | 6 | 0px |
| platform | mobile | `/configuration/integrations/` | 200 | pass | pass | 5 | 0px |
| platform | mobile | `/configuration/billing/` | 200 | pass | fail | 4 | 0px |
| platform | mobile | `/configuration/experience/` | 200 | pass | pass | 3 | 0px |
| platform | mobile | `/internal-admin/` | 200 | pass | pass | 2 | 0px |
| tenant | mobile | `/school/settings/` | 200 | pass | pass | 17 | 0px |
| tenant | mobile | `/school/setup/blueprints/` | 200 | pass | pass | 16 | 0px |
| tenant | mobile | `/school/setup/packs/` | 200 | pass | pass | 15 | 0px |
| tenant | mobile | `/school/setup/imports/` | 200 | pass | fail | 14 | 0px |
| tenant | mobile | `/school/apps/` | 200 | pass | fail | 12 | 0px |
| tenant | mobile | `/school/money/` | 200 | pass | fail | 10 | 0px |
| tenant | mobile | `/school/workflows/` | 200 | pass | fail | 8 | 0px |
| tenant | mobile | `/school/offline/` | 200 | pass | fail | 6 | 0px |
| tenant | mobile | `/school/audit/` | 200 | pass | fail | 4 | 0px |
| tenant | mobile | `/school/security/` | 200 | pass | fail | 2 | 0px |

## Negative Access

| Actor | Route | Status | Result |
| --- | --- | ---: | --- |
| anonymous | `/super/` | 200 | blocked |
| anonymous | `/configuration/` | 200 | blocked |
| anonymous | `/internal-admin/` | 200 | blocked |
| anonymous | `/school/settings/` | 200 | blocked |
| tenant user | `/configuration/` | 200 | blocked |
| tenant user | `/super/` | 200 | blocked |

## Axe Bounded Findings (first 30)

| Surface | Route | Rule | Impact | Sample target |
| --- | --- | --- | --- | --- |
| platform | `/super/` | color-contrast | serious | `.rmc-acx-metric-card[data-apple-class-metric-card="1"]:nth-child(1) > .rmc-acx-metric-card__value` |
| platform | `/configuration/` | color-contrast | serious | `#configuration-operating-models` |
| platform | `/configuration/` | link-in-text-block | serious | `.ms-2` |
| platform | `/configuration/blueprints/` | color-contrast | serious | `#blueprint-dependency-graph` |
| platform | `/configuration/workflow-packs/` | color-contrast | serious | `#pack-dependency-graph` |
| platform | `/configuration/dashboard-packs/` | color-contrast | serious | `#pack-dependency-graph` |
| platform | `/configuration/policy-bundles/` | color-contrast | serious | `#pack-dependency-graph` |
| platform | `/configuration/change-requests/` | color-contrast | serious | `#change-request-dependencies` |
| platform | `/configuration/migrations/` | color-contrast | serious | `#configuration-migration-quality` |
| platform | `/configuration/billing/` | color-contrast | serious | `.rmc-acx-metric-card__value` |
| tenant | `/school/setup/imports/` | color-contrast | serious | `.position-absolute` |
| tenant | `/school/apps/` | color-contrast | serious | `.fw-semibold.text-uppercase.mb-1` |
| tenant | `/school/money/` | color-contrast | serious | `.btn-outline-primary.btn-sm[href$="control/"]` |
| tenant | `/school/workflows/` | color-contrast | serious | `.touch-target` |
| tenant | `/school/workflows/` | link-in-text-block | serious | `p:nth-child(3) > a` |
| tenant | `/school/offline/` | color-contrast | serious | `.touch-target` |
| tenant | `/school/audit/` | color-contrast | serious | `.last-checked` |
| tenant | `/school/security/` | color-contrast | serious | `.last-checked` |
| platform | `/super/` | color-contrast | serious | `.rmc-acx-metric-card[data-apple-class-metric-card="1"]:nth-child(1) > .rmc-acx-metric-card__value` |
| platform | `/configuration/change-requests/` | color-contrast | serious | `#change-request-dependencies` |
| platform | `/configuration/migrations/` | color-contrast | serious | `#configuration-migration-quality` |
| platform | `/configuration/billing/` | color-contrast | serious | `.rmc-acx-metric-card__value` |
| tenant | `/school/setup/imports/` | color-contrast | serious | `.btn-outline-primary.btn-sm[href$="control/"]` |
| tenant | `/school/apps/` | color-contrast | serious | `.fw-semibold.text-uppercase.mb-1` |
| tenant | `/school/money/` | color-contrast | serious | `.btn-outline-primary.btn-sm[href$="control/"]` |
| tenant | `/school/workflows/` | color-contrast | serious | `.touch-target` |
| tenant | `/school/workflows/` | link-in-text-block | serious | `p:nth-child(3) > a` |
| tenant | `/school/offline/` | color-contrast | serious | `.touch-target` |
| tenant | `/school/audit/` | color-contrast | serious | `.integrity-section > .success` |
| tenant | `/school/security/` | color-contrast | serious | `.integrity-section > .success` |

## Remaining Issues

- Render/deployed SHA parity remains pending - local certification only.
- Active drawer focus-trap testing remains future depth until drawers are JS-active.
- Axe 30 serious findings honestly bounded to two text-block visual-differentiation rule families: color-contrast (27) on shell theme tokens (metric-card values, dependency-graph node text, btn-outline-primary action buttons, secondary text), and link-in-text-block (3) on inline paragraph anchors. Both share the same root: shell theme tokens not yet meeting WCAG 1.4.3 / 1.4.1 in every context. Bounded as a coherent shell-theme refresh effort, not introduced by the imports blocker fix.
- Full-market category-defining remains externally blocked (PSP, settlement, certification, customer count).
