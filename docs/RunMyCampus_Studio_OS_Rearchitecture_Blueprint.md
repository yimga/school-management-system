# RunMyCampus Studio OS Rearchitecture Blueprint

## Mission

Replace the current fragmented tool surfaces with a **single premium Studio OS**:

- **Current:** customizer, theme_colors, feature_control_panel, report_library, document_library_manage, workflow_hub, design_studio, setup simulator, scattered preview/settings.
- **Target:** One unified **RunMyCampus Studio OS** with five work modes: Experience, Automation, Output, Launch, Control.

Studio OS must feel: innovative, intuitive, professional, modern, low-click, preview-first, governed, and beautiful.

---

## 1. Why the Current Model Is Not Enough

| Current surface | Problem |
|-----------------|--------|
| `customizer.html` | Navigation card only; sends users elsewhere. Not a workspace. |
| `theme_colors.html` | Config page with preview; not a design environment. |
| `feature_control_panel.html` | Toggle panel; not capability composition. |
| `report_library.html` | Static library; not output design/publish. |
| `document_library_manage.html` | File manager; not document operating system. |
| `workflow_hub.html` | Hub of links; not automation studio. |
| `design_studio.py` | Template→PDF only; narrow scope. |
| Setup / onboarding | Scattered; not one Launch Studio. |

**North-star rule:** Users should think “I’m shaping experience / automating / publishing / launching / governing” — not “I’m opening customizer / feature control / report library.”

---

## 2. The New Model: One Shell, Five Modes

| Mode | Purpose | Replaces / absorbs |
|------|---------|--------------------|
| **Experience Studio** | Branding, theming, shells, portals, dashboards | customizer, theme_colors, theme packs, color_palette_studio, branding fragments |
| **Automation Studio** | Workflows, approvals, simulation, activation | workflow_hub, workflow_flow_gallery, approval hub entry, workflow preview |
| **Output Studio** | Reports, documents, certificates, exports | report_library, document_library_manage, reportcard_builder, design_studio outputs |
| **Launch Studio** | Signup→live with minimal clicks | guided_onboarding, setup_studio, marketing_setup_simulator, setup fragments |
| **Control Studio** | Capabilities, policies, integrations, runtime | feature_control_panel, site settings sprawl, runtime/blueprint/admin fragments |

All five share: one nav, one command/search, one preview engine, one publish/rollback, one activity/audit.

---

## 3. Codebase-Specific Migration Map

### 3.1 Current routes and files (to absorb or redirect)

| Current route/name | View / template | Future home |
|-------------------|-----------------|-------------|
| `siteconfig:customizer` | `views.customizer` → `customizer.html` | Experience Studio entry |
| `siteconfig:theme_colors` | `views.theme_colors_page` → `theme_colors.html` | Experience Studio theme pane |
| `siteconfig:feature_control_panel` | `views_feature_control.feature_control_panel` → `feature_control_panel.html` | Control Studio |
| `siteconfig:report_library` | `views.report_library` → `report_library.html` | Output Studio |
| `portal:document_library_manage` | portal view → `document_library_manage.html` | Output Studio |
| `siteconfig:workflow_hub` | `views_dashboard_config.workflow_hub` → `workflow_hub.html` | Automation Studio |
| `siteconfig:guided_onboarding` | customersuccess → guided onboarding | Launch Studio |
| `siteconfig:template_gallery` | `template_gallery_page` → `template_gallery.html` | Experience Studio (theme packs) |
| `siteconfig:reportcard_builder` | reportcard_builder → `reportcard_builder.html` | Output Studio |
| Design Studio (PDF) | `siteconfig/design_studio.py` | Output Studio backend service |
| `setup_simulator` (marketing) | `marketing_setup_simulator.html` | Public teaser for Launch Studio |

### 3.2 Key backend modules (refactor, do not delete yet)

