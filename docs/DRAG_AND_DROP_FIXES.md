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

## Troubleshooting

If drag-and-drop still doesn't work:

1. **Check browser console** for errors
2. **Verify Sortable.js loaded**: `console.log(window.Sortable)`
3. **Check page detection**: `console.log(document.body.dataset.dashboardPage)`
4. **Verify widgets have `data-widget-id`**: Inspect DOM
5. **Check toggle state**: Inspect `toggleCustomize` checkbox
6. **Network tab**: Check if `/api/dashboard/layout/{page}/` requests succeed
