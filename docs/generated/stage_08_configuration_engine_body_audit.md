# Stage 8 Configuration Engine Body Audit

Generated: 2026-07-09

Source prompt: `docs/prompts/stage-08-configuration-engine-body.md`

This pass is audit-first. It does not change production templates. The output below maps the real configuration body surfaces in the repository and defines the approved implementation target that should be built only after visual approval.

## Scope

Primary target: Core Configuration & Metadata Settings Engine body.

Secondary target: Day-to-Day Operations Workspace body, audit only.

Explicit boundary: no sidebar, header, or footer redesign in this stage.

## Route And Template Inventory

| Surface | Route or namespace | Current template/body | Stage 8 status |
| --- | --- | --- | --- |
| Tenant runtime configuration snapshot | `/siteconfig/configuration/runtime/` | `templates/siteconfig/partials/tenant_runtime_configuration_hub_body.html` | Needs redesign |
| Metadata and lineage hub | `/siteconfig/metadata/` | `templates/siteconfig/metadata_operator_hub.html` | Needs merge into engine canvas |
| Dynamic fields/EAV surface | `/siteconfig/metadata/dynamic-fields/` | `templates/siteconfig/metadata_dynamic_fields_operator.html` | Needs true field-builder body |
| Grading settings | `/siteconfig/grading-settings/` | `templates/siteconfig/grading_settings.html` | Needs formula matrix and live impact preview |
| Grading scale bands | `/siteconfig/grading-scale-bands/` | `templates/siteconfig/grading_scale_bands.html` | Needs relation to formula matrix |
| Academic years evidence | `/siteconfig/reports/academic-years/` | `templates/siteconfig/partials/academic_years_setup_evidence_body.html` | Needs lifecycle control model, not only evidence table |
| Billing/plan readonly | `/siteconfig/billing/plan/` | `templates/siteconfig/partials/billing_plan_readonly_body.html` | Needs PPP/local fee matrix integration |
| Tenant billing estimate | `/siteconfig/api/billing-estimate/` | API route from `tenant_billing_estimate_view` | Needs preview rail integration |
| Report card builder | `/siteconfig/reports/builder/` | `templates/siteconfig/partials/reportcard_builder_inner.html` | Has live preview, but should align to shared engine contract |
| Dashboard role configuration | `/siteconfig/dashboard-configuration/` | `templates/siteconfig/partials/dashboard_configuration_hub_body.html` | Has live preview sidecar and can be used as reference |
| Feature control | `/siteconfig/feature-control/` | `templates/siteconfig/feature_control_panel_content.html` | Has command layout and diff preview, should align to engine contract |
| Theme and experience | `/siteconfig/theme-colors/` and `/siteconfig/theme-experience/hub/` | `templates/siteconfig/partials/theme_colors_page_body.html`, `templates/siteconfig/partials/theme_experience_hub_body.html` | Has preview, but current form density and grid behavior need standardization |
| Platform configuration center | `/configuration/` | `templates/platform_runtime/configuration_center.html` | Good module hub, but not yet a body-level engine for metadata/formula/pricing/year control |
| Tenant school configuration center | `/configuration/`, `/school/configuration/` on tenant host | `templates/platform_runtime/school_configuration_center.html` | Good tenant-safe module hub, but lacks a unified configuration engine workspace |
| Studio work modes | `/studio/`, `/studio/experience/`, `/studio/automation/`, `/studio/output/`, `/studio/launch/`, `/studio/control/` | `templates/studio_os/modes/*.html` and `templates/studio_os/partials/workspace/*` | Associated surfaces, not the primary Stage 8 implementation target |

## Findings

### 1. Configuration body is fragmented

The settings engine currently exists as multiple independent pages:

- runtime snapshot
- metadata hub
- dynamic fields
- grading settings
- grading bands
- academic year evidence
- billing/plan estimate
- report card builder
- dashboard configuration
- feature control
- theme builder

This makes the product feel like links to separate tools instead of one programmable configuration engine.

Fix: create one shared body contract for the Core Configuration & Metadata Settings Engine. It should compose these areas into a full-width engine body with shared navigation, shared live preview, shared publish gate, and shared audit evidence.