| Module | Role after Studio OS |
|--------|----------------------|
| `apps/siteconfig/views.py` | customizer, theme_colors, report_library → delegate to studio_os or inline in modes |
| `apps/siteconfig/views_feature_control.py` | Control Studio data + actions |
| `apps/siteconfig/views_dashboard_config.py` | workflow_hub → Automation Studio entry |
| `apps/siteconfig/design_studio.py` | Output Studio: render_template_to_pdf, design_template_http_response_pdf |
| `apps/siteconfig/views_console_domains.py` | Console/domains → Control Studio or shared shell |
| `apps/portal` (document library) | Output Studio: document management |
| `apps/setup_studio/services.py` | Launch Studio: get_setup_studio_payload, compile_setup_studio |
| `apps/customersuccess/views_tenant.py` | Launch Studio: execute_launch_view, guided_onboarding_view |
| `static/js/color-palette-studio.js` | Experience Studio: palette UI |
| `static/js/site-settings-preview.js` | Shared preview engine (shell) |
| `templates/admin/components/color_palette_studio.html` | Experience Studio include |
| `templates/admin/components/theme_preview_assets.html` | Shared preview assets |

### 3.3 New app and routes

- **App:** `apps/studio_os`
- **Canonical entry:** `/studio/` (or `/studio-os/`) → shell with `?mode=experience|automation|output|launch|control`
- **Direct mode URLs:** `/studio/experience/`, `/studio/automation/`, `/studio/output/`, `/studio/launch/`, `/studio/control/`
- **Redirects (Phase 5):**  
  - `/siteconfig/customizer/` → `/studio/?mode=experience`  
  - `/siteconfig/theme-colors/` → `/studio/experience/?pane=theme`  
  - `/siteconfig/feature-control/` → `/studio/control/`  
  - `/siteconfig/reports/` → `/studio/output/`  
  - `/portal/backend/documents/` → `/studio/output/?pane=documents`  
  - `/siteconfig/workflow-hub/` → `/studio/automation/`  
  - `siteconfig:guided_onboarding` → `/studio/launch/`

---

## 4. Shared Shell Layout (IA)

- **Top bar:** Global search, command palette, tenant/school, notifications, AI trigger, user/role.
- **Left rail:** Studio OS home, Experience, Automation, Output, Launch, Control (+ optional Library/Help drawers).
- **Center canvas:** Mode-specific editing/composition/simulation.
- **Right rail:** Properties, impact summary, audit, publish/rollback, recommendations.
- **Bottom bar (when relevant):** Save draft, Preview, Compare, Publish, Rollback.

---

## 5. Implementation Phases (Summary)

| Phase | Focus | Deliverables |
|-------|--------|--------------|
| **1** | Shared shell | studio_os app, shell template, nav, mode routing, redirect stubs |
| **2** | Experience + Launch | Experience Studio (theme/brand from current theme_colors/customizer), Launch Studio (from guided_onboarding/setup_studio) |
| **3** | Automation + Output | Automation Studio (workflow hub → flow builder/simulator), Output Studio (report + document library + design_studio) |
| **4** | Control | Control Studio (feature control + capability/runtime views) |
| **5** | Retire old identities | Redirects from old URLs, deprecate old nav labels, single entry: Studio OS |

---

## 6. Success Criteria

- One place to “shape experience,” “automate,” “publish outputs,” “launch,” “govern.”
- Fewer clicks: choose mode → edit on canvas → preview → publish.
- One preview model and one publish/rollback model across modes.
- Goal-centered language (Experience, Automation, Output, Launch, Control), not internal labels (Customizer, Feature Control, Report Library).

---

## 7. Non-Negotiable

RunMyCampus must not keep growing separate tool pages. It must evolve into **one premium Studio OS** where experience, automation, outputs, launch, and control are each done in one place — inside one coherent workspace.

For detailed IA, component list, service layer, and data model per mode, see **Studio_OS_Implementation_Plan.md**.
