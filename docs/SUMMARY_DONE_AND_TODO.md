# Summary: What Has Been Done and What Is Yet to Be Done

Based on the **Unified Game Plan** (`docs/GAME_PLAN_UNIFIED.md`) and **Implementation Roadmap** (`docs/IMPLEMENTATION_ROADMAP.md`).

---

## What has been done

### Admin (`/admin`)

- **One frame:** The page at `/admin/` now uses the same shell as the rest of admin. `admin_dashboard.html` extends `base_site.html`, so you get the sidebar, model count badges, accordions, and design system on the index.
- **One theme toggle:** Duplicate theme button and script were removed from the dashboard. Theme is controlled only by the nav toggle in `base_site.html` (Light/Dark/System), persisted via `siteconfig:update_theme`.
- **Config on the index:** Admin dashboard uses `SITE.accent_color` for accent CSS vars, `SITE.tagline` / `SITE.site_name` for the subtitle, and `SITE_ADMIN_BACKGROUND_URL` for optional background image (with fallbacks).
- **URL clarity:** `/admin/dashboard/` redirects to `/admin/` so both show the same index.
- **Legacy template:** `admin/index.html` is kept as legacy (unused); no second dashboard UI.

### Backend & portal

- **Django Admin link:** “Django Admin” link added in the backend sidebar (staff section) so staff can jump from Backend Console to `/admin/`.
- **Recent Activity:** Already collapsible in the sidebar (classes, no duplicate IDs).
- **get_dashboard_context everywhere:** All dashboard views now use `get_dashboard_context(user, page)` from `apps/accounts/utils.py`:
  - Backend (`accounts`), Analytics, Finance, Payroll, Compliance, Parent dashboard (`portal`), Teacher dashboard (`evals`).
- Redundant imports of `load_dashboard_layout_settings` and `_can_customize` removed from the views that now use the helper.

### Backlog items (Phase 5)

