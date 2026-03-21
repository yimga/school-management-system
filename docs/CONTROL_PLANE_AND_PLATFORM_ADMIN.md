# Control plane (`/super/`) vs platform admin (`/admin/`)

**Validated against the codebase** (not a doc-only claim).

## Two surfaces by design

| Surface | URL (manager host) | Purpose | Access |
|---------|-------------------|---------|--------|
| **Control plane** | `/super/*` | Dashboards, catalogs, marketplace governance, billing overview, migration, trust, support, orchestration, etc. | `user_has_control_plane_access`: `is_superuser` **or** `role == SUPERADMIN`. Enforced by `TenantSuperAdminRequiredMiddleware` + per-view `require_super_access_with_host`. |
| **Platform backoffice** | `/admin/*` | **Raw Django admin CRUD** for models registered with `register_platform_admin` (siteconfig AI/registry, billing waivers, packages, marketplace proxy models, registries, automation, etc.). | `PlatformAdminSite.has_permission`: manager host + `is_staff` + `is_superuser`. |

`config/admin.py` states explicitly: *"Platform Backoffice: raw CRUD only. Single config surface is System config (siteconfig:console_domains_hub)."*

**Nothing was “moved entirely” from `/admin/` into `/super/`.** Many platform models have **no** first-class `/super/` screen; they remain **only** in `/admin/`. `/super/` adds **orchestration and catalog** views, not a duplicate of every changelist.

## Security (logical)

- **Manager host** (`ManagerHostControlPlaneRequiredMiddleware`): unauthenticated `/admin/*` redirects to `/super/` sign-in flow; authenticated users must pass `user_has_control_plane_access` for most manager paths.
- **`/super/`** is **narrower** in intent (operator dashboards) but uses the **same** operator contract as other control-plane APIs (`is_superuser` or `SUPERADMIN`).
- **Platform `/admin/`** additionally requires **`is_staff`** and **`is_superuser`** — typical platform operators satisfy both.

Tenant **`/admin/`** (`TenantAdminSite`) is a **different** site: tenant models only, **not** on manager host.

## Admin sidebar vs `/super/` sidebar

**`templates/admin/app_list.html`** (manager) includes:

- Dashboard, **Control plane**, System config, Theme & Experience, Feature Control, Integrations (advanced), Report Library, Blueprint Marketplace, Operator Help, plus **Apps** (all platform-admin models).

**`apps/schools/control_plane_nav.py`** builds **`CONTROL_PLANE_NAV`** for `/super/`. It previously **did not** list Theme, Feature Control, Platform backoffice, Integrations admin, or Report Library — only “System config” under Platform settings.

**Change:** the **Platform settings & admin** group now mirrors those **quick-link** destinations so operators on `/super/` see the same entry points as the admin sidebar (CRUD still happens in `/admin/` where no super view exists).

## Gaps that remain (by product choice)

- **Per-model CRUD** under **Apps** in admin is **not** reproduced as individual `/super/` routes (dozens of models). Use **Platform backoffice (model CRUD)** in the control-plane sidebar → `/admin/`.
- **Some `/super/` URLs** exist only in `super_urls.py` (e.g. group campuses, advancement, AI hub) and may not appear in the sidebar; they are linked from dashboards or bookmarks.

## Single source for `/super/` nav

- **`apps/schools/control_plane_nav.py`** — `build_control_plane_nav()`.
- When adding a **primary** operator surface, add it there; when adding **only** a model admin, use `register_platform_admin` and optionally link `/admin/` from docs or sidebar.
