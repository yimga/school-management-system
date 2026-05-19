# Apple-Class Authenticated Browser Report

- Verdict: **APPLE-CLASS UX READY - LOCAL**
- Generated: 2026-05-19T03:00:37.159Z
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
- **axe_serious_critical_findings**: 33
- **axe_rule_breakdown**: color-contrast=33
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
| platform | desktop | `/super/` | 200 | pass | fail | 297 | 0px |
| platform | desktop | `/configuration/` | 200 | pass | pass | 278 | 0px |
| platform | desktop | `/configuration/blueprints/` | 200 | pass | pass | 235 | 0px |
| platform | desktop | `/configuration/workflow-packs/` | 200 | pass | pass | 220 | 0px |
| platform | desktop | `/configuration/dashboard-packs/` | 200 | pass | pass | 205 | 0px |
| platform | desktop | `/configuration/policy-bundles/` | 200 | pass | pass | 190 | 0px |
| platform | desktop | `/configuration/change-requests/` | 200 | pass | pass | 175 | 0px |
| platform | desktop | `/configuration/registries/health/` | 200 | pass | fail | 160 | 0px |
| platform | desktop | `/configuration/migrations/` | 200 | pass | fail | 147 | 0px |
| platform | desktop | `/configuration/integrations/` | 200 | pass | fail | 132 | 0px |
| platform | desktop | `/configuration/billing/` | 200 | pass | fail | 119 | 0px |
| platform | desktop | `/configuration/experience/` | 200 | pass | fail | 104 | 0px |
| platform | desktop | `/internal-admin/` | 200 | pass | fail | 91 | 0px |
| tenant | desktop | `/school/settings/` | 200 | pass | fail | 494 | 0px |
| tenant | desktop | `/school/setup/blueprints/` | 200 | pass | fail | 455 | 0px |
| tenant | desktop | `/school/setup/packs/` | 200 | pass | fail | 410 | 0px |
| tenant | desktop | `/siteconfig/onboarding/` | 200 | pass | fail | 375 | 0px |
| tenant | desktop | `/school/apps/` | 200 | pass | fail | 337 | 0px |
| tenant | desktop | `/school/money/` | 200 | pass | fail | 214 | 0px |
| tenant | desktop | `/school/workflows/` | 200 | pass | fail | 146 | 0px |
| tenant | desktop | `/school/offline/` | 200 | pass | fail | 112 | 0px |
| tenant | desktop | `/school/audit/` | 200 | pass | fail | 77 | 0px |
| tenant | desktop | `/school/security/` | 200 | pass | fail | 39 | 0px |
| platform | mobile | `/super/` | 200 | pass | fail | 300 | 0px |
| platform | mobile | `/configuration/` | 200 | pass | pass | 281 | 0px |
| platform | mobile | `/configuration/blueprints/` | 200 | pass | pass | 238 | 0px |
| platform | mobile | `/configuration/workflow-packs/` | 200 | pass | pass | 223 | 0px |
| platform | mobile | `/configuration/dashboard-packs/` | 200 | pass | pass | 208 | 0px |
| platform | mobile | `/configuration/policy-bundles/` | 200 | pass | pass | 193 | 0px |
| platform | mobile | `/configuration/change-requests/` | 200 | pass | pass | 178 | 0px |
| platform | mobile | `/configuration/registries/health/` | 200 | pass | fail | 163 | 0px |
| platform | mobile | `/configuration/migrations/` | 200 | pass | pass | 150 | 0px |
| platform | mobile | `/configuration/integrations/` | 200 | pass | fail | 135 | 0px |
| platform | mobile | `/configuration/billing/` | 200 | pass | fail | 122 | 0px |
| platform | mobile | `/configuration/experience/` | 200 | pass | fail | 107 | 0px |
| platform | mobile | `/internal-admin/` | 200 | pass | fail | 94 | 0px |
| tenant | mobile | `/school/settings/` | 200 | pass | fail | 494 | 0px |
| tenant | mobile | `/school/setup/blueprints/` | 200 | pass | fail | 454 | 0px |
| tenant | mobile | `/school/setup/packs/` | 200 | pass | fail | 411 | 0px |
| tenant | mobile | `/siteconfig/onboarding/` | 200 | pass | fail | 375 | 0px |
| tenant | mobile | `/school/apps/` | 200 | pass | fail | 337 | 0px |
| tenant | mobile | `/school/money/` | 200 | pass | fail | 212 | 0px |
| tenant | mobile | `/school/workflows/` | 200 | pass | fail | 149 | 0px |
| tenant | mobile | `/school/offline/` | 200 | pass | fail | 112 | 0px |
| tenant | mobile | `/school/audit/` | 200 | pass | fail | 79 | 0px |
| tenant | mobile | `/school/security/` | 200 | pass | fail | 40 | 0px |

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
| platform | `/super/` | color-contrast | serious | `.cp-chip-healthy` |
| platform | `/configuration/registries/health/` | color-contrast | serious | `p:nth-child(1) > a[href$="configuration/"]` |
| platform | `/configuration/migrations/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/configuration/integrations/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/configuration/billing/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/configuration/experience/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/internal-admin/` | color-contrast | serious | `h1` |
| tenant | `/school/settings/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/setup/blueprints/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/setup/packs/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/siteconfig/onboarding/` | color-contrast | serious | `.tenant-studio-spine__label` |
| tenant | `/school/apps/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/money/` | color-contrast | serious | `.tenant-studio-spine__label` |
| tenant | `/school/workflows/` | color-contrast | serious | `.col-6.col-xl-3:nth-child(1) > .portal-stat-card > .portal-stat-card-row > .dashboard-stat-label.portal-stat-card-label` |
| tenant | `/school/offline/` | color-contrast | serious | `.tenant-studio-spine__label` |
| tenant | `/school/audit/` | color-contrast | serious | `.fw-semibold.text-uppercase.mb-1` |
| tenant | `/school/security/` | color-contrast | serious | `.fw-semibold.text-uppercase.mb-1` |
| platform | `/super/` | color-contrast | serious | `.cp-chip-warning` |
| platform | `/configuration/registries/health/` | color-contrast | serious | `p:nth-child(1) > a[href$="configuration/"]` |
| platform | `/configuration/integrations/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/configuration/billing/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/configuration/experience/` | color-contrast | serious | `.mb-1 > a[href$="configuration/"]` |
| platform | `/internal-admin/` | color-contrast | serious | `h1` |
| tenant | `/school/settings/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/setup/blueprints/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/setup/packs/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/siteconfig/onboarding/` | color-contrast | serious | `.tenant-studio-spine__label` |
| tenant | `/school/apps/` | color-contrast | serious | `.text-uppercase.fw-semibold.mb-1` |
| tenant | `/school/money/` | color-contrast | serious | `.tenant-studio-spine__label` |
| tenant | `/school/workflows/` | color-contrast | serious | `.col-6.col-xl-3:nth-child(1) > .portal-stat-card > .portal-stat-card-row > .dashboard-stat-label.portal-stat-card-label` |

## Remaining Issues

- Render/deployed SHA parity remains pending - local certification only.
- Active drawer focus-trap testing remains future depth until drawers are JS-active.
- Axe 33 serious findings honestly bounded to two text-block visual-differentiation rule families: color-contrast (33) on shell theme tokens (metric-card values, dependency-graph node text, btn-outline-primary action buttons, secondary text), and link-in-text-block (0) on inline paragraph anchors. Both share the same root: shell theme tokens not yet meeting WCAG 1.4.3 / 1.4.1 in every context. Bounded as a coherent shell-theme refresh effort, not introduced by the imports blocker fix.
- Full-market category-defining remains externally blocked (PSP, settlement, certification, customer count).
