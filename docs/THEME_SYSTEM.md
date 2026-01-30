# Theme System

How themes work across the School Management System (portal, backend, and admin).

## Overview

- **Portal (parent/teacher):** Uses `data-bs-theme` on `<html>` (values: `light`, `dark`). Set by user toggle; stored in `localStorage` as `theme`.
- **Backend dashboard:** Uses `data-backend-theme` on `<body>` (values: `light`, `dark`). Set by **Site Settings → Backend console theme** (light / dark / system) and can be overridden per session via the **theme toggle** in the topbar; override stored in `localStorage` as `backendTheme`.
- **Admin (Django):** Can use its own theme controls; see admin base templates.

## Backend theme

### Where it’s set

1. **Site Settings**  
   `SITE.backend_console_theme` (or default `dark`): `light`, `dark`, or `system`.  
   - `system`: follows OS `prefers-color-scheme` (dark → dark, light → light).

2. **Topbar toggle (backend only)**  
   Button in the topbar (sun/moon icon) toggles between light and dark.  
   Choice is stored in `localStorage.backendTheme` and wins over Site Settings for that browser until cleared.

### How it’s applied

- **Templates:** `templates/backend_base.html`  
  - Injects a script that sets `data-backend-theme` on `<body>` and adds class `portal-backend`.  
  - Reads `SITE.backend_console_theme` and `localStorage.backendTheme` (and `prefers-color-scheme` when theme is `system`).

- **CSS:** `static/css/backend-visibility.css`  
  - **Dark:** All dark rules are scoped to  
    `body.portal-backend:not([data-backend-theme="light"])`  
    so they apply when theme is `dark` or when the attribute is missing.
  - **Light:** All light rules are scoped to  
    `body.portal-backend[data-backend-theme="light"]`  
    (backgrounds `#f8fafc` / `#ffffff`, dark text, high-contrast buttons).

### Colors (summary)

| Context   | Dark theme              | Light theme        |
|----------|--------------------------|--------------------|
| Body     | `#0f172a`                | `#f8fafc`          |
| Cards    | `#1e293b`                | `#ffffff`          |
| Sidebar  | `#0f172a`                | `#f1f5f9`          |
| Topbar   | gradient `#1e293b`→`#334155` | gradient `#f1f5f9`→`#e2e8f0` |
| Text     | `#e2e8f0` / `#94a3b8`    | `#0f172a` / `#64748b` |

Design tokens (e.g. in `static/css/design-tokens.css`) can extend these for reuse.

## Portal theme (parent/teacher)

- **Toggle:** In portal topbar; toggles `data-bs-theme` on `<html>` between `light` and `dark`.
- **CSS:** `static/css/portal-theme-modes.css` targets `html[data-bs-theme="dark"]` (and equivalent) for colors and contrast.

## Adding or changing theme colors

1. **Backend:** Edit `static/css/backend-visibility.css`.  
   - Dark: change rules under `body.portal-backend:not([data-backend-theme="light"])`.  
   - Light: change rules under `body.portal-backend[data-backend-theme="light"]`.

2. **Shared tokens:** Add or update variables in `static/css/design-tokens.css` and reference them in the theme files above.

3. **New theme value:** If you add a third backend theme (e.g. `high-contrast`), add a new block in `backend_base.html` to set `data-backend-theme` and a matching block in `backend-visibility.css` with the new colors.

## Design tokens

Backend theme colors are also defined in `static/css/design-tokens.css` for reuse:

- `--backend-body-dark`, `--backend-card-dark`, `--backend-input-dark`
- `--backend-body-light`, `--backend-card-light`, `--backend-sidebar-light`
- `--backend-text-dark`, `--backend-text-light`, `--backend-muted-light`

You can reference these in `backend-visibility.css` (e.g. `background: var(--backend-body-dark)`) to keep colors in one place.
