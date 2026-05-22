# Studio OS Workflow Gear-Up audit (Phase 7)

_Generated 2026-05-22T12:34:48Z_

**Wave under audit:** v3.54.0 (Studio OS next-realm) + closeout in v3.55.x / v3.57.x

## Scope

Section-by-section workflow readiness audit of the 6 Studio OS sections (Overview / Experience / Automation / Output / Launch / Control). Read-only static walk; no Django boot; complements docs/generated/studio_os_code_truth_inventory.json (v3.54.0) and the 6 v3.54 next-realm audit JSONs without duplicating their per-panel deep-dives.

## Method

**Code walk:**

- `apps/studio_os/urls.py (48 routes verified)`
- `apps/studio_os/navigation.py (STUDIO_MODES + 5 mode focus sidebar builders)`
- `apps/studio_os/views.py:1296-1490 (studio_shell entrypoint context wiring)`
- `apps/studio_os/services.py:1189-1416 (4 v3.54.0 cockpit helpers verified)`
- `apps/studio_os/studio_guidance.py (Overview + 5 mode guidance objects + 9 launch panes)`
- `apps/studio_os/copilot_rail_service.py:186-215 (_RULES_INSIGHTS_BY_SURFACE — all 6 surfaces seeded)`
- `templates/studio_os/shell.html (cockpit chrome + rail + 5-mode nav + per-mode right-rail branches)`
- `templates/studio_os/shell_control_plane.html (manager host shell)`
- `templates/studio_os/modes/{experience,automation,output,launch,control}.html`
- `templates/studio_os/partials/* (40 partials enumerated)`
- `static/css/studio-mode-rail.css:5-20 (v3.54.0 systemic overflow fix verified intact)`

**Verification status legend:**

- `static_only` — Confirmed by code-walk; behavior under real DB / live HTTP not exercised in this phase.
- `verified_in_artifact` — Already certified by an existing audit JSON in docs/generated/.
- `code_truth_confirmed` — Confirmed by direct file read at the cited file:line.

## Horizontal-overflow sanity check (v3.54.0 systemic fix)

**Claim under test:** Memory v3.54.0 states the systemic horizontal-overflow root-cause fix lives at static/css/studio-mode-rail.css:5-14 and covers all 4 mode rails at a single point.

**File:** `static/css/studio-mode-rail.css` lines 5-20

**Rule observed:** `.studio-os__experience-rail a.experience-rail-link, .studio-os__output-rail a.output-rail-link, .studio-os__automation-rail a.automation-rail-link, .studio-os__launch-rail a.launch-rail-link { ... min-width: 0; overflow-wrap: anywhere; word-break: break-word; }`

**Verdict:** `INTACT`

**Notes:**

- Inline v3.54.0 comment at studio-mode-rail.css:14-16 still present.
- All three load-bearing declarations (min-width:0; overflow-wrap:anywhere; word-break:break-word) present on the shared selector.
- Control mode is NOT covered by this shared rule (no `.studio-os__control-rail a.control-rail-link` selector); Control uses governance_rail_to_focus_sidebar() in apps/studio_os/navigation.py:130 + control_plane_sidebar_studio_focus.html. Static walk shows Control rail labels are short (Config center / Feature control / Audit log / etc.), but the absence of the same defensive triple is a latent risk if longer localized governance labels land later — see mode_specific_issues for Control.

**Verification status:** `code_truth_confirmed`

## v3.54.0 honest deferrals — status now

| ID | Memory label | State |
|---|---|---|
| D1 | output_readiness_summary service | `PARTIAL` |
| D2 | automation workflow-health extension (paused / failing counts) | `DONE` |
| D3 | launch_timeline / approvals / risk (get_launch_readiness_summary) | `PARTIAL` |
| D4 | real signal counts for overview_signals | `PARTIAL` |

### D1 — output_readiness_summary service (`PARTIAL`)

**Expected consumer:** templates/studio_os/partials/output_readiness_preview_pane.html + workspace/output_canvas.html

**Evidence:** apps/studio_os/services.py:1319-1373 — get_output_readiness_summary() exists and returns packs_total/packs_with_deps/packs_missing_deps/documents_total/documents_published/service_online. packs_* keys are wired through get_output_dependency_graph(); documents_* keys are best-effort try-import of apps.reports.models.{Report,ReportPack}.

