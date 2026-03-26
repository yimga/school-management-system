# Phase 5 — Studio OS consolidation — mandatory route and canvas audit

**Authority:** Phase 5 evidence register (route→mode matrix, legacy mapping, native vs iframe). **Canonical platform completion states** remain in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (section 4 — Studio OS). Session trail: [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md). Checklist: [phase_05_studio_os.md](../phase_checklists/phase_05_studio_os.md).

**Updated:** 2026-03-24 — Phase 5 **CLOSED** for in-repo acceptance below; re-open only if regression tests or this matrix fail.

---

## 0. Granular tasker traceability (your Phase 5 spec — no backlog)

Each row is **DONE** in-repo with evidence. Nothing below is deferred to Phase 6.

| Spec tasker | Studio / platform home | Evidence |
|-------------|------------------------|----------|
| **Customizer** | `studio_os:experience` | Legacy `/siteconfig/customizer/`, `/admin/siteconfig/customizer/` → redirect; `deep_links.studio_legacy_urls_map` key `customizer`; Experience rail embed targets |
| **Theme colors** | Experience Studio (in-page) + `siteconfig:theme_colors` | `studio_shell` + `get_theme_colors_context` → `use_experience_in_page`; `theme_colors` remains for deep links / `?embed=1`; **3-pane** workbench `studio-os__experience-workbench` |
| **Feature control panel** | Control Studio | `studio_shell` `mode=control`; native `control_panel_html` when `settings.feature_control`; rail → `siteconfig:feature_control_panel`; outcome sections + operator model |
| **Workflow hub** | Automation Studio | Legacy `/siteconfig/workflow-hub/` → `studio_os:automation`; `pane=workflow` iframe to `workflow_center`; hub `studio_os:workflow_center` |
| **Report library** | Output Studio `?pane=reports` | Legacy `/siteconfig/report-library/`, `/siteconfig/reports/` → output + `pane=reports`; `deep_links` `report_library` query; native `output_reports_library_body.html` |
| **Document library** | Output Studio `?pane=documents` | Native `output_documents_native_wrapper.html` → `document_library_manage_inner.html` with `data-studio-output-native="documents"`; test below |
| **Setup simulators** | Launch + Automation + public teaser | **In-product:** Launch rail + `get_setup_studio_payload` overview (`launch_studio_overview_body.html`); guided onboarding embed (`_resolve_launch_iframe_src`); Automation `?pane=simulation` native explainer + simulation-engine subpage. **Public:** `setup_simulator_page` → `marketing_setup_simulator.html`, `name=setup_simulator`, path `/getting-started/simulator/` (`config/public_urls.py`) — same narrative as Launch Studio per marketing copy |
| **Preview fragments** | Studio preview pipeline | `studio_os:preview` (`studio_preview`), `studio_publish_api`, shell bottom bar POST preview (`shell.html` JS); `siteconfig:preview_from_form`; Experience “Preview” uses unified flow |
| **Output builders** | Output `?pane=builder` | `build_reportcard_builder_context(..., studio_output_native=True)` + `output_reportcard_builder_wrapper.html` → `reportcard_builder_inner.html` with `data-studio-output-native="builder"`; **no** pane-level `output_iframe_src` for builder |
| **Launch / setup flows** | Launch Studio | Left rail panes (`views.py`); native overview + plan; iframe wizards only where `_resolve_launch_iframe_src` maps (`onboarding`, `create_school`, `blueprints`, `branding`, `checklist`); non-embed `guided_onboarding` redirects to `studio_os:launch` (`apps/customersuccess/views_tenant.py`) |

### Required modes (all implemented)

| Mode | Shell route | Canvas partial |
|------|-------------|----------------|
| Experience | `studio_os:experience` | `modes/experience.html` |
| Automation | `studio_os:automation` | `partials/automation_mode_canvas.html` |
| Outputs | `studio_os:output` | `partials/output_mode_canvas.html` |
| Launch | `studio_os:launch` | `partials/launch_mode_canvas.html` |
| Control | `studio_os:control` | `partials/control_mode_canvas.html` |

### Specific requirements (all satisfied)

