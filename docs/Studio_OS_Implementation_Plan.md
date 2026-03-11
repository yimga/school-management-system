# Studio OS Implementation Plan (File-Level, Phased)

This plan bridges **RunMyCampus_Studio_OS_Rearchitecture_Blueprint.md** to the codebase with concrete files, routes, and order of work. Goal: one shell, five modes, minimal clicks, shared preview/publish.

**What’s left (all non-negotiable):** see **Studio_OS_Remaining_Work_Non_Negotiable.md** for the full checklist of 32 remaining items (shared shell chrome, shared services, in-page mode content, redirects, and click-reduction).

---

## Phase 1 — Shared Shell (Do First) ✅ Implemented

**Done:** `apps/studio_os` created; shell at `/studio/` with five mode routes; Studio added to dashboard primary CTAs, welcome grid, and command palette. Old URLs still work; redirects deferred to Phase 5.

### 1.1 Create `apps/studio_os`

| Action | Path |
|--------|------|
| Create app | `apps/studio_os/__init__.py` |
| App config | `apps/studio_os/apps.py` (e.g. `StudioOsConfig`) |
| Shell view | `apps/studio_os/views.py` → `studio_shell(request, mode=None)` |
| URL config | `apps/studio_os/urls.py`: `/`, `/experience/`, `/automation/`, `/output/`, `/launch/`, `/control/` |
| Shell template | `templates/studio_os/shell.html` (extends portal_base or backend_base; left rail = 5 modes, center = mode content, right = rail placeholder) |

### 1.2 Wire into project

| Action | File | Change |
|--------|------|--------|
| Register app | `config/settings.py` | Add `"apps.studio_os.apps.StudioOsConfig"` to `INSTALLED_APPS` |
| Mount URLs | `config/urls.py` | `path('studio/', include(('apps.studio_os.urls', 'studio_os'), namespace='studio_os'))` |

### 1.3 Shell template requirements

- **Left rail:** “Studio OS” home + Experience | Automation | Output | Launch | Control (goal-centered labels).
- **Center:** `{% block studio_canvas %}` — per-mode content (Phase 1: placeholder cards with “Coming soon” or link to current page).
- **Right rail:** Optional “Impact & publish” placeholder.
- **Top:** Breadcrumb “Studio OS > [Mode]”; optional global search/command placeholder.
- Reuse existing base (e.g. `portal_base.html` or `backend_base.html`) so header/auth already work.

### 1.4 Permission

- Reuse staff/school context (e.g. `@login_required`, school from `request.school`). No new permission in Phase 1; restrict to staff if needed.

### 1.5 Redirect stubs (optional in Phase 1)

- In `studio_os/views.py`, `studio_shell` can accept `mode` and render the correct placeholder. Old URLs are still valid; add redirects in Phase 5.

---

## Phase 2 — Experience Studio + Launch Studio ✅ Implemented

**Done:** Experience and Launch modes load theme_colors and guided_onboarding inside the Studio canvas via iframe (`?embed=1`). Right rail shows mode-specific hints and links.

### 2.1 Experience Studio

| Task | Detail |
|------|--------|
| Route | `studio_os:experience` or `studio_os:shell` with `mode=experience` |
| Content source | Pull in theme/brand from `siteconfig`: theme_colors view context, theme_packs, site_settings. Either embed `theme_colors.html` in an iframe/section or refactor to a shared partial used by both old URL and Studio. |
| Left rail | Brand identity, Theme packs, Layout presets, Portal shells (from customizer + theme_colors). |
| Center | Live preview: reuse `theme_preview_assets.html` + `site-settings-preview.js` and `color-palette-studio.js` (or their logic). |
| Right rail | Token properties, accessibility, publish/rollback (reuse theme_colors save/preview flow). |

**Files to touch:**

- `apps/studio_os/views.py`: add `experience_context(request)` or include siteconfig theme context.
- `apps/siteconfig/views.py`: optional `theme_colors_context()` helper used by both `theme_colors_page` and studio_os.
- `templates/studio_os/modes/experience.html`: new; include theme form + palette + preview.
- Keep `siteconfig:theme_colors` and `siteconfig:customizer` working until Phase 5 (redirect).

### 2.2 Launch Studio

| Task | Detail |
|------|--------|
| Route | `studio_os:launch` |
| Content source | `apps/setup_studio/services.get_setup_studio_payload(school)`, `apps/customersuccess/views_tenant.guided_onboarding_view`, `execute_launch_view`. |
| Left rail | Progress, setup health, required steps, recommended next. |
| Center | Current step / CTA (reuse guided onboarding content). |
| Right rail | Role preview, launch confidence. |

**Files to touch:**

- `apps/studio_os/views.py`: launch mode calls `get_setup_studio_payload`, passes to template.
- `templates/studio_os/modes/launch.html`: new; embed or extend guided onboarding flow.
- `apps/customersuccess/views_tenant.py`: optional refactor to return JSON/partial for Studio shell embedding.

---

## Phase 3 — Automation Studio + Output Studio ✅ Implemented

**Done:** Automation mode embeds workflow_hub; Output mode embeds report_library. Right rail links to Flow gallery, Document library, Report card builder.

### 3.1 Automation Studio

