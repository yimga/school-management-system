# Visual debt backlog

Audit of representative pages for shell consistency, headers, duplicated layouts, components, spacing, and states. Remediation tracked here. Blueprint §15.

## Audit dimensions

- **Shell consistency:** Correct base template and surface theme (marketing / cp / admin / tenant).
- **Headers:** Consistent title block (title, subtitle, breadcrumb, back link).
- **Duplicated layouts:** Same pattern repeated instead of shared partials.
- **Cards/tables/forms:** Aligned to table system, form system, card grammar.
- **Spacing:** Token-based (e.g. `--mkt-spacing-section`, `--table-density-*`).
- **Leftover templates:** Unused or duplicate templates to remove.
- **Colors:** Semantic tokens, no ad-hoc hex.
- **Sidebar grouping:** Matches taxonomy; active state correct.
- **Empty/loading/mobile:** Defined states per page family.

## Backlog items

| ID | Area | Description | Priority | Status |
|----|------|-------------|----------|--------|
| V1 | Control plane | Tenant Health: use page family title_block + content_card; table density token | P2 | Done |
| V2 | Control plane | Migration console: same; add filter row if filters exist | P2 | Done |
| V3 | Tenant | Student list: already has filter row; align to list-family partials | P2 | Done |
| V4 | Admin | Unfold list/detail: ensure Admin theme applied; table density | P2 | Done |
| V5 | Marketing | Inner pages: ensure all use marketing_page + marketing-home.css | P3 | Done |
| V6 | Global | Replace ad-hoc badge colors with semantic status chips (table-system) | P2 | Done |
| V7 | Global | Empty states: use partial `page_families/empty_state.html` where missing | P3 | Done |
| V8 | Global | Loading states: consistent skeleton or spinner per family | P3 | Done |
| V9 | Tenant | Role shells: ensure sidebar filtered by role (Phase 5) | P2 | Done |
| V10 | Control plane | Sidebar: collapse/compact icon mode (optional) | P3 | Done |
| V11 | Phase 8 | Chart: one analytics/super page using chart-rules.css (legend/axis/semantic colors) as reference | P3 | Done |

## Page family adoption

Pages refactored to use shared page family partials (Phase 7):

- **super_tenant_health.html** — List family: title_block, content_card, table-family, table-density-comfortable, empty_state, table-status-chip.
- **super_usage.html** — List family: title_block, content_card, table-family, table-density-comfortable, empty_state, table-status-chip.
- **backend_student_list.html** — List family: title_block (primary action), filter_row, content_card, table-status-chip.
- **super_migration_cloud.html** — Title block + content card (signature screen).
- **super_analytics_overview.html** — Title block + content cards + chart-rules reference (chart-container, chart-legend, chart-color--*).

## Phase 8 component systems

- **Table system** (`static/css/table-system.css`): density classes, `.table-family`, status chips, sticky first column, mobile scroll. Loaded in control plane, portal, base, admin.
- **Form system** (`static/css/form-system.css`): `.form-section`, validation, `.form-actions`. Loaded in all shells.
- **Card grammar** (`static/css/card-grammar.css`): `.card--kpi`, `.card--summary`, `.card--entity`, `.card--alert`, `.card--widget`, `.card--settings`. Loaded in all shells.
- **Chart rules** (`static/css/chart-rules.css`): legend/axis tokens, semantic series colors. Loaded in all shells.

Reference: Tenant Health and Migration Cloud use page family + table/card; student list uses title_block + filter_row + content_card.

## Remediation status

- **Done:** Design tokens, surface themes, control plane sidebar data-driven, marketing bar, experience_shells + sidebar taxonomy docs, role-to-nav mapping doc, page family partials, Phase 8 table/form/card/chart CSS, refactored pages, and **all follow-up items V1–V11**.
- **V1–V3:** Tenant Health and Migration use title_block + content_card + table-family; Student list uses title_block, filter_row, content_card; semantic status chips on tenant_health, super_usage, backend_student_list.
- **V4:** Admin theme via `data-surface="admin"`; table-system.css loaded in admin.
- **V5:** Marketing inner pages use `marketing_page.html` with `marketing-surface` and `marketing-home.css` (see MARKETING_PREMIUM_BAR.md).
- **V6:** table-status-chip used on super_tenant_health, super_usage, backend_student_list.
- **V7:** empty_state partial used when no tenants (tenant_health) and no schools (super_usage); student list uses dashboard_empty_state.
- **V8:** loading_state partial documented and reference in `docs/architecture/page_families.md`.
- **V9:** Role filtering implemented in `portal_sidebar_items.build_portal_sidebar_items`; documented in sidebar_navigation_taxonomy.md.
- **V10:** CP sidebar has collapsible groups (Bootstrap collapse) and compact icon-only mode (toggle + localStorage).
- **V11:** super_analytics_overview uses chart-container, chart-legend, chart-color--* from chart-rules.css.
