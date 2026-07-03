# RunMyCampus Nav Sidebar Filter Header Audit

- Scope: shared desktop nav sidebar toolbar used by operator, manager-admin, zero-ticket, and tenant shells
- Gap count: 0
- Toolbar include templates: 4

## Authenticated Shell Coverage
- `portal_base.html`: 331 templates extend this shell
- `control_plane_base.html`: 233 templates extend this shell
- `admin/base.html`: 1 templates extend this shell

## Shell Mounts
- PASS: `control_plane` via `templates/control_plane_base.html`
- PASS: `portal` via `templates/portal_base.html`
- PASS: `manager_admin` via `templates/admin/base.html`
- PASS: `zero_ticket` via `templates/siteconfig/zero_ticket_shell.html`

## Nav Partials
- PASS: `operator` via `templates/partials/control_plane_sidebar.html`
- PASS: `tenant` via `templates/partials/portal_sidebar.html`
- PASS: `manager_admin` via `templates/partials/manager_platform_admin_sidebar.html`
