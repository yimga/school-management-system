# Platform Workflow Info-Tags Audit (Phase 3)

_Generated 2026-05-22T17:30:51Z_

Code-truth audit of Phase 3 deliverables: the 4 component partials, workflow_registry.py + workflow_guidance.py modules, and the rmc-workflow-guidance.css bundle. Confirms what landed, taxonomy completeness, and the accessibility/dark-mode contract.

## Summary

- **components_landed**: `4`
- **python_modules_landed**: `2`
- **css_bundles_landed**: `1`
- **registry_workflow_count**: `16`
- **tag_taxonomy_count**: `20`
- **audience_constant_count**: `7`
- **css_rules_count**: `65`
- **css_off_token_markers**: `4`
- **css_sticky_overflow_markers**: `0`
- **templates_with_inline_style_attr**: `0`

## Tag taxonomy (20 constants)

  `ai-help-available`, `approval-required`, `audit-logged`, `billing-impact`, `blocks-launch`, `data-quality-issue`, `draft`, `external-required`, `manual-fallback`, `missing-setup`, `needs-review`, `not-reversible`, `optional`, `platform-only`, `preview-available`, `published`, `ready-to-launch`, `required`, `reversible`, `tenant-safe`

## Audience constants (7)

  `founder`, `operator`, `parent`, `public`, `student`, `teacher`, `tenant-admin`

## Registry — 16 workflows seeded

- `billing-set-up-tenant` — Billing — Set up tenant billing
- `marketplace-install-app` — Marketplace — Install an app
- `migration-cloud-connect-sis` — Migration Cloud — Connect SIS
- `migration-cloud-operator-health` — Migration Cloud — Operator health dashboard
- `migration-cloud-sign-maa` — Migration Cloud — Sign MAA
- `operator-tenant-lifecycle` — Operator — Tenant lifecycle
- `parent-portal-link-child` — Parent portal — Link a child
- `parent-portal-pay-invoice` — Parent portal — Pay invoice
- `studio-os-automation` — Studio OS — Automation mode
- `studio-os-control` — Studio OS — Control mode
- `studio-os-experience` — Studio OS — Experience mode
- `studio-os-launch` — Studio OS — Launch mode
- `studio-os-output` — Studio OS — Output mode
- `support-help-hub` — Support — Help hub
- `teacher-enter-marks` — Teacher — Enter marks
- `teacher-take-attendance` — Teacher — Take daily attendance

## Audience distribution

- `n`: 32
- `t`: 26
- `a`: 26
- `e`: 18
- `-`: 10
- `d`: 10
- `m`: 10
- `i`: 10
- `r`: 8
- `o`: 4
- `p`: 4
- `c`: 2
- `h`: 2

## Components landed

| Component | Path | Lines |
|---|---|---:|
| `workflow_info_tag.html` | `templates/components/workflow_info_tag.html` | 18 |
| `workflow_help_panel.html` | `templates/components/workflow_help_panel.html` | 80 |
| `workflow_next_action.html` | `templates/components/workflow_next_action.html` | 73 |
| `workflow_status_strip.html` | `templates/components/workflow_status_strip.html` | 61 |

## Accessibility contract

- Tags carry text labels (never icon-only)
- Color via var(--*) tokens only — no off-token literals
- WCAG AA contrast (>= 4.5:1) — enforced by scan_color_contrast.py baseline 0
- Dark/light parity via [data-theme=*] selectors
- No position: sticky + overflow: hidden combos (enforced by scan_sticky_with_overflow_hidden.py baseline 0)
- Mobile-safe via existing portal/marketing responsive grammar

## CI gates relevant to Phase 3

| Gate | Baseline | Applies to |
|---|---:|---|
| `audit_template_render_safety.py` | 0 | 4 new component templates must be clean |
| `scan_off_token_colors.py` | 0 | rmc-workflow-guidance.css must not introduce off-token literals |
| `scan_inline_style_off_token.py` | 0 | no inline style= attributes that bypass tokens |
| `scan_csp_nonce_emission.py` | 0 | any inline script gets nonce |
| `scan_undefined_css_classes.py` | 0 | all .rmc-workflow-* classes defined in the bundle |

## Honest deferrals

- Component wiring into shells — Phase 3 ships scaffolding only; Phase 4 wires into representative pages
- Template-tag library (workflow_guidance) — Phase 4 ships the {% load workflow_guidance %} filters
- Phase 11 tests (apps.platform_runtime.tests.test_workflow_registry / test_workflow_info_tags / test_workflow_guidance_contracts)

**Verdict:** `PHASE_3_INFO_TAGS_READY`
