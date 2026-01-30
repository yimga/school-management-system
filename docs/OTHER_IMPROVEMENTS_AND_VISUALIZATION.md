# Other Improvements & Data Visualization Styles

## Other improvements to be aware of

1. **Performance**
   - Lazy-load widget content (e.g. iframe or fetch) for below-the-fold widgets.
   - Virtualize long lists in list/feed widgets.
   - Cache layout and widget metadata in session or short-lived cache for repeat visits.

2. **Accessibility**
   - Full keyboard reorder (arrow keys + Enter to move focused widget up/down).
   - Screen reader announcements when layout is saved or reset.
   - Reduce motion: respect `prefers-reduced-motion` for drag animation and toasts.

3. **RBAC & security**
   - Audit log for layout changes (who reset, who reordered) — already partially in place via `_log_layout_audit`.
   - Per-page rate limit on layout PUT/DELETE to avoid abuse.

4. **UX**
   - “Restore previous layout” (one more level beyond undo) from a small history.
   - Copy layout from another role or page (e.g. “Use same layout as Backend”).
   - Dashboard presets: “Minimal”, “Focus on finance”, “Full” — apply a named preset.

5. **Mobile**
   - Bottom sheet for “Customize layout” on small screens instead of full-page instructions.
   - Swipe to reorder in list mode on touch devices.

6. **Admin**
   - Site-wide default layouts per role/page (already supported via `DashboardLayout` with `is_default=True`).
   - Preview how a role’s default layout looks before publishing.

### Other improvements you can do next

- **Chart.js view switching:** On pages that use Chart.js (e.g. compliance dashboard), add a small script that reads `data-widget-display-style` on the widget root and calls `chart.config.type = 'bar'|'line'|'pie'` (and `chart.update()`) so chart type follows the View dropdown.
- **Widget catalog alignment:** Ensure backend/parent/teacher dashboard cards that should support View have a matching `DashboardWidget` record (page + id) so the API returns `allowed_display_styles` and the View dropdown appears.
- **Reduce motion:** In `dashboard-layout-controls.css`, add `@media (prefers-reduced-motion: reduce) { .sortable-ghost, .sortable-drag { transition: none; } }` and tone down toast animation.
- **Keyboard reorder:** In edit mode, when the grip is focused, allow Arrow Up/Down to move the widget within the column and trigger `saveLayout()`.

---

## Data visualization styles (user choice per widget)

### What exists today

- **Size:** Small / Medium / Large (per widget, in ⋮ menu).
- **Style (variant):** Default / Compact / Flat (card look; per widget, in ⋮ menu).

Both are stored in the layout API and applied via `data-widget-size` and `data-widget-variant`. Widget templates and CSS can react to these (e.g. `.widget-variant-compact`).

### What “visualization style” adds

A per-widget **display style** so the user can choose **how** the widget’s data is shown:

| Widget type | Option name   | Allowed values (examples)     | Effect |
|-------------|---------------|--------------------------------|--------|
| Chart       | Chart type    | Bar, Line, Pie, Area, Doughnut | How the chart is drawn. |
| List / feed | Display as    | Card, List, Table, Compact     | Layout of items (cards vs rows vs table). |
| Stats       | Display as    | Card, Minimal, Inline          | Emphasis and density. |

- Stored in the same layout payload as `size` and `variant`, e.g. `display_style: "bar"` or `display_style: "list"`.
- Shown in the same ⋮ menu when the widget supports it (e.g. “Display” or “View” dropdown).
- Widget markup/CSS/JS can switch behavior using `data-widget-display-style` (or a class derived from it).

### Implementation status (done)

- **API:** Layout items accept and return optional `display_style`. GET response includes `allowed_display_styles` and `default_display_style` per widget (derived from `widget_type`). GET enriches layout items with `default_display_style` when missing so saved layouts stay compatible.
- **Frontend:** `collectLayout()` includes `display_style` from each widget’s `data-widget-display-style`. `applyPresentation()` sets size, variant, and display_style from layout/item/meta. The ⋮ menu has an optional **View** dropdown when the widget has `allowed_display_styles`; value is persisted with the layout and applied as `data-widget-display-style`.
- **CSS (visualization wired to widgets):** `dashboard-layout-controls.css` applies view-specific styles based on `[data-widget-display-style="…"]`:
  - **list** — Vertical list layout, left border accent, bar groups as rows.
  - **table** — Grid/table layout for `.insight-card`, `.subject-list` as key–value rows.
  - **compact** — Reduced padding and font size.
  - **line** / **area** — Chart-style hints (bar top edge, opacity) for `.insight-bar-row`.
  - **minimal** — Less chrome, hide meta/notes.
  - **inline** — Inline-flex content in card body.
- **Templates:** Any widget that uses `.insight-card`, `.insight-bar-row`, `.trend-pill`, `.subject-list`, or similar classes will respond to the View dropdown without template changes. For Chart.js or custom chart widgets, add JS that reads `data-widget-display-style` and re-renders (e.g. bar vs line vs pie).

Users can choose **Size**, **Style** (variant), and **View** (display style) per widget in the ⋮ menu; all are saved with the dashboard layout.