| Task | Detail |
|------|--------|
| Route | `studio_os:automation` |
| Content source | `siteconfig:workflow_hub`, `siteconfig:workflow_flow_gallery`, `accounts:approval_workflow_hub`, workflow APIs. |
| Left rail | Workflow packs, templates, trigger/action catalog. |
| Center | Flow builder or gallery (current workflow_flow_gallery content); later: visual builder. |
| Right rail | Simulation summary, impact, activation. |

**Files to touch:**

- `apps/studio_os/views.py`: automation mode; reuse workflow_hub and flow_gallery context.
- `templates/studio_os/modes/automation.html`: new; unify workflow hub + flow gallery in one view.
- `apps/siteconfig/views_dashboard_config.py`: optional helpers for “workflow list for school” used by studio.

### 3.2 Output Studio

| Task | Detail |
|------|--------|
| Route | `studio_os:output` |
| Content source | `siteconfig:report_library`, `portal:document_library_manage`, reportcard_builder, `siteconfig/design_studio.py`. |
| Left rail | Output types, report packs, document packs, filters. |
| Center | Report/document list + preview; reportcard builder and design_studio outputs in same mental model. |
| Right rail | Style, branding, data dependencies, publish. |

**Files to touch:**

- `apps/studio_os/views.py`: output mode; aggregate reports list, document library link, reportcard builder link; optional embed.
- `templates/studio_os/modes/output.html`: new; tabs or sections: Reports | Documents | Report cards | Certificates/IDs.
- `apps/siteconfig/design_studio.py`: keep as backend; call from Output Studio for PDF generation.
- `apps/portal` document views: linked from Output Studio; later optionally embedded.

---

## Phase 4 — Control Studio

| Task | Detail |
|------|--------|
| Route | `studio_os:control` |
| Content source | `siteconfig:feature_control_panel`, feature_control API, runtime/blueprint/admin fragments, plans/entitlements. |
| Left rail | Capabilities, policies, integrations, packs, registries, audits. |
| Center | Effective state, compare current vs proposed, staged changes. |
| Right rail | Impact, audit trail, rollback. |

**Files to touch:**

- `apps/studio_os/views.py`: control mode; reuse feature_control_panel context and forms.
- `templates/studio_os/modes/control.html`: new; embed or mirror feature_control_panel with Studio shell.
- `apps/siteconfig/views_feature_control.py`: optional helper for “feature state + audit” used by both old panel and Studio.

---

## Phase 5 — Retire Old Identities ✅ Implemented

**Done:** Direct visits to theme_colors, report_library, workflow_hub, feature_control_panel, guided_onboarding redirect to the corresponding Studio mode unless `?embed=1`. customizer redirects to Studio Experience. Nav: Studio is primary; Customizer/School Settings (customizer) removed from primary CTAs and admin header; sidebar and breadcrumbs use Studio/Experience/Outputs; first-login settings link and setup_studio step link point to Studio.

| Action | Detail |
|--------|--------|
| Redirects | Add in `apps/siteconfig/urls.py` or `apps/studio_os/urls.py`: customizer → studio_os:shell (mode=experience), theme_colors → studio_os:experience (pane=theme), feature_control_panel → studio_os:control, report_library → studio_os:output, document_library_manage → studio_os:output?pane=documents, workflow_hub → studio_os:automation, guided_onboarding → studio_os:launch. |
| Nav labels | In `apps/accounts/views.py`, `apps/dashboard/action_registry.py`, sidebar: replace “Customizer”, “Feature control”, “Report library”, “Document library”, “Workflow hub” with “Studio” or “Studio OS” linking to `/studio/`, and optionally secondary links to mode (Experience, Control, Output, Automation, Launch). |
| Breadcrumbs | `apps/siteconfig/breadcrumb_context.py`, context_processors: “Customizer” → “Experience (Studio)” or “Studio » Experience”. |
| Deprecation | Keep old routes as redirects; remove from primary nav and first-class product language. |

---

## Shared Components (Across Phases)

- **Preview:** Reuse `site-settings-preview.js`, `theme_preview_assets.html`, and preview_from_form URL for theme; extend pattern for other modes.
- **Publish/rollback:** Reuse theme_colors save flow; generalize to `studio_publish_service` later.
- **Command palette:** Phase 1 placeholder; implement in Phase 2+ (e.g. “Change school branding” → Experience Studio).
- **Activity/audit:** Reuse feature_control_audit and siteconfig audit patterns; surface in right rail.

---

## Click Reduction Checklist

- [ ] One entry: “Studio” or “Studio OS” in nav.
- [ ] Mode switch without leaving shell (left rail).
- [ ] Preview in same shell (center + right rail).
- [ ] Publish/rollback in same shell (right rail or bottom bar).
- [ ] No “open customizer → then theme colors → then site settings” for one goal; one mode covers the goal.
- [ ] Recommendations / “next best action” in shell (e.g. Launch Studio progress, Control Studio impact).

---

## Dependency Order

1. Phase 1 (shell) is required for all others.
2. Phase 2 can run in parallel after Phase 1 (Experience and Launch independent).
3. Phase 3 (Automation, Output) can run in parallel after Phase 1.
4. Phase 4 (Control) can follow or overlap with Phase 3.
5. Phase 5 after at least one mode is fully usable from the shell so redirects are meaningful.
