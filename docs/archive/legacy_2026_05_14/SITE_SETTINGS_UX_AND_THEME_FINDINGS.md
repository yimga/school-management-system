# Site Settings: Dedicated Page/Sidebar & Theme Findings

**Context:** You see Site Settings with (1) the main app sidebar (Dashboard, Site settings, Accounts, People…), (2) an internal vertical nav (At a glance, Branding, Theme & Experience, Finance Automation…), and (3) the Summary/content. You asked whether Site Settings should be its own dedicated page with its own dedicated sidebar, and why the theme looks different.

---

## 1. Should Site Settings be its own dedicated page with its own dedicated sidebar?

**What you have now**

- **Main sidebar (left):** App-level nav — Dashboard, Site settings, Accounts, People Management, etc. "Site settings" is one item.
- **Inside Site Settings:** A second, internal vertical sidebar (Phase 1.2) with sections: At a glance, Branding, Theme & Experience, Finance Automation, etc.

So Site Settings is already a dedicated *page* with its own *internal* sidebar. The open question is whether that internal sidebar should stay *inside* the content area or become *the* main sidebar when you’re on Site Settings.

### Option A – Keep current (two-level)

- Main sidebar always shows: Dashboard, Site settings, Accounts, People, …
- On Site Settings, the content area shows: internal settings sidebar + form.

**Pros:** Same pattern as rest of admin; quick jump to Dashboard/Users without leaving the frame.  
**Cons:** Two sidebars; Site Settings can feel like a subsection.

### Option B – Dedicated “Settings” experience (single main sidebar)

- When you open **Site settings**, the **main** left sidebar is replaced by the Settings sections only (General, Portal & content, Backend, Finance Automation, …).
- No second sidebar; the left rail is “Settings-only” with a way back (e.g. “← Back to admin” or “Dashboard” at the top).

**Pros:** Site Settings feels like its own app; one clear “I’m in Settings” state.  
**Cons:** No one-click access to Dashboard/Users from the left until you go back.

**Recommendation:**  
- **Short term:** Keeping the current two-level design (Option A) is reasonable and matches how many large admin UIs handle a big Settings area.  
- **If you want it to feel “more dedicated”:** We can implement Option B (main sidebar switches to Settings sections when on Site Settings, with a clear “Back to admin” / Dashboard entry at the top). That’s a small UX change in how the main nav is built for this one route.

---

## 2. Why the theme looks different

**What’s going on**

- **Main app sidebar** and **content area** use your admin theme stack:
  - `backend_console_theme` (e.g. dark, black, ink) sets body classes like `portal-backend-dark`, `portal-backend-ink`.
  - CSS like `admin-console-themes.css`, `admin_sidebar_enhanced.css`, `design-tokens.css` set:
    - Sidebar: `--admin-sidebar-bg`, `--admin-sidebar-surface`, etc. (e.g. `#0f172a`, `#000`, `#030712` by theme).
    - Content: `--admin-content-bg`, `--admin-content-surface` (e.g. `#0f172a`, `#1e293b`).
  - `base_site.html` injects `--admin-sidebar-active-border: {{ SITE.primary_color }}` (and related). So when **Primary** in the Summary is **#0c1222**, that deep blue is used for active/highlight in the main sidebar and for brand accents.

- **Internal Site Settings sidebar** (the one we added in Phase 1.2) does **not** use those variables. It uses Unfold/Tailwind utility classes:
  - `bg-base-50 dark:bg-base-800/50`
  - `border-base-200 dark:border-base-700`
  - `hover:bg-base-200 dark:hover:bg-base-700`
  - Active state in `change_form.html`: `rgba(37, 99, 235, 0.12)` (fixed blue), not `SITE.primary_color`.

So you get:

