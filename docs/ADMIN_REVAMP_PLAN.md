# Admin Revamp Plan

**Doc status: Closed.** Phase 1–3 tasks (remaining admin hex, Quick actions strip, inline styles) are **Closed (Phase 10 / deferred)**. Tracked in **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

A phased plan to revamp `/admin`: what’s done, what’s next, and how to execute it.

---

## What’s already done

- **Canonical tokens:** Primary = `--color-primary`, focus = `--focus-ring-color`; design-system-unified and design-tokens own them. See `docs/THEME_CANONICAL_TOKENS.md`.
- **Admin dashboard:** Token-based stats (BEM: `.admin-stat`, `.admin-stat--success`, etc.), user cards (`.admin-user-card`, `.admin-user-card__avatar`, `.admin-user-card__btn`), CTA and weather widget use design-system vars. Inline colors removed from `admin_dashboard.html`.
- **Theme preset panel:** Moved to `admin_theme.css`; BEM `.admin-theme-preset`, `.admin-theme-preset__actions`; uses `--color-*` vars.
- **Focus ring:** Single token; admin sidebar toggle uses `--admin-sidebar-focus-ring`; admin_theme and design-system use `--focus-ring-color`.
- **.env.local override:** Loaded with `override=True` so `DB_FILE` and other local vars always win over `.env`.
- **Sidebar/header:** Collapsible app groups, lively child blocks, SiteSettings-driven colors, theme presets. See `docs/ADMIN_UI.md`.

---

## Phase 1: Visual and token polish (admin-only)

**Goal:** Admin looks consistent and on-brand; no leftover hardcoded colors or competing tokens.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 1.1 | Remove or alias any remaining admin hardcoded hex in CSS | `admin_theme.css`, `admin-polish.css`, `admin_components.css` | All admin colors use `--color-*` or `--admin-sidebar-*` |
| 1.2 | Ensure list/change view tables use tokens (e.g. table header bg) | `admin_theme.css`, Unfold overrides | Table headers use `var(--color-bg-light)`; borders use `var(--color-border)` |
| 1.3 | Add “admin shell” wrapper class if missing | `base_site.html` | e.g. `.admin-shell` on `#main` or main wrapper for scoped overrides |
| 1.4 | Document admin-only CSS load order | `docs/ADMIN_UI.md` or `docs/CSS_LOAD_ORDER.md` | Short list: design-tokens → design-system-unified → admin-components → admin_theme → admin_sidebar_enhanced → … |

**Outcome:** One source of truth for admin colors; easy to theme from Site Settings.

---

## Phase 2: Dashboard content and UX

**Goal:** Admin index is useful at a glance and quick to navigate.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 2.1 | Wire dashboard KPIs to real data where still placeholder | `config/admin.py` (index view), `admin_dashboard.html` | e.g. total users, DB health, active sessions from DB/Redis; security counts from audit or logs |
| 2.2 | Add “Quick actions” strip (e.g. Add user, Add student, Open customizer) | `admin_dashboard.html`, permission checks in view | Strip of 3–5 buttons; links respect `has_add_permission` / `has_view_permission` |
| 2.3 | Optional: Recent activity or “last edited” in sidebar or dashboard | New template partial, view context | Small list of last 5–10 edited objects (model + link); permission-filtered |
| 2.4 | Optional: Dashboard widget layout configurable (order/hide) | `DashboardUserPreference` or similar, JS to reorder | User can reorder or hide dashboard sections; state saved per user |

**Outcome:** Dashboard reflects real state and shortens paths to common tasks.

---

## Phase 3: List and change views

**Goal:** List and form pages are clear, consistent, and accessible.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 3.1 | Standardize list view: actions bar, filters, search | Unfold config / `admin_theme.css` | Consistent spacing, token-based borders/backgrounds; sticky toolbar on scroll |
| 3.2 | Form layout: fieldset grouping, required indicators, help text | `admin_theme.css`, form templates | Clear sections; required `*` and help text use tokens; no inline styles |
| 3.3 | Replace any remaining inline styles in admin templates | `templates/admin/**/*.html` | Grep for `style=`; move to classes in `admin_theme.css` or `admin-dashboard.css` |
| 3.4 | Optional: Inline editing or “quick edit” for one or two high-traffic models | Custom admin template or Unfold feature | Only if product need exists |

**Outcome:** List and change views feel part of the same admin shell; WCAG-friendly.

---

## Phase 4: Navigation and information architecture

**Goal:** Sidebar and breadcrumbs make it obvious where you are and how to get back.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 4.1 | Highlight current app and model in sidebar | `app_list.html`, `admin_sidebar_enhanced.css` | `.current-app` and `.current-model` (or equivalent) with distinct style; already partially done—verify and extend |
| 4.2 | Breadcrumbs: ensure every admin page has them; style with tokens | `base_site.html`, Unfold, `admin_theme.css` | Breadcrumbs visible and styled; use `--color-text-muted`, `--color-text-primary` |
| 4.3 | Optional: “Back to list” / “Back to dashboard” in header or below breadcrumbs | Template partial, `admin_theme.css` | One predictable back link on change/view pages |
| 4.4 | Optional: Sidebar “pin” or “collapse to icons” for power users | `admin_sidebar_enhanced.css`, JS in `base_site.html` | Persisted preference; icons-only mode with tooltips |

