# Admin UI: Sidebar, Header, and RBAC

This document describes the admin dashboard sidebar, header, design tokens, and how RBAC (role-based access control) drives what users see. See **THEME_SYSTEM.md** for theme (light/dark) behavior.

## 1. RBAC: What is permission-filtered

**Everything in `/admin` is RBAC-compliant.** Users only see and use features they have permission to access.

| Area | How it’s filtered |
|------|-------------------|
| **Sidebar app list** | Django’s `get_app_list(request)` (and thus `_build_app_dict`) returns only apps/models the user has at least one of view/change/add/delete for. `config/admin.py`’s `get_app_list()` additionally removes app groups that have zero models after this filtering. |
| **Children (model links)** | Only models the user can view/change/add/delete appear; the sidebar is built from the same permission-filtered app list. |
| **Model count badges** | `get_all_model_counts` (in `apps/observability/templatetags/admin_extras.py`) is request-aware and only includes models for which `model_admin.has_view_permission(request)` is true. Cached per user (`admin_all_model_counts_{user.pk}`). |
| **Dashboard index (KPIs/widgets)** | The admin index view in `config/admin.py` only adds user/session, security/compliance, and finance-related KPIs to the context when the current user has the corresponding permissions (or is superuser). |
| **Header** | Theme toggle and logout are safe for any admin user; any future “quick links” or widgets in the header must be permission-checked. |

**Empty sidebar:** If after RBAC filtering there are no apps (e.g. staff with no model permissions), the sidebar shows a message: “No modules available. Contact an administrator for access.” (see `templates/admin/base_site.html`).

**Custom sidebar nav:** If Unfold’s custom `sidebar_navigation` (from settings) is ever used, it must be built from permission-checked data (e.g. same logic as `get_app_list(request)`) so RBAC is preserved.

## 2. Sidebar structure and CSS

- **Container:** `#nav-sidebar` (and Unfold’s inner nav). Fixed width (e.g. 280px), scrollable content, sticky footer for user block.
- **App list source:** The sidebar never uses a hardcoded app list; it always uses the list returned by the admin site for the current `request` (e.g. via `available_apps` / `app_list`).
- **Template override:** `templates/admin/app_list.html` adds classes for clearer CSS targeting:
  - **`.admin-app-group`** – each app section (wrapper div). Can have class `.current-app` when the current URL is under that app.
  - **`.admin-app-group__header`** – row containing the section title and collapse toggle.
  - **`.admin-app-group__title`** – section heading (app name). Styled with `--admin-sidebar-heading` for higher contrast than body text.
  - **`.admin-app-group__toggle`** – button to collapse/expand the model list. When collapsed, the group has class `.admin-app-group--collapsed`.
  - **`.admin-app-models`** – the list of model links (children) under each app. Has a subtle background and border (`--admin-sidebar-child-bg`, `--admin-sidebar-child-border`) so children are visually grouped; model links use pill-style padding and left-border active state.
- **Collapsible:** Each app group can be collapsed or expanded via the toggle. The current app (`.current-app`) starts expanded; state is persisted in `localStorage` per app. See `templates/admin/base_site.html` (collapsible script).
- **CSS:** All admin sidebar and children rules are scoped under **`#nav-sidebar`** in `static/css/admin_sidebar_enhanced.css` so Portal/Backend sidebars (`.sidebar` without `#nav-sidebar`) are unaffected.
- **Tokens:** Sidebar uses `--admin-sidebar-*` variables (see §4). Section titles use `--admin-sidebar-heading`; child links use `--admin-sidebar-text-muted` (default) and `--admin-sidebar-text` on hover/active; active item uses `--admin-sidebar-active-border` for the left border.

## 3. Header

- **Visual alignment:** The admin header (Unfold’s header in `#main`) uses the same design tokens as the sidebar where appropriate (`--admin-sidebar-surface`, `--admin-sidebar-border`, `--admin-sidebar-text`) so the header feels part of the same admin shell. See `static/css/admin_theme.css`.
- **Theme:** Header respects the same theme attributes (`data-theme`, `data-bs-theme`, `.dark`) as the sidebar.
- **Content:** Left: logo/site name. Right: theme toggle, user menu / logout. Any future quick links must be permission-checked.
- **Breadcrumbs:** If present, styled with the same muted color/size as sidebar section headers.

## 4. Design tokens (admin)

Variables are defined in `templates/admin/base_site.html` (overridden by SiteSettings when set) and have fallbacks in `static/css/design-tokens.css` and `static/css/admin_sidebar_enhanced.css`. Use these only in admin-scoped CSS (e.g. under `#nav-sidebar` or for the admin header).

