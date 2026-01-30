# Summary Game Plan — Dashboard & Portal Improvements

**Purpose:** Single reference for main work and all improvements so you can review and approve.  
**Last updated:** For your review.

---

## 1. Main Work Areas

| Area | Scope |
|------|--------|
| **Backend dashboard** | `/authentication/backend/` — RBAC-gated sections, sidebar, quick actions, recommended next steps |
| **Portal (parent/teacher)** | Parent dashboard, teacher dashboard, sidebar, stats, footer |
| **Layout & customization** | Drag-and-drop widget order, resizable sidebar, (planned) widget size |
| **Theme & visibility** | Light/dark, button/text contrast, footer compactness |
| **Deployment** | Branch/config (e.g. `deploy.sh`), Render, cache |

---

## 2. Completed Work

### 2.1 Backend dashboard & RBAC
- **RBAC enforcement:** `action_perms` (people, finance, site_settings, admin_panel) control which sections and buttons are shown. See `docs/RBAC_DASHBOARD_VISIBILITY.md`.
- **Sidebar:** `available_sidebar_items` with `allow=...`; only allowed items shown.
- **Templates:** `backend_dashboard.html` and backend sidebar use permission checks.

### 2.2 Portal sidebar & navigation
- **RBAC-aware sidebar:** Portal sidebar shows only links the user has permission for (`has_feature_permission`, `has_role`).
- **Structure fixes:** Single “Portal Tools”; “Portal Stats” under Analytics (staff) / Settings (teacher); “Documents” under Content & Documents; “System Configuration” merged into “Admin Panel” as last section.
- **No duplicate sections** for Portal Tools, Settings, or Admin Panel.

### 2.3 Theme & visibility
- **Theme system:** Portal uses `data-bs-theme` + `localStorage.theme`; backend uses `data-backend-theme` + `localStorage.backendTheme`. See `docs/THEME_SYSTEM.md`.
- **Button/text visibility:** Theme applied so buttons and text have sufficient contrast (`backend_base.html`, `backend-visibility.css`).
- **Footer:** More compact (reduced padding, gaps, min-height, image sizes) in `dashboard_footer.html`.
- **Footer links:** Admin-only links hidden for non-staff (e.g. parents) via `has_feature_permission` / `has_role`.

### 2.4 Dashboard data consistency
- **Attendance:** Parent dashboard sets `request.parent_dashboard_attendance_pct`; top-bar “Attendance” stat uses it so it matches the dashboard widgets (no 0% vs 100% mismatch).

### 2.5 Drag-and-drop (widget reorder)
- **Column detection:** Layout script supports explicit columns or single-column fallback; `data-dashboard-column="main"` when needed.
- **Toggle:** Supports both `toggleLayoutDrag` and `toggleCustomize`.
- **Page detection:** `data-dashboard-page` or URL-based (`/parent/`, `/teacher/`, `/backend/`).
- **Auto-enable:** Can use `data-custom-drag-enabled="true"` without toggle.
- **Conflict avoidance:** Customizer checks Sortable.js before enabling native drag.
- **Visual feedback:** CSS for ghost, chosen, drag state; hover in drag mode; mobile touch. See `docs/DRAG_AND_DROP_FIXES.md`.

### 2.6 Resizable portal sidebar
- **Implemented:** Drag handle between sidebar and main content (desktop only) in `portal_base.html`.
- **CSS:** `.portal-resize-handle`, `--portal-sidebar-width` (min/max).
- **Persistence:** Width saved to `localStorage` (`portal-sidebar-width`) and restored on load.

### 2.7 CI & quality
- **Lighthouse CI** and **axe-core** (accessibility) in CI workflow where configured.
- **Docs:** Migrations known issues, deployment/backend dashboard notes (where present in repo).

### 2.8 Deployment
- **Branch/config:** `deploy.sh` (or equivalent) uses configurable branch (e.g. `DEPLOY_BRANCH`, default `main`) so deploys match the branch you intend.
- **Docs:** Deployment and “clear build cache & deploy” guidance for Render (in deployment docs when present).

---

## 3. Extra Improvements (full list)

All planned/optional improvements in one place, including resize:

