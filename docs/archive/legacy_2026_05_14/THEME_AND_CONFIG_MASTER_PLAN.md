# Theme & Site Control Master Plan

This document maps the school management platform’s **theme** to the full set of design and layout components that define the visual appearance and user experience. The goal is **backend control of everything**: admins manage all theme components from Site Settings (and related models) so the site looks and behaves according to school branding and policy—across **Portal** (teachers, parents, students), **Backend Console** (staff workflow), and **Django Admin** (`/admin`).

---

## 1. Definition: What Is the “Theme”?

A **website theme** is the front-end design, layout, and styling that determines how the site looks and feels. In this platform, the theme is implemented as **design tokens and layout instructions served by the backend** to the frontend (HTML/CSS/JS).

### Essential Components of the Website Theme

| Component | Description | Where It Applies |
|-----------|-------------|------------------|
| **Header & navigation** | Top bar: branding, nav links, search, notifications, user menu | Portal, Backend, (Admin has its own) |
| **Footer** | Bottom: contact, copyright, links, badges | Portal, login, reports |
| **Typography** | Font families, sizes, styles for headings and body | All surfaces |
| **Color palette** | Backgrounds, text, buttons, links, semantic colors (success/danger) | All surfaces |
| **Page layout & structure** | Single/multi-column, sidebars, spacing, boxed vs fluid | Portal, Backend |
| **Hero / above-the-fold** | Login hero, portal background, carousel/banner | Login, Portal |
| **Buttons & CTAs** | Primary/secondary styles, hover states | All surfaces |
| **Responsive & adaptive design** | Mobile/tablet/desktop behavior | Code; breakpoints can be tokenized later |
| **Sidebar & widgets** | Nav sidebar, dashboard widgets, recent activity | Portal, Backend, Admin |
| **Forms & interactive elements** | Inputs, search, hover effects | All surfaces |

Admins should be able to control **Core Visual Identity**, **Layout/Navigation**, **Modular Widgets**, **Communication/Portal** (login, email, domain), and **Role-specific personalization** from the backend—without changing frontend code.

---

## 2. Three Theme Surfaces

| Surface | URL / Scope | Who Sees It | Theme Source |
|---------|-------------|-------------|---------------|
| **Portal** | `/portal/`, teacher/parent/student dashboards, `portal_base.html` | Teachers, Parents, Students | SiteSettings + ThemePack + DashboardUserPreference (per-user theme) |
| **Backend Console** | `/backend/`, workflow center, entity console, `backend_base.html` | Staff, Admins | SiteSettings.backend_console_theme (Dark/Light) + fixed CSS |
| **Django Admin** | `/admin/` | Staff, Superusers | SiteSettings.admin_sidebar_* colors + admin_theme_pack (logo/bg) |

- **Portal** and **Backend** share the same base layout (sidebar + header from `portal_base.html`); Backend overrides with `backend-dark-theme.css` / `backend-light-theme.css` and body class.
- **Admin** is a separate app; it uses CSS variables from `SITE.admin_sidebar_*` and optional ThemePack for logo/background.

---

## 3. Admin-Managed Theme Components (Full Mapping)

### 3.1 Core Visual Identity (Branding)

| Component | Portal | Backend | Admin | Current State | Gap / Plan |
|-----------|--------|---------|-------|---------------|------------|
| **Primary header logo** | ✅ SITE/ThemePack logo | ✅ Same (portal_base) | ✅ admin_theme_pack or theme_pack | Logo from SiteSettings or ThemePack; context: SITE_LOGO_URL, SITE_ADMIN_LOGO_URL | — |
| **Collapsed sidebar icon** | ❌ | ❌ | ❌ | No dedicated upload | **Add:** `sidebar_icon` (ImageField) on SiteSettings or ThemePack; use in sidebar when collapsed. |
| **Favicon** | ❌ Static | ❌ | ❌ | No favicon in Site Settings | **Add:** `favicon` (ImageField) on SiteSettings; output in base.html, portal_base, backend_base, admin base. |
| **Primary color** | ✅ primary_color | ✅ (via CSS vars in backend_dashboard) | ⚠️ admin_sidebar_* only | SiteSettings.primary_color, accent, success, warning, danger | Optional: “Use site primary for admin” toggle to sync admin accent with primary_color. |
| **Secondary / accent** | ✅ accent_color | ✅ | — | SiteSettings.accent_color | — |
| **Semantic colors** | ✅ success, warning, danger | ✅ | — | In SiteSettings | — |
| **Typography – primary font** | ✅ brand_font | ✅ | — | SiteSettings.brand_font; ThemePack.font_family | — |
| **Typography – secondary font** | ❌ | ❌ | ❌ | None | **Add (optional):** `secondary_font` + “use for headings” so admins can set a distinct heading font. |
| **Base font size** | ❌ | ❌ | ❌ | In CSS only | **Add (optional):** `base_font_size` (e.g. 14, 16) as design token; use in root CSS variable. |

