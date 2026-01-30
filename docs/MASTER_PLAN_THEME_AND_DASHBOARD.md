# Master Plan: Theme, Dashboard & Admin Customization

This document is the **single overview** of how the school management platform’s **theme**, **custom dashboards**, and **admin-controlled configuration** fit together. It ties everything we’ve discussed into one plan and shows how each part connects.

---

## 1. What We’re Controlling (Big Picture)

| Layer | What it controls | Who configures it | Where it applies |
|-------|------------------|-------------------|------------------|
| **Theme & site identity** | Look and feel: logo, colors, typography, header/footer, login, layout style, sidebar defaults | Admins via **Site Settings** (Branding, Theme & Experience, Footer, etc.) | Portal (teacher/parent), Backend (staff), Django Admin |
| **Custom dashboards** | Which widgets appear, their order, size, and presentation; drag-and-drop layout (backend only) | Admins via **Dashboard Widgets** + **Site Settings**; staff users via **drag-and-drop** on backend dashboard only | Backend dashboard (staff); teacher/parent dashboards use **fixed** layout |
| **Role-based behavior** | Who sees which widgets, which pages, default views | Admins via **DashboardWidget** (required_role, allowed_roles), **Site Settings** (default_dashboard_widgets, etc.) | All dashboards |

**In one sentence:** Admins control **branding and global layout** from Site Settings and **widget catalog and role visibility** from the Dashboard Widgets admin; **staff** can additionally **reorder and resize** widgets on the **backend dashboard** via drag-and-drop; teachers and parents see a **fixed, sensible** dashboard layout.

---

## 2. How Custom Dashboards Work on This Platform

Creating a custom dashboard here uses **built-in admin panel features** and a **configurable panel system**—not an external tool like Domo or Power BI. The following map to what we have:

| Common method (industry) | How we do it on this platform |
|--------------------------|-------------------------------|
| **Drag-and-drop UI builders** | **Backend dashboard only:** Staff use a “Drag & drop layout” toggle; `dashboard-layout.js` (Sortable.js) and `/api/dashboard/layout/backend/` save order/size/variant per user. Teacher and parent dashboards do **not** offer drag-and-drop; they use a fixed template order. |
| **Built-in admin “Dashboards” / “Reports”** | Admins go to **Site Settings → Dashboard Widgets** (or the Django admin for `DashboardWidget`). Each row = one widget (card): id, name, page, required_role, allowed_roles, template_path, allowed_sizes, default_size, etc. No “Create New Dashboard” wizard; widgets are pre-defined and turned on/off per role/page. |
| **Pre-built widgets / metrics** | **DashboardWidget** catalog: each widget has a `widget_type` (stats, chart, list, action, alert, feed), `page` (backend, teacher, parent, finance, analytics, …), and `required_role` / `allowed_roles`. Admins enable/disable and set default size/variant. Data comes from existing views/services (e.g. backend stats, parent_dashboard_widget_data). |
| **Visualization (charts, graphs)** | Chart widgets use backend data and render in the dashboard template (e.g. Chart.js). **Implemented:** chart type (bar/pie/line/doughnut/radar) per widget via `DashboardWidget.chart_type`; passed as `data-widget-chart-types` on `#dashboard-layout`; `dashboard-charts.js` reads it and uses the configured type when the canvas is inside a `[data-widget-id]` container. |
| **Customization settings (sizing, rearranging)** | **Backend only:** Staff can resize and reorder panels; layout is saved in **DashboardLayout** (user + page `backend`). Teacher/parent: **no** rearranging; layout is fixed in the template. |

So: we use **admin-configured widgets** and **staff-only drag-and-drop** on the backend to get a “custom dashboard” experience without external BI tools. Teachers and parents get a **consistent, fixed layout** that admins control via which widgets are enabled for their role.

---

## 3. Three Surfaces and Where Theme vs Dashboard Apply

