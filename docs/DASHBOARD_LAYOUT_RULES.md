# Dashboard layout rules

Short reference for backend (and shared) dashboard layout and containment so cards, metrics, and sections auto-adjust as data grows with no spillage.

## Scope

- **Backend dashboard** (`accounts/backend_dashboard.html`): primary target. Body has `data-dashboard-page="backend"` (set in template + portal_base JS).
- **Teacher / parent dashboards**: use `dashboard-page-teacher` / `dashboard-page-parent` on body; same containment ideas can be applied via shared classes or `[data-dashboard-page]` when set on ancestor.

## Principles

1. **No redundancy**  
   One place for KPIs (Overview), one for Operations Watch + Quick Links (horizontal strip), one for calendar/time (right rail). No duplicate nav bridge row; Portal Home and Configuration Engine live in the main header only.

2. **Containment (no spillage)**  
   - Grid/flex children and card bodies: `min-width: 0`, `overflow: hidden` (or `overflow: auto` for scrollable list/chart areas).  
   - Card titles and key text: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` (or `line-clamp` for multi-line).  
   - Chip and action labels: same ellipsis so long text doesn’t push layout.

3. **Compact empty states**  
   Cards with “No data to display” or a single empty-list message use reduced padding and `min-height: 0` so they don’t create large vertical gaps (see `dashboard-layout-controls.css`).

4. **Flow**  
   Header → Overview → Operations Watch + Quick Links (horizontal) → Welcome → main workspace grid → right rail (calendar/time only).

## Files

- **Layout / containment CSS:** `static/css/dashboard-layout-controls.css` (containment, ellipsis, compact empty states).  
- **Backend dashboard styling:** `static/css/backend-dashboard-v2.css` (grid, welcome block, ops-quick row, chips, actions).  
- **Templates:** `templates/accounts/backend_dashboard.html` (no `admin_nav_bridge`; Ops Watch + Quick Links in horizontal row; rail = calendar only).

## Adding new dashboard cards

- Use shared card class (e.g. `.backend-v2-panel`) and ensure card body has `min-width: 0` and `overflow: hidden` (or `overflow: auto` for scrollable content).  
- Reserve right padding for widget gear if the card has a settings control.  
- For empty state, use a single `.small.text-muted` block so compact empty-state rules apply.
