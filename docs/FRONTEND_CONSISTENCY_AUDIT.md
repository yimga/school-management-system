# Frontend consistency audit

Component inventory, table/form/card/state usage, visual debt map, template reuse, and page-family assignment (Execution Master §3.11). Use this to drive the "high-end feel" into actual code.

## Component inventory

| Category | Source | Usage |
|----------|--------|--------|
| **Tables** | table-system.css (.table-family, .table-density-*, .table-status-chip) | List pages: super_tenant_health, super_usage, backend_student_list, backend_applicant_list, etc. |
| **Forms** | form-system.css (.form-section, validation, .form-actions) | All forms; backend create/edit, admin, portal. |
| **Cards** | card-grammar.css (.card--kpi, .card--summary, .card--entity, .card--alert, .card--widget, .card--settings) | Dashboards, list headers, detail panels. |
| **Charts** | chart-rules.css (chart-container, chart-legend, chart-color--*) | super_analytics_overview, reports, dashboards. |
| **Buttons** | Bootstrap + design-tokens (--school-primary, --school-accent) | All surfaces; use btn-primary, btn-outline-* consistently. |
| **Chips/badges** | .table-status-chip, .badge (semantic modifiers) | Status in tables and lists; avoid ad-hoc bg-* colors. |
| **Sidebars** | control_plane_sidebar.html, portal_sidebar.html | Control plane and tenant; data-driven from nav builders. |
| **Page family partials** | partials/page_families/ (title_block, action_bar, filter_row, content_card, empty_state, loading_state) | List, detail, dashboard pages; see page_families.md. |

## Table inventory

- **List-family pages** should use: .table-family, .table-density-comfortable (or compact/spacious), .table-status-chip for status.
- **Reference:** backend_student_list, super_tenant_health, super_usage, people/backend_applicant_list.
- **Gap:** Any list template not using table-system classes should be refactored (track in VISUAL_DEBT_BACKLOG).

## Form inventory

- **Form pages** should use: .form-section for grouping, consistent field sizes, validation feedback from form-system.
- **Reference:** backend_student_create, admin forms (Unfold), portal forms.
- **Gap:** Ad-hoc form layouts; migrate to form-section and shared validation styling.

## Card inventory

- **Dashboard and detail pages** should use card-grammar classes (card--kpi, card--summary, card--entity, etc.) instead of generic .card with one-off styles.
- **Reference:** super_migration_cloud, super_analytics_overview, dashboard widgets.
- **Gap:** Generic .card without modifier class; replace with card--* for consistency.

## State inventory

- **Empty:** Use partial `partials/page_families/empty_state.html` (message, icon, optional empty_state_actions).
- **Loading:** Use `partials/page_families/loading_state.html` or skeleton; swap on HTMX load.
- **Error:** Consistent alert pattern; no random colors.
- **Reference:** docs/architecture/page_families.md.

## Visual debt map

- **VISUAL_DEBT_BACKLOG.md** tracks items (shell consistency, headers, tables, cards, spacing, sidebar, empty/loading). Remediation status and reference pages are listed there.
- **New pages** must: extend correct shell base, use page family partials, use design-tokens and surface-themes, avoid TBD/placeholder text (use "—" or N/A).

## Template reuse map

- **Shell bases:** control_plane_skeleton → control_plane_base; portal_base; backend_base; marketing_base; admin/base_site. All tenant/control/marketing pages must extend one of these.
- **Partials:** page_families/*, partials/control_plane_sidebar.html, partials/portal_sidebar.html. Use include; do not duplicate layout HTML.
- **Duplicate layout:** Any template that reimplements header + sidebar + main content instead of extending base should be refactored (see CLEANUP_AND_DELETION_PLAN.md).

## Page-family assignment audit

| Family | Partial(s) | Example templates |
|--------|------------|-------------------|
| Dashboard | title_block, content_card, widgets | super_dashboard, portal dashboards |
| List | title_block, filter_row, content_card, table-family, empty_state | super_tenant_health, super_usage, backend_student_list |
| Record detail | title_block, action_bar, content_card | super_tenant_360, invoice_detail |
| Wizard | steps, form-section, sidebar summary | backend_student_create, create_school_wizard |
| Settings | form-section, card--settings | feature_control_panel, user_preferences |
| Queue/inbox | list family + status chips | support_queue, applicant list |
| Report/analytics | title_block, chart-rules, export | super_analytics_overview, reports/* |
| Inspector/diff | panels, side-by-side | super_policy_diff |

Assign every new page to a family and use the corresponding partials and CSS.

## References

- docs/architecture/page_families.md
- docs/VISUAL_DEBT_BACKLOG.md
- docs/architecture/PAGE_FAMILY_AND_SHELL_MAP.md
- docs/architecture/CLEANUP_AND_DELETION_PLAN.md
- static/css/table-system.css, form-system.css, card-grammar.css, chart-rules.css
- templates/partials/page_families/
