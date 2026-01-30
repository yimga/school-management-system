# Dashboard Drag-and-Drop: Complete Makeover Plan

This document outlines **what’s wrong today** and **options for a simpler, easier drag-and-drop** for admin, parent, and teacher dashboards.

---

## 1. What Exists Today (and Why It’s Confusing)

### Current flow
- **Toggle:** A checkbox “Drag & drop layout” lives in a **customize card** with many other options (Show quick links, Tile density, Sidebar shortcuts, Manage links). Users must turn this on before anything is draggable.
- **Handle:** The **entire widget card** is the drag handle (`handle: '[data-widget-id]'`). Clicking anywhere on a card can start a drag, which conflicts with links, buttons, and inputs inside the card (filter tries to exclude those but the affordance is still “whole card”).
- **No grip:** When “Drag & drop layout” is on, there is **no visible drag handle** (e.g. grip icon). Users don’t know what to grab.
- **Two scripts:** `dashboard-layout.js` (Sortable.js) does the actual reorder; `dashboard-customizer.js` handles the toggle and other settings. Behavior is split and not obvious.
- **Persistence:** Layout is saved via `PUT /api/dashboard/layout/{page}/`. Backend uses `DashboardLayout` per user/role. Parent and teacher templates set `data-custom-drag-enabled="true"`, but docs say “teacher and parent see a fixed layout” – so behavior can feel inconsistent.
- **Extra UI in “customize”:** Each widget gets a **⋯ (gear)** that opens Size/Style. That adds more controls and cognitive load when the main ask is “reorder cards.”

### Resulting pain
1. **Discoverability:** Users don’t know they must enable “Drag & drop layout” first.
2. **Affordance:** No clear “grip” – unclear what to drag.
3. **Accidental drags:** Clicking a link/button inside a card can still initiate drag (or feel broken).
4. **Too many options:** One block mixes: drag, sidebar, tile density, shortcuts, custom links – overwhelming.
5. **No feedback:** Unclear that the layout was saved (no “Saved” or toast).
6. **Role confusion:** Unclear whether parent/teacher can reorder and whether it’s saved the same way as admin.

---

## 2. Options for a Simpler System

### Option A: Simplify the current drag-and-drop (evolution)

**Idea:** Keep Sortable.js and the API, but make the flow obvious and safe.

| Change | Description |
|--------|-------------|
| **Single “Customize dashboard” entry** | One clear action: “Customize dashboard” (button or switch). When ON: show a short message (“Drag cards to reorder. Use the grip on the left to drag.”) and **only** reorder-related UI. Move “Tile density”, “Sidebar shortcuts”, “Manage links” to a separate “Dashboard settings” or “Preferences” area so “Customize” = reorder only. |
| **Visible drag handle** | Add a **grip icon** (e.g. `⋮⋮` or `⠿`) on the **left edge** of each card, only in customize mode. In Sortable, set `handle: '.dashboard-card-grip'` so **only the grip** starts a drag. Clicks on the rest of the card (links, buttons) do not drag. |
| **Save feedback** | After a successful PUT, show a small toast or inline text: “Layout saved.” (and optionally “Revert” to reset to default). |
| **Same behavior for admin, parent, teacher** | If parent/teacher are allowed to customize layout, use the same API and the same UI (one toggle, one grip, one message). If not, hide “Customize dashboard” for those roles and keep a fixed layout. |

**Pros:** Reuses existing API and scripts; minimal backend change.  
**Cons:** Still two scripts; column logic and “main” fallback stay as-is.

---

### Option B: Dedicated “Customize layout” mode (clear separation)

**Idea:** Treat customization as a **separate mode** (like “Edit layout” or “Arrange widgets”), not a checkbox buried in other options.

| Change | Description |
|--------|-------------|
| **One button: “Arrange widgets”** | In the dashboard header or top of the page: a single button “Arrange widgets” (or “Customize layout”). Clicking it **enters** customize mode: URL could stay the same, or add `?layout=edit`. |
| **Mode-specific UI** | In this mode: (1) Dim or overlay the rest of the page slightly. (2) Show a bar: “Drag cards to reorder. [Done] [Reset to default].” (3) Each card shows **only a left-edge grip** for dragging; no gear menu unless you add it in a second phase. (4) “Done” saves and exits; “Reset” restores default order and exits. |
| **No toggle mixed with other options** | Remove “Drag & drop layout” from the card that has sidebar/tile density/links. Customize = only this “Arrange widgets” flow. |

