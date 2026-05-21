# Studio OS Automation — Next-Realm Audit (v3.54, 2026-05-21)

**Agent 3 of 6** owns Automation. This audit precedes the Phase B implementation.

## 1. Current surface inventory

### Templates (Agent 3-owned)

| File | Purpose | State |
|---|---|---|
| `templates/studio_os/modes/automation.html` | Mode shell — extends `studio_os/shell.html`, renders hero + guidance + mode_canvas | Functional but lacks per-section CSS link |
| `templates/studio_os/partials/automation_mode_canvas.html` | Tenant vs operator branching; tenant gets workspace_layout, operator host gets legacy two-pane | Functional; ok |
| `templates/studio_os/partials/workspace/automation_canvas.html` | Pane dispatcher: overview / dependency / health / explainer / iframe / fallback | Functional but overview lacks cockpit summary tiles |
| `templates/studio_os/partials/workspace/automation_rail.html` | Sub-tool list rendered from `automation_left_rail` (13 entries) | Functional, plain ul. No icons/secondary text. |
| `templates/studio_os/partials/automation_overview_body.html` | Row of pack-graph (col-lg-6) + workflow-health (col-lg-6) + CTAs | Lacks summary tiles + simulation preview pane |
| `templates/studio_os/partials/automation_workflow_health_body.html` | `pack_count` + `template_count` list | Honest but thin — only 2 metrics |
| `templates/studio_os/partials/automation_dependency_graph_body.html` | Pack → templates nested ul | Overflow risk: no min-w-0, no word-break on `<code>` |
| `templates/studio_os/partials/automation_environment_banner.html` | staging vs production, publish/rollback readiness | No tenant/operator scope label |
| `templates/studio_os/partials/automation_explainer_in_canvas.html` | Simple title/subtitle/body card for explainer panes | Ok |

### Routes (read-only)

| Route name | View (apps/studio_os/views.py) | Real or scaffolded? |
|---|---|---|
| `automation_conflict_detection` | line 816 | Explainer page; no real conflict engine in studio_os |
| `automation_staged_activation` | line 846 | Explainer page |
| `automation_replay_rollback` | line 876 | Explainer page; links to `studio_os:rollback` (REAL) |
| `automation_visual_builder` | line 939 | Explainer + REAL link to `apps.automation:visual_workflow_designer` |
| `automation_natural_language_workflow` | line 975 | Explainer-only; no NL→workflow engine |
| `automation_simulation_engine` | line 990 | **PARTIAL-REAL**: pulls `canonical_triggers` + `ready_playbooks`, exposes `apps.automation:visual_workflow_simulate` URL |
| `automation_dependency_graph` | line 1087 | REAL: `get_automation_dependency_graph()` over `WorkflowPack` |
| `automation_workflow_health` | line 1117 | REAL but thin: only `pack_count` + `template_count` |

### Shell context vars (mode='automation' branch, views.py:1565-1706)

`automation_pane`, `automation_conflict_pane_url`, `automation_iframe_src`, `automation_dependency_graph`, `automation_health_summary` ({pack_count, template_count}), `automation_workflow_center_pane_url`, `automation_simulation_pane_url`, `automation_explainer`, `automation_left_rail` (13 entries), `automation_simulation_summary` (string), `automation_environment` ({staging_package_count, production_package_count, staging_vs_production_detail, workflow_simulation_ready, publish_readiness, rollback_readiness}), `workflow_entries` (always `[]`).

## 2. Overflow risks (per ownership scope)

| File:line | Failure mode | Fix |
|---|---|---|
| `automation_dependency_graph_body.html:3-23` | Long pack/template names + `<code>` in nested `<ul>` overflow narrow column | Wrap in `.rmc-automation-graph-scroll{overflow-x:auto; min-width:0; word-break:break-word}` |
| `automation_workflow_health_body.html:4-7` | Long template names don't wrap | Apply `word-break:break-word` + responsive `.rmc-automation-metric` |
| `automation_overview_body.html:11-19` | `.row.g-3` columns lack `.min-w-0` — flex child cannot shrink under content width | Add `min-w-0` to `.col-lg-6` |
| `workspace/automation_rail.html:5-11` | Long pane labels overflow 12.5rem rail | `.automation-rail-link{word-break:break-word}` |

## 3. Simulation preview model

**State: PARTIAL-REAL.** `studio_automation_simulation_engine` (views.py:990) resolves URLs to:
- `apps.automation:visual_workflow_simulate` (real simulate API)
- `apps.automation:visual_workflow_dispatch_test`
- `apps.automation:visual_workflow_publish`
- `apps.automation:outcomes_console`
- pulls `canonical_triggers` per school + `ready_playbooks`

**Gap:** The in-shell pane (canvas) currently renders only the explainer body. The cockpit does NOT show projected actions / would-be-affected-records / risk warnings. Operator must navigate to subpage AND then to `visual_workflow_designer`.

**Honest deferral:** Build `automation_simulation_preview_pane.html` partial. Render an honest empty state when no simulation has been run. Provide "Run simulation" CTA wired to `apps.automation:visual_workflow_simulate`. Do NOT fabricate simulation results.