**Still missing:**

- Per-pack listing (only aggregate counts surface)
- Document-published counter depends on Report.is_published — defensive try/except keeps it at 0 when the field is absent
- No call from views.py — the helper is defined but not wired into studio_shell context for mode=='output'; the preview pane consumes whatever output_* context already exists

### D2 — automation workflow-health extension (paused / failing counts) (`DONE`)

**Expected consumer:** automation_workflow_health body + cockpit rail

**Evidence:** apps/studio_os/services.py:1189-1237 — get_automation_workflow_health_summary now returns pack_count + template_count + paused_count + failing_count (paused_count via WorkflowPack.is_active=False; failing_count via apps.orchestration.models.ProcessRun.status='failed'). v3.54.0 comment at line 1196-1197 documents the extension.

**Still missing:**

- Helper still defensive — when WorkflowPack lacks is_active or ProcessRun import fails, both counters silently return 0 (operator cannot distinguish 'zero failing' from 'feature absent'). A service_online discriminator would close the loop.

### D3 — launch_timeline / approvals / risk (get_launch_readiness_summary) (`PARTIAL`)

**Expected consumer:** templates/studio_os/partials/launch_readiness_preview_pane.html + launch canvas

**Evidence:** apps/studio_os/services.py:1376-1416 — get_launch_readiness_summary returns timeline=[] / approvals_pending=<count> / risk_summary='' / service_online=<bool>. Only approvals_pending is real (from apps.accounts.models_workflow.ApprovalWorkflow). timeline and risk_summary are honest empty stubs.

**Still missing:**

- Timeline data source — no source identified; v3.54 audit acknowledged this is backend deferred
- Risk summary computation — no source identified; renders empty string by design
- Helper still not wired into views.py::studio_shell mode=='launch' branch (verified absent from views.py:1492-1500 region) — preview pane lives in launch_canvas but receives no launch_readiness_summary context var

### D4 — real signal counts for overview_signals (`PARTIAL`)

**Expected consumer:** templates/studio_os/partials/cockpit_signal_strip.html + overview_command_cockpit.html

**Evidence:** apps/studio_os/services.py:1251-1316 — get_overview_signals returns a 5-key dict. 3 of 5 are real: pending_launches (School.objects.all()[:50] walk + get_setup_studio_payload.launch_ready check), active_automations (WorkflowPack.is_active=True count, falls back to total count), output_readiness_pct (derived from get_output_dependency_graph). 2 of 5 are honest None: draft_experiences (no source wired), open_blockers (no source wired). Comment at services.py:1314-1315 explicitly acknowledges 'Draft experiences + open blockers: not yet implemented backend-side.'

**Still missing:**

- draft_experiences — no theme/experience drafts model wired; would need ThemeRevision or ExperiencePackDraft table
- open_blockers — no aggregated blockers source; v3.54 next-realm audit recommended pulling from launch_payload.launch_blockers + feature_control_audit warnings + automation conflicts

## Per-section audit

### OVERVIEW

**Route:** `/studio/ (studio_os:shell, current_mode=None)`

**Priority:** `high` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `yes` |
| primary_action_present | `yes` |
| next_best_action_present | `yes` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `yes` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (12):**

- `studio_os:shell  (path '', studio_shell, name='shell')`
- `studio_os:set_operator_school`
- `studio_os:approval_hub  (hubs/approvals/)`
- `studio_os:workflow_center  (hubs/workflow/)`
- `studio_os:import_hub  (hubs/import/)`
- `studio_os:global_search`
- `studio_os:recommendations`
- `studio_os:audit`
- `studio_os:copilot_rail_context`
- `studio_os:copilot_rail_insights`
- `studio_os:copilot_rail_send`
- `studio_os:copilot_rail_send_stream`

**Purpose evidence:** templates/studio_os/partials/overview_command_cockpit.html:25-200 — mission hero (next best action) + 5-card mode grid + readiness/recently-edited/live-previews triptych + operational hubs rail. Hero eyebrow literally reads 'Next best action' (overview_command_cockpit.html:32).

**Primary action evidence:** overview_command_cockpit.html:36-39 — primary CTA renders studio_recommendations[0] with 'Open' button + arrow icon; falls back to 'Choose a mode to start' empty hero when no recommendations (overview_command_cockpit.html:50-58).

