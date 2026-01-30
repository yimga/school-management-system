# Implementation Roadmap: Game Plan Execution

This doc tracks **what’s done** and **how to implement the rest** of the unified game plan. Use it with `docs/GAME_PLAN_UNIFIED.md` (sections 1–7 = plan, section 8 = how to proceed, section 9 = guardrails).

---

## Done

### Phase 1: Admin — one frame + one theme

- **`templates/admin/admin_dashboard.html`**
  - Changed `{% extends "admin/base.html" %}` → `{% extends "admin/base_site.html" %}` so the page at `/admin/` uses the same shell as the rest of admin (sidebar, model counts, accordions, design system).
  - Removed the duplicate theme toggle button from the dashboard header. Theme is now controlled only by the nav toggle in `base_site.html` (Light/Dark/System, persisted via `siteconfig:update_theme`).
  - Removed the inline `toggleTheme()` and theme-loading script; kept `generateCalendar()`, timestamp, `loadWeather()`, `loadDailyMessage()`.
  - Removed unused `.theme-toggle-btn` CSS.

**Smoke-test:** Visit `/admin/`, then e.g. `/admin/people/studentprofile/`. You should see the same sidebar and nav theme toggle; switching theme on the index should match changelist pages.

### Phase 2: Admin — config on the index

- **`templates/admin/admin_dashboard.html`**: Wired `--admin-accent` and `--admin-accent-light` from `SITE.accent_color|default:"#ff9500"`. Tagline/subtitle uses `SITE.tagline|default:SITE.site_name|default:"School System Management"` with `{% if SITE %}` guard. Main container uses `SITE_ADMIN_BACKGROUND_URL` for optional background image (with fallback).
- **`config/urls.py`**: `/admin/dashboard/` now redirects to `/admin/` so both URLs show the same index.

### Phase 3: Backend & portal

- **`templates/partials/portal_sidebar.html`**: Added “Django Admin” link (staff section) pointing to `{% url 'admin:index' %}` so staff can jump from backend to admin. Recent Activity is already collapsible with classes `recent-activity-toggle`, `recent-activity-content` (no duplicate IDs).

### Phase 4: Redundancy & cleanup

- **`apps/accounts/views.py`**: `backend_dashboard` now uses `get_dashboard_context(request.user, "backend")` from `apps/accounts/utils.py` for `dashboard_settings`, `allow_custom_layout`, `dashboard_layout_url`, `widget_meta_json`. Removed direct import of `load_dashboard_layout_settings`.
- **All other dashboard views** now use `get_dashboard_context(user, page)`:
  - **analytics**: `apps/analytics/views.py` dashboard → `get_dashboard_context(request.user, "analytics")`; removed `load_dashboard_layout_settings`, `_can_customize` imports.
  - **finance**: `apps/finance/views.py` dashboard → `get_dashboard_context(request.user, "finance")`; removed `load_dashboard_layout_settings`, `_can_customize`, `get_dashboard_widget_metadata` imports.
  - **payroll**: `apps/payroll/views.py` dashboard → `get_dashboard_context(request.user, "payroll")`.
  - **compliance**: `apps/compliance/views.py` ComplianceDashboardView.get → `get_dashboard_context(request.user, "compliance")`.
  - **portal** parent_dashboard and **evals** teacher_dashboard already used `get_dashboard_context`; removed unused `load_dashboard_layout_settings`, `_can_customize` from portal and evals.
- **`templates/admin/index.html`**: Kept as legacy (comment already states it’s not used; `/admin/dashboard/` redirects to `/admin/`).

### Phase 5: Backlog

- **GradingDeadline**: View and command already stubbed (view returns empty deadlines + message; command returns early with warning). Services return `None`/`[]`. No code change.
- **Report logo URLs**: Already built in `apps/reports/management/commands/generate_regional_reports.py` (absolute logo URL for email templates).
- **Widget chart types**: `apps/accounts/views.py` backend_dashboard now uses `getattr(w, "chart_type", None)` so chart_type is safe when the field is missing on `DashboardWidget`.
- **Boxed layout**: Added optional CSS in `templates/portal_base.html`: `body.portal-boxed .main-content` and `body.portal-boxed [data-portal-main]` get `max-width: 1280px` and centered margins. Toggle by adding class `portal-boxed` to `body` when desired.

---

## How to implement the rest (reference; all phases above are done)

### Phase 2 (reference)

**Goal:** The template that renders at `/admin/` uses Site Settings for palette and background (and optionally stats).

**Steps (completed):**

1. **Use SITE and ThemePack in the dashboard template**
   - In `templates/admin/admin_dashboard.html`, in the `<style>` block where `:root` is defined, optionally drive CSS variables from context, e.g.:
     - `--admin-accent`: `{{ SITE.accent_color|default:"#ff9500" }}` or from `SITE_ADMIN_THEME` if you have it.
     - Background: if you want the dashboard content area to use the admin background image, add something like `background-image: url('{{ SITE_ADMIN_BACKGROUND_URL|default:"" }}');` on the main container (with a fallback when empty).
   - Add `|default:""` or fallback hex values wherever you use `SITE`, `SITE_ADMIN_THEME`, or `SITE_LOGO_URL` so missing config (e.g. fresh install) doesn’t break the page.

2. **Replace hardcoded copy**
   - Replace “Gilead School System Management” with something from config if you have a site name/tagline field (e.g. `{{ SITE.site_name|default:"Gilead School System Management" }}`). Only if that field exists on SiteSettings.