**Pros:** Very clear mental model (“I’m now arranging” vs “I’m using the dashboard”).  
**Cons:** Requires a small “mode” state and possibly one extra endpoint for “default layout” (e.g. GET default, POST reset).

---

### Option C: Reorder via a simple list (no drag on the dashboard)

**Idea:** Users don’t drag cards on the dashboard itself. They open a **“Widget order”** screen (or modal) and reorder a **list** of widget names (e.g. up/down buttons or a single drag list).

| Change | Description |
|--------|-------------|
| **“Widget order” / “Customize dashboard”** | One link or button that opens a dedicated page (or modal): “Drag or use arrows to set the order of widgets on your dashboard.” |
| **List UI** | One column list: “Quick Actions”, “Attendance”, “Recent activity”, … with **up/down** buttons and/or drag handle per row. No columns; order = top to bottom (or you define “column” as “left block” / “right block” with two lists if you need it later). |
| **Apply** | “Save” writes order (and optionally column) to the same API (`layout.items`). Dashboard template renders widgets in that order. |

**Pros:** No accidental drags; works on touch; simple to explain (“Change order in this list”).  
**Cons:** User doesn’t see the actual dashboard while reordering (unless you show a preview).

---

### Option D: Remove drag for parent/teacher; keep only for admin

**Idea:** Only **admin/backend** dashboard is customizable. Parent and teacher get a **fixed, sensible default order** (no toggle, no drag, no “Customize dashboard”).

| Change | Description |
|--------|-------------|
| **Backend (admin)** | Keep or simplify drag-and-drop as in Option A or B: one clear “Customize layout” or “Arrange widgets”, grip handle, save feedback. |
| **Parent & teacher** | Remove “Drag & drop layout” toggle and any drag script from parent/teacher dashboard. Remove `data-custom-drag-enabled` and layout API usage for those pages (or keep API but never show the UI). Order comes only from server-side default (e.g. `DashboardWidget.order` or a fixed template order). |

**Pros:** Easiest for parents and teachers (“it just works”); less to support.  
**Cons:** Parents/teachers can’t personalize widget order.

---

## 3. Recommended Direction: Hybrid (A + B + D)

A practical path that gives a **complete makeover** and **much simpler** experience:

### Phase 1: One clear action, grip handle, save feedback (Option A + B ideas)

1. **Single entry point**
   - **Admin/backend:** One control: “Customize layout” (or “Arrange widgets”) as a **button** in the dashboard header or just above the widget area. Click = “edit layout” mode. No “Drag & drop layout” checkbox mixed with sidebar/links.
   - **Parent/teacher (if you keep customization):** Same one button: “Customize layout.” If you decide to remove customization for them (Option D), skip this for those roles.

2. **Grip handle only**
   - In customize mode, each widget card gets a **visible grip** (e.g. `⋮⋮` or icon) on the **left** (or top-left). Sortable `handle` = that grip only. No drag when clicking elsewhere on the card.

3. **Short instruction + feedback**
   - When customize is on: one line of text: “Drag cards by the grip to reorder. Your layout is saved automatically.”
   - After save: “Layout saved” (toast or inline, 2–3 seconds).

4. **Separate “Dashboard settings”**
   - Move “Show quick links”, “Tile density”, “Sidebar shortcuts”, “Manage links” out of the “Customize layout” flow. Put them under “Dashboard settings” or “Preferences” so “Customize layout” = **only** reorder (and optionally size/variant later).

### Phase 2: Optional “Arrange widgets” mode (Option B)

- “Customize layout” could **enter a mode**: toolbar “Done” / “Reset to default”, grip-only drag, then “Done” saves and exits. This makes it even clearer that the user is “editing layout” and not using the dashboard.

### Phase 3: Role decision (Option D)

- **Decide:** Do parent and teacher get layout customization?
  - **If no:** Remove toggle and drag from parent/teacher dashboards; fix their default order in the backend; document “only admin/backend can customize layout.”
  - **If yes:** Use the **same** one-button + grip + feedback flow and the same API so behavior is identical everywhere.

---

## 4. Implementation Checklist (Phase 1)

Use this as a concrete list for the makeover:

- [ ] **Backend / parent / teacher templates**
  - [ ] Remove “Drag & drop layout” checkbox from the card that also has sidebar/tile density/links.
  - [ ] Add one “Customize layout” or “Arrange widgets” button (or switch) that turns “layout edit” on/off.
  - [ ] When “layout edit” is on, show one short sentence: “Drag cards by the grip to reorder. Layout saves automatically.”