**Next best action evidence:** overview_command_cockpit.html:32-46 — explicit 'Next best action' eyebrow + primary + optional secondary CTA from studio_recommendations[1].

**Preview action evidence:** overview_command_cockpit.html:131-144 — 'Live previews' card C in the triptych lists studio_role_preview_entries with target=_blank.

**How-to panel evidence:** templates/studio_os/shell.html:62-64 — guidance panel included only when not current_mode; apps/studio_os/studio_guidance.py:19-47 supplies OVERVIEW_GUIDANCE (tip + 3 Q&A).

**AI guidance evidence:** apps/studio_os/copilot_rail_service.py:187-191 'shell' bucket provides 3 rules-fallback insights ('Pick a mode', 'Press Cmd+K', 'Use a blueprint'). Cloud-first path wired through services.ai_helpers.invoke_with_request.

**Live preview evidence:** studio_role_preview_entries renders in shell.html:127-135 right-rail + overview_command_cockpit.html:131-144 triptych Card C.

**Operator/tenant evidence:** shell.html:179-190 (operational hubs rail) gates RBAC + Feature control chips behind {% if request.public_host_kind == 'manager' %}. shell_control_plane.html provides manager-host shell, shell.html provides tenant. Operator/tenant boundary documented in docs/generated/studio_os_operator_tenant_mode_model.json.

**Mode-specific issues:**

- **OV-1** (`medium`) — overview_signals 2-of-5 keys still honest None — draft_experiences + open_blockers render '—' placeholder with no backing service.
  - Where: `apps/studio_os/services.py:1314-1315`
  - Phase 4 recommendation: Wire draft_experiences via ThemeRevision (or per-tenant 'draft' state on SiteSettings.theme_payload); wire open_blockers via union of launch_payload.launch_blockers + recent feature-control-audit warnings + automation conflict_detection findings.

- **OV-2** (`low`) — Overview lacks Phase-3 information-tags surface — there is no per-section 'workflow info chip' row (e.g. role / step-count / typical-time) above the hero.
  - Where: `templates/studio_os/partials/overview_command_cockpit.html:30-58`
  - Phase 4 recommendation: Phase 3 should ship a workflow_info_tags partial used here above the hero — emit role-required, click-count, average-time, dependency tags.

- **OV-3** (`low`) — Mode-card grid hard-codes mode->URL mapping with if/elif chain (5 branches) — duplicates STUDIO_MODES id->route mapping that is already authoritative in navigation.
  - Where: `templates/studio_os/partials/overview_command_cockpit.html:65-70`
  - Phase 4 recommendation: Move per-mode URLs into STUDIO_MODES entries so the template can do `{{ m.url }}` without if/elif.

**Simplification recommendation:** Land the 2 missing overview_signals (draft_experiences + open_blockers) and add information_tags above the hero so the cockpit speaks honest counts for all 5 tiles and exposes step-count / typical-time / role at-a-glance.

---

### EXPERIENCE

**Route:** `/studio/experience/`

**Priority:** `high` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `yes` |
| primary_action_present | `yes` |
| next_best_action_present | `yes` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `yes` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (9):**

- `studio_os:experience  (experience/)`
- `studio_os:experience_recommendations`
- `studio_os:experience_compare`
- `studio_os:experience_theme_tokens`
- `studio_os:experience_portal_shell_layouts`
- `studio_os:experience_dashboard_visual_packs`
- `studio_os:experience_school_website_blocks`
- `studio_os:experience_communication_style_packs`
- `studio_os:experience_packs`

**Purpose evidence:** templates/studio_os/modes/experience.html:16 — _mode_hero include sets mode_purpose='Brand identity, theme packs, layout. Changes propagate through the configurability cascade so the tenant brand wins.'

**Primary action evidence:** experience.html:16 — primary_cta_url=legacy_urls.theme_colors, primary_cta_label='Theme & colors'; secondary_cta_url=legacy_urls.customizer.

**Next best action evidence:** studio_guidance.MODE_GUIDANCE['experience'] tip; copilot_rail bucket 'experience' surfaces 3 next-action prompts (Generate palette / Compare themes / Edit semantic tokens). Top-of-page guidance has primary_action/secondary_action/preview_url slots in studio_guidance_panel.html:42-60.

