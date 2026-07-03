# RunMyCampus Nav Sidebar Filter Header Gap Analysis

- Code-owned gaps found: 0
- Shared toolbar source: `templates/partials/rmc_nav_sidebar_toolbar.html`
- Shared CSS source: `static/css/rmc-nav-sidebar.css`
- Shared JS source: `static/js/rmc-nav-sidebar.js`

## Result
No code-owned gaps were found for desktop sidebar surfaces that use the shared nav-sidebar toolbar.

## Coverage
- Operator control-plane pages inherit the toolbar through `control_plane_base.html`.
- Tenant pages inherit the toolbar through `portal_base.html`.
- Manager `/admin/` pages inherit the toolbar through `templates/admin/base.html` when on the manager host.
- Zero-ticket diagnostic pages inherit the toolbar through `templates/siteconfig/zero_ticket_shell.html`.
- Mobile offcanvas menus are outside this request because they do not have the collapse-icon/Navigation header slot.

## Measurements
- `portal_base.html` extending templates: 331
- `control_plane_base.html` extending templates: 233
- `admin/base.html` extending templates: 1
- Toolbar include templates: 4