3. **Optional: wire admin_portal_stats_config**
   - If you want stat cards to be config-driven, in the view that builds context for the admin index (`config/admin.py` → `index()`), pass `admin_portal_stats_config` (or a processed version) and in the template loop over it to render cards. Back the numbers with real data (e.g. the same `total_users`, `student_count` you already pass).

4. **Decide `/admin/dashboard/`**
   - If you have a URL `/admin/dashboard/` (e.g. observability), decide: redirect to `/admin/`, or keep as a separate view. Document in this file or in `GAME_PLAN_UNIFIED.md` section 9 (URL clarity).

---

### Phase 3: Backend & portal — confirm and close links

**Goal:** Recent Activity and theme work; portal default view and sidebar are config-driven; optional Admin link from backend.

**Steps:**

1. **Backend**
   - Confirm Recent Activity in the sidebar is collapsible and not duplicated (one block, classes like `recent-activity-toggle`, `recent-activity-content`; no duplicate IDs). Templates: `templates/partials/portal_sidebar.html`, `templates/backend_base.html`.
   - Confirm `backend_console_theme` (dark/light) from Site Settings is applied in `templates/backend_base.html` (e.g. loading the correct CSS file).
   - Optional: add a “Django Admin” link in the backend header or sidebar (e.g. in `portal_sidebar.html` staff section or in the nav bridge) so staff can jump from backend to admin.

2. **Portal**
   - Confirm “My Workflow” and default dashboard view work (post-login redirect, set-default view links). Code: `apps/accounts/views.py` (`redirect_view`), `apps/siteconfig/views.py` (`set_default_dashboard_view`), dashboard templates.
   - Confirm drag-and-drop layout toggle is hidden for teacher/parent (only staff can customize). Templates: `templates/teacher/dashboard.html`, `templates/parent/dashboard.html` (conditional on `allow_custom_layout` or similar).
   - If `portal_sidebar_order` and `build_portal_sidebar_items` exist in `apps/siteconfig/portal_sidebar_items.py` and context, confirm the portal sidebar order is driven by config; if the sidebar is static again, note “sidebar order: static” in this file and add “reintroduce config-driven order” to backlog.

3. **Smoke-test**
   - Visit backend home, one teacher dashboard, one parent dashboard. Check theme, sidebar, and links.

---

### Phase 4: Redundancy & cleanup

**Goal:** One admin index template in use; optional helper for dashboard context and layout loading.

**Steps:**

1. **Admin template**
   - You now use `admin_dashboard.html` (extends `base_site.html`) for `/admin/`. Decide what to do with `templates/admin/index.html`: keep for another URL (e.g. `/admin/dashboard/`), or remove. If you remove it, delete the file and document here.

2. **Optional: get_dashboard_context()**
   - When you next touch a portal or backend dashboard view, add a helper, e.g. in `apps/siteconfig/dashboard_views.py` or a new `apps/siteconfig/context_helpers.py`:
     ```python
     def get_dashboard_context(user, page: str) -> dict:
         from django.urls import reverse
         from django.utils.safestring import mark_safe
         import json
         # ... load_dashboard_layout_settings, _can_customize, get_dashboard_widget_metadata
         return {
             "dashboard_settings": load_dashboard_layout_settings(user, page),
             "allow_custom_layout": _can_customize(user),
             "dashboard_layout_url": reverse("api:dashboard-layout", kwargs={"page": page}),
             "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
         }
     ```
   - Use it in `backend_dashboard`, teacher dashboard, parent dashboard, etc., so you don’t repeat the same 4–5 lines.

3. **Optional: shared layout loader**
   - When you next change layout behavior, add a single function, e.g. `get_layout_for_page(user, page)`, that implements the fallback (user → role → default). Use it from both the dashboard layout API and `load_dashboard_layout_settings()` so logic lives in one place.

4. **Dashboard JS**
   - When you’re in that code, pick one approach: merge `dashboard-layout.js` and `dashboard-customizer.js`, or strip drag logic from customizer so only layout.js does drag. See `docs/CODE_REVIEW_GAPS_REDUNDANCIES.md` and game plan section 6.

---

### Phase 5: When you’re in that code (backlog)

- **GradingDeadline:** Restore a minimal model or replace all references with one source (e.g. `SubjectAssignment.deadline_at`). Remove dead code. Files: `apps/analytics/views.py`, `apps/analytics/services.py`, `apps/portal/services.py`, `apps/evals/views.py`, `apps/analytics/management/commands/send_deadline_reminders.py`.
- **Report logo URLs:** Ensure the report pipeline (e.g. `generate_regional_reports`) builds absolute logo URLs in one place for emails.
- **Widget chart types:** In the dashboard layout API and backend dashboard template, expose and use `chart_type` for widgets that support it.
- **Boxed layout / portal:** If you want a boxed portal layout, add a flag or class in `portal_base.html` and switch layout via CSS; keep full-width as default.

---

## Quick reference

| Phase | Focus | Main files | Status |
|-------|--------|------------|--------|
| 1 | Admin frame + one theme | `templates/admin/admin_dashboard.html` | ✅ Done |
| 2 | Admin config on index | `templates/admin/admin_dashboard.html`, `config/urls.py` | ✅ Done |
| 3 | Backend & portal | `portal_sidebar.html` (Django Admin link) | ✅ Done |
| 4 | Redundancy & cleanup | `accounts/views.py` (get_dashboard_context), `admin/index.html` kept | ✅ Done |
| 5 | Backlog | GradingDeadline stubbed, report logos, chart_type safe, boxed CSS | ✅ Done |

When you complete a phase or a step, add a short “Done: …” under **Done** above and/or tick the item in `docs/GAME_PLAN_UNIFIED.md` section 8.
