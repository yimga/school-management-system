# Audit: Admin & Control Plane Improvements

**Date:** 2026-03-08  
**Scope:** All items from the admin/control-plane improvement plan and optional/deferred items.

---

## 1. Original production fixes (verified)

| Item | Status | Evidence |
|------|--------|----------|
| Unclosed `{% if %}` in title block | **Fixed** | `templates/partials/page_families/title_block.html`: inner `{% if back_label %}` now has `{% endif %}`; duplicate `{% endif %}` removed. |
| `quota_limits` assignment on /super/usage/ | **Fixed** | `apps/schools/super_views.py`: uses `school.quota_limits_list = quotas.get(...)`; `templates/schools/super_usage.html` iterates `school.quota_limits_list`. |
| Favicon 500s | **Fixed** | `config/tenant_urls.py`: `favicon_redirect` view and `path("favicon.ico", favicon_redirect)`; redirects to `static("images/runmycampus-icon.png")`. No physical `static/favicon.ico` required (redirect suffices). |

---

## 2. Admin sidebar & index (7 items)

| Item | Status | Evidence |
|------|--------|----------|
| Compact mode: generic icon for model links | **Done** | `templates/admin/app_list.html`: model links use `.admin-sidebar-model-icon` and `.admin-sidebar-model-link-text`; `admin-sidebar-polish.css`: compact mode hides text, shows icon. |
| Tenant admin index (index_tenant when not manager) | **Done** | `config/admin.py`: `TenantAdminSite.index_template_name = "admin/index_tenant.html"`; `PlatformAdminSite.index_template_name = "admin/index_superadmin.html"`. Index view uses `self.index_template_name` (no runtime branch; template is per site). |
| System & configuration first on manager | **Done** | `config/admin.py` `get_app_list()`: when `self.is_platform_site()`, moves `siteconfig` to front of `app_list`. |
| Persist quick-group open/closed state | **Done** | `templates/admin/base_site.html`: `getQuickAccessState()` reads `admin-qa-overview`, `admin-qa-config`, `admin-qa-content` from localStorage. `app_list.html`: each group toggle writes to localStorage. |
| Compact toggle: expand/collapse icon by state | **Done** | `templates/admin/sidebar_inner.html`: two spans (`.admin-sidebar-compact-icon-expand`, `.admin-sidebar-compact-icon-collapse`). CSS shows one or the other based on `body.admin-sidebar-compact`. |
| Pinned links in admin sidebar | **Done** | `app_list.html`: Pinned section with `#admin-sidebar-pinned-list`, "Pin this page" button. `base_site.html`: getAdminPinned/setAdminPinned/renderAdminPinned, localStorage key `runmycampus-admin-pinned`, max 5, unpin by URL. |
| Breadcrumbs show "Configuration Engine" | **Done** | `templates/admin/base.html`: block `admin_breadcrumbs` with "Configuration Engine" link to admin:index, then app label and model when `opts` present. |

---

## 3. Optional: Control plane (/super/)

| Item | Status | Evidence |
|------|--------|----------|
| Keyboard shortcuts (e.g. `g d` → dashboard) | **Done** | `templates/control_plane_base.html`: `g` then `d`/`c`/`a`/`b`/`s`/`m`/`u`/`h`/`p` with 1.2s timeout; `?` shows help overlay; Esc closes. |
| Recent (last few super pages) | **Done** | `control_plane_base.html`: pushRecent/renderRecent, sessionStorage `runmycampus-cp-recent`, max 5. `partials/control_plane_sidebar.html`: `#cpNavRecentWrap`, `#cpNavRecentList` filled by JS. |

---

## 4. Optional: A11y

| Item | Status | Evidence |
|------|--------|----------|
| Focus when collapsing sections | **Done** | Quick-access group headers are `<h3 role="button" tabindex="0">`; focus remains on button (no programmatic move needed). |
| Live region for sidebar updates | **Done** | `base_site.html`: `#admin-sidebar-live` with `aria-live="polite"`; `announceAdminSidebar(msg)`; called on pinned list update and from app_list on quick-group toggle (Overview/Configuration/Content & tools). |

---

## 5. Optional: RTL

| Item | Status | Evidence |
|------|--------|----------|
| RTL styling for admin sidebar | **Done** | `static/css/admin-sidebar-polish.css`: `[dir="rtl"]` rules for nav border, section titles, quick-group title/label/chevron, links, app title, pinned items, compact toggle, fixed sidebar position (`left: auto; right: 0`). |

---

## 6. Issues found and fixed during audit

| Issue | Fix |
|-------|-----|
| **title_block.html** had one extra `{% endif %}` and the inner `{% if back_label %}` block was missing `{% endif %}` (could cause template error or wrong scope). | Inner block closed with `{% endif %}` before `</a>`; duplicate `{% endif %}` on the following line removed. |

---

## 7. Not implemented (by design)

- **static/favicon.ico**: Not added; `/favicon.ico` redirects to `/static/images/runmycampus-icon.png`. If you need a physical `favicon.ico` for legacy clients, add it under `static/`.
- **Admin index template selection by request**: Template is chosen by which admin site is used (Tenant vs Platform), not by a runtime check in `index()`. Both sites use the same sidebar; only the index template differs.
- **Control plane**: Keyboard shortcuts for non-/super/ pages, "Recent" persistence across sessions (currently sessionStorage). These could be extended if required.

---

## 8. File reference

| Area | Key files |
|------|-----------|
| Admin sidebar | `templates/admin/app_list.html`, `templates/admin/sidebar_inner.html`, `templates/admin/base_site.html`, `templates/admin/base.html`, `static/css/admin-sidebar-polish.css` |
| Admin index / app list | `config/admin.py`, `templates/admin/index_superadmin.html`, `templates/admin/index_tenant.html` |
| Control plane | `templates/control_plane_base.html`, `templates/partials/control_plane_sidebar.html` |
| Favicon | `config/tenant_urls.py` |
| Super usage | `apps/schools/super_views.py`, `templates/schools/super_usage.html` |
| Title block | `templates/partials/page_families/title_block.html` |

---

**Conclusion:** All planned items are implemented. One template bug in `title_block.html` was found and fixed during this audit.
