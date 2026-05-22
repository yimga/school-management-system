# Platform How-To System Audit (Phase 2)

_Generated 2026-05-22T17:30:51Z_

Pairs with the spec at [`docs/architecture/RUNMYCAMPUS_WORKFLOW_HOW_TO_SYSTEM.md`](../architecture/RUNMYCAMPUS_WORKFLOW_HOW_TO_SYSTEM.md). Captures **what already exists on disk** for help / AI guidance / feedback coverage, what Phase 3 landed, and where Phase 4+ needs to wire.

## Summary

- **apps_with_routes**: `27`
- **apps_with_help_template_in_templates_dir**: `6`
- **apps_importing_services_ai_helpers**: `13`
- **apps_importing_feedback**: `6`
- **help_template_files_count**: `17`
- **howto_template_files_count**: `0`
- **faq_template_files_count**: `7`
- **phase3_components_present**: `True`
- **phase3_workflow_registry_present**: `True`
- **phase3_workflow_guidance_present**: `True`
- **phase3_css_bundle_present**: `True`

## Phase 3 landed artifacts

**templates:**
- `templates/components/workflow_info_tag.html`
- `templates/components/workflow_help_panel.html`
- `templates/components/workflow_next_action.html`
- `templates/components/workflow_status_strip.html`

**python_modules:**
- `apps/platform_runtime/workflow_registry.py`
- `apps/platform_runtime/workflow_guidance.py`

**css_bundles:**
- `static/css/rmc-workflow-guidance.css`

## Existing help/howto/FAQ template inventory (24 files)

**Help templates:**
- `templates/components/was_this_helpful.html`
- `templates/components/workflow_help_panel.html`
- `templates/feedback/help_center.html`
- `templates/feedback/partials/help_center_engage_strip.html`
- `templates/feedback/partials/help_center_quick_feature.html`
- `templates/marketing/partials/mkt_help_engine.html`
- `templates/marketing/partials/mkt_help_hub.html`
- `templates/partials/help_community_lane.html`
- `templates/partials/help_contextual_drawer.html`
- `templates/partials/help_deflection_strip.html`
- `templates/partials/help_module_inline_assistant.html`
- `templates/partials/help_persona_quickstart.html`
- `templates/partials/help_proactive_nudge.html`
- `templates/portal/email/help_north_star_report.html`
- `templates/portal/support_help_hub.html`
- `templates/schools/partials/manager_help_analytics_body.html`
- `templates/schools/partials/manager_help_center_body.html`

**FAQ templates:**
- `templates/apicenter/super/ai_center_faq_candidates.html`
- `templates/marketing/components/_faq_accordion.html`
- `templates/portal/faq_detail.html`
- `templates/portal/faq_list.html`
- `templates/portal/faq_submit.html`
- `templates/portal/operator/faq_detail_body.html`
- `templates/portal/operator/faq_list_body.html`

## Apps importing `services.ai_helpers` (AI-hook capable, 13)

  `analytics`, `api`, `automation`, `communication`, `dashboard`, `finance`, `migration_cloud`, `observability`, `people`, `platform_runtime`, `portal`, `siteconfig`, `studio_os`

## Apps importing `apps.feedback` (6)

  `customersuccess`, `feedback`, `observability`, `portal`, `schools`, `siteconfig`

## Gaps

### `apps_with_routes_no_help_no_ai_no_feedback` (12 apps)

  `academics`, `compliance`, `evals`, `events`, `integrations_marketplace`, `metadata`, `orchestration`, `payroll`, `reports`, `requests`, `sales`, `school_events`

### `apps_with_routes_no_help` (24 apps)

  `academics`, `accounts`, `analytics`, `api`, `apicenter`, `automation`, `communication`, `compliance`, `evals`, `events`, `finance`, `integrations_marketplace`, `marketplace`, `metadata`, `migration_cloud`, `orchestration`, `payroll`, `platform_runtime`, `reports`, `requests`, `sales`, `school_events`, `siteconfig`, `studio_os`

### `apps_with_workflow_templates_no_feedback_hook` (16 apps)

  `academics`, `accounts`, `apicenter`, `communication`, `compliance`, `evals`, `events`, `finance`, `marketplace`, `migration_cloud`, `payroll`, `platform_runtime`, `reports`, `requests`, `sales`, `studio_os`

## Phase 4 wiring plan (representative, not exhaustive)

| Target | Workflow key | Components | Closes |
|---|---|---|---|
| `templates/studio_os/modes/output.html` | `studio-os-output` | status_strip, info_tag, next_action, help_panel | Phase 7 OP-1 (no _mode_hero, no primary CTA) |
| `templates/migration_cloud/connector/_wizard_base.html` | `migration-cloud-connect-sis` | status_strip, info_tag, help_panel | — |
| `templates/parent/dashboard.html` | `parent-portal-pay-invoice` | next_action, info_tag | — |

## Honest deferrals

- Operator UI to edit SiteSettings.cockpit_payload.workflow_guidance.<key>.enabled per-tenant — Phase 5/6 audits recommend; Phase 3 left as scaffolding-only
- Promotion of Phase 1's 112-workflow classification matrix into the 16-row registry — rebuild_from_classification_matrix() extension point exists; requires operator review per workflow
- Workflow guidance Django template-tag library — Phase 4 lands the {% load workflow_guidance %} loader

**Verdict:** `PHASE_2_AUDIT_READY`
