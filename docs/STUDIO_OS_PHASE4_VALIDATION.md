# Studio OS — Phase 4 validation (implementation spine)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4 (Studio OS rearchitecture).

**Goal:** Studio OS is the **main creation/configuration spine**; legacy standalone tool *names* are not first-class entry points (use config-level redirects in [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) where applicable).

---

## 1. Automated tests (required)

From repo root:

```bash
python -m pytest apps/studio_os/tests/ -q
```

Covers: `deep_links`, `studio_rail_resolution`, `launch_and_automation_rails`, `experience_rollback`, `preview_context`.

---

## 2. Mode inventory (code + URL)

| Mode | URL name | Shell template | Notes |
|------|-----------|----------------|--------|
| Overview | `studio_os:shell` | `studio_os/shell.html` | Mode picker |
| Experience | `studio_os:experience` | `studio_os/modes/experience.html` | In-page theme when `use_experience_in_page`; else iframe rail |
| Automation | `studio_os:automation` | `studio_os/modes/automation.html` → `partials/automation_mode_canvas.html` | Tenant shell extends `shell.html`; canvas body is shared with control-plane `shell_main_content` |
| Output | `studio_os:output` | `studio_os/modes/output.html` → `partials/output_mode_canvas.html` | Same |
| Launch | `studio_os:launch` | `studio_os/modes/launch.html` → `partials/launch_mode_canvas.html` | Same |
| Control | `studio_os:control` | `studio_os/modes/control.html` | In-page feature control when permitted; else embed |

Implementation: `apps/studio_os/views.py` (`studio_shell`), `apps/studio_os/urls.py`.

### Workflow center (`studio_os:workflow_center`)

- View: `apps/accounts/views_workflow.py` → `workflow_center` (permission: `settings.manage`).
- Automation Studio **Workflow** pane iframes `…/studio/hubs/workflow/?embed=1` → `accounts/workflow_center_embed.html` (shared body: `accounts/partials/workflow_center_main.html`).
- **Manager host, no school:** `_manager_host_without_school_workflow_redirect` is **skipped** when `embed=1` so the iframe can load; full-page visits without embed still redirect to the super dashboard with a message.

---

## 3. Legacy redirects (fragmented tools → Studio)

| Legacy surface | Replacement | Status |
|----------------|-------------|--------|
| Customizer (`/siteconfig/customizer/`, admin path) | `studio_os:experience` | REDIRECT (config urls) |
| Workflow hub | `studio_os:automation` | REDIRECT |
| Report library / `/siteconfig/reports/` | `studio_os:output?pane=reports` (default; merges query) | REDIRECT |
| **Theme colors** (`GET /siteconfig/theme-colors/`) | **Staff:** `302` → `/studio/experience/`. **Non-staff** (settings.manage only): `302` → `?standalone=1` same path. **`embed=1`** preserved for iframes. | Implemented in `siteconfig.views.theme_colors_page` |
| **Feature control** (`GET`, no `embed=1`) | `302` → `/studio/control/` | Implemented in `views_feature_control.feature_control_panel` |
| **Document library** (`GET`, no `embed=1`) | `302` → `/studio/output/?pane=documents` | Implemented in `portal.views_documents.document_library_manage` |
| Deep-link map `theme_colors` | `studio_legacy_urls_map` → `studio_os:experience` | `deep_links.py` |

Forms still **POST** to `siteconfig:theme_colors` and related names; success redirect prefers Studio for **staff**, else `theme_colors?standalone=1`.

---

## 4. Acceptance criteria vs codebase

