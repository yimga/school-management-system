# Canonical Theme Tokens

Single source of truth for theme-aware styling across Portal, Backend, Admin, and standalone pages (login, base). All dark overrides are defined in **design-tokens.css** and **design-system-unified.css** for `html[data-theme="dark"]`, `html[data-bs-theme="dark"]`, and `body.portal-backend-dark`.

## Load order

1. **design-tokens.css** – shared variables; light defaults in `:root`, dark overrides in one block for data-theme and body.portal-backend-dark.
2. **design-system-unified.css** – design system palette; same dark selectors so backend/admin get `--color-bg-primary`, `--color-text-primary`, etc.
3. **theme-everywhere-dark.css** – minimal overrides only for legacy `.bg-white` and inline `style="background: white"` until all templates use tokens. New UI must not rely on this file.

## Surface and content tokens (design-tokens.css)

| Token | Light | Dark | Use for |
|-------|--------|------|---------|
| `--admin-content-bg` | #ffffff | #0f172a | Main content area, body, cards |
| `--admin-content-surface` | #ffffff | #1e293b | Elevated surfaces: dropdowns, modals, inputs |
| `--admin-content-card-bg` | #ffffff | #1e293b | Cards, panels |
| `--admin-content-text` | #0f172a | #f1f5f9 | Primary text |
| `--admin-content-text-muted` | #475569 | #94a3b8 | Secondary/muted text |
| `--admin-content-border` | rgba(15,23,42,0.12) | rgba(148,163,184,0.25) | Borders |
| `--admin-content-accent-fg` | #ffffff | #f1f5f9 | Text on accent/primary buttons |
| `--admin-surface` | #ffffff | #1e293b | Alias for content surface (cards, panels) |
| `--admin-text` | #0f172a | #f1f5f9 | Alias for content text |
| `--admin-border` | rgba(15,23,42,0.12) | rgba(148,163,184,0.25) | Alias for content border |
| `--portal-bg` | rgba(247,251,255,1) | #0f172a | Portal/body background |
| `--portal-text` | #111827 | #e2e8f0 | Portal body text |
| `--portal-text-muted` | #6c757d | #94a3b8 | Portal muted text |
| `--portal-border` | rgba(15,23,42,0.08) | rgba(148,163,184,0.2) | Portal borders |
| `--overlay-bg` | rgba(255,255,255,0.98) | #1e293b | Modals, overlays |
| `--overlay-text` | #0f172a | #e2e8f0 | Text on overlay |

## Spacing (design-tokens.css – single source)

All spacing uses a 4px base unit. Prefer `--token-space-*` or `--spacing-*` (aliased from tokens).

| Token | Alias | Value | Use for |
|-------|--------|-------|---------|
| `--token-space-xs` | `--spacing-xs` | 0.25rem (4px) | Tight gaps, icon padding |
| `--token-space-sm` | `--spacing-sm` | 0.5rem (8px) | Inline gaps, small padding |
| `--token-space-md` | `--spacing-md` | 1rem (16px) | Default padding, gaps |
| `--token-space-lg` | `--spacing-lg` | 1.5rem (24px) | Section spacing, card padding |
| `--token-space-xl` | `--spacing-xl` | 2rem (32px) | Large sections |
| `--token-space-2xl` | `--spacing-2xl` | 3rem (48px) | Hero / block spacing |
| `--token-space-3xl` | `--spacing-3xl` | 4rem (64px) | Page-level spacing |

Dashboard-specific: `--dashboard-gap-sm` (12px), `--dashboard-gap-md` (16px), `--dashboard-gap-lg` (24px). **design-system-unified.css** does not redefine spacing so this file remains the single source.

## Design system tokens (design-system-unified.css)

- **Primary:** `--color-primary`, `--color-primary-light`, `--color-primary-dark` (buttons, links, accents).
- **Background:** `--color-bg-primary`, `--color-bg-light`, `--color-bg-lighter` (overridden in dark for body.portal-backend-dark and html[data-bs-theme="dark"]).
- **Text:** `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`.
- **Borders:** `--color-border`, `--color-border-light`.
- **Focus:** `--focus-ring-color` (set to `var(--color-primary)` in dark).

## Rule for new and updated styles

- **Do not** use hardcoded `#fff`, `#ffffff`, or `background: white` for any theme-dependent surface (cards, headers, dropdowns, modals, inputs, login card, etc.).
- **Do** use the tokens above: e.g. `background: var(--admin-content-bg)`, `color: var(--admin-content-text)`, `border-color: var(--admin-content-border)`.
- For text on accent/primary buttons use `var(--admin-content-accent-fg)`.
- Admin sidebar and Site config may override `--color-primary` (and related) per SITE. Scoped overrides (e.g. `--admin-sidebar-focus-ring`) apply only where needed.

## Theme and color audit (summary)

A full theme-pack and color audit was done across the codebase to improve consistency and visuals:

- **design-tokens.css**: Added semantic `--stat-admin`, `--stat-student`, `--stat-teacher`, `--stat-parent` for dashboard stats; dark block overrides for contrast.
- **Templates**: Replaced hardcoded hex in admin dashboard (Total Users stats), dashboard header (logo placeholder), quick actions (card header, badge, neutral icon), user dropdown (avatar gradient, stats block, section headers, dropdown items), admin nav bridge (brand icon and title text), global search (trigger, modal, inputs, results), notification center (bell hover, badge, header, tabs). All use `var(--...)` with fallbacks where appropriate.
- **CSS**: portal-theme-modes.css skip-link and dark body/card/sidebar now use `--portal-bg`, `--admin-content-surface`, `--portal-text`, `--portal-text-muted`, `--focus-ring-color`, `--admin-content-accent` instead of raw hex.
- **Rule**: New UI should use tokens from this doc; avoid new hardcoded `#hex` for theme-dependent colors.