- [ ] **Widget cards**
  - [ ] In layout-edit mode, inject a **grip element** (e.g. `<span class="dashboard-card-grip" aria-label="Drag to reorder">⋮⋮</span>`) on the left of each `[data-widget-id]` card. Hide grip when not in layout edit mode.
  - [ ] Ensure grip is the only draggable area (Sortable `handle: '.dashboard-card-grip'`).

- [ ] **dashboard-layout.js**
  - [ ] Use grip as handle: `handle: '.dashboard-card-grip'` (fallback to `[data-widget-id]` only if no grip found).
  - [ ] After successful PUT, show “Layout saved” (toast or inline).
  - [ ] Enable/disable Sortable based on “layout edit” state (your new button/switch), not the old “Drag & drop layout” checkbox.

- [ ] **dashboard-customizer.js**
  - [ ] Stop toggling “drag mode” from the old checkbox. Either remove that toggle or wire it to the new “Customize layout” button so that “Customize layout” = drag mode on + show grip + show instruction.
  - [ ] Move sidebar/tile density/custom links into a separate “Dashboard settings” section (or leave as-is but clearly separate from “Customize layout”).

- [ ] **API**
  - [ ] No change required if payload stays `{ layout: { items: [ ... ] } }`. Optionally add a “Reset to default” that GETs default layout and PUTs it.

- [ ] **Parent/teacher**
  - [ ] Decide: keep or remove layout customization for them. If remove: hide “Customize layout” and any layout API call for parent/teacher; fix default order in backend/templates.

- [ ] **Docs**
  - [ ] Update user-facing help: “To reorder widgets: click ‘Customize layout’, then drag cards by the grip on the left. Layout saves automatically.”
  - [ ] In code/KB: document that grip is the only drag handle and that “Customize layout” is the single entry point.

---

## 5. Summary

| Today | After makeover |
|-------|-----------------|
| “Drag & drop layout” checkbox buried with other options | One “Customize layout” (or “Arrange widgets”) action |
| Whole card is drag handle → accidental drags | Only a **grip** on the card starts a drag |
| No visible affordance | Grip icon visible in customize mode |
| No save feedback | “Layout saved” after PUT |
| Unclear for parent/teacher | Decision: same flow for all roles or customization only for admin |
| Reorder + sidebar + density + links in one block | Reorder separated from “Dashboard settings” |

This plan gives you a **complete makeover** and a **much simpler, easier** way to do drag-and-drop for admin (and optionally parent/teacher): one entry point, one clear affordance (grip), automatic save with feedback, and no mixing with unrelated options.

---

## 6. Recommendation

**Recommendation: Hybrid with a clear “edit mode” (Option A + B), and same flow for admin, parent, and teacher.**

- **Why not Option C (list only):** Users don’t see the live dashboard while reordering; drag-on-dashboard with a grip is more intuitive once the grip is obvious.
- **Why not Option D (admin only):** If the flow is simple (one button + grip + “Layout saved”), giving parent and teacher the same “Customize layout” reduces special cases and support (“everyone can reorder the same way”). You can still restrict by role later if needed.
- **Why Hybrid A + B:**  
  - **One button “Customize layout”** (not a checkbox among others) so the action is discoverable.  
  - **Click = enter “edit layout” mode:** show a small toolbar (“Drag cards by the grip to reorder.” + **Done** + **Reset to default**), show grips on cards, and only the grip starts a drag.  
  - **Done** saves (if needed) and exits; **Reset** loads default order, saves, and exits.  
  - Automatic save on each drop is optional; if you prefer explicit save, **Done** is the only save action.  
  This gives the clarity of a “mode” (Option B) without a separate page, and the simplicity of one handle + feedback (Option A).

**Concrete choice:**  
- **Entry:** One button: **“Customize layout”** (or “Arrange widgets”) in the dashboard header or just above the widget area.  
- **Mode:** When on, show a thin bar: instruction + “Done” + “Reset to default”. Only the **grip** on each card is draggable.  
- **Save:** Either save on every drop (with “Layout saved” toast) or only when user clicks **Done**.  
- **Roles:** Use the same UI and API for admin, parent, and teacher so behavior is identical and easy to document.

---

## 7. Additional Improvements to the Recommended Option

These improvements make the recommended option more robust, accessible, and predictable.