**Outcome:** Users can orient quickly and recover from deep drill-downs.

---

## Phase 5: Accessibility and keyboard

**Goal:** Admin is usable with keyboard and assistive tech; focus and contrast are consistent.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 5.1 | Audit focus order on dashboard and main list/change views | Manual or pa11y | Document and fix any focus traps or illogical order |
| 5.2 | Ensure all interactive elements have visible focus (already using `--focus-ring-color`) | `admin_theme.css`, `admin_sidebar_enhanced.css` | No focusable element without outline/ring |
| 5.3 | Skip link “Skip to main content” on admin | `base_site.html`, `admin_theme.css` | Same pattern as portal; visible on focus |
| 5.4 | Optional: Landmark roles and live regions for dynamic updates | Templates, `admin_theme.css` | `role="main"`, `aria-live` for messages if needed |

**Outcome:** Admin passes WCAG 2.1 AA where applicable; keyboard-only flow works.

---

## Phase 6: Mobile and responsive

**Goal:** Admin is usable on tablets and large phones (even if “desktop-first”).

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 6.1 | Sidebar: offcanvas or slide-over on narrow viewport | `admin_sidebar_enhanced.css`, `base_site.html` | Breakpoint (e.g. &lt;992px): sidebar toggles to overlay; toggle button in header |
| 6.2 | Dashboard grid: cards stack; KPIs and quick actions wrap | `admin_dashboard.html`, `dashboard-responsive.css` | No horizontal scroll; touch-friendly targets |
| 6.3 | List view: horizontal scroll for wide tables or card layout option | `admin_theme.css`, Unfold | Table scrolls or switches to card list on small screens |
| 6.4 | Forms: full-width inputs and buttons on small screens | `admin_theme.css` | Single column; min height for buttons ~44px |

**Outcome:** Admin is usable on tablet and acceptable on large phones.

---

## Phase 7: Performance and maintainability

**Goal:** Admin stays fast and easy to change.

| # | Task | Where | Deliverable |
|---|------|--------|-------------|
| 7.1 | Lazy-load or defer non-critical dashboard widgets | `admin_dashboard.html`, JS | e.g. weather or “recent activity” loaded after first paint |
| 7.2 | Ensure admin CSS is not duplicated (single entry per file) | `base_site.html` | No duplicate link tags; optional single “admin.bundle.css” later |
| 7.3 | Document “add a new admin page/section” steps | `docs/ADMIN_UI.md` or new `docs/ADMIN_EXTENDING.md` | Short checklist: template, view, URL, permission, sidebar (if custom nav) |
| 7.4 | Optional: Admin-specific cache (e.g. model counts) and cache invalidation | `admin_extras.py`, cache backend | TTL and invalidation on model save/delete where needed |

**Outcome:** Clear ownership of admin assets and a path for future changes.

---

## Suggested order

1. **Phase 1** – Visual and token polish (foundation; quick).
2. **Phase 2** – Dashboard content and UX (high impact).
3. **Phase 3** – List and change views (consistency across admin).
4. **Phase 4** – Navigation and IA (wayfinding).
5. **Phase 5** – Accessibility and keyboard.
6. **Phase 6** – Mobile and responsive.
7. **Phase 7** – Performance and maintainability.

Phases 1–3 give the biggest visible and UX gain; 4–6 improve usability and inclusivity; 7 keeps the revamp sustainable.

---

## Key files reference

| Area | Files |
|------|--------|
| Admin shell, scripts, stylesheet order | `templates/admin/base_site.html` |
| Dashboard layout and widgets | `templates/admin/admin_dashboard.html`, `config/admin.py` (index view) |
| Sidebar structure and badges | `templates/admin/app_list.html`, `templates/admin/base_site.html`, `templates/admin/includes/model_count_badge.html` |
| Admin CSS (global) | `static/css/admin_theme.css`, `static/css/admin_sidebar_enhanced.css`, `static/css/admin-dashboard.css`, `static/css/admin-components.css` |
| Theme config and preset | `templates/admin/components/admin_theme_preset.html`, `templates/admin/siteconfig/sitesettings/change_form.html` |
| Design tokens | `static/css/design-tokens.css`, `static/css/design-system-unified.css`, `docs/THEME_CANONICAL_TOKENS.md` |
| RBAC and permissions | `config/admin.py`, `apps/observability/templatetags/admin_extras.py`, `docs/ADMIN_UI.md` |

---

## Success criteria

- **Visual:** All admin screens use design-system tokens; no hardcoded hex in admin templates/CSS for theme-dependent colors.
- **Dashboard:** KPIs reflect real data where applicable; at least one “quick actions” strip; layout responsive.
- **Navigation:** Current app/model clear in sidebar; breadcrumbs on all pages; optional back link.
- **A11y:** Focus visible everywhere; skip link present; keyboard navigable; contrast meets WCAG AA.
- **Mobile:** Sidebar works as overlay on narrow viewports; dashboard and forms usable on tablet.
- **Docs:** `ADMIN_UI.md` and this plan updated; CSS load order and “how to add admin content” documented.

Use this plan as a checklist; complete Phase 1 first, then iterate through 2–7 as capacity allows.