| Requirement | How it is met |
|-------------|----------------|
| Experience **3-pane** | Mode rail + canvas workbench (rail \| primary \| related tools) + shell right “Impact” (`shell.html`) |
| Automation **simulation / conflict** | `?pane=simulation` explainer; conflict subpage + rail CTA “Review conflict detection”; `automation_simulation_summary` on rail |
| Output **native, non-brittle** | All eight rail panes use native partials or denied-state cards; `output_iframe_src` only for true fallback; builder **live preview** may use iframe **inside** builder inner template (isolated, not full-canvas brittle) |
| Launch **guided, low-click** | Single rail with labeled panes; overview aggregates health/checklist/role previews; deep links to plan + wizards |
| Control **governance spine** | Outcome sections, operator model, audit entries, feature panel in-shell, full governance rail |

### Mandatory audit items (this document)

| Audit item | Where addressed |
|------------|-----------------|
| Tool → Studio route mapping | **§0** (this table) + **§1** (full matrix) |
| Old fragmented identity survival | **§6** + legacy redirects + `test_phase_05_legacy_redirects.py` |
| Studio mode completeness | **§0** modes table + **§1** |
| Native output behavior | **§2.2** + `test_output_native_builder.py` (all panes) |
| Launch flow coherence | **§2.3** + **§0** launch row |

---

## 1. Studio OS URL → work mode matrix

Prefix: **`/studio/`** (namespace `studio_os`). Source of truth: `apps/studio_os/urls.py`.

