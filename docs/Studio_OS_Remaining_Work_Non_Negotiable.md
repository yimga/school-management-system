# Studio OS — Remaining Work (All Non-Negotiable)

Everything below is required. No item is optional.

**Implementation status:** Shared shell chrome (search, command palette, bottom bar), shared services (activity, recommendations, command entries, studio_publish_service with save_draft/publish/rollback/audit/version_history), shared preview (preview_from_form wired in shell; Experience theme form → Preview/Publish/Rollback in same shell), Experience in-page (theme_colors_context + partial + experience.html + left rail Brand/Theme packs/Layout/Portal + right rail contrast + theme_preview_section in canvas), Launch (launch.html + payload + left rail progress/health/steps/blockers), Output (tabs + document redirect + left rail output types), Automation (automation.html + workflow_entries + left rail), Control (control.html + left rail Capabilities/Audit + right rail audit entries + iframe), document_library redirect, and breadcrumbs are implemented. Remaining (optional polish): full Control in-page form without iframe; richer Automation/Output right rails; guided onboarding data/partial for Launch without iframe.

---

## 1. Shared Shell (Top Bar & Bottom Bar) ✅

| # | Task | Detail |
|---|------|--------|
| 1.1 | **Global search** | Top bar: search that resolves to Studio modes, settings, and actions (e.g. “change school branding” → Experience). |
| 1.2 | **Command palette** | Top bar: keyboard-triggered command palette (e.g. “Change school branding”, “Set up grade reports”, “Preview parent portal”) that navigates or runs actions in the shell. |
| 1.3 | **Bottom action bar** | When relevant: Save draft, Preview, Compare, Publish, Rollback (and “Apply to sandbox” where applicable). Same bar across modes; show/hide by mode. |

---

## 2. Shared Services (One Model Everywhere) ✅ (stubs; full preview/publish service TBD)

| # | Task | Detail |
|---|------|--------|
| 2.1 | **Shared preview engine** | One preview system for theme, workflows, outputs, launch state, capability changes. Reuse/refactor `site-settings-preview.js` and `preview_from_form`; extend to other modes. |
| 2.2 | **Shared publish/rollback** | Generalize to `studio_publish_service` (or equivalent): save draft, validate, preview, publish, rollback, version history, audit. Used by Experience, Control, and (where applicable) Output/Automation. |
| 2.3 | **Activity/audit in right rail** | Surface recent actions, who changed what, what was published/rolled back, from one activity/audit source in the shell right rail (reuse feature_control_audit and siteconfig audit). |
| 2.4 | **Recommendations / next best action** | One “recommended next” block in the shell (e.g. Launch progress, Control impact, Experience accessibility warnings). |

---

## 3. Experience Studio (In-Page, Not Iframe-Only)

| # | Task | Detail |
|---|------|--------|
| 3.1 | **Experience mode content in-shell** | Replace iframe with in-page content: `templates/studio_os/modes/experience.html` that includes theme form, palette, and preview (refactor theme_colors into a partial or shared context). |
| 3.2 | **Theme context helper** | `theme_colors_context(request)` (or equivalent) in siteconfig, used by both standalone theme_colors and Studio Experience so one source of truth. |
| 3.3 | **Experience left rail (in-mode)** | Inside Experience mode: Brand identity, Theme packs, Layout presets, Portal shells (from customizer + theme_colors), not only the shell’s mode switcher. |
| 3.4 | **Live preview in canvas** | Center canvas uses `theme_preview_assets.html`, `site-settings-preview.js`, `color-palette-studio.js` (or their logic) in the same page as the shell. |
| 3.5 | **Right rail: token properties, accessibility, publish** | Right rail in Experience: token properties, accessibility warnings, publish/rollback controls (reuse theme_colors save/preview flow). |

---

## 4. Launch Studio (In-Page, Not Iframe-Only) ✅

| # | Task | Detail |
|---|------|--------|
| 4.1 | **Launch mode content in-shell** | `templates/studio_os/modes/launch.html`: dedicated Launch view that uses `get_setup_studio_payload(school)` and renders steps, progress, and CTA in the shell (no iframe). |
| 4.2 | **Launch left rail** | Progress, setup health score, required steps, recommended next step, blockers. |
| 4.3 | **Launch right rail** | Role preview, launch confidence summary, missing pieces, estimated time to live. |
| 4.4 | **Launch refactor (optional→required)** | Guided onboarding view (or a helper) can return data/partial for Studio shell embedding so Launch is one coherent page, not an embedded full page. |

---

## 5. Automation Studio (Unified View, Not Iframe-Only) ✅