| Criterion | Evidence |
|-----------|----------|
| Studio OS is the main spine | Five modes + overview; shell toolbar (search, commands); right rail “Impact & publish” |
| Old tool identities not first-class | LEGACY redirects for customizer / workflow / report library; Studio overview copy points to modes |
| Output experience native where required | Control mode renders `feature_control_panel_partial` in-page when permitted (`embed_url = None`); Experience mode uses in-page theme form when context loads |
| Native + tab row + pack previews (§4.4 **DONE**) | **Horizontal tabs** (`studio-os__output-tabs`) mirror the left rail. **In-canvas sample-data previews** per active `ReportPack` (`get_output_report_pack_preview_cards`, `data-studio-output-pack-previews`, `?pack=` focus on graph). **Documents, branding, policy, report card builder, `pane=reports`, `pane=credentials`** use `data-studio-output-native`; builder preview = iframe/new tab **by design**; POSTs → `?pane=builder&step=…`. |

---

## 5. Design system on Studio surfaces

- Shell loads tokens via `portal_base` → `design-tokens.css` + `design-system-phase2-enforcement.css`.
- Mode rail + **Output tab row** chrome: `static/css/studio-mode-rail.css` (Experience / Output / Automation / Launch; no inline hex in those mode templates).

---

## 6. Phase 2 cross-check

```bash
python scripts/verify_design_system_phase2.py
```

Ensures global token layers and migrated components did not regress.

| Phase 2 doc § | Studio OS evidence (nothing missed for spine) |
|---------------|-----------------------------------------------|
| §1 Load order | Tenant `/studio/` → `portal_base` → `design-tokens.css` + `design-system-phase2-enforcement.css`. Manager Studio → `control_plane_skeleton` (same two sheets). |
| §2 `--ds-*` | Available on all Studio pages inheriting those bases. |
| §3 `.ds-*` | Use on new Studio-facing components as elsewhere; mode chrome uses `studio-mode-rail.css` + tokens. |
| §4 Task 4 | Mode rails: external `studio-mode-rail.css`. Shell grid/rail: `static/css/studio-shell-layout.css` linked from `shell_extrastyle.html` (no inline theme block); see DESIGN_SYSTEM_PHASE2.md §4. |
| §5 Marketing | N/A to Studio canvas (marketing is separate base). |
| §6 Acceptance | Touched Studio surfaces align to product family; dark/light via portal/control-plane theme pipeline. |
| §7 Verification | Run `verify_design_system_phase2.py` + `pytest apps/studio_os/tests/` after Studio CSS changes. **Last gate run:** both PASS in CI/local before advancing agenda. |

---

## 7. Line-by-line SOT §4.1–4.6 audit (Phase 4 spine **DONE**; same bar for all subsections)

SOT §4.1–§4.6 are **`Status: DONE`** in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md): **§11.1 rail/hub scope is complete** for each mode. **Embed iframes** and **billing/plan SKU depth**, **deeper simulation productization**, and **§5 toolset vignettes** are **not** PARTIAL Studio gates—they roll forward under **§11.4** (release cadence) and **§5** (toolset remediation) with the same treatment for every §4.x block.

### 7.1 §4.1 Studio OS shell

| SOT requirement | Verified in codebase | Test / command |
|-----------------|----------------------|----------------|
| Global search API | `studio_os:global_search`, `studio_global_search` | `pytest apps/studio_os/tests/` (indirect via shell) |
| Command palette | `shell.html`, `shell_main_content.html`, CMD+K handlers | Manual / browser |
| Cross-host deep links | `deep_links.py`, `resolve_studio_href` | `test_deep_links.py`, `test_studio_rail_resolution.py` |
| Unified left rail | `studio_os__rail` in shell templates | Visual |
| Preview / publish / rollback | `studio_preview`, `studio_publish_api`, `studio_rollback` | `test_preview_context.py`, `test_experience_rollback.py` |
| Activity / audit | `get_studio_activity_feed`, `studio_audit_api` | Shell context |
| Recommendations | `get_studio_recommendations`, API route | Shell context |
| Role preview | `studio_role_preview_entries` | Shell template |
| Five mode hubs + iframe/native switcher | `modes/*.html`, `partials/*_mode_canvas.html`, `studio_shell` | `pytest apps/studio_os/tests/` |
| Control-plane parity | `shell_control_plane.html`, `shell_main_content.html` includes mode canvases | Manual on `manager` host |
| **DONE (SOT §4.1)** | Legacy redirects per LEGACY_PATH_INVENTORY; Output pack previews + tabs ship in §4.4 | Further URL hygiene → **§1.7 / §11.4** (same as other modes) |