### 2. Runtime metadata/EAV is read-first, not builder-first

`metadata_operator_hub.html` and the tenant runtime hub link to dynamic fields, but the body does not present a first-class field builder with:

- entity selector
- field type picker
- validation rules
- visibility scope
- tenant/operator ownership
- preview of resulting student/staff/admission forms
- publish impact and rollback

Fix: make runtime metadata the left lane of the engine. The admin raw CRUD path remains an advanced fallback, not the main body.

### 3. Grading settings are too form-like

`grading_settings.html` is a simple form for grading scale, language, and homework component. It does not show formula composition, component weights, regional rule inheritance, report-card impact, or preview before save.

Fix: replace the body model with a formula matrix:

- rows: assessment components
- columns: weight, cap, required evidence, term behavior, report-card output
- live grade calculation sample
- warnings for overweight or missing components
- preview in report card and teacher gradebook contexts

### 4. PPP/local pricing is not part of the configuration body

Billing exists in separate plan and estimate surfaces. The Stage 8 requirement calls for PPP invoicing and local pricing matrix clarity. The current configuration center does not expose this as an editable or previewable body lane.

Fix: add a localized fee matrix lane:

- currency and market profile
- PPP multiplier
- invoice cycle
- fee item type
- tax/discount/sponsorship notes
- student-family invoice preview
- operator policy guard for platform-owned pricing

### 5. School-year lifecycle is evidence-only

`academic_years_setup_evidence_body.html` is a narrow read-only table. It proves data exists, but it does not act like a lifecycle control surface.

Fix: add a year lifecycle lane:

- draft year
- active year
- closing year
- locked/archive state
- branch/clone from prior year
- readiness checklist
- irreversible action guard
- dry-run preview of class, term, fee, report, and workflow effects

### 6. Live preview is inconsistent

Good references already exist:

- dashboard role preview sidecar
- report card builder preview controls and popout
- feature control diff preview
- theme live preview and publish guard

But the preview contract is not universal. Runtime metadata, grading, PPP billing, and academic-year lifecycle do not all provide the same 100 percent preview options.

Fix: standardize a live preview rail:

- inline preview when supported
- popout preview for complex surfaces
- open-in-new-tab preview as fallback
- device and role selector
- preview evidence strip
- preview-required publish guard for high-impact changes

### 7. Some evidence pages are too narrow

Several body partials use `container` plus `max-width: var(--rmc-report-measure)`, especially report/evidence surfaces. That is acceptable for text reports, but not for the configuration engine. The engine body must use full-width `container-fluid` and a dense but controlled canvas.

Fix: the engine body should not inherit narrow evidence-page layout. Evidence tables can remain narrow when opened directly, but inside the engine they should appear as side panels or drilldowns.

## Day-To-Day Operations Workspace Audit Notes

This pass sampled:

- `templates/accounts/backend_dashboard.html`
- `templates/accounts/workflow_center.html`
- `templates/accounts/partials/workflow_center_main.html`

Findings:

- The day-to-day workspace already has a stronger operational bento and command layout than older configuration pages.
- It still has legacy fallback density and long conditional sections that should be audited separately.
- Workflow Center has a better body contract than most configuration pages: main lane plus side rail.
- No Stage 8 production change should be made to operations pages unless needed to support the configuration engine contract.

Future operations body audit should focus on:

- eliminating duplicated hero/strip patterns
- verifying no hidden legacy dashboard renders under current mode
- reducing long-scroll dashboard fallback sections
- ensuring every operational action has preview/simulation where it changes configuration

## Proposed Shared Body Contract

Create a shared body pattern named:

`configuration-engine-canvas`

Recommended implementation shape:

- `templates/siteconfig/partials/configuration_engine_canvas_body.html`
- `templates/siteconfig/configuration_engine.html`
- `static/css/configuration-engine-canvas.css`
- `static/js/configuration-engine-preview.js`

Body regions:

1. Command strip
   - tenant/operator scope
   - active region
   - draft/publish state
   - preview-required warnings

2. Engine lanes
   - Runtime metadata builder
   - Grading/formula matrix
   - PPP/local pricing matrix
   - School-year lifecycle