**Preview action evidence:** templates/studio_os/partials/workspace/experience_inpage_canvas.html:10 — includes experience_live_preview_pane.html (v3.54.0 new). studio_role_preview_entries also renders in right-rail.

**How-to panel evidence:** experience.html:18 includes studio_guidance_panel.html; studio_guidance.py:50-71 supplies tip + Q&A ('What is Experience mode?' / 'Why do I see contrast warnings?').

**AI guidance evidence:** copilot_rail_service.py:192-196 ('experience' bucket: exp-palette / exp-compare / exp-tokens). Cloud path wired.

**Live preview evidence:** experience_live_preview_pane.html partial exists and is included via experience_inpage_canvas.html:10.

**Operator/tenant evidence:** On manager host (no school resolved) the embed_url is suppressed (views.py:1317-1322); rail labels wrap safely; theme_colors view enforces tenant scoping. studio_role_preview_entries gated by request.school.

**Mode-specific issues:**

- **EX-1** (`medium`) — 13-entry experience focus sidebar (build_experience_focus_sidebar) plus the rail INSIDE the workspace creates double-navigation cognitive load on tenant — operator on manager gets one sidebar, tenant gets two.
  - Where: `apps/studio_os/navigation.py:283-330 + apps/studio_os/views.py:1444-1465`
  - Phase 4 recommendation: Pick one source of truth: either the focus sidebar (manager) or the inline rail (tenant). Today both exist; consolidate around the inline rail with the v3.54.0 overflow fix, drop the duplicate focus sidebar for tenant host.

- **EX-2** (`low`) — experience_workspace_two_col flag is set when experience_context_tool_links is empty — the only signal a 3-pane canvas is appropriate. Brittle: if NoReverseMatch swallows all 10 candidate links, layout silently degrades to 2-col.
  - Where: `apps/studio_os/views.py:1490`
  - Phase 4 recommendation: Make 3-col explicit via an operator preference (experience_canvas_layout in SiteSettings) rather than derived-from-empty-list.

- **EX-3** (`low`) — Live preview pane in experience_inpage_canvas.html:10 has no postMessage / iframe protocol — it appears to be a partial-render not a true iframe preview, so it cannot show 'this is what tenant will see after publish' until the publish loop runs.
  - Where: `templates/studio_os/partials/experience_live_preview_pane.html`
  - Phase 4 recommendation: Either wire an iframe to /preview/?token=<staff-preview-token> with a postMessage refresh on token-change, or rename the pane to 'token diff preview' so the label matches the behavior.

**Simplification recommendation:** Collapse the dual navigation (focus sidebar + inline rail) into one canonical Experience rail and either wire a true iframe live preview or rename the existing pane to match its diff-style behavior.

---

### AUTOMATION

**Route:** `/studio/automation/`

**Priority:** `high` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `yes` |
| primary_action_present | `yes` |
| next_best_action_present | `yes` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `yes` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (9):**

- `studio_os:automation  (automation/)`
- `studio_os:automation_conflict_detection`
- `studio_os:automation_staged_activation`
- `studio_os:automation_replay_rollback`
- `studio_os:automation_visual_builder`
- `studio_os:automation_natural_language_workflow`
- `studio_os:automation_simulation_engine`
- `studio_os:automation_dependency_graph`
- `studio_os:automation_workflow_health`

**Purpose evidence:** templates/studio_os/modes/automation.html:14 — mode_purpose='Workflows, triggers, simulations, and conflict detection. Preview before publishing; rollback is one click.'

**Primary action evidence:** automation.html:14 — primary_cta_url=automation_workflow_center_pane_url, primary_cta_label='Workflow center'; secondary_cta_url=automation_simulation_pane_url.

**Next best action evidence:** automation_overview_body.html:68 includes automation_simulation_preview_pane (Simulate-before-activate is the canonical NBA). Copilot rail 'automation' bucket surfaces 'auto-simulate' first (copilot_rail_service.py:197-200).

**Preview action evidence:** automation_simulation_preview_pane.html (v3.54.0 new) included from automation_overview_body.html:68.

**How-to panel evidence:** automation.html:16 includes studio_guidance_panel.html; studio_guidance.py:72-92 MODE_GUIDANCE['automation'] supplies tip + Q&A.

