# Theme & Site Control Plan

This document maps the current site configuration to a full "website theme" model, clarifies how **Backend Console** vs **Django Admin** themes relate, and provides a phased plan so admins have control of everything on the site.

---

## 1. Current Config vs Essential Theme Components

| Component | What Exists Today | Where It's Used | Admin-Configurable? |
|-----------|-------------------|-----------------|---------------------|
| **Header & navigation** | Top bar (`.topbar`) with logo, search, weather, user dropdown | Portal (parent/teacher/backend) via `portal_base.html` | **Partial**: Logo, primary/accent from Site Settings; no toggle for search/notifications per area. |
| **Footer** | Footer fields in SiteSettings | Portal footer (when included) | **Yes**: `footer_accreditation_text`, `footer_accreditation_subtext`, `footer_support_hours`, `footer_whatsapp_url`, `footer_status_text`, `footer_badges`, `footer_links`. |
| **Typography** | `brand_font` (SiteSettings), ThemePack `font_family` | Portal via `portal_base` / design-system; reports use report style | **Yes**: Site Settings + Theme Pack. |
| **Color palette** | `primary_color`, `accent_color`, `success_color`, `warning_color`, `danger_color` (SiteSettings + ThemePack) | Portal, Backend dashboard inline vars; reports use ReportCardStyle | **Yes**: Site Settings + Theme Packs. |
| **Page layout** | Fluid layout; sidebar show/hide per dashboard; ThemePack `layout` (STANDARD, etc.) | Portal + Backend | **Partial**: Dashboard layout (customizer) per user; no global "boxed vs fluid" for portal. |
| **Hero / above-the-fold** | Login and portal can use `background_image`, `video_background`, `svg_background` | Portal; logo opacity/mode | **Yes**: Site Settings + Theme Pack (logo, bg image, video, svg). |
| **Buttons & CTAs** | Styled via design-system and theme colors | Everywhere | **Indirect**: Colors from palette; no dedicated "CTA style" config. |
| **Responsive design** | CSS breakpoints and mobile styles | All templates | **No**: Hardcoded in CSS. |
| **Sidebar & widgets** | Portal sidebar (single template); Backend Console sidebar (same template, different sections); Django Admin sidebar (separate) | Portal: `portal_sidebar.html`; Admin: Unfold/sidebar enhanced | **Partial**: See "Three theme surfaces" below. |
| **Forms & interactive** | Bootstrap + custom CSS | All | **Indirect**: Theme colors; no form-specific theme tokens. |

---

## 2. How Backend Console, Portal, and Django Admin Themes Tie Together

There are **three distinct theme surfaces**:

| Surface | URL / Scope | What Drives It | Admin Control Today |
|---------|-------------|----------------|---------------------|
| **Portal** (parent/teacher dashboards, login) | `/portal/`, `/authentication/login/`, etc. | `portal_base.html`; `SITE_THEME` (= SiteSettings theme_pack or default ThemePack); `SITE` (SiteSettings). Colors: `primary_color`, `accent_color`, `brand_font`, `use_dark_mode`, `theme_brightness`. Logo/background from SiteSettings or ThemePack. | **Site Settings**: Theme pack, primary/accent/success/warning/danger, font, dark mode, theme brightness. **Theme Packs**: Optional pack with logo, bg image, video, custom CSS. |
| **Backend Console** (staff workflow, entity console) | `/authentication/backend/`, Workflow Center, etc. | `backend_base.html`; loads either `backend-dark-theme.css` or `backend-light-theme.css`. | **Site Settings**: **Backend console theme** = Dark (grey) or Light. **No** per-color config for Backend Console; colors are fixed in CSS. |
| **Django Admin** (`/admin/`) | Django Admin only | `admin/base_site.html`; CSS variables from **SiteSettings admin_sidebar_*** (e.g. `admin_sidebar_bg_color`, `admin_sidebar_text_color`, …). Optional **Admin theme pack** (`admin_theme_pack`) for logo/background. | **Site Settings**: **Admin Sidebar Theme** section: 14 color fields (sidebar bg, surface, border, text, muted, hover, active, badge, child gradient/border/hover/active). **Admin theme pack** for admin-specific logo/background. |

