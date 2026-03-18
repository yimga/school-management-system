# Glass surface design recipe (marketing + product)

**Purpose:** One visual language from marketing → login → dashboard.  
**CSS:** `static/css/glass-surface-recipe.css`  
**Loaded on:** `templates/marketing/base_marketing.html`, `templates/portal_base.html`, `templates/backend_base.html`. **Studio OS rail** uses the same tokens in `templates/studio_os/partials/shell_extrastyle.html` (`.studio-os__rail`).

## Variables

| Token | Light (tenant) | Dark / backend | Marketing (dark hero) |
|-------|----------------|----------------|------------------------|
| `--rmc-glass-blur` | 14px | 14px | 14px |
| `--rmc-glass-bg` | ~78% white | ~72% slate | ~12% white on dark |
| `--rmc-glass-border` | soft white | slate outline | white 20% |
| `--rmc-glass-shadow` | slate tint | deeper | dark lift |

## Utility classes

- **`.rmc-glass-surface`** — cards, panels, modals.
- **`.rmc-glass-surface--strong`** — elevated surfaces.
- **`.rmc-glass-sidebar-shell`** — left rail (portal/backend when applied).

## Rules

1. Prefer tokens over one-off `backdrop-filter` in new UI.
2. Respect `prefers-reduced-motion`: reduce blur only if policy requires (accessibility doc).
3. Marketing hero may override `--rmc-glass-*` locally for contrast; keep blur radius aligned.

## Changelog

- 2026-03: Initial shared recipe for §8.0 continuity.