**AI guidance evidence:** copilot_rail_service.py:197-200 ('automation' bucket: auto-simulate / auto-natural / auto-staged).

**Live preview evidence:** automation_simulation_preview_pane present; primary CTA explicitly named 'Simulation engine'.

**Operator/tenant evidence:** automation_workflow_health_summary helper (services.py:1189-1237) is tenant-agnostic by design (platform-wide counts); for tenant host the values still render but represent platform totals — operator semantics noted in studio_os_operator_tenant_mode_model.json.

**Mode-specific issues:**

- **AU-1** (`medium`) — get_automation_workflow_health_summary returns 0 for paused_count and failing_count when WorkflowPack.is_active or ProcessRun import is unavailable — operator cannot distinguish 'genuinely zero' from 'feature absent'.
  - Where: `apps/studio_os/services.py:1206-1223`
  - Phase 4 recommendation: Add a service_online flag to the helper (same pattern used by get_output_readiness_summary/get_launch_readiness_summary) and render 'unknown' chip when False.

- **AU-2** (`medium`) — automation_workflow_health_summary is platform-wide (not tenant-scoped) — on a tenant host the operator sees platform-aggregate counts which violates the tenant-isolation principle for read surfaces.
  - Where: `apps/studio_os/services.py:1199-1209`
  - Phase 4 recommendation: Add an optional school= filter to the helper (WorkflowPack.objects.filter(school=request.school)) and pass it from views.py when current_mode=='automation' and request.school is set.

- **AU-3** (`low`) — automation focus sidebar has 13 panes (build_automation_focus_sidebar at navigation.py:235-259) — same double-nav cognitive load as Experience.
  - Where: `apps/studio_os/navigation.py:235-259`
  - Phase 4 recommendation: Collapse to 6-8 essential panes; demote less-used into a 'More tools' disclosure.

**Simplification recommendation:** Make get_automation_workflow_health_summary tenant-scoped and add service_online so platform counts don't leak across the tenant boundary; shrink the 13-pane focus sidebar to the 6 most-used.

---

### OUTPUT

**Route:** `/studio/output/`

**Priority:** `critical` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `partial` |
| primary_action_present | `no` |
| next_best_action_present | `unclear` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `yes` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (4):**

- `studio_os:output  (output/)`
- `studio_os:output_dependency_graph`
- `studio_os:output_branding_inheritance`
- `studio_os:output_policy_registry`

**Purpose evidence:** templates/studio_os/modes/output.html — no _mode_hero include; canvas opens directly with studio_guidance_panel + output_mode_canvas. Purpose only surfaces via studio_guidance MODE_GUIDANCE['output'] tip (studio_guidance.py:94-115).

**Primary action evidence:** templates/studio_os/modes/output.html:11-14 — NO _mode_hero include; no primary CTA at the top of the page. output_mode_canvas.html:16-26 only renders an 'Outputs are not loaded in this view' empty state with an 'Open Outputs' button when embed_url is absent.

**Next best action evidence:** Copilot rail 'output' bucket (copilot_rail_service.py:202-206: out-branding / out-policy / out-dependency) — informational only, not surfaced as a CTA strip. No primary 'next best action' button rendered on the page chrome.

**Preview action evidence:** workspace/output_canvas.html:8 includes output_readiness_preview_pane (v3.54.0 new).

**How-to panel evidence:** output.html:12 includes studio_guidance_panel.html; studio_guidance.py:94-115 MODE_GUIDANCE['output'] supplies tip + Q&A.

**AI guidance evidence:** copilot_rail_service.py:202-206 ('output' bucket).

**Live preview evidence:** output_readiness_preview_pane partial wired at workspace/output_canvas.html:8.

**Operator/tenant evidence:** output_mode_canvas.html:2 gates the workspace_layout component on `output_left_rail and request.public_host_kind != 'manager'` — operator gets a different layout. embed_url fallback at output_mode_canvas.html:8-14 handles operator without selected tenant.

**Mode-specific issues:**