| Surface | URL | Who | Theme (look & feel) | Dashboard (widgets & layout) |
|---------|-----|-----|----------------------|-----------------------------|
| **Portal (teacher)** | `/portal/teacher/` | Teachers | SiteSettings + ThemePack + user theme preference | Fixed template order; widgets from DashboardWidget + resolve_dashboard_widgets; **no** drag-and-drop. |
| **Portal (parent)** | `/portal/parent/` | Parents | Same | Same: fixed layout, **no** drag-and-drop. |
| **Backend** | `/backend/` | Staff, admins | SiteSettings.backend_console_theme (Dark/Light), same header/sidebar as portal | **Drag-and-drop enabled.** Staff see “Drag & drop layout” toggle; layout saved per user to DashboardLayout (page=backend). |
| **Django Admin** | `/admin/` | Staff, superusers | SiteSettings.admin_sidebar_* colors + admin_theme_pack (logo/bg) | Admin has its own dashboard/templates; not the same widget system as portal/backend. |

Theme = **global** (logo, colors, header, footer, login, layout style).  
Dashboard = **per-page, per-role** (which widgets, and on backend only: per-user order/size).

---

## 4. How It All Ties Together

### 4.1 Flow: From Admin Config to What the User Sees

1. **Admin configures theme (Site Settings)**  
   Branding, colors, fonts, backend_console_theme, admin_sidebar_* , footer, etc. → Used by base templates (portal_base, backend_base, admin base_site) so **every** page gets the same look and structure.

2. **Admin configures widgets (Dashboard Widgets)**  
   Each DashboardWidget: page, required_role, allowed_roles, template_path, sizes/variants. Defines **what can appear** on each dashboard. Default widget set per role comes from `default_dashboard_widgets(role)` (e.g. in SiteSettings / code).

3. **Page load (e.g. backend or parent dashboard)**  
   - **Theme:** Base template pulls from SiteSettings (and ThemePack) → header, sidebar, colors, layout_style (when we add it).  
   - **Dashboard:** View calls `load_dashboard_layout_settings(user, page)` and passes `dashboard_layout_url` and `allow_custom_layout`.  
   - **Backend:** `allow_custom_layout` is True for staff → “Drag & drop layout” toggle and customizer JS are shown; GET/PUT `/api/dashboard/layout/backend/` load/save layout.  
   - **Teacher/Parent:** `allow_custom_layout` is False → No toggle, no customizer; fixed template order; GET still loads any saved layout (e.g. from a previous role or admin-set default) for display, but PUT is forbidden so they cannot change layout.

4. **Saving layout (backend only)**  
   Staff drag widgets → JS sends PUT to `/api/dashboard/layout/backend/` → API checks `_can_customize(user)` (staff or role in ALLOWED_CUSTOM_ROLES: ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN) → Saves to DashboardLayout (user, page=backend). Teacher/parent PUT returns 403.

So: **theme** drives the **frame** (chrome, branding, layout style); **dashboard** drives the **content** (widgets and, on backend only, their order/size). Both are admin-configurable; only staff can **customize** layout via drag-and-drop.

### 4.2 Option A: Drag-and-Drop Only on Backend (Current Design)

- **ALLOWED_CUSTOM_ROLES** = ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN (no TEACHER, no PARENT).  
- **allow_custom_layout** is True only for staff (or those roles). Teacher/parent get False → no “Drag & drop layout” card, no dashboard-customizer.js.  
- **API:** GET `/api/dashboard/layout/<page>/` still allowed for teacher/parent (so their page can load layout if needed); PUT/PATCH require `_can_customize(user)` → 403 for teacher/parent.  
- Result: **Backend = customizable dashboard; teacher/parent = fixed dashboard.**

### 4.3 Where the “5-Second Glance” Fits

- **Backend:** Staff can put “Quick actions,” “Finance trend,” “Attendance snapshot,” etc. where they want so the first glance is relevant.  
- **Teacher/Parent:** Admins control relevance by **which widgets are enabled** for the role and by **template order**; users get a consistent, fast-to-scan layout without needing to customize.

---

## 5. Reference to Detailed Plans