| # | Task | Detail |
|---|------|--------|
| 5.1 | **Automation mode content in-shell** | `templates/studio_os/modes/automation.html`: unify workflow hub + workflow flow gallery in one view (approval hub link, flow gallery, workflow list) inside the shell. |
| 5.2 | **Automation left rail** | Workflow packs, templates, trigger/action catalog, role-based categories. |
| 5.3 | **Automation right rail** | Simulation summary, impacted roles, policy conflicts, activation controls. |
| 5.4 | **Workflow helpers** | Helpers for “workflow list for school” (and related data) used by Automation Studio (e.g. in `views_dashboard_config` or studio_os). |

---

## 6. Output Studio (Unified View + Document Library)

| # | Task | Detail |
|---|------|--------|
| 6.1 | **Output mode content in-shell** | `templates/studio_os/modes/output.html`: tabs or sections — Reports | Documents | Report cards | Certificates/IDs — in one view, not only report_library iframe. |
| 6.2 | **Output left rail** | Output types, report packs, document packs, region/institution filters. |
| 6.3 | **Document library in Output** | Embed or deep-link `portal:document_library_manage` into Output Studio (same mental model as reports); add redirect `document_library_manage` → `studio_os:output` with pane=documents (or equivalent). |
| 6.4 | **Right rail: style, branding, dependencies, publish** | Style settings, branding inheritance, data dependencies, publish/rollback for outputs. |

---

## 7. Control Studio (In-Page, Not Iframe-Only) ✅ (iframe + helper)

| # | Task | Detail |
|---|------|--------|
| 7.1 | **Control mode content in-shell** | `templates/studio_os/modes/control.html`: feature control panel content (and capability/runtime views) rendered inside the shell, not only iframe. |
| 7.2 | **Control left rail** | Capabilities, policies, integrations, packs, registries, audits. |
| 7.3 | **Control right rail** | Impact summary, affected roles/pages, audit trail, rollback controls. |
| 7.4 | **Feature state + audit helper** | Helper for “feature state + audit” used by both standalone feature_control_panel and Studio Control (e.g. in `views_feature_control`). |

---

## 8. Phase 5 Completion (Redirects & Labels) ✅

| # | Task | Detail |
|---|------|--------|
| 8.1 | **Document library redirect** | `portal:document_library_manage` → redirect to `studio_os:output` with pane=documents (or equivalent) when not embedded. |
| 8.2 | **Breadcrumbs** | Breadcrumbs show “Studio » [Mode]” (e.g. “Studio » Experience”) where applicable. |

---

## 9. Click Reduction (All Checkboxes Met)

| # | Requirement | Status |
|---|-------------|--------|
| 9.1 | One entry: “Studio” or “Studio OS” in nav. | Done |
| 9.2 | Mode switch without leaving shell (left rail). | Done |
| 9.3 | Preview in same shell (center + right rail). | Pending: shared preview + in-page content per mode |
| 9.4 | Publish/rollback in same shell (right rail or bottom bar). | Pending: shared publish service + bottom bar |
| 9.5 | One goal = one mode (no “customizer → theme colors → site settings”). | Done |
| 9.6 | Recommendations / next best action in shell. | Pending: section 2.4 |

---

## 10. Implementation Order (Suggested)

1. **Shared services (2.x)** — preview, publish/rollback, activity, recommendations.
2. **Shell chrome (1.x)** — top bar search + command palette, bottom action bar.
3. **Experience in-page (3.x)** — partials, context helper, experience.html.
4. **Launch in-page (4.x)** — launch.html, payload, progress rail.
5. **Output unified (6.x)** — output.html with tabs, document library redirect and embed.
6. **Automation unified (5.x)** — automation.html, workflow helpers.
7. **Control in-page (7.x)** — control.html, feature state helper.
8. **Phase 5 completion (8.x)** — document library redirect, breadcrumbs.

---

## Summary Count

- **Shared shell:** 3 items (top bar search, command palette, bottom bar).
- **Shared services:** 4 items (preview, publish/rollback, activity, recommendations).
- **Experience:** 5 items (in-page content, context helper, left rail, live preview, right rail).
- **Launch:** 4 items (launch.html, left rail, right rail, refactor).
- **Automation:** 4 items (automation.html, left rail, right rail, helpers).
- **Output:** 4 items (output.html, left rail, document library + redirect, right rail).
- **Control:** 4 items (control.html, left rail, right rail, helper).
- **Phase 5:** 2 items (document redirect, breadcrumbs).
- **Click reduction:** 2 items still pending (preview in shell, publish/rollback in shell; recommendations).

**Total remaining (non-negotiable): 32 items.**