| # | Improvement | Description |
|---|-------------|-------------|
| 1 | **Role-aware “Reset to default”** | “Reset to default” restores the **role’s** default order (admin vs parent vs teacher), not a single global default. Backend already has per-page layout; ensure default layout is defined per role/page so reset is predictable. |
| 2 | **One-level Undo** | After a drag, show a short-lived “Layout saved. [Undo]” so users can revert the last change without using “Reset to default.” Store previous layout in memory and restore it on Undo (then optionally PUT that state). |
| 3 | **Column labels in edit mode** | If the dashboard has two columns (e.g. main + sidebar), in customize mode show small labels above each column: “Column 1”, “Column 2” (or “Main”, “Sidebar”). Makes it obvious where a card will drop when dragging between columns. |
| 4 | **Mobile: list reorder fallback** | On viewports below ~768px, “Customize layout” could open a **list** of widget names with up/down buttons (or a single drag list) instead of drag-on-cards, to avoid fiddly drag on touch. Same API (order only); different UI. |
| 5 | **First-time hint (optional)** | First time a user lands on the dashboard (e.g. `localStorage` flag), show a one-time tooltip near “Customize layout”: “You can reorder these cards—click here, then drag by the grip.” Dismiss = set flag, never show again. |
| 6 | **Persistence message** | When layout is saved for the first time (or when you show “Layout saved”), optionally add: “Your layout is saved and will appear on all your devices.” Reduces “did it really save?” anxiety. |
| 7 | **Loading state** | While the layout API (GET) is in progress, show a subtle skeleton or “Loading your layout…” so the page doesn’t jump when the saved order is applied. Especially helpful on slower connections. |
| 8 | **Keyboard / accessibility** | In customize mode, make the grip focusable (Tab). Optional: when focus is on the grip, allow Arrow Up / Arrow Down to move that widget up or down one position (no drag required). Announce moves to screen readers (“Widget X moved to position 2”). |
| 9 | **Defer or hide Size/Style in first release** | Keep the grip and reorder as the only customization in the first release. Hide or remove the per-widget **⋯ (gear)** Size/Style menu until reorder is solid; then reintroduce as “Card size” / “Card style” in a second phase to avoid overwhelming users. |
| 10 | **Same copy everywhere** | Use the same button label (“Customize layout”), same instruction (“Drag cards by the grip to reorder”), and same “Layout saved” / “Reset to default” / “Done” on backend, parent, and teacher dashboards. One set of strings to translate and one mental model for all roles. |
| **11** | **Resize widgets (users and admin)** | In the same “Customize layout” mode, **both users and admin** can resize each dashboard card. **(a) Size selector:** On each card, show a small control (e.g. dropdown or S / M / L chips) to set **Small**, **Medium**, or **Large**. The layout API already supports `size` per item; persist it with the same PUT. **(b) Optional – drag to resize:** Add a **resize handle** (e.g. on the right or bottom edge of the card) that users can drag to change width/height; map the result to a size class (sm/md/lg) or store explicit width. Drag-to-resize is more intuitive but needs min/max and possibly grid alignment. Start with (a) for all roles; add (b) later if desired. |

**Suggested order:** Implement 1 (grip + mode + Done/Reset) and 2 (save feedback) first. Then add **role-aware Reset** (1), **column labels** (3), and **loading state** (7). **Resize widgets** (11) can ship with or right after reorder: same “Customize layout” mode, size selector (S/M/L) for every card for **users and admin**; optional drag-edge resize later. **Undo** (2), **mobile list fallback** (4), **first-time hint** (5), **persistence message** (6), **keyboard** (8), and **defer gear** (9) can follow as polish.

---

## 8. Admin-Only Flexibility (Out of the Box)

The base plan gives **everyone** the same reorder flow (one button, grip, Done/Reset). That keeps parent/teacher simple. To give **admins more flexibility** without complicating other roles, add **admin-only** features on top. Parent/teacher keep: reorder only, one column (or fixed two columns). Admins get extra levers.