- **GradingDeadline:** Implemented via `SubjectAssignment.deadline_at`. Analytics deadlines view, `send_deadline_reminders` command, portal/analytics services, and `get_teacher_compliance` use it; `extend_deadline_view` extends and saves; template uses `subject_assignment.deadline_at`.
- **Report logo URLs:** Already handled in `generate_regional_reports.py` (absolute logo URL for emails).
- **Widget chart types:** Backend dashboard uses `getattr(w, "chart_type", None)` so missing `chart_type` on `DashboardWidget` does not break.
- **Boxed layout:** Body class in `portal_base.html` uses `layout-{{ SITE.layout_style|default:'fluid' }}` and adds `portal-boxed` when `SITE.layout_style == 'boxed'`; CSS already constrains main content.
- **admin_portal_stats_config:** Wired in `config/admin.py` index: section_stats from counts, `resolve_admin_portal_stats()` from `apps/siteconfig/admin_portal_stats.py`; context passes `admin_portal_stats` and `admin_portal_stats_display`; backend dashboard uses shared resolver.
- **Shared layout loader:** `get_layout_for_page(user, page)` in `apps/siteconfig/dashboard_views.py` used by `load_dashboard_layout_settings()` and dashboard layout API GET.
- **Dashboard JS:** Native drag removed from `dashboard-customizer.js`; only `enableCustomizeMode`/`disableCustomizeMode` (show/hide meta controls); reordering handled by `dashboard-layout.js` (Sortable.js).
- **Sidebar RBAC:** Recent Activity (admin LogEntry feed) is staff/admin-only; hidden for TEACHER and PARENT. System Configuration and Django Admin link already staff-only. Teacher and parent sidebars show only role-allowed sections (see `docs/SMOKE_TEST_STEPS.md`).
- **Accessibility:** Skip link (aria-label, #main-content); main region `id="main-content"` and `role="main"`; sidebar toggle and theme toggle aria-labels and focus-visible; Recent Activity collapsible keyboard (Enter/Space). See `docs/ACCESSIBILITY.md`.
- **Smoke test:** `docs/SMOKE_TEST_STEPS.md` documents manual checks for admin, backend, teacher dashboard, parent dashboard, and RBAC.
- **KB role-based visibility:** `KBCategory` and `KBArticle` have `target_roles` (JSONField). Empty = visible to all; `["PARENT"]` / `["TEACHER"]` = only that role. Views filter by `request.user` role; staff/superuser see all. Admin: "Visibility by role" fieldset and list column.

### Docs

- **`docs/ADMIN_AUDIT.md`:** Audit of `/admin` (what’s good, gaps, redundancy, config).
- **`docs/GAME_PLAN_UNIFIED.md`:** Single game plan (admin, backend, portal, themes, config, redundancy) with section 8 “How to proceed” and section 9 “Other things to keep in mind.”
- **`docs/IMPLEMENTATION_ROADMAP.md`:** Tracks completed phases and reference steps; all five phases marked done.

---

## What is yet to be done (optional / when you’re ready)

### Admin

- **Graceful fallbacks:** Added in key templates: `portal_base.html` (SITE_THEME, SITE.layout_style), `admin/base_site.html` (SITE_LOGO_URL, SITE sidebar vars with `{% if SITE %}`), `portal_sidebar.html` (Portal Tools wrapped in `{% if SITE %}`). Further passes optional.

### Backend console

- **backend_console_theme:** Already present on SiteSettings and wired in `backend_base.html` (light/dark/system). Nothing left to do unless you add more options.

### Portal

- **Portal sidebar order:** If your codebase has `portal_sidebar_order` and `build_portal_sidebar_items` (e.g. in `apps/siteconfig/portal_sidebar_items.py` and context processor), the sidebar template can use `PORTAL_SIDEBAR_ITEMS` when set; otherwise the sidebar is static. Reintroduce or wire that if you want config-driven order.

### Redundancy / code quality

- **admin/index.html:** Deleted (legacy; `/admin/` uses `admin_dashboard.html`).

### Design system / themes (optional)

- **Single design token file:** Not done. Admin, backend, and portal each have their own config; unifying into one token file is optional and can wait until you need it (e.g. rebranding, accessibility).

### Guardrails (when you touch UI)

- **Accessibility:** When changing shells or theme toggles, keep contrast, focus, and keyboard/screen reader in mind; see `docs/ACCESSIBILITY.md` if present.
- **Smoke-test:** After big changes, hit `/admin/`, a changelist, backend home, and one teacher/parent dashboard; confirm theme and sidebar.
- **Doc hygiene:** When you complete an item, tick it or add “Done: …” in the roadmap or game plan.

---

## Quick reference

| Area              | Done                                                                 | Yet to do (optional)                                      |
|-------------------|----------------------------------------------------------------------|-----------------------------------------------------------|
| Admin             | One frame, one theme, config on index, `/admin/dashboard/` redirect, **admin_portal_stats wired**, **graceful SITE fallbacks in base_site** | — |
| Backend           | Django Admin link, Recent Activity collapsible, **backend_console_theme wired** | — |
| Portal            | All dashboards use `get_dashboard_context`; **portal-boxed from SITE.layout_style** | Config-driven sidebar order if desired |
| Redundancy        | One admin index template; one theme toggle; **get_layout_for_page**; **drag stripped from customizer**; **legacy admin/index.html deleted** | — |
| GradingDeadline   | **SubjectAssignment.deadline_at** used everywhere; extend_deadline view + get_teacher_compliance fixed | — |
| Report logos      | Already in generate_regional_reports                                 | —                                                         |
| Widget chart_type | Safe getattr in backend dashboard                                    | Add `chart_type` to API/model if you need it              |
| KB (Knowledge Base) | **Role-based visibility:** `target_roles` on KBCategory and KBArticle; parents see parent topics, teachers see teacher topics; staff see all. Migration `portal.0013_kb_target_roles`. | Run `migrate portal` when DB is ready |

For full detail and execution steps, use **`docs/GAME_PLAN_UNIFIED.md`** (sections 8 and 9) and **`docs/IMPLEMENTATION_ROADMAP.md`**.