**Summary**

- **Portal**: One coherent theme from Site Settings + Theme Pack (colors, font, logo, footer, brightness).
- **Backend Console**: Single setting **Backend console theme** (Dark/Light); not wired to the same color palette as Portal or Admin.
- **Django Admin**: Its own **Admin Sidebar Theme** color set + optional Admin theme pack; separate from Portal and Backend Console.

So: **Backend Console** and **Django Admin** are intentionally separate from the main portal theme. Admin can configure Portal theme in detail, Admin sidebar in detail, and Backend Console only as Dark vs Light.

---

## 3. Admin-Manageable Theme Components (Your List) vs Current State

### 3.1 Core Visual Identity (Branding)

| Component | Current State | Gap / Plan |
|-----------|----------------|-----------|
| **Logos** (header, collapsed sidebar icon, favicon) | Header logo: SiteSettings `logo` or ThemePack `logo`; used in portal. Admin: `SITE_ADMIN_LOGO_URL` from admin theme. | **Gap**: No dedicated "collapsed sidebar icon"; no **favicon** field in SiteSettings (favicon is static). **Plan**: Add `favicon` (ImageField) and optional `sidebar_icon`; use in base templates. |
| **Color palette** | Primary, accent, success, warning, danger in SiteSettings + ThemePack. | **Good**. Optional: expose semantic labels (e.g. "Pass color") in UI. |
| **Typography** | `brand_font` (SiteSettings), ThemePack `font_family`. | **Good**. Optional: secondary font, base font size in settings. |

### 3.2 Layout and Navigation

| Component | Current State | Gap / Plan |
|-----------|----------------|-----------|
| **Sidebar** (dark/light, expanded/collapsed, menu order) | Portal: one sidebar; dark/light from `use_dark_mode` / `theme_brightness`. Backend: Dark/Light from `backend_console_theme`. Admin: 14 admin_sidebar_* colors. | **Gap**: No global "sidebar default state" (expanded/collapsed); no admin UI to reorder portal menu items. **Plan**: Add `sidebar_default_collapsed` (bool); add optional JSON `portal_sidebar_order` or use existing dashboard/sidebar config if it exists. |
| **Header** (search, notifications, profile) | Header is same for portal/backend; search and controls present in template. | **Gap**: No toggles to show/hide search bar or notification bell per role/surface. **Plan**: Add `header_show_search`, `header_show_notifications` (or JSON) and respect in `portal_base.html`. |
| **Layout style** (boxed vs fluid) | Layout is fluid. ThemePack has `layout` (STANDARD, etc.) but not clearly wired to boxed/fluid. | **Gap**: No explicit "boxed" vs "full-width" for portal. **Plan**: Add `layout_style` (boxed | fluid) and a wrapper class in base template. |

### 3.3 Modular Dashboard Widgets

| Component | Current State | Gap / Plan |
|-----------|----------------|-----------|
| **Widget visibility** | `default_dashboard_widgets(role)`, `DashboardUserPreference`, `resolve_dashboard_widgets`; backend dashboard has widget toggles. | **Good**: Admins can control defaults; users can customize. |
| **Data visualization** (chart types) | Chart types are usually fixed per widget in code. | **Gap**: No admin setting for "use Bar vs Pie vs Line" per widget. **Plan**: Optional JSON on SiteSettings or per-widget config (e.g. `dashboard_widget_chart_types`) for key widgets. |

### 3.4 Communication & Portal Customization

| Component | Current State | Gap / Plan |
|-----------|----------------|-----------|
| **Custom domains** | Not in app; typically reverse proxy / hosting. | **Out of scope** for theme; document in deployment guide. |
| **Email templates** | Not audited here. | **Plan**: If missing, add backend editor or placeholders for system emails (password reset, receipts) with school logo/colors. |
| **Login interface** | Login uses portal base; can use `background_image`, logo. | **Gap**: No login-specific "welcome message" or announcement in SiteSettings. **Plan**: Add `login_welcome_html` or `login_announcement` and render on login template. |

### 3.5 Role-Specific Personalization

