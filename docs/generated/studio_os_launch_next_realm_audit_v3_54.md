# Studio OS Launch — Next-Realm Audit (v3.54, 2026-05-21)

Agent 5 of the 6-agent next-realm fan-out. Owns the Launch section of Studio OS.

## 1. Launch surface inventory

- Mode shell: `templates/studio_os/modes/launch.html` → extends `studio_os/shell.html`
- Modes shell wires `launch_payload`, `launch_role_previews`, `launch_health_summary`, `launch_ready`, `launch_left_rail`, `launch_pane`, `launch_iframe_src`, `launch_studio_base_url`, `school_template_summaries`, `platform_catalog_valid`, `current_blueprint_reference`.
- Routes: `studio_os:launch`, `studio_os:launch_select_plan`, `studio_os:school_infrastructure_{preview,validate,apply}_api`.
- Panes: overview, onboarding, create_school, plan, blueprints, infrastructure, branding, migration, role_preview, checklist (10).
- Native panes: overview, plan, role_preview, infrastructure. Rest iframe.

`launch_payload` schema observed in `apps/setup_studio/services.py::get_setup_studio_payload`:

```
launch_payload = {
  current_step_key, current_step, completed_keys, progress_percent,
  step_state, recommendations, role_previews, preview_cards, preview_workspace,
  launch_checklist, launch_blockers, launch_orchestration,
  health_score, health_breakdown, health_summary, launch_ready,
  recommended_blueprint, blueprint_rankings, recommended_starter_stack,
  migration_path_flow, data_path_choices, recommended_next, registry_alignment,
  steps (computed by get_setup_studio_payload)
}
```

## 2. Overflow risks

| File | Issue | Severity | Mitigation |
|---|---|---|---|
| `launch_school_infrastructure_body.html` | `#studio-infra-diff` table `<th>` "After" cell stringifies up to 500 chars of module list (`school_infrastructure.py:246`); narrow viewport overflow | high | wrap in `.rmc-launch-table-scroll` (overflow-x:auto), `min-width:0` on flex parents, `word-break:break-word` on td |
| `launch_studio_overview_body.html` | starter-stack comma-joined inline; registry alignment rows can have long values | medium | `min-width:0` + `word-break:break-word` on `.rmc-launch-row` |
| `launch_studio_role_preview_pane.html` | long role labels + details push buttons | low | `min-width:0` + word break on `.rmc-launch-role-card` |
| `workspace/launch_canvas.html` | iframe child of workspace main; manager-host fast-path also needs `min-width:0` | low | `.rmc-launch-canvas { min-width: 0 }` |

## 3. Launch readiness model

- `launch_ready = not launch_blockers` (computed in `_score` then re-set at L1536 in `apps/setup_studio/services.py`).
- `health_score` 0-100, computed against `step_state` completion.
- `launch_blockers` is a list of dicts; current UI only renders the **count**, never the contents.
- **No `approvals` field.** Approvals must be inferred from blocker entries or the operator's own admin paths.
- **No `rollout_timeline` field.** `migration_path_flow` is a wizard sequence, not a date-anchored rollout timeline.
- **No `risk_summary` field.**
- `execute_launch(school_id, actor_id)` service exists in `setup_studio/services.py:1643` for go-live, but no UI affordance calls it today (intentionally — operator gating).

## 4. Operator vs tenant launch responsibilities

| Action | Owner | Today's behavior |
|---|---|---|
| Apply school infrastructure pack | Operator | `school_infrastructure_apply_api` always returns 501 "platform-governed" |
| Approve plan / billing entitlement | Operator | No UI yet (plan not productized) |
| Govern rollback | Operator | Honest "disabled unless platform enables rollback" |
| Execute go-live | Operator | `execute_launch` service, no Studio button |
| Complete onboarding steps | Tenant | guided_onboarding iframe pane |
| Sign roles, invite staff | Tenant | wired via launch_role_previews |
| Preview by role | Tenant | role_preview pane |
| Select plan tier | Tenant | placeholder until productized |
| Choose school template (preview only) | Tenant | school_infrastructure preview API |