1. **Different surfaces:** Main sidebar and content use theme-driven vars (and possibly #0c1222 as primary); the internal settings panel uses Tailwind `base-*`, which can be a different shade (e.g. different grey/blue) and opacity.
2. **Different accent:** Active/highlight on the main sidebar uses your configured primary (#0c1222 or theme); the internal settings sidebar uses a hardcoded blue for `.settings-nav-link.active`.

That’s why the theme “looks different” on Site Settings: the internal sidebar and its active state are not using the same design tokens as the rest of the admin.

---

## 3. Recommended theme fix

**Goal:** Make the Site Settings *internal* sidebar and its active state match the rest of the admin.

1. **Use admin design tokens for the internal sidebar**
   - In `settings_sidebar.html`, replace Tailwind background/border classes with CSS variables, e.g.:
     - Background: `var(--admin-content-surface)` or `var(--admin-sidebar-surface)` (depending on whether we want it to match content or main sidebar).
     - Border: `var(--admin-content-border)` or `var(--admin-sidebar-border)`.
   - Add a small block in `change_form.html` (or a shared admin CSS file) that defines these for the Site Settings wrapper so the internal nav uses the same palette as the main admin.

2. **Use the same accent for active state**
   - In `change_form.html`, change `.settings-nav-link.active` to use:
     - `background: var(--admin-sidebar-active-bg)` (or a transparent variant),
     - `color: var(--admin-sidebar-active-border)` or `var(--brand-primary)`.
   - That way the “purple-blue” highlight and primary (#0c1222 or whatever is set) are consistent between main sidebar and Site Settings internal nav.

3. **Optional**
   - If the Summary “Primary” is used as a background anywhere (e.g. content area), ensure that’s intentional and documented so the deep blue (#0c1222) doesn’t make the content area look different from other admin pages by accident.

After this, the theme on Site Settings should no longer look different from the rest of the admin; then we can decide whether to move to Option B (dedicated main sidebar for Settings) or keep the current two-level layout.

---

## 4. Next steps (how to proceed)

1. **Theme:** Implement the token-based styling for the Site Settings internal sidebar and active state (steps above). Quick win, no change to information architecture.
2. **Dedicated sidebar (optional):** If you want Site Settings to feel like its own app, we can implement Option B: when the route is Site Settings, render the main sidebar with only Settings sections + “Back to admin”/Dashboard. We can do this after or in parallel with the theme fix.

If you tell me your preference (theme-only first, or theme + Option B together), I can outline the exact template/CSS edits next.

---

## 5. Applied: Theme alignment (internal sidebar)

**Done:** The Site Settings internal sidebar and mobile dropdown now use the same design tokens as the rest of the admin.

- **`templates/admin/siteconfig/sitesettings/settings_sidebar.html`**
  - Removed Tailwind `bg-base-*` / `border-base-*` classes from the nav and mobile elements; added semantic classes (`site-settings-sidebar-nav`, `settings-nav-group-label`, `site-settings-mobile-trigger`, `site-settings-mobile-dropdown`, `site-settings-mobile-link`) so styling is driven by CSS variables.

- **`templates/admin/siteconfig/sitesettings/change_form.html`**
  - Added scoped CSS that sets:
    - **Desktop nav:** `background: var(--admin-content-surface)`, `border-color: var(--admin-content-border)`, `color: var(--admin-content-text)`; group labels use `--admin-content-text-muted`; links use `--admin-content-text`, hover uses `--admin-sidebar-hover-bg`, active uses `--admin-sidebar-active-bg`, `color: var(--admin-sidebar-active-border)` and a 2px left border with `--admin-sidebar-active-border` (which comes from `SITE.primary_color` in `base_site.html`).
    - **Mobile trigger and dropdown:** Same tokens (`--admin-content-surface`, `--admin-content-border`, `--admin-content-text`, `--admin-sidebar-hover-bg`, `--admin-content-text-muted` for labels).

Result: The internal Settings panel matches the main admin sidebar and content area in both light and dark themes, and the active section uses your configured primary/accent (e.g. #0c1222) consistently.