- **OP-1** (`high`) — Output mode template does NOT include _mode_hero.html — unlike Experience / Automation / Launch, the Output mode landing has no hero, no clear primary CTA, and no health/status chip at the top. The operator drops straight into output_mode_canvas which renders either an iframe or an empty-state.
  - Where: `templates/studio_os/modes/output.html:11-14`
  - Phase 4 recommendation: Add _mode_hero include with mode_label='Outputs', mode_purpose, primary_cta_url=studio_os:output?pane=builder, secondary_cta_url=studio_os:output_dependency_graph, mode_health_status driven by get_output_readiness_summary.service_online + packs_missing_deps.

- **OP-2** (`medium`) — get_output_readiness_summary helper is defined in services.py but not wired into studio_shell when mode=='output' — the preview pane has no readiness context to consume (its context comes from whatever the consumer page already populates).
  - Where: `apps/studio_os/views.py (studio_shell mode==output branch — output context vars not extended with summary)`
  - Phase 4 recommendation: In views.py::studio_shell, when mode=='output', call get_output_readiness_summary() and set context['output_readiness_summary']. Update output_readiness_preview_pane.html to consume it.

- **OP-3** (`medium`) — get_output_readiness_summary documents_total / documents_published only resolves if apps.reports.models.{Report,ReportPack} exists — silently returns 0 on any other repo shape, hiding real document counts.
  - Where: `apps/studio_os/services.py:1355-1372`
  - Phase 4 recommendation: Walk the registry of first-class output models (output_dependency_graph nodes already enumerate packs); join to a documents-published view rather than module-import-by-name probing.

**Simplification recommendation:** Output mode needs a hero — add the _mode_hero include and wire get_output_readiness_summary() into the mode's context so the preview pane shows real readiness counts.

---

### LAUNCH

**Route:** `/studio/launch/`

**Priority:** `critical` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `yes` |
| primary_action_present | `yes` |
| next_best_action_present | `yes` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `yes` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (2):**

- `studio_os:launch  (launch/)`
- `studio_os:launch_select_plan`

**Purpose evidence:** templates/studio_os/modes/launch.html:14 — mode_purpose='Plan, role-preview, and infrastructure for going live. Guided onboarding is the fastest path.' Mode hero carries mode_health_label + mode_health_status driven by launch_payload.health_score.

**Primary action evidence:** launch.html:14 — primary_cta_url=legacy_urls.guided_onboarding, primary_cta_label='Guided onboarding'.

**Next best action evidence:** Right-rail in shell.html:189-206 renders launch_role_previews + launch_health_summary + 'Ready to launch' badge or 'Complete setup steps' nudge.

**Preview action evidence:** workspace/launch_canvas.html:23 includes launch_studio_role_preview_pane which itself includes launch_readiness_preview_pane (v3.54.0 new).

**How-to panel evidence:** launch.html:16 includes studio_guidance_panel.html; studio_guidance.py:116-160 MODE_GUIDANCE['launch'] + 10 LAUNCH_PANE_GUIDANCE entries (overview/onboarding/create_school/plan/blueprints/infrastructure/branding/migration/role_preview/checklist).

**AI guidance evidence:** copilot_rail_service.py:207-211 ('launch' bucket: launch-preview / launch-checklist / launch-plan).

**Live preview evidence:** launch_readiness_preview_pane + launch_studio_role_preview_pane both wired.

**Operator/tenant evidence:** When school is absent on manager host, embed_url is suppressed (views.py:1317-1322); launch_payload only fills when school is present (views.py:1492-1496).

**Mode-specific issues:**

- **LA-1** (`high`) — get_launch_readiness_summary helper is defined (services.py:1376-1416) but not wired into studio_shell when mode=='launch'. Of its 4 keys, only approvals_pending is real — timeline=[] and risk_summary='' are honest empty stubs. Preview pane renders without ever receiving a context var named launch_readiness_summary.
  - Where: `apps/studio_os/services.py:1414-1416 + apps/studio_os/views.py:1492-1500 (no call site)`
  - Phase 4 recommendation: Wire get_launch_readiness_summary() into views.py::studio_shell mode=='launch' branch. Source the timeline from setup_studio.checklist progress (already computed in launch_payload). Source risk_summary from launch_payload.launch_blockers.

- **LA-2** (`low`) — _mode_hero in launch.html:14 sets `mode_health_label=launch_payload.health_score|stringformat:'s%% ready'` — stringformat:'s' on an int produces literal 's%% ready' (str format conversion), which is likely a typo for ':d' or just passes through with the value as-is. Hard to tell statically without runtime.
  - Where: `templates/studio_os/modes/launch.html:14`
  - Phase 4 recommendation: Verify the format spec at runtime; if the intent was '<n>% ready', use `|stringformat:'d' add:'% ready'` chain or move formatting into the view.

