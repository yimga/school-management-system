# Unified Game Plan: Admin, Backend, Portal, Themes & Config

**One big plan** that ties together: admin audit, backend console, portal dashboards, themes, config, redundancy, UX, and the “other things to keep in mind” (accessibility, mobile, smoke-test, security, fallbacks, doc hygiene). Treat this as the single map—**sections 1–7** are the plan; **section 8 (How to proceed)** is the execution roadmap with phases and first actions; **section 9** is other things to keep in mind when you execute.

---

## 1. Big Picture

We have **three main “hubs”** that staff and users see:

| Hub | Who | Purpose |
|-----|-----|---------|
| **Django Admin** (`/admin`) | Staff / superusers | Data, models, site config, system settings |
| **Backend Console** (`/backend`) | Staff | Orchestration, workflows, recent activity, entity console |
| **Portal** (teacher/parent dashboards) | Teachers, parents | Day-to-day work, grades, finance, workflow center |

**Themes and config** touch all three: admin sidebar colors, backend dark/light, portal layout, dashboard defaults. **Redundancy** shows up as duplicate templates, duplicate theme toggles, and two dashboard UIs for admin. The game plan is: **one clear “frame” per hub**, **one theme story per hub** (or shared where it makes sense), and **close loops** so config actually drives what users see.

---

## 2. Admin (`/admin`)

**What we talked about:** Audit showed the shell (`base_site.html`) is strong—design system, config-driven sidebar, model counts, accordions, theme toggle—but the **dashboard at `/admin/`** doesn’t use it. Two dashboard templates exist; only one is live, and the live one doesn’t use Site Settings.

**Open-minded direction (pick one path, or blend):**

- **Unify the frame**
  - **Option A:** Make the page at `/admin/` use the same shell as the rest of admin. E.g. have `admin_dashboard.html` extend `admin/base_site.html` and drop its content into the `content` block. Then the first screen after login gets sidebar, model counts, accordions, and nav theme toggle automatically.
  - **Option B:** Switch `GileadAdminSite.index()` to render `admin/index.html` (which already extends `base_site.html`), and move the “rich” content (metrics, calendar, security, preview/finance cards) from `admin_dashboard.html` into `index.html` or shared includes. Over time, retire or repurpose `admin_dashboard.html`.
  - Either way, **one** admin index template that extends `base_site.html` so the “dashboard feel” matches changelist pages.

- **One theme story in admin**
  - Use a single theme toggle (the one in `base_site.html` that calls `siteconfig:update_theme` and `USER_THEME_PREFERENCE`). Remove duplicate toggles and scripts from whichever template ends up as the admin index so there’s no competing `localStorage` keys or `body.light-mode` logic.

- **Wire config to the live index**
  - Whichever template actually renders at `/admin/`, drive it from Site Settings where it helps: e.g. `SITE_ADMIN_THEME` / `SITE_ADMIN_BACKGROUND_URL` for palette and background, and optionally `admin_portal_stats_config` for which stat cards appear (backed by real data when possible). Replace hardcoded copy (e.g. “Gilead School System Management”) with site name/tagline from config when it’s easy.

- **Optional cleanup**
  - If you unify on one index template, the other can be removed or kept only for a different URL (e.g. “detailed dashboard” at `/admin/dashboard/`). No need to do both templates forever.

**Not rigid:** You can do “unify frame + one theme” first and leave stats/config for a later pass. The biggest win is the index using the same shell as the rest of admin.

---

## 3. Backend Console (`/backend`)

**What we talked about:** Dark/grey theme, Recent Activity in the left sidebar, collapsible Recent Activity, theme config from Site Settings (`backend_console_theme`), link from admin (nav bridge).

**Open-minded direction:**

- **Theme**
  - Keep using `backend_console_theme` (dark/light) from Site Settings so admins can set the default. Optionally respect a *user* preference (e.g. from the same mechanism as portal) later if you want; for now, site-level is enough.

- **Recent Activity**
  - Keep it in the sidebar (staff-only), loaded once and reused for desktop/mobile if needed. Collapsible with state in `localStorage` is done; just avoid duplicate blocks or duplicate IDs (use classes and `querySelectorAll` where you have multiple instances).

- **Consistency with admin**
  - Backend is the “friendly” orchestration hub; admin is the “data” hub. The nav bridge (admin → Backend Console) already links them. You could add a “Django Admin” link from the backend header/sidebar so the loop is closed both ways—only if it fits your UX.

**Not rigid:** If you later want a single “staff dashboard” that merges admin index and backend home, that can be a separate phase. For now, two hubs with clear roles and one theme each is fine.

---

