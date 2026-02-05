# Admin Sidebar Restructure Plan

Plan to **completely restructure** the /admin sidebar. The **dashboard (main content)** stays as-is; this doc is only about the **left-hand navigation**.

---

## 1. How this ties in with the current plans

| Plan | What it covers | Relation to sidebar |
|------|----------------|--------------------|
| **ADMIN_DASHBOARD_CHANGE_PLAN.md** | Changing the **content** of the /admin page (KPIs, layout, quick actions, data). | Dashboard = main area you like. Sidebar = nav that wraps it; restructure sidebar separately. |
| **ADMIN_REVAMP_PLAN.md** | Full admin revamp (tokens, dashboard, list views, **Phase 4: Navigation/IA**, a11y, mobile). | Phase 4 is “navigation and IA” (current app highlight, breadcrumbs, back link, pin/collapse). **Sidebar restructure** is a bigger change: not just polish but **new structure** (grouping, order, layout). |
| **This doc** | **Sidebar only:** data source, grouping, order, template, CSS, JS. | Use this when you want the **sidebar** completely restructured; keep dashboard plan for **content** and revamp plan for **global** admin work. |

**Summary:** You keep the dashboard look. You change the **sidebar** (what’s in it, how it’s grouped and ordered, how it looks). This doc is the plan for that. It fits **before or alongside** Phase 4 of the revamp plan (do sidebar restructure first, then Phase 4 polish like “current” highlight and breadcrumbs).

---

## 2. Current sidebar structure (what you have today)

| Layer | Where | What it does |
|-------|--------|----------------|
| **Data** | `config/admin.py` → `get_app_list(request)` | Builds app list from Django’s `_build_app_dict`; applies custom **order** and **names** (e.g. "👤 Accounts", "👥 People Management"); returns list of apps, each with `models` (permission-filtered). |
| **Template** | `templates/admin/app_list.html` | Renders one **admin-app-group** per app; each group has a header (app name) + **admin-app-models** (links to changelist). Uses `request.path` for `.current-app` / `.current-model`. |
| **Shell** | `templates/admin/base_site.html` | Wraps sidebar in `#nav-sidebar`; injects **search** (“Jump to model…”), **model count badges** (from `get_all_model_counts`), **collapsible** state (localStorage per app), **empty state** message. |
| **CSS** | `static/css/admin_sidebar_enhanced.css` | Width, colors (tokens), child block style, collapse toggle, badges. Tokens come from `base_site.html` (SITE). |
| **RBAC** | Same data + template | Only apps/models the user has permission to see; empty groups are removed in `get_app_list`. |

So today: **flat list of apps** (each with a custom name/icon and order), each app is a **collapsible group** of model links, with search and count badges on top.

---

## 3. What “completely restructure” can mean (options)

Pick the options that match what you want; then we implement in phases.

| Option | Description | Effort |
|--------|-------------|--------|
| **A. Top-level categories** | Group apps under headings (e.g. **People** → Accounts, People, Auth; **Academic** → Academics, Evals, Reports; **Finance** → Finance, Payroll; **System** → Portal, Analytics, Compliance, Siteconfig). Sidebar becomes **Category → App → Models** (3 levels). | Medium: new data structure + template. |
| **B. Reorder / rename only** | Keep one level (app → models) but change order and labels in `get_app_list`. No new template structure. | Low: config only. |
| **C. Different layout** | Same data, different look: e.g. sections with strong dividers, or icons-only collapse, or “mega” expandable section. | Low–medium: CSS + optional small template tweaks. |
| **D. Extra sidebar items** | Add fixed items: **Dashboard** (link to /admin/), **Site settings**, **Backend console**, **Logout**. Above or below the app list. | Low: template + maybe view/context. |
| **E. Search / filters** | Keep or improve “Jump to model”; optional filter by category or role. | Low–medium: JS + optional backend. |
| **F. Configurable order** | Let superusers (or SiteSettings) define sidebar order or which apps appear in which category. | Higher: model or config + migration. |

**Suggested starting point:** Decide between **(1) categories (A)** vs **(2) flat but reordered/renamed (B)**. Then add **D** (Dashboard + key links) and **C** (layout polish). **E** and **F** can follow.

---

## 4. Phased implementation (how to do it)

### Phase S1: Agree target structure (no code)

- [ ] Choose: **categories (A)** or **flat reorder (B)**.
- [ ] If categories: list categories and which apps go under each (e.g. People: accounts, people, auth; Academic: academics, evals, reports; …).
- [ ] Decide: **extra items (D)** at top (Dashboard, Settings, …) and/or bottom (Logout).
- [ ] Optional: wireframe or list of section titles and order.

**Outcome:** One-page “target sidebar” spec (sections + order + any fixed links).

---

### Phase S2: Data and grouping (backend)

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| S2.1 | If **flat (B):** adjust `app_order` and names in `get_app_list`. | `config/admin.py` | New order and labels; no new keys. |
| S2.2 | If **categories (A):** add a mapping `category_key → [app_labels]` and optional `category_label`; build a structure `categories → [ { name, order, apps: [ { app_label, name, models } ] } ]`. | `config/admin.py` | New method e.g. `get_app_list_grouped(request)` or extend `get_app_list` to return grouped structure; keep RBAC (only include apps/models user can see). |
| S2.3 | Expose grouped or flat list in template context (e.g. `sidebar_app_list` or `app_list` with new shape). | Same view/site that renders sidebar | Template can iterate over categories → apps → models. |