| Topic | Document | Contents |
|-------|----------|----------|
| **Theme & site control (full)** | [THEME_AND_CONFIG_MASTER_PLAN.md](./THEME_AND_CONFIG_MASTER_PLAN.md) | Definition of theme, three surfaces, admin-managed components (branding, layout, widgets, communication, role-specific), phased implementation (Phase A–D), how theme ties with drag-and-drop, **how it works on backend/teacher/parent**, “Is it important? Do we need it?”, implementation checklist. |
| **Drag-and-drop (backend only)** | Same doc, §6 | What the drag-and-drop system controls, what the theme plan adds around it, data flow, **Option A** (backend only), API and ALLOWED_CUSTOM_ROLES. |
| **Drag-and-drop fixes / behavior** | [DRAG_AND_DROP_FIXES.md](./DRAG_AND_DROP_FIXES.md) | Column detection, toggle IDs, page detection, script conflicts, visual feedback. |
| **Widget catalog & layout seeds** | [KB_WIDGET_CATALOG_LAYOUTS.md](./KB_WIDGET_CATALOG_LAYOUTS.md) | Where to edit widgets, layout persistence, adding new movable blocks, migrations. |

---

## 6. Implementation Status (Summary)

| Area | Status | Notes |
|------|--------|--------|
| **Theme: branding, colors, fonts** | ✅ In place | SiteSettings, ThemePack, context_processors. |
| **Theme: backend console Dark/Light** | ✅ In place | backend_console_theme, backend-dark-theme.css / backend-light-theme.css. |
| **Theme: admin sidebar** | ✅ In place | admin_sidebar_* colors, admin_theme_pack. |
| **Theme: login, favicon, header toggles, layout_style, sidebar defaults** | ✅ In place | Phase A–C: login from SITE, header toggles, favicon, layout_style (boxed/fluid), default_sidebar_collapsed, portal_sidebar_order. |
| **Dashboard: widget catalog & role visibility** | ✅ In place | DashboardWidget, default_dashboard_widgets, resolve_dashboard_widgets. |
| **Dashboard: drag-and-drop (backend only)** | ✅ Configured (Option A) | ALLOWED_CUSTOM_ROLES excludes TEACHER/PARENT; API PUT requires _can_customize. Teacher/parent see fixed layout. |
| **Dashboard: layout persistence** | ✅ In place | DashboardLayout, `/api/dashboard/layout/<page>/`, dashboard-layout.js, dashboard-customizer.js (backend only). |
| **Dashboard: chart type per widget** | ✅ In place | DashboardWidget.chart_type; backend_dashboard passes widget_chart_types_json; #dashboard-layout has data-widget-chart-types; dashboard-charts.js uses it when creating charts (per-widget override). |

---

## 7. One-Page Diagram (How They Tie)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ADMIN (Site Settings + Dashboard Widgets)        │
│  • Branding: logo, colors, fonts, favicon, login hero                     │
│  • Theme: backend_console_theme, admin_sidebar_*, layout_style, etc.     │
│  • Widgets: which cards exist, for which page/role, sizes/variants       │
└─────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Base templates (portal_base, backend_base, admin base_site)             │
│  → Apply theme (header, footer, sidebar, colors, layout wrapper)         │
└─────────────────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Portal       │ │ Backend      │ │ Django Admin │
│ (teacher,    │ │ (staff)      │ │ (staff)      │
│  parent)     │ │              │ │              │
│              │ │              │ │              │
│ Fixed        │ │ Drag-and-    │ │ Own          │
│ dashboard    │ │ drop layout  │ │ dashboard    │
│ layout       │ │ (toggle +    │ │ & sidebar    │
│              │ │  API save)   │ │              │
│ allow_       │ │ allow_       │ │              │
│ custom_      │ │ custom_      │ │              │
│ layout=False │ │ layout=True  │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
        │                 │
        ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  DashboardLayout (per user + page)  /  DashboardWidget (catalog)         │
│  • Backend: staff can PUT layout for page=backend                        │
│  • Teacher/Parent: GET only; no PUT → fixed order in template            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

This is the **bigger plan**: theme and dashboard are configured in the admin; theme applies globally to all three surfaces; the **custom dashboard** (drag-and-drop, sizing, rearranging) is **backend-only**; teacher and parent get a **fixed, admin-controlled** dashboard that still uses the same widget catalog and role rules.