## 4. Portal (Teacher / Parent Dashboards)

**What we talked about:** Workflow Center links, default dashboard view (Overview vs Workflow vs others), sidebar order (`portal_sidebar_order`), drag-and-drop layout restricted to staff, notifications bell.

**Open-minded direction:**

- **Workflow Center**
  - Keep “My Workflow” in sidebar and on dashboard cards. Default dashboard view (e.g. “send me to Workflow after login”) is already configurable per user; no need to lock it to one choice.

- **Sidebar order**
  - If `portal_sidebar_order` and `build_portal_sidebar_items` exist, use them so the sidebar order is config-driven. If the current implementation is static again (to avoid duplicate entries), consider reintroducing a *single* ordered list built from config so you don’t have to edit the template for every reorder.

- **Drag-and-drop**
  - Restrict customization to backend (staff) users; teacher/parent see a fixed layout. Toggle can be hidden for non-staff. One source of truth for “who can customize” (e.g. `_can_customize(request.user)`) in the layout API and in the template.

- **Notifications**
  - If you have a notifications bell in the portal header, drive it from the same context (e.g. `SHOW_HEADER_NOTIFICATIONS`, `NOTIFICATIONS_UNREAD_COUNT`) so it’s consistent and easy to turn off via config.

**Not rigid:** Teacher/parent don’t need to match admin or backend complexity. Simple, stable layout and one place for “default view” is enough.

---

## 5. Themes & Config (Cross-Cutting)

**What we talked about:** Different config items for admin vs backend vs portal; dashboard “feel”; optional design token / single source.

**Open-minded direction:**

- **Per-hub clarity**
  - **Admin:** SiteSettings (sidebar colors, logo/opacity) + ThemePack for admin (`SITE_ADMIN_THEME`, background, logo). User theme preference for admin can stay in the same place it is now (e.g. DashboardUserPreference or cookie).
  - **Backend:** `backend_console_theme` (dark/light) from Site Settings. Same idea: one setting, one place.
  - **Portal:** Active theme / layout preferences as you already have; optional high-contrast or reduced motion from user prefs.

- **No need to force one system**
  - Admin can have its own palette (ThemePack + sidebar vars); backend its own dark/light; portal its own. Unifying everything into one design token file is optional and can come later if you want to tighten consistency. Prefer “config drives the right hub” over “one global theme for all.”

- **Dashboard feel**
  - “Dashboard feel” = same frame (shell), same theme control, and where possible same config source for that hub. For admin, that means index uses `base_site.html` and ThemePack/sidebar vars. For backend, that means one theme and one sidebar. For portal, that means default view and sidebar order from config. You don’t have to make all three look the same—just consistent *within* each.

**Not rigid:** Add a shared design system or tokens only when the payoff is clear (e.g. rebranding, accessibility). Until then, per-hub config is enough.

---

## 6. Redundancy & Closing Loops

**What we talked about:** Two admin dashboard templates, duplicate theme toggles, duplicate dashboard JS, repeated context setup, layout loading in two places.

**Open-minded direction:**

- **Admin**
  - One admin index template (extends `base_site.html`). One theme toggle (in the shell). Remove or repurpose the other template and remove duplicate toggle scripts. **Loop closed:** “Change theme in admin” and “change sidebar colors in Site Settings” both affect what users see.

- **Dashboard context (portal/backend)**
  - If the same 4–5 lines (dashboard_settings, allow_custom_layout, layout URL, widget_meta_json) are repeated in every dashboard view, consider a small helper or context mixin: e.g. `get_dashboard_context(user, page)` so adding a new dashboard page is one call. Optional; do it when you touch a second or third view.

- **Dashboard layout loading**
  - API and `load_dashboard_layout_settings()` both do layout fallback (user → role → default). One shared helper (e.g. `get_layout_for_page(user, page)`) used by both keeps behavior and defaults in one place. You can do this when you next change layout behavior.

- **JS: dashboard-layout vs dashboard-customizer**
  - Two files (Sortable.js vs native drag) can conflict. Options: (A) Merge into one and use Sortable.js for drag, customizer only for “settings” (sidebar, links, variants); (B) Keep customizer but strip drag logic so only layout.js does drag; (C) One file that does layout + settings. Pick one when you next work on dashboards; no need to do it upfront.

**Not rigid:** “Close the loop” means: when an admin changes something in config, that change shows up where the user expects. Prioritize admin shell + theme; then dashboard context/layout/JS when you’re in that code anyway.

---

## 7. Other Gaps (When You’re Ready)

**From code review / past work:**

- **GradingDeadline**
  - Model was removed; references remain. Either restore a minimal model or replace with something like `SubjectAssignment.deadline_at` (or another single source) and remove dead code. Do when you touch deadlines/reminders.

