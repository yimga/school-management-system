# Admin Black Theme

This document describes the black theme system for the Django admin (`/admin`) at Gilead School Management. The recommended theme pack is **Deep Space / Midnight Blue**, which provides a professional black sidebar and forms.

---

## 1. Recommended Theme Pack

**Deep Space / Midnight Blue** (slug: `admin-deep-space-midnight`)

| Token | Value | Purpose |
|-------|-------|---------|
| `dashboard_bg` | `#101010` | Main background |
| `surface` | `#222222` | Cards, panels, sidebar |
| `primary` | `#3B86D1` | Actions, links, focus |
| `accent` | `#5ba3e8` | Highlights |
| `text` | `#F8F9FA` | Body text |
| `muted` | `#b8bcc4` | Labels, secondary |
| `border` | `rgba(248,249,250,0.12)` | Subtle dividers |

**How to apply:** Site Settings → Theme & Experience → Admin theme pack → select "Deep Space / Midnight Blue".

**Seed command:** Run `python manage.py seed_admin_dashboard_palettes` to ensure all palettes (including Deep Space) exist.

---

## 2. CSS Token Reference

Tokens are injected in `templates/admin/base_site.html` from `SITE_ADMIN_THEME.palette.admin_dashboard`. Fallbacks use Deep Space values when no theme is set.

| Token | Purpose |
|-------|---------|
| `--admin-palette-dashboard-bg` | Main background |
| `--admin-palette-surface` | Cards, modules, sidebar sections |
| `--admin-palette-primary` | Primary actions, focus ring |
| `--admin-palette-accent` | Highlights |
| `--admin-palette-text` | Body text |
| `--admin-palette-muted` | Secondary text |
| `--admin-palette-border` | Borders |
| `--admin-sidebar-bg` | Sidebar background |
| `--admin-sidebar-surface` | Sidebar surface |
| `--admin-sidebar-text` | Sidebar text |
| `--admin-sidebar-text-muted` | Sidebar muted text |
| `--admin-sidebar-border` | Sidebar border |
| `--admin-sidebar-hover` | Sidebar hover state |
| `--admin-sidebar-active` | Sidebar active state |
| `--admin-sidebar-active-border` | Active item accent |
| `--admin-form-bg` | Form row background |
| `--admin-input-bg` | Input/select/textarea background |
| `--admin-input-border` | Input border |
| `--admin-input-text` | Input text |
| `--admin-label` | Label color |
| `--admin-help` | Help text color |
| `--admin-focus` | Focus ring color |

---

## 3. Files

| File | Role |
|------|------|
| `templates/admin/base_site.html` | Injects palette vars; sets `data-theme="dark"` when black theme active |
| `static/css/admin-sidebar-black.css` | Sidebar and child menu black overrides |
| `static/css/admin_theme.css` | Forms, modules, header; uses palette tokens |
| `static/css/admin-dark-readability.css` | Dark content area; uses palette vars |
| `apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py` | Defines Deep Space and other palettes |

---

## 4. Auto Dark Mode

When the admin theme pack has a black/dark palette (slug contains `deep-space`, `midnight`, `-dark`, or `high-contrast-dark`), the page automatically sets:

- `data-theme="dark"`
- `data-bs-theme="dark"`
- `class="dark"` on `<html>`

This ensures `admin-dark-readability.css` and Unfold dark styles apply correctly.

---

## 5. Customization

To add a new black theme pack:

1. Add a palette definition in `seed_admin_dashboard_palettes.py` with `dashboard_bg` in `#0a0a0a`–`#181818` range.
2. Run `python manage.py seed_admin_dashboard_palettes`.
3. Select the new pack in Site Settings → Admin theme pack.
4. If the slug does not contain `deep-space`, `midnight`, `-dark`, or `high-contrast-dark`, add it to the auto-dark check in `base_site.html` extrahead, or users can manually toggle Dark in the theme control.