- **Resize widgets on the dashboard** — Users and admin can set dashboard card/widget size (e.g. Small / Medium / Large) so cards take up more or less space. Optionally later: drag-to-resize on card edges.
- **Resize items on the dashboard** — Same as above: individual dashboard items (cards, widgets) can be resized; available in customize/layout mode for both users and admin.
- **Drag-and-drop makeover (UX)** — Single “Customize layout” button, grip-only drag handle, clear instructions and save feedback.
- **Resizable portal sidebar** — Already done: drag handle to resize sidebar width; persists in browser.
- **Widget reorder** — Already done: reorder widgets via drag-and-drop; persistence via API.
- **Other UX extras** — Reset to default layout, one-level undo, column labels in edit mode, mobile list reorder, first-time hints, keyboard accessibility.

---

## 4. Planned / Optional Improvements (detail)

### 4.1 Drag-and-drop makeover (UX)
- **Single “Customize layout” button** — Enter edit mode explicitly (no unclear checkbox).
- **Grip-only drag** — In edit mode, only a visible grip (e.g. ⋮⋮) is the drag handle; rest of card is clickable.
- **Instructions + save feedback** — e.g. “Drag cards by the grip to reorder. Layout saves automatically.” + toast on save.
- **Dashboard settings separate** — Sidebar prefs, tile density, shortcuts, etc. out of the customize flow.
- **Same flow for all roles** — Admin, parent, teacher use same button, grip, and API (with role-aware defaults if needed).
- **Extras (optional):** Reset to default, one-level undo, column labels in edit mode, mobile list reorder, first-time hints, loading states, keyboard accessibility.

### 4.2 Resize widgets & resize dashboard items (users & admin)
- **Resize widgets:** In customize mode, each dashboard widget/card can be resized. Users and admin both get this.
- **Size presets (recommended first):** Small / Medium / Large per widget (dropdown or buttons); persist per widget (e.g. `size` or `variant`).
- **Resize items on the dashboard:** Same feature — individual dashboard items (cards, widgets) are resizable; applies to parent, teacher, and backend dashboards.
- **Optional later:** Drag-to-resize on card edges (more flexible, more implementation work).

### 4.3 Testing & verification
- **Manual:** Teacher/Parent/Backend dashboards — toggle “Drag & drop layout” / “Customize layout”, reorder widgets, refresh and confirm persistence.
- **Manual:** Portal sidebar resize — drag handle, reload, confirm width persists.
- **Manual:** RBAC — log in as parent vs staff and confirm sidebar/footer/backend sections match permissions.
- **Manual:** Theme — light/dark and contrast on backend/portal.

---

## 5. Approval Checklist (for you)

Use this to review and approve scope:

- [ ] **RBAC & visibility** — Backend and portal show only what the user is allowed; sidebar and footer match role/permissions.
- [ ] **Theme & footer** — Light/dark and contrast are acceptable; footer is compact and non-staff don’t see admin links.
- [ ] **Dashboard data** — Attendance and other stats are consistent between top bar and widgets.
- [ ] **Sidebar structure** — No duplicate sections; Portal Stats, Documents, Admin Panel in the right places.
- [ ] **Resizable sidebar** — Portal sidebar drag-to-resize and persistence are acceptable.
- [ ] **Drag-and-drop (current)** — Widget reorder with toggle, column fallback, and persistence are acceptable.
- [ ] **Planned: makeover** — Agree to pursue “Customize layout” button, grip-only drag, and clearer instructions/save feedback (when prioritised).
- [ ] **Resize widgets** — Agree to add ability for users and admin to resize dashboard widgets/cards (e.g. Small/Medium/Large).
- [ ] **Resize items on dashboard** — Agree that individual dashboard items can be resized (same as resize widgets; for parent, teacher, backend).
- [ ] **Planned: makeover** — Agree to pursue “Customize layout” button, grip-only drag, and clearer instructions/save feedback (when prioritised).
- [ ] **Deployment** — Branch and “clear cache & deploy” process are correct for your environment.

---

## 6. Where to Find More Detail

| Topic | Doc / location |
|-------|-----------------|
| RBAC dashboard & sidebar | `docs/RBAC_DASHBOARD_VISIBILITY.md` |
| Theme (portal & backend) | `docs/THEME_SYSTEM.md` |
| Drag-and-drop fixes | `docs/DRAG_AND_DROP_FIXES.md` |
| Resizable sidebar | `templates/portal_base.html` (handle, CSS, JS, localStorage) |
| Backend dashboard template | `templates/accounts/backend_dashboard.html` |
| Portal sidebar | `templates/partials/portal_sidebar.html` |
| Footer | `templates/components/dashboard_footer.html` |

---

**Next step:** Review the checklist in §5, tick what you approve, and note any changes or priorities (e.g. “do makeover before widget resize” or “widget resize first”). Then we can align implementation order.