### 7.2 §4.2 Experience Studio

| SOT “Must support” | Hub + rail / embed / in-page | Notes |
|--------------------|------------------------------|--------|
| Theme, customizer, school theme, packs, tokens, layouts, dashboard packs, website blocks, comm packs, compare, publish/rollback, brand import, AI recs | `experience.html`, `studio_os/views.py` experience rail + views | §11.1 items [x] in SOT |
| **DONE (SOT §4.2)** | New catalog packs / uniformity | **§11.4** product iteration (not PARTIAL §4.2) |

### 7.3 §4.3 Automation Studio

| SOT “Must support” | Evidence |
|--------------------|----------|
| Workflow, flow gallery, approval, visual builder, NL workflow, simulation, dependency graph, conflict, staged, replay/rollback, health | `automation_mode_canvas.html`, standalone views, `studio_os/urls.py` | `test_launch_and_automation_rails.py` |
| Workflow center embed | `workflow_center?embed=1`, `workflow_center_embed.html`, skip manager redirect when embed | Same test module |
| **DONE (SOT §4.3)** | Deeper simulation / builder productization | **§5.7 / §11.4** (same deferral class as Launch plan picker) |

### 7.4 §4.4 Output Studio

| SOT “Must support” | Evidence |
|--------------------|----------|
| Rail + **tabs**, pack previews, ReportPack/DocumentPack, branding, signature, retention, dependency graph, publish/rollback, reports/credentials panes | `output_mode_canvas.html`, `get_output_report_pack_preview_cards`, `build_report_pack_preview` row normalization, `test_output_native_builder.py` | Studio + siteconfig integration |
| **DONE (SOT §4.4)** | Additional statutory report SKUs / §5.3 “Report Platform” depth | **§5.3 / §11.4** (not PARTIAL §4.4) |

### 7.5 §4.5 Launch Studio

| SOT “Must support” | Evidence |
|--------------------|----------|
| Hub, health, role preview, create school, select plan, blueprint, branding, starter stack, migration path, checklist, AI coach, confidence | `launch_mode_canvas.html`, `get_setup_studio_payload`, onboarding API tests in siteconfig | `test_launch_and_automation_rails.py` (iframes / native) |
| **DONE (SOT §4.5)** | Full billing SKU plan picker | **Billing / §11.4** (not PARTIAL §4.5) |

### 7.6 §4.6 Control Studio

| SOT “Must support” | Evidence |
|--------------------|----------|
| Capability, runtime, policy/entitlement/pack/integration, registry, metadata, diff/impact, rollback, AI cleanup | `control_mode_canvas.html`, rails in `views.py` | Shell + embeds |
| **DONE (SOT §4.6)** | Further bounded-console consolidation | **§5.9 / §11.4** (not PARTIAL §4.6) |

### 7.7 “Ready for next phase” checklist

1. `python -m pytest apps/studio_os/tests/ -q` → PASS  
2. `python scripts/verify_design_system_phase2.py` → PASS  
3. No duplicate Studio canvas markup: Automation / Output / Launch modes include `partials/*_mode_canvas.html` only  
4. Open **next agenda item** from SOT execution ordering (e.g. §2763 table: Phase IV §5 depth, Phase II §2.4, or external backlog) — **§4 spine is closed (DONE); §5 / §11.4 own follow-on depth** with **consistent** handling across all former PARTIAL narratives

---

*Audit routine: re-run §7.7 commands after any `apps/studio_os/`, `templates/studio_os/`, or Studio-related `static/css/` change.*
