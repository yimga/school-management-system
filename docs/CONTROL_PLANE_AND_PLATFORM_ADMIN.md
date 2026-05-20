# Control plane (`/super/`) vs platform admin (`/admin/`)

**Validated against the codebase** (not a doc-only claim).

**Single execution ledger:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§2.1.1** (control plane world-class bar: operator policy, governance, bridge manifest API).

**In-product policy page:** `/super/operator-policy/` — `super:operator_policy` (super-first vs break-glass admin, change classes, metrics/API pointers).

**Automation:** `GET /api/internal/control-plane/bridge-manifest/` — JSON list of every `super:admin_bridge` entry (control-plane auth only; not tenant staff). Manifest also ships `surface_spine`, `paired_super_first`, and `surface_parity_ok` (batch **1252**).

**Operator surface strip (batch 1252–1253):** On manager host, `/super/`, `/configuration/`, and `/admin/` render a shared **Surfaces** pill row (`components/rmc_operator_surface_strip.html`) wired by `apps/schools/super_admin_paired_surfaces.py` + `operator_surface_ia_context`. High-traffic super-first lists and nested `/super/marketplace/*`, `/super/security/*`, `/super/trust/*` routes show **Open platform admin**; admin changelists with a super-first twin show **Open operator view**. Mechanical gates: `python scripts/verify_super_admin_surface_parity.py --write` → `docs/generated/super_admin_surface_matrix.json`; `python scripts/verify_manager_render_parity.py --write-matrix` (matrix + `/-/version/` JSON on manager/public urlconfs); Playwright `bash scripts/run_manager_surface_parity.sh` / `tests/e2e/manager-surface-parity.spec.js`. Hosted parity (batch 1199): set `RENDER_PARITY_BASE_URL` / `MANAGER_PARITY_BASE_URL` when running `verify_manager_render_parity.py`.

## Two surfaces by design

| Surface | URL (manager host) | Purpose | Access |
|---------|-------------------|---------|--------|
| **Control plane** | `/super/*` | Dashboards, catalogs, marketplace governance, billing overview, migration, trust, support, orchestration, **operator policy**, etc. | `user_has_control_plane_access`: `is_superuser` **or** `role == SUPERADMIN`. Enforced by `TenantSuperAdminRequiredMiddleware` + per-view `require_super_access_with_host`. |
| **Platform backoffice** | `/admin/*` | **Raw Django admin CRUD** for models registered with `register_platform_admin` (siteconfig AI/registry, billing waivers, packages, marketplace proxy models, registries, automation, etc.). Visual parity with control plane: SOT **§11.4 batch 1246** (`admin-cp-parity.css`, `cool-apple` aesthetic). | `PlatformAdminSite.has_permission`: manager host + `is_staff` + `is_superuser`. |

`config/admin.py` states explicitly: *"Platform Backoffice: raw CRUD only. Single config surface is Configuration Control Center (siteconfig:console_domains_hub)."*

**Changelist navigation is integrated:** `super:admin_bridge` + `apps/schools/super_admin_bridge_registry.py` maps **every** platform-registered changelist used for fleet config (siteconfig, integrations_marketplace, runtime_blueprints, global_registries, packages, etc.) to a stable `/super/admin-bridge/<slug>/` URL — operators need not hardcode `/admin/...` paths. **Editing** still uses Django admin for models without dedicated super CRUD forms; **first-class** super screens (catalogs, AI hub, Configuration Control Center) remain the default operator path where they exist.

## Security (logical)

- **Manager host** (`ManagerHostControlPlaneRequiredMiddleware`): unauthenticated `/admin/*` redirects to `/super/` sign-in flow; authenticated users must pass `user_has_control_plane_access` for most manager paths.
- **`/super/`** is **narrower** in intent (operator dashboards) but uses the **same** operator contract as other control-plane APIs (`is_superuser` or `SUPERADMIN`).
- **Platform `/admin/`** additionally requires **`is_staff`** and **`is_superuser`** — typical platform operators satisfy both.

Tenant **`/admin/`** (`TenantAdminSite`) is a **different** site: tenant models only, **not** on manager host.

## Admin sidebar vs `/super/` sidebar

**`templates/admin/app_list.html`** (manager) includes:

- Dashboard, **Control plane**, Configuration Control Center, Theme & Experience, Feature Control, Integrations (advanced), Report Library, Blueprint Marketplace, Operator Help, plus **Apps** (all platform-admin models).

**`apps/schools/control_plane_nav.py`** builds **`CONTROL_PLANE_NAV`** for `/super/`. It previously **did not** list Theme, Feature Control, Platform backoffice, Integrations admin, or Report Library — only “Configuration Control Center” under Platform settings.

**Change:** the **Platform settings & admin** group now mirrors those **quick-link** destinations so operators on `/super/` see the same entry points as the admin sidebar (CRUD still happens in `/admin/` where no super view exists).

## Remaining product choices

- **Per-model CRUD forms** are still Django admin for most models; **bridges** provide `/super/` entry points to the same changelists. Building duplicate CRUD in `/super/` for every model is optional and product-gated.
- **Some `/super/` URLs** exist only in `super_urls.py` (e.g. group campuses, advancement) and may not appear in the sidebar; they are linked from dashboards or bookmarks.

## Single source for `/super/` nav

- **`apps/schools/control_plane_nav.py`** — `build_control_plane_nav()`.
- When adding a **primary** operator surface, add it there; when adding **only** a model admin, use `register_platform_admin` and optionally link `/admin/` from docs or sidebar.

---

## Platform `/admin/` audit (2026-05-20)

**Scope:** manager-host `PlatformAdminSite` (`/admin/`), all sub-pages (index, app index, changelist, change form, history, delete), sidebar IA, bridges, and operator workflows vs `/super/`.