**Outcome:** Backend returns the structure you want (flat or grouped); RBAC unchanged.

---

### Phase S3: Template restructure

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| S3.1 | If **flat:** keep `app_list.html` but adjust markup/classes if you change layout (e.g. section dividers). | `templates/admin/app_list.html` | Same data shape, clearer sections or order. |
| S3.2 | If **categories:** new template (or big update to `app_list.html`): loop over categories → apps → models; use BEM classes e.g. `.admin-sidebar-category`, `.admin-sidebar-category__title`, `.admin-sidebar-app`, `.admin-sidebar-app__models`. | `templates/admin/app_list.html` or partial included from base_site | Markup matches new data (3 levels or 2); keep `current-app` / `current-model` via request.path. |
| S3.3 | Add **extra items (D):** Dashboard, Site settings, Backend console, Logout. | Same template or `base_site.html` (sidebar block) | Links at top or bottom of sidebar; permission-check where needed. |
| S3.4 | Keep or move **search** and **badges** so they work with new structure (e.g. search over all model links; badges still from MODEL_COUNTS). | `base_site.html` (JS) or template | Search and badges still work after restructure. |

**Outcome:** Sidebar markup reflects new structure; optional fixed links; search/badges intact.

---

### Phase S4: CSS and behaviour

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| S4.1 | Style new classes (categories, section titles, nested lists). | `admin_sidebar_enhanced.css` | Uses existing tokens; no new inline styles. |
| S4.2 | Collapsible: per-app and, if categories, per-category (optional). | `base_site.html` (JS) | Reuse or extend current collapse logic; localStorage keys for new structure. |
| S4.3 | Current location: ensure `.current-app` / `.current-model` (or equivalent) stay visible (e.g. open parent category + app). | JS + CSS | Active item and its parents clearly indicated. |
| S4.4 | Mobile: sidebar still offcanvas/slide-over on narrow viewports. | `admin_sidebar_enhanced.css` | No regression. |

**Outcome:** Sidebar looks and behaves as in your target spec; works on small screens.

---

### Phase S5: RBAC and docs

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| S5.1 | Confirm: only apps/models the user has permission to see appear; empty categories are hidden. | `get_app_list` / `get_app_list_grouped` | RBAC unchanged. |
| S5.2 | Update **ADMIN_UI.md** (sidebar section) and this plan with final structure and file list. | `docs/ADMIN_UI.md`, this doc | Next dev knows how sidebar is built. |

**Outcome:** Permissions correct; docs match implementation.

---

## 5. Tie-in with dashboard and revamp plans

- **Dashboard:** You keep the current dashboard **look and content** (or follow ADMIN_DASHBOARD_CHANGE_PLAN for content only). Sidebar restructure does **not** change the dashboard template; it only changes the **nav** that wraps it.
- **Revamp Phase 4:** After sidebar restructure, Phase 4 (current app highlight, breadcrumbs, back link, pin/collapse) still applies: make sure “current” state and breadcrumbs work with the **new** sidebar structure.
- **Order of work:** You can do **sidebar restructure first** (this plan), then continue **dashboard content** (ADMIN_DASHBOARD_CHANGE_PLAN) and **revamp** (ADMIN_REVAMP_PLAN) without conflict.

---

## 6. Key files (sidebar only)

| Purpose | File |
|--------|------|
| Sidebar data (order, names, optional categories) | `config/admin.py` → `get_app_list` / new grouped method |
| Sidebar markup (apps and models, optional categories) | `templates/admin/app_list.html` |
| Sidebar shell (search, badges, collapse, empty state) | `templates/admin/base_site.html` (block that includes app_list + scripts) |
| Sidebar styles | `static/css/admin_sidebar_enhanced.css` |
| Sidebar tokens | `templates/admin/base_site.html` (inline `:root` from SITE) |
| Model counts for badges | `apps/observability/templatetags/admin_extras.py` → `get_all_model_counts` |
| RBAC | Same as now: Django’s `_build_app_dict` + filtering in `get_app_list` |

---

## 7. Success criteria (sidebar restructure)

- Structure matches your spec (categories or flat, order, names).
- Dashboard and all other admin pages still load; sidebar is the only thing that changed.
- RBAC: users only see apps/models they have permission for; empty groups/categories hidden.
- Current page is clear in the sidebar (highlight/open parents).
- Extra items (Dashboard, Settings, etc.) appear where you decided; permissions respected.
- Search and count badges still work.
- Sidebar works on mobile (offcanvas/slide-over).
- ADMIN_UI.md (and this doc) updated.

Use this plan to restructure the sidebar; use ADMIN_DASHBOARD_CHANGE_PLAN only for **content** of the /admin page; use ADMIN_REVAMP_PLAN for the rest of the admin (tokens, list views, a11y, mobile).