- **Report logo URLs**
  - If report emails need absolute logo URLs, ensure the report pipeline builds them (e.g. in `generate_regional_reports` or equivalent). One place, one format.

- **Widget chart types**
  - If backend dashboard widgets support chart types, expose `chart_type` in the layout API and use it in the template so “dashboard feel” includes the right chart. Small, when you’re in that API.

- **Boxed layout / portal**
  - If you want a “boxed” portal layout, keep it behind a flag or class (e.g. in `portal_base.html`) so you can switch without breaking full-width. Optional.

**Not rigid:** These are “when it fits” items. Tackle them in the order that matches your next feature or bug, not in a fixed sequence.

---

## 8. How to Proceed (Execution Roadmap)

Use this as the single “what to do first, then next” path. Skip or reorder phases if needed; the goal is one clear way to proceed.

---

### Start here (before Phase 1)

- [ ] Read **section 1 (Big picture)** and **section 9 (Other things to keep in mind)** so you know the three hubs and the guardrails (accessibility, smoke-test, security, fallbacks, doc hygiene).
- [ ] Decide whether you’re starting with **Admin** (biggest impact: one frame + one theme) or **Backend/Portal** (quicker checks). Recommendation: start with Admin.

---

### Phase 1: Admin — one frame + one theme (highest impact)

**Goal:** The page at `/admin/` uses the same shell as the rest of admin (sidebar, model counts, accordions, nav theme toggle). One theme toggle for admin; no duplicates.

**First actions:**

1. **Unify the frame**
   - **Option A (fastest):** In `templates/admin/admin_dashboard.html`, change the first line from `{% extends "admin/base.html" %}` to `{% extends "admin/base_site.html" %}`. Move the current full-page content into `{% block content %}` only (strip any duplicate `<html>`/shell). Save and open `/admin/` — you should see the admin sidebar and nav.
   - **Option B:** In `config/admin.py`, change `index()` to render `admin/index.html` instead of `admin/admin_dashboard.html`. Move the “rich” content (metrics, calendar, preview/finance cards) from `admin_dashboard.html` into `index.html` (or includes). Then the index already extends `base_site.html`.

2. **One theme toggle**
   - In whichever template is now the admin index, remove the duplicate theme toggle markup and the inline `toggleTheme()` / `localStorage` script. Rely on the theme toggle in `base_site.html` (nav-global). If the index had its own Light/Dark/System UI, delete it so there’s only one.

3. **Smoke-test**
   - Visit `/admin/`, then one changelist (e.g. `/admin/people/studentprofile/`). Confirm: same sidebar, same theme toggle, theme persists when you switch. Quick mobile check (narrow viewport) if you have 2 minutes.

4. **Doc**
   - In this file or in `docs/ADMIN_AUDIT.md`, add a line: “Done: Admin index uses base_site.html; one theme toggle.”

**When Phase 1 is done:** Admin “dashboard feel” matches the rest of admin. You can stop here for a while or continue to Phase 2.

---

### Phase 2: Admin — config on the index

**Goal:** The template that renders at `/admin/` uses Site Settings for palette and background (and optionally stats), so changing Site Settings changes what users see.

**First actions:**

1. In the admin index template, use `SITE_ADMIN_THEME` and `SITE_ADMIN_BACKGROUND_URL` (and `SITE` for sidebar vars if you need them in the content area). Add `|default:""` or fallback colors where needed so missing config doesn’t break the page (see **section 9 — Graceful fallbacks**).

2. Replace the most obvious hardcoded strings (e.g. “Gilead School System Management”) with site name or tagline from config if you have a field for it.

3. Optionally wire `admin_portal_stats_config` to which stat cards appear (and back them with real data from the context `index()` already passes). Defer if you’re short on time.

4. Smoke-test again: change a sidebar color or admin theme in Site Settings, reload `/admin/` — does it update?

5. Decide and document: what should `/admin/dashboard/` do? Redirect to `/admin/`, or stay as a separate view? (See **section 9 — URL clarity**.)

---

### Phase 3: Backend & portal — confirm and close links

**Goal:** Recent Activity and theme work; portal default view and sidebar are config-driven; optional cross-link backend ↔ admin.

**First actions:**

1. **Backend:** Confirm Recent Activity in the sidebar is collapsible and not duplicated (one block, classes not duplicate IDs). Confirm `backend_console_theme` (dark/light) from Site Settings is applied. Optionally add a “Django Admin” link in the backend header/sidebar so staff can jump to admin.