- **LA-3** (`low`) — Launch focus sidebar has 10 panes (build_launch_focus_sidebar at navigation.py:211-232) — long enough to warrant grouping (Setup / Configure / Preview / Go live).

**Simplification recommendation:** Wire get_launch_readiness_summary into the mode='launch' context so the preview pane gets real timeline + risk data, and validate the stringformat call on launch_payload.health_score.

---

### CONTROL

**Route:** `/studio/control/`

**Priority:** `critical` | **Verification:** `static_only`

**Readiness signals:**

| Signal | State |
|---|---|
| clear_workflow_purpose | `partial` |
| primary_action_present | `no` |
| next_best_action_present | `unclear` |
| preview_action_present | `yes` |
| information_tags_present | `no` |
| how_to_panel_present | `yes` |
| ai_guidance_present | `yes` |
| horizontal_overflow_safe | `partial` |
| live_preview_present | `yes` |
| operator_mode_safe | `yes` |
| tenant_mode_safe | `yes` |

**Routes covered (4):**

- `studio_os:control  (control/)`
- `studio_os:system_config_console`
- `studio_os:control_impact`
- `studio_os:ai_cleanup`

**Purpose evidence:** templates/studio_os/modes/control.html — no _mode_hero include. Purpose surfaces via studio_guidance MODE_GUIDANCE['control'] tip ('Feature control turns modules on or off per school...').

**Primary action evidence:** control.html:10-13 — no _mode_hero, no primary CTA at top. control_mode_canvas.html:24-44 renders an outcome-bento (control_outcome_sections) — no single primary action.

**Next best action evidence:** Right-rail in shell.html:222-241 surfaces control_audit_entries + 'Full audit' button when present. Copilot rail 'control' bucket (copilot_rail_service.py:212-215) — informational only.

**Preview action evidence:** workspace/control_canvas.html:244 includes control_governance_preview_pane (v3.54.0 new).

**How-to panel evidence:** control.html:11 includes studio_guidance_panel; studio_guidance.py:138-159 MODE_GUIDANCE['control']. Also operator_control_model 6-paragraph disclosure at control_mode_canvas.html:60-79.

**AI guidance evidence:** copilot_rail_service.py:212-215 ('control' bucket: ctl-audit / ctl-impact / ctl-rbac).

**Live preview evidence:** control_governance_preview_pane wired at workspace/control_canvas.html:244.

**Operator/tenant evidence:** control_mode_canvas.html:81 gates workspace_layout on `control_left_rail and request.public_host_kind != 'manager'`. Manager host gets the rmc-studio-workspace--control inline. control_audit_entries actor rendering uses actor_display (PII-safe per shell.html:230-234 v3.54.0 comment).

**Mode-specific issues:**

- **CT-1** (`high`) — Control mode template does NOT include _mode_hero.html — same defect as Output. Operator drops straight into control_outcome_sections bento with no clear primary CTA, no health chip, no purpose statement at the top.
  - Where: `templates/studio_os/modes/control.html:10-13`
  - Phase 4 recommendation: Add _mode_hero include with mode_label='Control', mode_purpose, primary_cta_url=legacy_urls.feature_control, secondary_cta_url=studio_os:control_impact, mode_health_status driven by recent audit findings count.

- **CT-2** (`medium`) — Control rail (governance_rail_to_focus_sidebar at navigation.py:130-147) is NOT covered by the v3.54.0 shared rail overflow fix at studio-mode-rail.css:5-20. The shared rule targets only experience/output/automation/launch rail-link classes. If localized governance labels grow (e.g. translated 'Blueprints & policy packs' in a long-word locale), Control could regress to the horizontal-overflow class.
  - Where: `static/css/studio-mode-rail.css:5-20 vs apps/studio_os/navigation.py:130-147`
  - Phase 4 recommendation: Either extend the shared selector at studio-mode-rail.css:5-20 to include `.studio-os__control-rail a` / the focus-sidebar selector, or add a defensive `min-width:0; overflow-wrap:anywhere; word-break:break-word` to the studio-focus-layout rule that the focus sidebar consumes. Apply v3.54.0 'fix at abstraction' lesson preemptively.