| Component | Current State | Gap / Plan |
|-----------|----------------|-----------|
| **Instructor vs student views** | Different dashboards (teacher vs parent/student); different sidebar sections by role. | **Good**: Role-based dashboards and sidebar. Optional: explicit "dashboard mode" (utility vs content) per role in settings. |

---

## 4. Phased Plan for "Control of Everything"

### Phase 1 – Quick wins (no new models)

1. **Favicon**  
   - Add `SiteSettings.favicon` (ImageField, optional).  
   - Use in `portal_base.html` and `backend_base.html` (and admin base if desired) as `<link rel="icon">`.

2. **Backend Console tied to design tokens (optional)**  
   - Either: add a few Backend Console color fields (e.g. `backend_sidebar_bg`, `backend_surface`) and use them in `backend-dark-theme.css`,  
   - Or: document that Backend Console theme is "Dark vs Light" only and keep single setting.

3. **Login welcome / announcement**  
   - Add `SiteSettings.login_welcome_text` or `login_announcement` (CharField/TextField or HTML).  
   - Render on authentication login template.

4. **Header toggles**  
   - Add `header_show_search` and `header_show_notifications` (BooleanField) to SiteSettings.  
   - In `portal_base.html`, show/hide search and notification bell based on these.

### Phase 2 – Layout and navigation

5. **Sidebar default state**  
   - Add `sidebar_default_collapsed` (BooleanField, default False).  
   - Pass to frontend and set initial sidebar state (e.g. in `dashboard-layout.js` or sidebar component).

6. **Layout style**  
   - Add `layout_style` with choices (e.g. `fluid`, `boxed`) to SiteSettings (or ThemePack).  
   - In base template, add wrapper class (e.g. `layout-boxed` / `layout-fluid`) and CSS for max-width when boxed.

7. **Portal menu order**  
   - If not already present: add optional `portal_sidebar_order` (JSON list of section IDs or menu keys) and sort sidebar sections in `portal_sidebar.html` by this order.

### Phase 3 – Polish and optional

8. **Email templates**  
   - Audit existing email sending; add placeholders for logo, primary_color, school name in HTML emails; optional simple backend editor for one or two key emails.

9. **Dashboard chart types**  
   - Optional JSON config (e.g. `dashboard_widget_chart_types`) mapping widget id to chart type; use in dashboard JS when rendering charts.

10. **Documentation**  
   - One "Theme & site control" doc for admins: what each section in Site Settings does, and how Portal vs Backend Console vs Django Admin themes relate (this document as basis).

---

## 5. Where Things Live in Admin

- **Site Settings** (single record):  
  Branding (site name, tagline, logo, favicon), **Theme** (primary/accent, font, use_dark_mode, **backend_console_theme**, theme_brightness, theme_pack), **Footer** (all footer_*), **Portal** (portal_features, quick_actions, announcements, etc.), **Admin Sidebar Theme** (14 colors), **Admin theme pack**, **Admin Portal** (admin_portal_stats_config), **Layout/header** (once added: header toggles, sidebar default, layout_style), **Login** (login welcome/announcement).

- **Theme Packs** (optional):  
  For portal (and optionally admin): primary/accent, font, logo, background image/video/svg, custom CSS, layout. Used when Site Settings points to a pack.

- **Django Admin** appearance:  
  Driven only by **Admin Sidebar Theme** colors and **Admin theme pack** (logo/background). Not mixed with Backend Console or Portal theme.

---

## 6. Summary Table: Current vs After Plan

| Area | Now | After plan |
|------|-----|------------|
| **Portal** | Colors, font, logo, footer, theme pack, dark/brightness | + Favicon, login message, header toggles, sidebar default state, layout style, optional menu order. |
| **Backend Console** | Dark vs Light only | Unchanged, or + optional color tokens. |
| **Django Admin** | 14 sidebar colors + admin theme pack | Unchanged. |
| **Email / login** | Logo/colors where used | + Login welcome text; email placeholders (and optional editor). |
| **Dashboard widgets** | Visibility and user customizer | + Optional chart-type config. |

This gives a single place (Site Settings + Theme Packs) for admins to control branding, layout, header, footer, login, and the three theme surfaces (Portal, Backend Console, Admin) in a clear, consistent way.
