# Backend Dashboard Investigation

## 1. Layout Script and Missing Content

### What the layout script does
- **File:** `static/js/dashboard-layout.js`
- **Purpose:** Loads saved dashboard layouts from the API, applies widget order/position, and enables drag-and-drop customization for teacher/parent dashboards.

### Backend-specific behavior
At line ~415, the script has:
```javascript
if (page === 'backend') return;
```
So for the backend dashboard, the script **exits early** and does NOT:
- Fetch saved layout from the API
- Apply/reorder widgets
- Move DOM elements

The backend content (Quick Actions, Analytics filters, Finance trend, etc.) is **all in the HTML template** and is **not** loaded or manipulated by the layout script. Nothing was deleted or hidden by the script.

### Why content might appear missing
If the main area looks empty, possible causes:
1. **CSS/layout** – Float layout (aside right, main left) or overflow rules could push content off-screen or collapse it
2. **Viewport** – Content may be below the fold; scrolling down might reveal it
3. **Conditional rendering** – Some cards depend on `action_perms`, `gce_enabled`, or other context; they won’t show if those are empty/false

### Template structure
- `#dashboard-layout` contains: Quick Actions, Analytics filters, Finance trend, Attendance snapshot, Portal insights, Pending referrals, Grade imports, Certification overview, RBAC snapshot, Permissions overview, Entity management, Entity orchestrator
- All of these are defined in `templates/accounts/backend_dashboard.html` (lines ~840–1290)

---

## 2. Top-right shadow

### Likely cause
The **Admin Nav Bridge** (`admin_nav_bridge.html`) uses:
```css
background: linear-gradient(115deg, #ff6a88 0%, #9b6bff 55%, #172554 100%);
```
At 100%, the gradient ends in `#172554` (dark blue). With `position: sticky` and full width, the right side of this bar is a strong dark blue. That creates a vertical band at the top right that can look like a shadow or a second panel/dashboard tucked behind.

### Other observations
- **Nav bridge gradient** – Pink → purple → dark blue can produce a sharp edge on the right
- **Box shadow** – `box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15)` adds depth and can enhance the “shadow” effect
- **Sidebar overlap** – The right sidebar (clock, Copilot) may sit next to or under this dark edge, adding to the illusion of hidden content

---

## 3. Fixes applied

1. **Clock/calendar alignment** – Moved down (~4.5rem) so the top lines up with the Workflow Center row
2. **Calendar layout** – Switched to a 7-column grid so weekday labels align with dates
3. **Chat head / AI copilot spacing** – Set to 1 inch apart on all dashboards
4. **Dashboard visibility** – `#dashboard-layout` given `display: block`, `min-height: 200px`, and `overflow: visible` to avoid hidden or collapsed content
