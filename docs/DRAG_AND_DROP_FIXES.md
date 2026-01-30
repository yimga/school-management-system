# Drag-and-Drop Dashboard Improvements

## Issues Fixed

### 1. Missing Column Containers
**Problem**: `dashboard-layout.js` required explicit `[data-dashboard-column]` containers, but many widgets were directly inside `#dashboard-layout`.

**Solution**: Modified `initDragDrop()` to:
- Detect explicit column containers first
- Fall back to treating `#dashboard-layout` as a single column if none exist
- Auto-assign `data-dashboard-column="main"` to the root container

### 2. Toggle Button Mismatch
**Problem**: `dashboard-layout.js` looked for `toggleLayoutDrag` but templates use `toggleCustomize`.

**Solution**: Updated to check for both button IDs:
```javascript
const dragToggle = document.getElementById('toggleLayoutDrag') || document.getElementById('toggleCustomize');
```

### 3. Page Detection
**Problem**: Page name wasn't always set correctly, causing drag-and-drop to fail silently.

**Solution**: Enhanced page detection:
- First checks `document.body.dataset.dashboardPage`
- Falls back to URL path analysis (`/parent/`, `/teacher/`, `/backend/`, etc.)
- Defaults to `'backend'` if nothing matches

### 4. Auto-Enable Logic
**Problem**: Drag-and-drop only enabled if toggle was checked, but users expected it to work automatically.

**Solution**: 
- Auto-enables if `data-custom-drag-enabled="true"` is set (even without toggle)
- Respects toggle state if toggle exists
- Adds small delays to ensure DOM is ready

### 5. Script Conflicts
**Problem**: Both `dashboard-layout.js` (Sortable.js) and `dashboard-customizer.js` (native HTML5) could conflict.

**Solution**: 
- `dashboard-customizer.js` now checks if Sortable.js is active before enabling native drag
- Prevents double-enabling

### 6. Visual Feedback
**Problem**: No clear visual indication when drag mode is active.

**Solution**: Added CSS for:
- `sortable-ghost`: Semi-transparent placeholder while dragging
- `sortable-chosen`: Highlighted widget being dragged
- `sortable-drag`: Opacity adjustment during drag
- Hover effects in drag mode
- Mobile touch support

## Testing Checklist

- [ ] Teacher dashboard (`/portal/teacher/`): Toggle "Drag & drop layout" → widgets should be draggable
- [ ] Parent dashboard (`/portal/parent/`): Toggle "Drag & drop layout" → widgets should be draggable  
- [ ] Backend dashboard (`/backend/`): Toggle "Drag & drop layout" → widgets should be draggable
- [ ] Mobile: Test touch drag on phone/tablet
- [ ] Persistence: Drag a widget, refresh page → position should be saved
- [ ] Console: Check browser console for any errors

## Files Modified

1. `static/js/dashboard-layout.js`
   - Enhanced column detection (fallback to root container)
   - Improved page detection (URL-based fallback)
   - Better toggle button detection (`toggleCustomize` support)
   - Auto-enable logic based on `data-custom-drag-enabled`
   - Better error handling and console logging

2. `static/css/dashboard-layout-controls.css`
   - Added Sortable.js drag state styles (ghost, chosen, drag)
   - Added hover effects in drag mode
   - Mobile touch support

3. `static/js/dashboard-customizer.js`
   - Added check to avoid conflicts with Sortable.js

## How It Works Now

1. **Initialization**: 
   - `dashboard-layout.js` loads Sortable.js from CDN
   - Detects page name from body dataset or URL
   - Finds column containers (or uses root as single column)

2. **Enable Drag**:
   - Checks if `toggleCustomize` is checked
   - If no toggle, checks `data-custom-drag-enabled="true"`
   - Creates Sortable instances for each column
   - Adds `drag-mode` class for visual feedback

3. **Saving**:
   - On drag end, collects widget positions
   - Sends to `/api/dashboard/layout/{page}/` via PUT
   - Backend saves to `DashboardLayout` model

4. **Loading**:
   - On page load, fetches saved layout
   - Applies widget positions and sizes/variants
   - Restores user's custom arrangement

## Sidebar entry (Customize layout)

**Added:** A "Dashboard layout" section in the **left sidebar** (portal sidebar) so users can open customize mode without scrolling to the main content.

- **Where:** In `portal_sidebar.html`, above "Settings", a section **Dashboard layout** with a button **Customize layout**.
- **When visible:** Only on dashboard pages that support custom layout (backend, parent, teacher). Views pass `show_layout_customize_in_sidebar = True` when `allow_custom_layout` is True.
- **Behavior:** Clicking the sidebar button has the same effect as clicking the "Customize layout" button above the dashboard (toggles edit mode; grip-only drag and ⋮ menu for size).
- **JS:** `dashboard-layout.js` wires `#sidebar-customize-layout-trigger` to trigger the same toggle as `#btnCustomizeLayout`.

## Implemented improvements

1. **Reset to default** — In edit mode, a "Reset to default layout" control that restores the role’s default order and sizes (API + UI).
2. **One-level undo** — After a reorder or size change, show "Undo" briefly and allow reverting the last action.
3. **Column labels in edit mode** — When there are multiple columns, show labels (e.g. "Main", "Side") so users know where they’re dropping.
4. **Mobile list reorder** — On small screens, optional list-style reorder (e.g. up/down) instead of drag if touch drag is awkward.
5. **First-time hint** — One-time tooltip or short message on first visit: "You can reorder and resize cards from the sidebar or the Customize layout button."
6. **Loading states** — Skeleton or spinner when layout is loading; disable drag until layout is applied.
7. **Keyboard accessibility** — In edit mode, focus management and keyboard reorder (e.g. arrow keys + Enter to move).
8. **Drag-to-resize (optional)** — Resize handles on card edges in edit mode for pixel-level width/height (more work; current Small/Medium/Large is enough for most users).
9. **Dashboard settings in sidebar** — Move tile density, show sidebar, shortcuts, and custom links into a collapsible "Dashboard settings" block in the sidebar so all layout/config is in one place.

## Troubleshooting

If drag-and-drop still doesn't work:

1. **Check browser console** for errors
2. **Verify Sortable.js loaded**: `console.log(window.Sortable)`
3. **Check page detection**: `console.log(document.body.dataset.dashboardPage)`
4. **Verify widgets have `data-widget-id`**: Inspect DOM
5. **Check toggle state**: Inspect `toggleCustomize` checkbox
6. **Network tab**: Check if `/api/dashboard/layout/{page}/` requests succeed