### Surface map

| Layer | Implementation | Notes |
|-------|----------------|-------|
| **Shell** | `templates/admin/base.html` + `admin-cp-parity.css` | Control-plane chrome: sidebar, topbar, scroll host `#cp-main-content`, breadcrumb separators (no literal `/` list items). |
| **Index** | `admin/index_superadmin.html` | Section-grouped **model catalog** + metrics + shortcuts; search via `admin-platform-catalog.js`. |
| **Sidebar** | `manager_platform_admin_sidebar.html` + `app_list.html` | Quick links + filterable app/model tree (`data-admin-search`). |
| **Changelist** | `admin/change_list.html` + `admin_changelist_header.html` | In-page title, record count, Add pill on manager host; filters scroll inside rail. |
| **Change form** | `admin/change_form.html` + `admin_change_form_header.html` | History / Add another in-page on manager host. |
| **Bridges** | `super:admin_bridge` + `PLATFORM_ADMIN_BRIDGES` | Slug → admin changelist; catalog adds **Open super view** when a bridge exists. |
| **IA sections** | `PlatformAdminSite.PLATFORM_APP_SECTIONS` (9) | Platform Configuration → … → Advanced System Objects. |
| **Registration** | `register_platform_admin` across ~21 apps | ~171 models on platform site (tenant site is separate). |

### Findings (pre–gear-up)

| Issue | Severity | Status |
|-------|----------|--------|
| Changelist vertical stretch / content at bottom | P0 | **Fixed** — `admin-cp-parity.css` flex + scroll host. |
| Breadcrumb literal `/` items | P0 | **Fixed** — CSS separators + proper labels. |
| Add action missing on manager changelists | P0 | **Fixed** — `change_list_object_tools.html`. |
| No search across ~171 models | P0 | **Fixed** — `build_platform_admin_catalog` + index/sidebar search. |
| Duplicate steering (path banner + outcome deck + siteconfig hints) | P1 | **DONE** — `admin_operator_steering_strip.html` (dismissible, sessionStorage). |
| `admin/dashboard/` redirects to index; rich `admin_dashboard.html` unused | P2 | **Partial** — index KPIs wired; dedicated dashboard template still optional. |
| Dual marketplace app labels in sidebar | P2 | Open — consolidate IA copy. |
| App index pages still flat Unfold default | P2 | **DONE** — `app_index.html` + `enrich_app_index_models()`. |

### Gear-up roadmap (aggressive)

| Tier | Deliverable | Proof |
|------|-------------|-------|
| **P0** | Model catalog + sidebar filter | `platform_admin_catalog.py`, `index_superadmin.html`, `admin-platform-catalog.js`; `test_platform_admin_catalog.py`. |
| **P0** | Scroll reachability on all admin page types | `admin-cp-parity.css`; `test_manager_portal_chrome_contract.py`. |
| **P1** | Single operator steering strip | `admin_steering.py`, `admin_operator_steering_strip.html`; `verify_admin_steering_strip_contract.py`. |
| **P1** | Changelist **Open operator view** on bridged models | `super_admin_paired_surfaces.py` (`on_manager_admin`); `admin_changelist_header.html`. |
| **P2** | Index KPIs from `build_admin_dashboard_context` | `build_admin_index_kpi_strip()`; `admin_index_kpis` on index. |
| **P2** | App index (`admin/app_index.html`) | `PlatformAdminSite.app_index()` + `enrich_app_index_models()`. |
| **P3** | Admin changelist render smoke + Playwright | `verify_admin_changelist_render_contract.py`; `SWEEP_TIER=operator+admin npm run sweep:abrupt-end`. |

### Key files

- `config/admin.py` — `PlatformAdminSite.index()` injects `admin_catalog`.
- `apps/siteconfig/platform_admin_catalog.py` — catalog builder.
- `static/css/admin-platform-catalog.css`, `static/js/admin-platform-catalog.js`.
- `templates/admin/index_superadmin.html`, `templates/partials/manager_platform_admin_sidebar.html`.

---

## Post-deploy operator checklist (batch 1361)

After shipping manager UX / weather / feedback hardening to **Render** (or any Postgres host):

1. **Migrations (required)** — Pre-deploy must run `scripts/release/render_predeploy.sh` (not plain `migrate` when `USE_DJANGO_TENANTS=1`). Ensures `feedback` tables exist and `siteconfig` **0180** / **0181** apply.
2. **Feedback** — If `/contact-us/` or `/super/voice-of-customer/` still show the “tables missing” banner, re-run migrate for `feedback`; defensive `db_readiness` is not a substitute.
3. **Weather catalog** — One-time (idempotent):
   ```bash
   python manage.py seed_global_weather_locations
   ```
   Or full platform bootstrap (includes weather via `--with-weather-locations`):
   ```bash
   RUN_BOOTSTRAP_PLATFORM_CATALOG=1 ./scripts/release/render_predeploy.sh
   ```
   Optional predeploy-only flag: `RUN_SEED_GLOBAL_WEATHER_LOCATIONS=1` (see `scripts/release/render_predeploy.sh`).
4. **Client cache** — Hard refresh after deploy; service worker bumps to `sms-v3.51.1-operator-ux-closeout-1361-*`.
5. **Staging E2E** — With Django up and hosts mapped:
   ```bash
   export MSYS_NO_PATHCONV=1
   export RENDER_PARITY_BASE_URL=https://<your-render-manager-host>
   bash scripts/run_manager_surface_parity.sh
   ```
   Playwright against **live Render** is Lane 2 evidence, not repo-gate blocking.

**Out of scope (v3.34):** FACTS / Skyward companion **write** paths remain `// honest-stub:` until counsel sign-off — see [`FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`](FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md).
