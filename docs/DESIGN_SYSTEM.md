# Design System (Phase 5)

## Canonical token source

- **Primary:** `static/css/design-tokens.css` — load first. Defines brand (`--school-primary`, `--school-accent`), admin/portal/backend surfaces, spacing (4px base), typography, and focus.
- **Override:** Base templates (base.html, portal_base.html, backend_base.html) inject `--school-primary` and `--school-accent` from SiteSettings/theme so the app reflects the school’s brand.
- **Unified:** `static/css/design-system-unified.css` adds component-level tokens (shadows, radius, z-index). Prefer `--school-primary` from design-tokens for buttons and accents; avoid hardcoded hex for brand.

## Navy/Slate default palette (Phase 5.2)

- **Admin sidebar / content:** `--admin-sidebar-bg: #0f172a`, `--admin-content-text: #0f172a`, `--admin-content-text-muted: #475569`. Slate grays for text and borders.
- **Portal:** `--portal-text`, `--portal-text-muted`, `--portal-border` in design-tokens; dark theme overrides in the same file.
- Use one accent (e.g. `--school-primary`) for CTAs and active states; keep gradients to header/CTA only (Phase 5.5).

## H1–H4 type scale (Phase 5.3)

Defined in `design-tokens.css`:

| Token         | Approx. size | Use for   |
|---------------|--------------|-----------|
| `--heading-h1` | 24–32px    | Page title |
| `--heading-h2` | 20–24px    | Section    |
| `--heading-h3` | ~18px      | Card/subsection |
| `--heading-h4` | 16px       | Labels/small headings |

Use in CSS: `font-size: var(--heading-h1);` etc. Prefer these over ad‑hoc `display-*` or `fw-bold` for headings.

## 4px/8px spacing grid (Phase 5.4)

- **design-tokens.css:** `--token-space-xs` (4px) through `--token-space-3xl` (64px); aliases `--spacing-*`.
- Use these for padding, margins, and gaps in dashboard, cards, forms, and lists instead of one-off values.

## Reduce visual noise (Phase 5.5)

- **Borders:** Prefer `--admin-content-border`, `--portal-border`; avoid inline `border: 1px solid #…`.
- **Shadows:** Use the scale in design-system-unified (`--shadow-sm` … `--shadow-2xl`).
- **Gradients:** Restrict to header/CTA (e.g. `--header-brand-bg`); use flat fills for sidebar and cards.

## Apply across portal, backend, admin (Phase 5.6)

- **base.html:** Login and shared pages; sets `--school-primary` when SITE exists; loads design-tokens + design-system-unified.
- **portal_base.html:** Portal; overrides `--school-primary` from theme; same token set.
- **backend_base.html:** Backend; extends portal_base and overrides theme from admin theme.
- **Admin (Django):** base_site and admin CSS use `--admin-*` and `ADMIN_RESOLVED_PRIMARY` from context so the same token set and hierarchy apply.