| Path (suffix) | URL name | Primary handler | Studio mode / category | Canvas / shell |
|---------------|----------|-----------------|------------------------|----------------|
| `""` | `shell` | `studio_shell` | Overview (no mode) | `shell.html` |
| `hubs/approvals/` | `approval_hub` | `approval_workflow_hub` | Hub (Automation family) | Wrapped hub view |
| `hubs/workflow/` | `workflow_center` | `workflow_center` | Hub | Wrapped hub view |
| `hubs/import/` | `import_hub` | `import_hub` | Hub | Wrapped hub view |
| `experience/` | `experience` | `studio_shell` `mode=experience` | **Experience** | `modes/experience.html` + `shell` |
| `experience/recommendations/` | `experience_recommendations` | `_render_studio_subpage` | Experience | Native subpage in shell |
| `experience/compare/` | `experience_compare` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/theme-tokens/` | `experience_theme_tokens` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/portal-shell-layouts/` | `experience_portal_shell_layouts` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/dashboard-visual-packs/` | `experience_dashboard_visual_packs` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/school-website-blocks/` | `experience_school_website_blocks` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/communication-style-packs/` | `experience_communication_style_packs` | `_render_studio_subpage` | Experience | Native subpage |
| `experience/experience-packs/` | `experience_packs` | `_render_studio_subpage` | Experience | Native subpage |
| `automation/` | `automation` | `studio_shell` `mode=automation` | **Automation** | `modes/automation.html` + `partials/automation_mode_canvas.html` |
| `automation/conflict-detection/` | `automation_conflict_detection` | Subpage view | Automation | Native subpage |
| `automation/staged-activation/` | `automation_staged_activation` | Subpage view | Automation | Native subpage |
| `automation/replay-rollback/` | `automation_replay_rollback` | Subpage view | Automation | Native subpage |
| `automation/visual-builder/` | `automation_visual_builder` | Subpage view | Automation | Native subpage |
| `automation/natural-language-workflow/` | `automation_natural_language_workflow` | Subpage view | Automation | Native subpage |
| `automation/simulation-engine/` | `automation_simulation_engine` | Subpage view | Automation | Native subpage |
| `automation/dependency-graph/` | `automation_dependency_graph` | Subpage view | Automation | Native subpage |
| `automation/workflow-health/` | `automation_workflow_health` | Subpage view | Automation | Native subpage |
| `output/` | `output` | `studio_shell` `mode=output` | **Outputs** | `modes/output.html` + `partials/output_mode_canvas.html` |
| `output/dependency-graph/` | `output_dependency_graph` | Subpage view | Outputs | Native subpage |
| `output/branding-inheritance/` | `output_branding_inheritance` | Subpage view | Outputs | Native subpage |
| `output/policy-registry/` | `output_policy_registry` | Subpage view | Outputs | Native subpage |
| `launch/` | `launch` | `studio_shell` `mode=launch` | **Launch** | `modes/launch.html` + `partials/launch_mode_canvas.html` |
| `launch/select-plan/` | `launch_select_plan` | `studio_launch_select_plan` | Launch | Subpage / shell per view |
| `control/` | `control` | `studio_shell` `mode=control` | **Control** | `modes/control.html` + `partials/control_mode_canvas.html` |
| `control/system-config/` | `system_config_console` | `studio_system_config_console` | Control | Subpage |
| `control/impact/` | `control_impact` | `studio_control_impact` | Control | Subpage |
| `control/ai-cleanup/` | `ai_cleanup` | `studio_ai_cleanup` | Control | Subpage |
| `preview/` | `preview` | `studio_preview` | API / action | JSON / redirect |
| `publish/` | `publish` | `studio_publish_api` | API / action | POST |
| `save-draft/` | `save_draft` | `studio_save_draft_api` | API / action | POST |
| `version-history/` | `version_history` | `studio_version_history_api` | API | GET |
| `search/` | `global_search` | `studio_global_search` | Cross-mode | View |
| `recommendations/` | `recommendations` | `studio_recommendations_api` | Cross-mode | JSON |
| `audit/` | `audit` | `studio_audit_api` | Cross-mode | API |
| `rollback/` | `rollback` | `studio_rollback` | Cross-mode | POST |

**Count:** 44 `path()` entries in `apps/studio_os/urls.py` (verified 2026-03-24).

---

## 2. Query-string panes (single shell, multiple canvases)

### 2.1 Automation (`/studio/automation/?pane=`)

| Pane key | Canvas | Iframe (`_resolve_automation_iframe_src`) |
|----------|--------|-------------------------------------------|
| `overview` | Native (`automation_overview_body`) | No |
| `outcomes` | — | Yes → `automation:outcomes_console` |
| `workflow` | — | Yes → `studio_os:workflow_center` |
| `flow_gallery` | — | Yes → `siteconfig:workflow_flow_gallery` |
| `approval` | — | Yes → `studio_os:approval_hub` |
| `dependency` | Native graph body | No |
| `health` | Native health body | No |
| `conflict`, `staged`, `replay`, `visual_builder`, `nl_workflow`, `simulation` | Native explainer | No |

Rail CTA “Review conflict detection” links to `?pane=conflict` when not on that pane (`automation_mode_canvas.html`).

### 2.2 Outputs (`/studio/output/?pane=`)

| Pane key | Rendering | Notes |
|----------|-----------|--------|
| `dependency` | Native (`output_dependency_graph_body`) | `data-studio-output-native="dependency"` |
| `reports` | Native (`output_reports_library_body`) | `data-studio-output-native="reports"` |
| `documents` | Native wrapper | Permission-gated |
| `builder` | Native wrapper / builder | `data-studio-output-native="builder"`; live preview may use iframe by design |
| `credentials` | Native | `data-studio-output-native="credentials"` |
| `branding` | Native | |
| `policy` | Native | |
| Fallback | Iframe + “Open in full window” | Only when native context missing |

Tests: `apps/studio_os/tests/test_output_native_builder.py`.

### 2.3 Launch (`/studio/launch/?pane=`)

| Pane key | Canvas | Iframe (`_resolve_launch_iframe_src`) |
|----------|--------|----------------------------------------|
| `overview` | Native (payload or empty state) | No |
| `plan` | Native (`launch_select_plan_body`) | No |
| `onboarding`, `create_school`, `blueprints`, `branding`, `checklist` | — | Yes (guided wizards / embed targets) |

### 2.4 Control (`/studio/control/`)

- **Governance spine:** Outcome sections + operator model + **in-shell feature control HTML** when `settings.feature_control` perm (`control_panel_html`); else iframe rail to first embed target (`control_mode_canvas.html`).
- **Left rail:** Config center, Feature control, Audit, Runtime inspector, Metadata, Lineage, Integrations, Blueprints, Policy diff, Billing, Impact, AI cleanup (`views.py` control block).

### 2.5 Experience (`/studio/experience/`)

- **Native theme in page:** `get_theme_colors_context` + **three-pane workbench** (`studio-os__experience-workbench`: section rail \| primary \| related tools). CSS: `static/css/studio-shell-layout.css`.
- **Fallback:** Left rail + iframe to first embed URL; same grid includes related-tools column when links resolve.
- **Global shell:** Mode rail + `studio-os__right` impact column (`shell.html`) — tokens, contrast, version, audit.

---

## 3. Legacy fragmented URLs → Studio OS (not primary surfaces)

Implemented redirects (tenant: `config/tenant_urls.py`; default / CI: `config/urls.py`; manager: `config/manager_urls.py`). Product rule: old paths **redirect**, not serve duplicate first-class pages.

**URLconf order (non-negotiable):** `path("admin/siteconfig/customizer/", …)` must appear **before** `path("admin/", admin_site.urls)` so Django matches the Studio redirect instead of handing the path to the admin app (which would 302 to login). Verified by `apps/studio_os/tests/test_phase_05_legacy_redirects.py`.

| Legacy path | Redirect target | Notes |
|-------------|-----------------|--------|
| `/admin/siteconfig/customizer/` | `studio_os:experience` | Back-compat |
| `/siteconfig/customizer/` | `studio_os:experience` | Phase B |
| `/siteconfig/workflow-hub/` | `studio_os:automation` | Query string preserved (tenant) |
| `/siteconfig/report-library/`, `/siteconfig/reports/` | `studio_os:output` + `pane=reports` | Default pane |

**Deep-link map for menus / manager:** `apps/studio_os/deep_links.py` → `studio_legacy_urls_map()` (e.g. `report_library` appends `?pane=reports`). Tests: `apps/studio_os/tests/test_deep_links.py`, `test_studio_rail_resolution.py`.

---

## 4. Mandatory validation commands (Phase 5 gate)

| Command | Expected |
|---------|----------|
| `python -m pytest apps/studio_os/tests/ -q` | **PASS** (includes `test_phase_05_granular_taskers`, `test_phase_05_legacy_redirects`, `test_output_native_builder` all panes) |
| `python scripts/verify_cursor_phase5_studio_os.py` | **PASS** (structural + redirect + full `reverse()` sweep; **§10**) |
| `python scripts/verify_design_system_phase2.py` | **PASS** (Studio shell CSS in required list) |

Optional cross-checks already used elsewhere: `apps/schools/tests/test_primary_control_plane_nav.py` (operator nav to Studio), `apps/siteconfig/tests/test_control_outcome_center.py` (Control Studio outcomes).

---

## 5. Acceptance criteria (Phase 5 mission) — PASS/FAIL

| Criterion | Result | Evidence |
|-----------|--------|----------|
| Studio OS is the real creation/configuration spine | **PASS** | Five modes + hubs + APIs in §1 matrix; shell `shell.html` / `shell_control_plane.html`; publish/rollback/preview routes |
| Old tool identities are not primary product surfaces | **PASS** | §3 redirects + `studio_legacy_urls_map`; SOT §1.7 notes siteconfig customizer/report_library/workflow_hub removed in favor of Studio |
| Touched workflows are lower-click and coherent | **PASS** | Output native panes + tabs; Experience workbench + related tools; Automation conflict CTA; Launch overview/plan native |
| Output Studio native and reliable on touched paths | **PASS** | `output_mode_canvas.html` native-first; tests assert `data-studio-output-native`; iframe only fallback / builder preview |
| Experience Studio three-pane (in-canvas) | **PASS** | `studio-os__experience-workbench` + `experience_workbench_context.html`; `--two-col` when no context links |
| Automation simulation/conflict awareness | **PASS** | Explainer panes + rail summary + conflict deep link; iframe for workflow center / outcomes where heavy |
| Launch flow coherence | **PASS** | Rail panes + native overview/plan + iframe for wizards per `_resolve_launch_iframe_src` |
| Control Studio governance spine | **PASS** | Outcome sections + operator model + native feature panel when permitted |

---

## 6. Fragmented identity survival (audit question)

| Old identity | Still reachable as own URL? | Primary entry |
|-------------|----------------------------|---------------|
| Customizer | Redirect only / embed | `studio_os:experience` |
| Workflow hub | Redirect + Automation pane / iframe | `studio_os:automation` |
| Report library | Redirect + Output `pane=reports` | `studio_os:output` |
| Theme colors | `siteconfig:theme_colors` (functional page) | Also embedded in Experience rail / in-page form when context loads |
| Feature control | `siteconfig:feature_control_panel` | Control Studio rail + native partial when permitted |

**Conclusion:** Legacy slugs do not compete as parallel “home” pages; Studio modes are canonical.

---

## 7. Related documentation (no new parallel roadmap)

- [STUDIO_RAIL_CONTROL_PLANE_URLS.md](../STUDIO_RAIL_CONTROL_PLANE_URLS.md) — rail URL resolution.
- [STUDIO_OS_PHASE4_VALIDATION.md](../STUDIO_OS_PHASE4_VALIDATION.md) — historical §4.1 validation (pytest reminder).
- SOT **section 4** — parent statuses and non-negotiables.

---

## 8. Definition of done — Phase 5 is **fully closed** (not partial)

Phase 5 in this repository is **complete end-to-end** for its **declared scope** when **all** of the following are true:

| Gate | Status (2026-03-24) |
|------|---------------------|
| Every acceptance row in **§5** is **PASS** with **no waivers** | **Yes** |
| Every **granular tasker** in **§0** traced (no backlog) | **Yes** |
| Mandatory route matrix **§1** + pane/iframe inventory **§2** published | **Yes** |
| Legacy URLs in **§3** redirect to Studio; admin customizer route ordered **before** `admin/` | **Yes** (see `test_phase_05_legacy_redirects.py`) |
| `python -m pytest apps/studio_os/tests/ -q` | **PASS** |
| `python scripts/verify_cursor_phase5_studio_os.py` | **PASS** (mechanical re-audit; **§10**) |
| `python scripts/verify_design_system_phase2.py` | **PASS** |
| Checklist [phase_05_studio_os.md](../phase_checklists/phase_05_studio_os.md) | All items **[x]** |
| Execution log [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) Phase 5 block | Marked **CLOSED** |

**There is no open “partial Phase 5” checklist item** in-repo for this scope.

---

## 9. What this document does **not** claim (avoid scope confusion)

Completing **Phase 5** does **not** by itself close **Cursor phases 6–12**, **ZIP Phase 5 (SiteSettings)**, or **SOT “continuous”** tracks (§11.4, Phase H, statutory report SKUs, etc.). Those are separate execution slices with their own checklists and gates in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

If the goal is **the entire 12-phase program** with nothing left: that is **not** a single Phase 5 artifact; proceed phase-by-phase using the same A–F discipline and append blocks to the execution log.

---

## 10. Mechanical re-audit (not high-level — repeat anytime)

Run:

```bash
python scripts/verify_cursor_phase5_studio_os.py
```

This script **proves in code**, on every run:

| Check | Meaning |
|-------|---------|
| Audit file sections §0, §1, §8 exist | Doc was not gutted between audits |
| `siteconfig/urls.py` has **no** `name="customizer"`, `workflow_hub`, `report_library` | Fragmented tool **pages** are not re-registered as primary Django routes there |
| `config/urls.py`, `tenant_urls.py`, `manager_urls.py` | `admin/siteconfig/customizer/` line appears **before** `path("admin/", …)` |
| HTTP GET legacy paths | 302 to `studio_os:experience`, `automation`, or `output?pane=reports` |
| Every `studio_os:*` route | `reverse()` succeeds under `ROOT_URLCONF` |
| `siteconfig:theme_colors`, `siteconfig:preview_from_form` | `reverse()` succeeds |

**Note:** Script name uses **Cursor Phase 5** to avoid confusion with `scripts/verify_phase_5_siteconfig.py` (**ZIP Phase 5** / SiteSettings).

---

## 11. What automated gates still **do not** replace (second-audit honesty)

These are **outside** the mechanical script and pytest scope; a human or staging run can still find issues without contradicting Phase 5 closure **for repo structural acceptance**:

| Area | Why it is not fully machine-gated |
|------|-----------------------------------|
| Visual / UX polish | Pixel-perfect layout, animation, copy tone |
| Staging / prod hosts | Different `ALLOWED_HOSTS`, TLS, CDN — use release checklist |
| Every permission matrix | Tests use superuser/staff fixtures; edge RBAC combos may need manual smoke |
| Manager vs tenant host | Default tests use `config.urls` (tenant-style monolith); manager URLconf is **also** checked for admin redirect **order** in source only |
| Embedded iframes at runtime | Cross-origin, session cookies, `embed=1` pages — integration tests recommended when changing those views |

**Bottom line:** Phase 5 is **done end-to-end for repository deliverables** (routes, redirects, native panes, docs, automated tests + mechanical verifier). A **product** audit can still ask for staging video or role-matrix smoke; that does not reopen Phase 5 unless it finds a **contradiction** (e.g. legacy URL stops redirecting, or a `name="workflow_hub"` reappears in `siteconfig/urls.py`).