2. **Portal:** Confirm “My Workflow” and default dashboard view work; confirm drag-and-drop is hidden for teacher/parent (staff only). If `portal_sidebar_order` exists, confirm sidebar order is driven by it (or note that it’s static for now and add to backlog).

3. Smoke-test: backend home, one teacher dashboard, one parent dashboard. Theme and sidebar behave; no broken links.

---

### Phase 4: Redundancy & cleanup

**Goal:** One admin index template in use; optional helper for dashboard context and layout loading.

**First actions:**

1. If you used Option A in Phase 1, you now have `admin_dashboard.html` extending `base_site.html`. Decide whether to keep `admin/index.html` (e.g. for `/admin/dashboard/` only) or remove it. If you used Option B, decide whether to keep or remove `admin_dashboard.html`. Document the decision.

2. When you next touch a portal/backend dashboard view, consider adding `get_dashboard_context(user, page)` and reusing it so you don’t repeat the same 4–5 lines. Optional.

3. When you next change layout behavior, consider a shared `get_layout_for_page(user, page)` used by both the API and `load_dashboard_layout_settings()`. Optional.

4. Dashboard JS (layout vs customizer): pick one approach when you’re in that code (merge, or strip drag from customizer). No need to do it in Phase 4 unless you’re already there.

---

### Phase 5: When you’re in that code (no fixed order)

- **GradingDeadline:** Restore or replace with one source (e.g. `SubjectAssignment.deadline_at`); remove dead references.
- **Report logo URLs:** Ensure report pipeline builds absolute logo URLs in one place.
- **Widget chart types:** Expose `chart_type` in layout API and use in backend dashboard if needed.
- **Boxed layout / portal:** Add behind a flag in `portal_base.html` if you want it.

---

### How to use this section

- **Do Phase 1 first** if you want the biggest win (admin index = same shell as rest of admin). Then Phase 2 when you’re ready to wire config.
- **Do Phase 3** when you’re touching backend or portal anyway.
- **Do Phase 4** after Phase 1 (and 2 if you did it) so you don’t leave two index templates and two theme toggles forever.
- **Phase 5** is backlog: do each item when you’re in that area or when it blocks you.
- **Stay open-minded:** If a phase doesn’t apply (e.g. you don’t use backend theme), skip it. When you complete something, tick it or add “Done: …” (doc hygiene, section 9).

---

## 9. Other Things to Keep in Mind

**Accessibility**  
When you change shells or theme toggles, keep accessibility in mind: contrast (especially in dark theme), focus states, and keyboard/screen reader flow. High-contrast and reduced-motion prefs already exist in some places; preserve or extend them when you touch that UI. See `docs/ACCESSIBILITY.md` if you have it.

**Mobile / responsive**  
Admin and backend have responsive styles; portal has mobile considerations. When you change a shell (e.g. admin index extending `base_site`), do a quick check on a narrow viewport so sidebar collapse and content stack still work.

**Smoke-test after big changes**  
After unifying admin index or removing a template: hit `/admin/`, one changelist, backend home, and one teacher/parent dashboard. Confirm theme persists, sidebar works, and no broken links. No need for a full regression—just “did we break the main path?”

**Security**  
Config-driven UI is great; just keep RBAC and staff checks in place. Admin and backend are staff-only; layout customization is already restricted to staff. When you add new “config drives UI” features, ensure only the right roles see or change them.

**URL clarity: `/admin/` vs `/admin/dashboard/`**  
Today `/admin/` is the custom index (admin_dashboard.html), and `/admin/dashboard/` can point at observability or the same template. When you unify to one index template, decide whether `/admin/dashboard/` should redirect to `/admin/`, stay as a separate “detailed” view, or be removed—and document it so the next person knows.

**Graceful fallbacks**  
If `SiteSettings` or `ThemePack` is missing (e.g. fresh install, migration not run), templates that use `SITE`, `SITE_ADMIN_THEME`, or `SITE_LOGO_URL` should have sensible defaults (e.g. `|default:""` or fallback colors) so the app doesn’t blow up. Worth a quick scan when you wire config to the live index.

**Doc hygiene**  
When you complete an item from this plan or from ADMIN_AUDIT / CODE_REVIEW, tick it or add a one-line “Done: …” so the doc stays useful. Future-you (or a teammate) will thank you.

---

**Summary:** One clear frame and one theme story per hub (admin, backend, portal); wire config so it drives what users see; remove duplicate templates and toggles where it’s easy; close loops (config → UI). **To proceed:** go to **section 8 (How to proceed)** — start with the “Start here” checklist, then Phase 1 (admin frame + theme). Do the rest in order or skip/reorder as needed; tick items and add “Done: …” as you go (section 9).