3. Live preview rail
   - role selector
   - device selector
   - inline preview
   - popout preview
   - new-tab preview
   - evidence and publish gate

4. Audit and rollback footer
   - change summary
   - owner/scope
   - approval state
   - rollback snapshot

## Approval Artifact

Browser-ready mockup:

`var/design-previews/stage-08-configuration-engine-before-after.html`

Latest approval-preview revision:

- Adds tenant header correction: `More` sits on the same line as `Home`, `Finance`, `Messages`, and `Analytics`; global search is compressed so navigation can move closer to center.
- Adds tenant Studio work-mode contract for Overview, Experience, Automation, Outputs, Launch, and Control.
- Adds Theme/Experience preview requirement: inline preview is first-class, with popout, new-tab, cached last-good state, and screenshot/evidence fallback if embedding fails.
- Adds Django configuration body contract for operator and tenant backend/configuration pages: full-width form body, sticky actions, grouped fields, right-side intelligence/audit rail, and explicit tenant/operator boundary state.
- Adds audit rule: no body may contain a large blank chasm, unmanaged overlap, unusable preview lane, or narrow inherited Django form when a full-width configuration surface is appropriate.

World-class approval revision:

- Raises the design target from "fixed layout" to a reusable command-fabric standard for tenant and operator configuration pages.
- Requires aggressive use of screen real estate without cramping: left mode rail, center workbench, right safety/preview rail, and independent scroll boundaries.
- Treats the following as blocking visual defects across tenant and operator pages: overlapping panels, leaking text, body sections rendering under the footer, preview lanes too narrow to inspect, dead center space, and inherited Django forms floating in empty width.
- Requires the audit page to inventory every matching route/template before implementation is considered complete.
- Requires approved fixes to be applied platform-wide and tenant-wide, not only to the single route used for the screenshot.

Next-level approval revision:

- Adds configuration intelligence strips so users see impact, scope, preview state, and rollback posture before acting.
- Adds Studio journey maps for each mode so configuration work has a visible path from scope to publish.
- Adds mode-specific impact/audience/recovery panels instead of generic repeated cards.
- Adds a live-preview fallback matrix: inline, popout inspector, new-tab proof, last-good preview, and evidence capture.
- Adds Django conversion rules for inherited admin pages: full-width grouped task bodies, tenant/operator scope indicators, long-value inspectors, and permission previews.
- Adds audit scoring and heatmap targets so the implementation loop can report route coverage, visual pass rate, boundary pass rate, and preview fallback pass rate.

Space-intelligence approval revision:

- Primary pages must stay spacious. The main workbench should remain the dominant surface instead of being squeezed by permanent helper columns.
- Inline content is allowed only when it remains readable and does not reduce the workbench below the target width.
- Live preview must not be cramped. If a preview cannot be inspected comfortably inline, it must open as a large modal, popout inspector, or signed tenant-route new tab.
- Audit trails, long values, JSON, field history, recommendations, preview errors, and contextual help should move to drawers, inspectors, popovers, or modals when always-visible placement would steal useful space.
- Every approval mockup and implementation audit must show itemized improvements: current problem, improved behavior, and proof required.
- Blocking defects now include cramped inline preview, support panels stealing permanent width without active use, missing modal/popout/new-tab fallback for previewable changes, and long content leaking outside containers.

## Implementation Gate

Do not modify production templates until the before/after mockup is approved.

Once approved, implement in this sequence:

1. Create shared engine canvas CSS/JS and template partial.
2. Wire tenant runtime configuration into the canvas.
3. Add metadata/EAV builder body lane.
4. Add grading formula matrix lane.
5. Add PPP/local fee matrix lane.
6. Add school-year lifecycle lane.
7. Standardize live preview fallback options.
8. Reuse the contract in report card builder, feature control, and theme experience where appropriate.
9. Apply the tenant Studio body contract to Overview, Experience, Automation, Outputs, Launch, and Control.
10. Apply the full-width Django configuration body contract to tenant backend/configuration pages and operator Django pages where the inherited narrow layout is still used.
11. Verify tenant/backend links never redirect to operator `/admin/` or `/super/` unless the surface is explicitly operator-owned.
12. Run route/template inventory and visual smoke tests.
13. Update this audit with implemented/remaining status.