Gating signal: `request.public_host_kind == 'manager'`.

## 5. Role-preview pane audit

- File: `templates/studio_os/partials/launch_studio_role_preview_pane.html`
- Backing data: `launch_payload.role_previews` (built by `setup_studio.services`)
- Roles surfaced are driven by tenant context (admin/teacher/parent/student/portal typically)
- **Honest empty state already present** — fallback CTAs to guided onboarding + launch overview
- Improvements: lift into `.rmc-launch-role-*` grammar with apple-tier card grid + per-role icon + min-width:0

## 6. Required actions per file

| File | Action |
|---|---|
| `templates/studio_os/modes/launch.html` | minor — link `studio-launch-cockpit.css` |
| `templates/studio_os/partials/launch_mode_canvas.html` | minor — already correct dispatch logic |
| `templates/studio_os/partials/launch_school_infrastructure_body.html` | aggressive refactor — current state panel + preview-of-apply + honest "Operator action required" CTA replacing fake Apply |
| `templates/studio_os/partials/launch_select_plan_body.html` | aggressive refactor — honest "coming soon" with what each side can do today |
| `templates/studio_os/partials/launch_studio_overview_body.html` | **aggressive refactor** — convert to launch readiness command center |
| `templates/studio_os/partials/launch_studio_role_preview_pane.html` | minor repair — extend with rmc-launch-* polish |
| `templates/studio_os/partials/workspace/launch_canvas.html` | minor repair — canvas wrapper class |
| `templates/studio_os/partials/workspace/launch_rail.html` | minor repair — add per-pane icons + aria-current |
| NEW `templates/studio_os/partials/launch_readiness_preview_pane.html` | create — honest per-role preview cockpit |
| NEW `static/css/studio-launch-cockpit.css` | create — `.rmc-launch-*` grammar |
| NEW `apps/studio_os/tests/test_launch_readiness_cockpit.py` | create — render + a11y + gating + money-float guards |

## 7. Coordinator tasks for other agents

1. **Add `launch_timeline` context var** to `studio_shell` (mode=='launch'). Honest empty list when no source. Optionally add `launch_approvals` and `launch_risk_summary`. (Owner: views/services agent.) Suggested diff:

   ```python
   # in studio_shell, after launch_payload assignment:
   context["launch_timeline"] = (
       payload.get("launch_timeline") or []
   )
   context["launch_approvals"] = (
       payload.get("launch_approvals") or []
   )
   context["launch_risk_summary"] = (
       payload.get("launch_risk_summary") or []
   )
   ```

2. **Filename clarification.** `launch_studio_overview_body.html` lives in Launch's ownership but its name implies Overview. Agent 5 has refactored aggressively assuming it is the Launch overview body (consistent with how `launch_mode_canvas.html` includes it on tenant host). If Overview/Agent 1 needs it, revert to regression-only.

3. **Operator request-apply signal.** Expose `launch_can_request_apply` from views to avoid templates inferring from preview JSON.

## 8. Missing context vars handled honestly

- `launch_timeline` → empty-state "Timeline coming online" card.
- `launch_approvals` → empty-state "Approvals tracker pending" (operator-only).
- `launch_risk_summary` → empty-state "No risks flagged".

## 9. Scanner risks (pre-check)

| Scanner | Status |
|---|---|
| `scan_money_float` | clean — no float() on money values added |
| `scan_inline_style_off_token` | clean — no inline literal colors |
| `scan_undefined_css_classes` | new `.rmc-launch-*` defined in `studio-launch-cockpit.css` |
| `scan_off_token_colors` | clean — semantic tokens only |
| `scan_theme_locked_token_text` | clean — semantic-first |
| `scan_sticky_with_overflow_hidden` | clean — no sticky+hidden combination |
| `audit_template_render_safety` | clean — balanced includes |
| `scan_role_strings` | clean — labels from context |