### 3.2 Layout and Navigation Controls

| Component | Portal | Backend | Admin | Current State | Gap / Plan |
|-----------|--------|---------|-------|---------------|------------|
| **Sidebar – dark/light** | ✅ use_dark_mode, theme_brightness, user pref | ✅ backend_console_theme | ✅ admin_sidebar_* (full color set) | Each surface has its own control | — |
| **Sidebar – default expanded/collapsed** | ⚠️ User pref only | ⚠️ | — | DashboardUserPreference.sidebar_collapsed | **Add:** `default_sidebar_collapsed` (bool) on SiteSettings; use as initial value for new users. |
| **Sidebar – menu order** | ❌ | ❌ | — | Portal sidebar order is code-driven | **Add:** Optional JSON config (e.g. `portal_sidebar_order` or per-role) listing menu item IDs; render sidebar from it when set. |
| **Header – search** | ✅ In code | ✅ | — | No admin toggle | **Add:** `show_header_search` (bool); conditionally show search in portal_base/backend header. |
| **Header – notifications** | ✅ In code | ✅ | — | No admin toggle | **Add:** `show_header_notifications` (bool). |
| **Header – user profile / quick links** | ✅ In code | ✅ | — | No admin toggle | **Add:** `show_header_profile_menu` (bool). |
| **Layout style – boxed vs fluid** | ❌ | ❌ | — | Layout is fluid | **Add:** `layout_style` (boxed \| fluid); wrapper class in portal_base/backend_base; CSS max-width when boxed. |

### 3.3 Modular Dashboard Widgets

| Component | Portal | Backend | Admin | Current State | Gap / Plan |
|-----------|--------|---------|-------|---------------|------------|
| **Widget visibility by role** | ✅ | ✅ | — | default_dashboard_widgets(role), DashboardWidget, DashboardUserPreference | Document; optionally “default widgets per role” in Site Settings (JSON). |
| **Widget order/layout** | ✅ | ✅ | — | DashboardLayout, user drag/drop, visible_widgets | — |
| **Chart type per widget** | ❌ | ❌ | — | Chart type fixed in code | **Add (optional):** Config on DashboardWidget or SiteSettings JSON (e.g. widget_id → bar/pie/line); use in dashboard JS when rendering charts. |

### 3.4 Communication & Portal Customization