| # | Admin-only feature | What it does | Why it helps admins |
|---|--------------------|--------------|----------------------|
| **A1** | **Show/hide widgets (widget picker)** | In customize mode, admins see an **“Add/remove widgets”** or **“Widget catalog”**: a list of all widgets allowed for the backend page (from `DashboardWidget` where `page=backend` and role allowed). Checkboxes or toggle: show Quick Actions, show Finance summary, show Activity log, etc. Parent/teacher see a **fixed set** of cards (no picker). | Admins tailor the dashboard to their role (finance-heavy vs operations vs minimal). Parents/teachers get a curated set. |
| **A2** | **Multiple columns / regions** | Backend dashboard can have **2–3 drop zones** in customize mode: e.g. **Main**, **Sidebar**, **Bottom**. Admins drag cards between zones; order within each zone is saved. Parent/teacher have **one column** (or a fixed two-column layout with no zone choice). | Admins decide what’s “main” vs “sidebar” vs “below the fold.” Others get a single stream or fixed layout. |
| **A3** | **Extra resize options (admin)** | **Everyone** gets resize (Small / Medium / Large) in customize mode (see Section 7, improvement 11). **Admins only** can get *additional* options: e.g. **Full width** (span all columns), or **drag-edge resize** (drag the card edge to set custom width), or more size steps (e.g. 1/2/3 grid width). Parent/teacher keep S/M/L only. | Admins get finer control (full-width, drag to resize); users get standard S/M/L. |
| **A4** | **Layout presets / templates** | Admins can **save** the current layout as a named preset (e.g. “Finance focus”, “Minimal”, “Full”) and **switch** between presets from a dropdown. Optionally **load** a preset as the new layout. Parent/teacher have one saved layout (no presets). | Admins switch context (e.g. start of term vs reporting) without re-dragging every time. |
| **A5** | **Set default layout for other roles** | Admins have an option: **“Set as default for Parents”** / **“Set as default for Teachers”**. So the admin’s current backend layout doesn’t change, but they can **define the default** that new parents/teachers see (or that “Reset to default” uses for that role). Stored as `DashboardLayout` with `user=None`, `role=PARENT`/`TEACHER`, `is_default=True`. | Admins control the “out of the box” experience for parents and teachers; those users can still personalize from that default. |
| **A6** | **Full-width / spanning widgets** | Backend allows some widgets to be **full width** (span all columns) in customize mode. Admins choose “Full width” from the gear or a dropdown on the card. Parent/teacher always single column, so no spanning. | Admins can highlight one big widget (e.g. key metrics) without giving everyone a complex layout. |
| **A7** | **Dashboard “views” or tabs** | Admins get **multiple named views** of the backend dashboard (e.g. “Operations”, “Finance”, “People”). Each view has its own layout (order + visibility + size). A tab or dropdown at the top switches the view. Parent/teacher have a single view. | One login, several “dashboards” for different tasks; no reordering when switching. |
| **A8** | **Widget catalog with “Add to dashboard”** | In customize mode, admins see an **“Add widget”** button that opens a **catalog** of available backend widgets (from `DashboardWidget`). Click to add a widget to the bottom (or to a chosen column). Remove via a small ✕ on the card in edit mode. Parent/teacher only reorder existing cards (no add/remove). | Admins grow or shrink the dashboard to match their workflow; others get a fixed, stable set. |

### How to implement without breaking “same flow” for basics

- **Same base for everyone:** One “Customize layout” button, grip, Done, Reset. Reorder is the same for admin, parent, teacher.
- **Admin extras are additive:**  
  - **If admin:** In customize mode, show **in addition**: “Add/remove widgets” (A1), column labels and multiple drop zones (A2), per-card size (A3), “Save as preset” / “Load preset” (A4), optional “Set as default for Parents/Teachers” (A5), full-width option (A6), or views/tabs (A7).  
  - **If parent/teacher:** In customize mode, show only: instruction, grip, Done, Reset. No picker, no presets, no “set default for others,” no size control, single column (or fixed two-column with no zone editing).
- **API:** Same `GET/PUT /api/dashboard/layout/{page}/` for all. Payload can include optional fields: `visible_widget_ids` (admin), `preset_name` (admin), `column` (admin when multi-column), `size` (admin). Backend validates role and only reads/writes these when the user is admin (or allowed role).
- **RBAC:** Gate admin-only features by existing “can customize” logic (e.g. `_can_customize(user)` or `user.is_staff` / role in ADMIN, LEADERSHIP, IT_ADMIN). Parent/teacher never receive the admin-only UI or options.

### Suggested order for admin flexibility

1. **Phase 1 (same for all):** Grip, mode, Done, Reset, save feedback, role-aware Reset.  
2. **Phase 2 (admin flexibility):**  
   - **A1** (show/hide widgets) and **A8** (add from catalog) – biggest impact: admins choose which cards exist.  
   - **A2** (multiple columns/regions) – if backend dashboard already has or can have two columns.  
   - **A3** (per-widget size, admin only) – bring back the gear for admins only.  
3. **Phase 3 (optional):** **A4** (presets), **A5** (set default for parents/teachers), **A6** (full-width), **A7** (multiple views/tabs).

This way the **base experience** stays one simple flow for everyone, while **admins get meaningfully more flexibility** (choose widgets, columns, size, presets, defaults for others) without cluttering parent/teacher screens.