## 4. Approval / rollback / staged-activation flow

- Approval hub: `studio_os:approval_hub` (real, `apps.accounts.views_workflow.approval_workflow_hub`)
- Rollback: `studio_os:rollback?mode=automation` (real)
- Staged activation: explainer-only; no real engine endpoint in this scope
- Replay/rollback: explainer-only; links to `studio_os:rollback`

**Risk indicators:** environment banner has `publish_readiness.ready` + `rollback_readiness.available` booleans. No granular per-workflow risk badges.

**Gap:** No approval queue tile on the Automation cockpit canvas. No "recent runs" surface. No rollback availability badge separate from environment banner.

## 5. Tenant vs operator scope

- **Operator (`request.public_host_kind == 'manager'`)** sees same partial set; per `automation_mode_canvas.html:3-4`, workspace_layout is DISABLED on manager host (operator gets legacy two-pane), which is acceptable.
- **Tenant scope** is implicit: `WorkflowPack` queryset is school-scoped, `canonical_triggers` are pulled `for_school(school_id)`.

**Gap:** No visible tenant scope label in environment banner. Operator can't tell if they're seeing platform-level or tenant-level state.

## 6. Destructive-action gating

- Today: Automation partials do NOT expose Activate / Run now / Delete trigger buttons. Subpage explainers link out to `apps.automation` routes — destructive gating lives there.
- No shared `data-rmc-confirm` reader exists in `static/js/_pages/studio_os__shell.js` (verified by grep).
- **Decision:** Use `data-rmc-confirm="..."` attribute marker AND `onclick="return confirm(...)"` fallback. Flag the missing shared reader as a coordinator task.

## 7. Required actions

| File | Action | Reason |
|---|---|---|
| `templates/studio_os/modes/automation.html` | Minor repair | Wire `studio-automation-cockpit.css` |
| `templates/studio_os/partials/automation_mode_canvas.html` | Minor repair | Always include environment_banner regardless of pane |
| `templates/studio_os/partials/workspace/automation_canvas.html` | Aggressive refactor | Cockpit summary tiles on overview pane + embed simulation_preview_pane |
| `templates/studio_os/partials/workspace/automation_rail.html` | Aggressive refactor | 8+ sub-tools w/ icon + label + secondary text; word-break |
| `templates/studio_os/partials/automation_overview_body.html` | Aggressive refactor | Summary tiles (active/paused/failing) + responsive min-w-0 |
| `templates/studio_os/partials/automation_workflow_health_body.html` | Minor repair | Word-break + responsive .rmc-automation-metric grid |
| `templates/studio_os/partials/automation_dependency_graph_body.html` | Minor repair | Horizontally-scrollable container |
| `templates/studio_os/partials/automation_environment_banner.html` | Minor repair | Add operator-vs-tenant scope label |
| `templates/studio_os/partials/automation_explainer_in_canvas.html` | Keep | Already responsive |
| `templates/studio_os/partials/automation_simulation_preview_pane.html` | **Create** | Honest empty state; trigger/actions/risks/record-count |
| `static/css/studio-automation-cockpit.css` | **Create** | `.rmc-automation-*` grammar |
| `apps/studio_os/tests/test_automation_simulation_cockpit.py` | **Create** | Cockpit-specific tests |

## 8. Coordinator tasks (flagged for parent agent)

1. **Shared `rmc-confirm` JS handler** — add a listener in `static/js/_pages/studio_os__shell.js` that reads `data-rmc-confirm` and prompts before action. We use `onclick='return confirm(...)'` fallback with parallel `data-rmc-confirm` attribute for forward compat.
2. **Granular workflow status counts** — `apps/studio_os/services.py::get_automation_workflow_health_summary` returns only `pack_count` + `template_count`. Cockpit needs `active` / `paused` / `failing` counts. We render "unknown" badges and read defensively (`|default:0` chain).
3. **Approval queue summary count** — surface `approval_hub` queue size in context so the cockpit tile can show it. Today we link out only.
4. **Recent runs / last simulation timestamp** — banner needs "Last simulation: 12 min ago". No plumbing today.
5. **Tenant scope label** — expose `request.tenant.display_name` (NOT slug) in context so banner can read "School automations: Westwood High".

## 9. Scanner risk assessment

| Scanner | Risk | Notes |
|---|---|---|
| `scan_undefined_css_classes` | 0 | All `.rmc-automation-*` classes defined in `studio-automation-cockpit.css` |
| `scan_inline_style_off_token` | 0 | No inline `style=""` |
| `scan_off_token_colors` | 0 | Design tokens only; allow-markers where intentional |
| `scan_theme_locked_token_text` | 0 | Semantic tokens (`--text-*`/`--surface-*`/`--hairline`) |
| `scan_theme_attribute_contract` | 0 | No `[data-theme]` selectors |
| `scan_print_statements` / `scan_bare_except` | 0 | Test file uses `assertContains` + named exceptions only |
| `audit_template_render_safety` | 0 | All `{% include %}` targets exist; balanced tags |
| `scan_money_float` / `scan_pii_logging_smell` / `scan_drf_schema_coverage` | n/a | No Python view code touched |