- **CT-3** (`medium`) — control_outcome_sections appears in two nested {% if %} branches in control_mode_canvas.html (top-of-page bento + collapsed-disclosure wrapper when control_panel_html present). The duplication is hard to read and risks the 'render twice' regression that hit v3.27.1.
  - Where: `templates/studio_os/partials/control_mode_canvas.html:11-49`
  - Phase 4 recommendation: Refactor into a single block; gate the disclosure wrapper via a CSS class, not a duplicate include path.

**Simplification recommendation:** Add the _mode_hero include to Control mode and preemptively cover the control rail in the shared overflow fix at studio-mode-rail.css:5-20 — same architectural pattern v3.54.0 used elsewhere.

---

## Preserve list (already meets the bar)

- **?** — 
- **?** — 
- **?** — 
- **?** — 
- **?** — 
- **?** — 
- **?** — 
- **?** — 

## Summary for Phase 4 (rebuild)

### top_3_studio_specific_defects

- {"rank": 1, "id": "OP-1 + CT-1", "summary": "Output mode and Control mode templates do NOT include _mode_hero.html — only 3 of 5 modes (Experience/Automation/Launch) have a hero. Operator drops straight into canvas with no clear primary CTA, no purpose statement, no health chip. This is the single most visible workflow gap because every other section's hero sets the 'next best action' contract.", "phase4_action": "Add _mode_hero include to templates/studio_os/modes/output.html and control.html; supply mode_purpose / primary_cta_url / mode_health_status from the existing readiness helpers."}
- {"rank": 2, "id": "OP-2 + LA-1", "summary": "get_output_readiness_summary and get_launch_readiness_summary helpers are defined (services.py:1319/1376) but NOT wired into studio_shell — the preview panes render without their readiness context. The helpers exist but are dead code from the consumer's perspective.", "phase4_action": "In apps/studio_os/views.py::studio_shell, call get_output_readiness_summary() when mode=='output' and get_launch_readiness_summary(request) when mode=='launch'; expose under context['output_readiness_summary'] / context['launch_readiness_summary']; update the 2 preview panes to consume."}
- {"rank": 3, "id": "CT-2", "summary": "Control rail is NOT covered by the v3.54.0 shared overflow fix at studio-mode-rail.css:5-20 — the shared selector hits only experience/output/automation/launch rail-link classes. Control uses the governance focus sidebar which lives outside the protected abstraction. Long localized governance labels can regress to horizontal overflow.", "phase4_action": "Extend the shared selector at static/css/studio-mode-rail.css:5-20 to include the governance focus-sidebar selector OR add a defensive min-width:0; overflow-wrap:anywhere; word-break:break-word to studio-focus-layout.css for the focus-sidebar link rule. Apply v3.54.0 'fix at abstraction' lesson preemptively."}

### phase4_rebuild_recommendations

- DO add _mode_hero includes to Output + Control modes (closes a measurable workflow gap; pattern already exists for Experience/Automation/Launch).
- DO wire get_output_readiness_summary + get_launch_readiness_summary into studio_shell so the preview panes consume their helpers.
- DO close the 2 remaining honest-None overview signals (draft_experiences + open_blockers) by wiring real services. Or — if a data source genuinely is not available — drop the keys rather than ship permanent None placeholders.
- DO add a Phase-3 workflow_info_tags partial (role / step-count / typical-time / dependencies) above each mode hero, consumed via studio_guidance contract extension.
- DO extend the v3.54.0 overflow fix to cover the Control governance rail OR add the defensive triple to studio-focus-layout.css.
- DO NOT replace studio_guidance_panel.html — the Phase-3 workflow_help_panel should plug INTO it (it already has primary_action/secondary_action/preview_url/blocker slots).
- DO NOT replace the copilot rail — it is already AI-guidance-present across all 6 surfaces with rules-fallback.
- DO NOT duplicate the operator/tenant gate — use the established `{% if request.public_host_kind == 'manager' %}` pattern + `request.school` resolution.


## Constraints observed

- no_code_changes
- stdlib_only_helpers
- no_django_runtime
- read_only_walk
- no_commits_or_sot_updates
- no_emojis
- file_line_citations