| Component | Portal | Backend | Admin | Current State | Gap / Plan |
|-----------|--------|---------|-------|---------------|------------|
| **Custom / branded domain** | — | — | — | Not in config | **Add (optional):** `portal_domain` or `branded_domain` (display only) for “You’re logging in to …” and emails; actual DNS remains external. |
| **Email templates – school branding** | — | — | — | templates/emails/* use hardcoded colors (e.g. #2c3e50, #3498db) | **Add:** Base email layout that receives SITE (logo URL, primary_color, site_name); use in report_ready and other system emails so all emails share school logo/colors. |
| **Login interface** | ✅ Page exists | — | — | auth/login.html uses hardcoded gradient (#7c3aed, #ec4899), no SITE | **Add:** Drive login hero from SITE: logo, primary_color, accent_color, background (or theme pack). Add optional `login_hero_heading`, `login_hero_subtext` (or use site_name/tagline). |

### 3.5 Role-Specific Personalization

| Component | Portal | Backend | Admin | Current State | Gap / Plan |
|-----------|--------|---------|-------|---------------|------------|
| **Instructor vs student view style** | ✅ Different dashboards per role | — | — | Different templates (teacher/dashboard, parent/dashboard, etc.) | **Optional:** “Default widgets per role” in Site Settings (JSON: role → widget IDs) so admin can set utility-heavy vs content-focused defaults without code. |
| **Dashboard “skin” or density** | ⚠️ | — | — | User theme_preference (light/dark); no “density” | **Optional:** Per-role dashboard_style (e.g. compact vs spacious) or rely on widget presets. |

---

## 4. Implementation Plan (Phases)

### Phase A – Quick Wins (no new models)

| # | Item | Deliverable |
|---|------|-------------|
| A1 | **Login interface** | Use SITE logo, primary_color, accent_color, background (or theme pack) in `auth/login.html`. Add optional `login_hero_heading`, `login_hero_subtext` (or use site_name/tagline). |
| A2 | **Header toggles** | Add booleans: `show_header_search`, `show_header_notifications`, `show_header_profile_menu` (and optionally `show_header_theme_toggle`). Use in portal_base and backend header partials. |
| A3 | **Favicon** | Add `favicon` (ImageField) to SiteSettings; output in base.html, portal_base.html, backend_base.html, admin base_site.html. |
| A4 | **Layout style** | Add `layout_style` (choices: boxed, fluid) to SiteSettings; apply wrapper class in portal_base and backend_base; add CSS for max-width when boxed. |
| A5 | **Default sidebar collapsed** | Add `default_sidebar_collapsed` (bool) to SiteSettings; when creating or defaulting DashboardUserPreference, set sidebar_collapsed from it. |

### Phase B – Email and Communication

| # | Item | Deliverable |
|---|------|-------------|
| B1 | **Email branding** | Create base email template (or include snippet) that receives SITE (logo URL, primary_color, site_name). Refactor report_ready_* and other system emails to extend/include it so header and footer use school branding. |
| B2 | **Branded domain (display)** | Optional field `portal_domain` or `branded_domain` on SiteSettings; show in login (“You’re logging in to …”) and in email footer; no DNS logic. |

### Phase C – Navigation and Sidebar

| # | Item | Deliverable |
|---|------|-------------|
| C1 | **Sidebar menu order** | Define fixed set of portal sidebar item IDs. Add optional JSON field (e.g. `portal_sidebar_order` or per-role) on SiteSettings; in portal_sidebar.html, render items in that order when set; otherwise keep current order. |
| C2 | **Collapsed sidebar icon** | Add optional `sidebar_icon` (ImageField) to SiteSettings or ThemePack; in sidebar, when collapsed, show this icon instead of or with logo. |

### Phase D – Optional Advanced

| # | Item | Deliverable |
|---|------|-------------|
| D1 | **Chart type per widget** | If a widget supports multiple chart types, add config (e.g. on DashboardWidget or in widget config JSON) so admin can choose Bar/Pie/Line per metric; use in dashboard JS. |
| D2 | **Secondary font** | Add `secondary_font` (CharField) and “use for headings” (bool) to SiteSettings; expose as CSS variable; use in base/portal CSS for headings. |
| D3 | **Base font size** | Add `base_font_size` (IntegerField or choice) to SiteSettings; expose as `--base-font-size` in root; use in rem-based typography. |
| D4 | **Default widgets per role** | Optional JSON on SiteSettings: role → list of widget IDs; use when initializing DashboardUserPreference or when resolving default visible_widgets for a role. |
| D5 | **Admin “use site primary”** | Optional boolean “Use site primary/accent for admin”; when True, override or blend admin_sidebar_active_border (and similar) from SiteSettings.primary_color. |

---

## 5. Where Each Surface Gets Its Config

- **Portal:** Site Settings → Branding, Theme & Experience (theme_pack, primary/accent, brand_font, use_dark_mode, theme_brightness), Footer, Portal Content. After Phase A–C: Login, Header toggles, Favicon, Layout style, Sidebar order, Default sidebar collapsed. User-level: DashboardUserPreference (theme_preference, sidebar_collapsed, visible_widgets).
- **Backend Console:** Site Settings → Theme & Experience → Backend console theme (Dark/Light). Same header/sidebar structure as portal; after Phase A: header toggles, favicon, layout_style.
- **Django Admin:** Site Settings → Theme & Experience → Admin Sidebar Theme (all admin_sidebar_* colors), Admin theme pack (logo/background). Optional (Phase D5): “Use site primary for admin.”

---

## 6. How This Ties with the Drag-and-Drop Dashboard System

The platform has a **custom drag-and-drop dashboard** that lets users (and admins) arrange widgets, choose tile variants, and persist layout per page (teacher, parent, backend, finance, analytics, etc.). The **theme/site control plan** and the **drag-and-drop dashboard** work together as follows.

### 6.1 What the Drag-and-Drop System Controls

- **DashboardWidget** (admin catalog): Defines which cards exist (id, name, page, required_role, allowed_roles, template_path, allowed_sizes, default_size, allowed_variants, default_variant). Admins enable/disable and configure widgets in **Site Settings → Dashboard Widgets** (or the DashboardWidget model).
- **DashboardLayout** (per user + page, or role default): Stores the **saved layout** for a page: `layout.items` (widget id, column, order, size, variant) and `layout.__settings__` (show_sidebar, tile_variant, sidebar_items, custom_links, widget_meta). Fetched/saved via **`/api/dashboard/layout/<page>/`** (GET/PUT). Used by `dashboard-layout.js` (Sortable.js) and `dashboard-customizer.js`.
- **DashboardUserPreference**: User-level preferences: `visible_widgets`, `theme_preference`, `sidebar_collapsed`, legacy `dashboard_layout`. **Theme preference** (light/dark/system) and **sidebar collapsed** are both theme-related and dashboard-related: the theme plan adds a **site-wide default** (e.g. `default_sidebar_collapsed`) that applies when a user has no preference yet; the user's own choice continues to override.
- **Default widget set per role**: `default_dashboard_widgets(role)` in SiteSettings (from `ROLE_WIDGET_DEFAULTS`) defines which widget IDs are available by default for a role. **Theme plan Phase D4** proposes an optional **Site Settings JSON** (e.g. default widgets per role) so admins can set "instructor vs student" default layouts without code.

So: **widget catalog and role-based visibility** = DashboardWidget + default_dashboard_widgets; **where widgets sit and how they look (size/variant)** = drag-and-drop → DashboardLayout; **user theme/sidebar prefs** = DashboardUserPreference, with optional site-wide defaults from the theme plan.

### 6.2 What the Theme Plan Adds Around the Dashboard

| Theme plan item | Relation to drag-and-drop dashboard |
|----------------|-------------------------------------|
| **Layout style (boxed vs fluid)** | Applies to the **page wrapper** (e.g. `#dashboard-layout`'s container). Drag-and-drop operates **inside** that wrapper; boxed/fluid only changes max-width and centering. No change to how layout is saved or loaded. |
| **Default sidebar collapsed** | Site-wide default for "sidebar collapsed" on first load. When creating or defaulting `DashboardUserPreference`, set `sidebar_collapsed` from SiteSettings. The **nav sidebar** (portal_sidebar) is separate from layout `__settings__.show_sidebar` (dashboard right-sidebar/widget area); theme plan affects the **main nav sidebar** only. |
| **Sidebar menu order** | Optional JSON for **portal nav sidebar** item order (e.g. Dashboard, Workflow, Messages). Does **not** reorder dashboard **widgets**; widget order is entirely from drag-and-drop and `DashboardLayout.layout.items`. |
| **Header toggles** (search, notifications, profile) | Show/hide elements in the **top bar** that wraps all dashboards. Same header for teacher/parent/backend; toggles affect every page that uses that header, including pages with drag-and-drop. |
| **Widget visibility by role** | Already implemented: `DashboardWidget` + `required_role`/`allowed_roles` + `default_dashboard_widgets(role)`. Theme plan only adds optional **default widgets per role** in Site Settings (JSON) so admins can set defaults without editing code. |
| **Chart type per widget** | Optional: store chart type (bar/pie/line) in **widget config** (e.g. `DashboardWidget` or `layout.__settings__.widget_meta[widget_id]`). Dashboard JS would read this when rendering chart widgets; layout API already persists `widget_meta`. |

### 6.3 Data Flow Summary

1. **Page load (e.g. backend dashboard):**  
   - **Theme:** Backend base template loads `backend_console_theme`, layout_style (boxed/fluid), favicon, header toggles from SiteSettings.  
   - **Dashboard:** View calls `load_dashboard_layout_settings(user, page)` → gets `DashboardLayout` (user-specific or role default) → passes `dashboard_settings` (e.g. widget_meta, tile_variant) and `dashboard_layout_url` to the template.  
   - **Widget list:** For "which widgets exist," backend uses `DashboardWidget` filtered by page + role; for "which widgets to show" on portal views that use it, `resolve_dashboard_widgets(role, preference)` uses default_dashboard_widgets + user preference.

2. **Drag-and-drop save:**  
   - User reorders or resizes widgets → JS sends `PUT /api/dashboard/layout/<page>/` with `layout.items` + `__settings__`.  
   - API validates against **allowed_widgets** (from DashboardWidget), saves to **DashboardLayout** (user, page). Theme/site settings do **not** override this; they only provide site-wide defaults (sidebar collapsed, default widgets per role if we add that).

3. **Consistency:**  
   - **Theme** = global look (colors, logo, header, footer, layout style, sidebar default state).  
   - **Drag-and-drop dashboard** = per-page, per-user (or per-role default) **content layout** and widget presentation (size, variant, order). Both can be managed from the backend; theme does not replace the dashboard system—it wraps and defaults it.

### 6.4 How It Works on Backend, Teacher, and Parent (Same Flow, Different Page)

The drag-and-drop dashboard uses the **same mechanism** on all three profiles; only the **page name** and **who can customize** differ.

| Step | Backend | Teacher | Parent |
|------|---------|---------|--------|
| **View** | `accounts.views.backend_dashboard` | `evals.views.teacher_dashboard` | `portal.views.parent_dashboard` |
| **Page name** | `"backend"` | `"teacher"` | `"parent"` |
| **Context** | `load_dashboard_layout_settings(user, "backend")`, `dashboard_layout_url` = `/api/dashboard/layout/backend/`, `allow_custom_layout` = `_can_customize(user)` | Same via `get_dashboard_context(user, "teacher")` → `"teacher"` | Same via `get_dashboard_context(user, "parent")` → `"parent"` |
| **Template** | `accounts/backend_dashboard.html` | `teacher/dashboard.html` | `parent/dashboard.html` |
| **Markup** | `<div id="dashboard-layout" data-save-url="..." data-load-url="...">` + "Drag & drop layout" toggle (`#toggleCustomize`) | Same | Same |
| **JS** | `dashboard-layout.js` runs; sets `body.dataset.dashboardPage` from URL or template; GET/PUT `/api/dashboard/layout/<page>/` | Same (page = teacher) | Same (page = parent) |
| **Who can customize** | Staff or role in `ALLOWED_CUSTOM_ROLES` (ADMIN, LEADERSHIP, IT_ADMIN, TEACHER, PARENT, SUPERADMIN). Backend dashboard is staff-only; so effectively staff. | Same: TEACHER is in `ALLOWED_CUSTOM_ROLES`, so teachers see the toggle and can drag/save. | Same: PARENT is in `ALLOWED_CUSTOM_ROLES`, so parents see the toggle and can drag/save. |

**Flow in one sentence:** The view passes `dashboard_layout_url` (e.g. `/api/dashboard/layout/parent/`) and `allow_custom_layout` to the template; the template renders `#dashboard-layout` and the "Drag & drop layout" toggle; `dashboard-layout.js` fetches the current layout from the API, enables Sortable when the toggle is on, and on drag-end PUTs the new layout to the same API; the API saves to `DashboardLayout` for that user + page.

**Backend (staff):** `backend_dashboard` in `apps/accounts/views.py` builds `dashboard_settings`, `dashboard_layout_url`, `allow_custom_layout` and renders `backend_dashboard.html`.  
**Teacher:** `teacher_dashboard` in `apps/evals/views.py` calls `get_dashboard_context(request.user, "teacher")` and merges that into the context; template is `teacher/dashboard.html`.  
**Parent:** `parent_dashboard` in `apps/portal/views.py` calls `get_dashboard_context(request.user, "parent")` and unpacks it as `**dashboard_context`; template is `parent/dashboard.html`.

So: **same backend API, same JS, same data model**; only the page identifier (`backend` / `teacher` / `parent`) and the view/template differ.

### 6.5 Is It Important? Do We Need It?

**What it does:** Lets users (backend staff, teachers, parents) **reorder and resize dashboard widgets** and persist that per user per page. Without it, everyone sees the **same fixed order** (the order in the HTML template).

**Is it important?**  
- **For power users and adoption:** Some staff/parents/teachers prefer to put "what I use most" at the top; reordering can reduce clutter and make the dashboard feel personal.  
- **For most schools:** A **fixed, sensible default order** is enough. Many users never touch the toggle.

**Do we need it?**  
- **You do not need it for the product to work.** The dashboard works fine with a fixed layout; drag-and-drop is a **nice-to-have**, not a requirement for core workflows (viewing grades, finance, assignments, etc.).  
- **You might want it** if: (1) you want to offer "customize your dashboard" as a selling point, or (2) power users (e.g. office staff, active parents) have asked for it.  
- **You can simplify** by:  
  - **Option A:** Keep it only for **backend** (staff) and hide the toggle for teacher/parent (e.g. remove TEACHER and PARENT from `ALLOWED_CUSTOM_ROLES`, or pass `allow_custom_layout=False` for portal pages).  
  - **Option B:** Keep it as-is for all three but don’t invest further (no new features).  
  - **Option C:** Remove it entirely: stop passing `dashboard_layout_url` and the toggle, and rely on fixed template order; you could later reintroduce a simpler "widget on/off" list without drag-and-drop.

**Recommendation:** Treat it as **optional**. If your school (or product) doesn’t care about per-user layout, disable it for teacher/parent (Option A) or use fixed layouts (Option C). If you want to keep the feature, the current design is consistent across backend, teacher, and parent—no change needed except possibly tightening who can customize.

**Implemented (Option A):** Drag-and-drop layout customization is **backend (staff) only**. TEACHER and PARENT were removed from `ALLOWED_CUSTOM_ROLES` in `apps/siteconfig/dashboard_views.py`; the layout API returns 403 on PUT/PATCH for users who do not pass `_can_customize(user)`. Teacher and parent dashboards receive `allow_custom_layout=False`; they see a fixed template order. See [MASTER_PLAN_THEME_AND_DASHBOARD.md](./MASTER_PLAN_THEME_AND_DASHBOARD.md) for the full picture.

See also: `docs/DRAG_AND_DROP_FIXES.md`, `docs/KB_WIDGET_CATALOG_LAYOUTS.md`, `static/js/dashboard-layout.js`, `static/js/dashboard-customizer.js`, `apps/api/dashboard_layout_api.py`, `apps/siteconfig/dashboard_views.py`.

---

## 7. Implementation Checklist (Summary)

- [x] **Login:** Drive from SITE (logo, primary/accent, background); optional login_hero text fields.
- [x] **Header:** show_header_search, show_header_notifications, show_header_profile_menu; use in portal_base and backend.
- [x] **Favicon:** Add to SiteSettings; use in all base templates.
- [x] **Layout:** layout_style (boxed/fluid); wrapper + CSS in portal and backend bases.
- [x] **Sidebar:** default_sidebar_collapsed; optional portal_sidebar_order (and per-role); optional sidebar_icon.
- [x] **Email:** Base email template with SITE logo/primary; use in all system emails.
- [x] **Branded domain:** Optional portal_domain/branded_domain for display.
- [x] **Optional:** Chart type per widget; secondary_font; base_font_size; default widgets per role; admin “use site primary”.

Once these are done, the backend has **control of** header, footer, typography, color palette, login, layout, sidebar, widgets, and email branding across **Portal**, **Backend Console**, and **Admin**, with a clear mapping from each theme component to Site Settings (and related models) and no reliance on hardcoded visuals for branding-critical areas.