| Variable | Purpose |
|----------|---------|
| `--admin-sidebar-bg` | Sidebar background |
| `--admin-sidebar-surface` | Surface/panel background (header, cards) |
| `--admin-sidebar-border` | Borders |
| `--admin-sidebar-text` | Primary text (body links, active child links) |
| `--admin-sidebar-text-muted` | Child link default text; secondary text |
| `--admin-sidebar-heading` | Section titles (app group name); higher contrast than muted |
| `--admin-sidebar-hover-bg` | Hover background |
| `--admin-sidebar-active-bg` | Active item background |
| `--admin-sidebar-active-border` | Active item left border (accent) |
| `--admin-sidebar-badge-bg` / `--admin-sidebar-badge-text` | Count badges |
| `--admin-sidebar-child-bg` | Child block background (subtle grouping) |
| `--admin-sidebar-child-border` | Child block border |
| `--admin-sidebar-child-hover` / `--admin-sidebar-child-active` | Child link hover/active tints |
| `--admin-sidebar-child-text` / `--admin-sidebar-child-text-muted` | Child link text (optional in SiteSettings; leave blank for auto contrast) |

**SiteSettings fields** (admin base_site injects these into `:root` when set): `admin_sidebar_bg_color`, `admin_sidebar_surface_color`, `admin_sidebar_border_color`, `admin_sidebar_text_color`, `admin_sidebar_text_muted_color`, `admin_sidebar_hover_color`, `admin_sidebar_active_color`, `admin_sidebar_active_border_color`, `admin_sidebar_badge_bg_color`, `admin_sidebar_badge_text_color`, `admin_sidebar_child_bg_start`, `admin_sidebar_child_bg_end`, `admin_sidebar_child_border_color`, `admin_sidebar_child_hover_color`, `admin_sidebar_child_active_color`, optional `admin_sidebar_child_text_color` and `admin_sidebar_child_text_muted_color` (leave blank for auto contrast), and `admin_use_site_primary` (use site primary for active border). Tune these in Site configuration to customize sidebar and children without editing CSS.

**Configurable from admin vs not**

- **Configurable from admin:** All of the above sidebar and child-block color fields (including optional child link text colors), plus **Admin theme pack** (logo, background image). Edit at **Admin → Site config → Site settings → Admin Sidebar Theme** (collapsible fieldset). Use **Apply theme preset** (Lively Slate, Dark minimal, Light card) to fill all Admin Sidebar Theme colors at once, then Save. The change form includes a theme preview (small-screen sidebar/card) that updates as you change colors.
- **Not configurable from admin (hardcoded in CSS/templates):** Layout details (sidebar width, child block border radius, left accent bar, spacing, collapsible behavior) live in CSS/templates only. Child link text colors are auto-derived per light/dark theme when the optional SiteSettings fields are left blank.

**Complete revamp from admin**

- **Visual/theme revamp (colors, child gradient, hover/active, badges, logo, background):** Yes. You can change every sidebar and child color plus theme pack from Site Settings → Admin Sidebar Theme, so a full look revamp is possible without code.
- **Structural/layout revamp (sidebar position, menu structure, dashboard layout):** No. Changing where the sidebar sits, how the menu is built, or the dashboard layout requires code and template changes (e.g. `base_site.html`, `app_list.html`, `admin_sidebar_enhanced.css`, Unfold). That cannot be done from the admin panel alone.

Reuse these for the header where it makes sense; add `--admin-header-*` only if needed. Document any new variables here.

## 5. Key files

| Purpose | File(s) |
|--------|--------|
| App list (filter empty apps), index (permission-gate KPIs) | `config/admin.py` |
| Permission-filtered model counts | `apps/observability/templatetags/admin_extras.py` |
| Sidebar markup (app groups, children) | `templates/admin/app_list.html` |
| Badge script, empty sidebar message, accordion, collapsible app groups | `templates/admin/base_site.html` |
| Sidebar + children CSS (scoped to `#nav-sidebar`) | `static/css/admin_sidebar_enhanced.css` |
| Header alignment with sidebar tokens | `static/css/admin_theme.css` |
| Dashboard KPIs template | `templates/admin/admin_dashboard.html` |

## 6. Validation checklist

After changes, confirm:

1. **Admin** – `/admin/` and a model list (e.g. `/admin/accounts/accessrole/`): sidebar app groups, child links, header, theme toggle, dark/light. Log in as a **staff user with limited permissions** (e.g. only `accounts.view_user`, `accounts.change_user`) and confirm the sidebar shows only permitted apps/models and no sensitive KPIs/widgets.
2. **Backend** – Sidebar (portal style), header, widgets, theme unchanged.
3. **Portal parent/teacher** – No admin CSS regressions.
4. **One app dashboard** – Layout and sidebar correct.

**Token safety:** Keep new variables under `--admin-*` and use them only in admin-scoped CSS so other dashboards are unaffected.
