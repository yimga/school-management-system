# Theme Configuration Guide

This guide explains how the theme system behaves and how administrators and users can customize it safely.

## Automatic + Manual Theme Flow

1. By default the admin respects the operating system preference via `prefers-color-scheme`.  
2. The **Theme toggle** in the admin header sets `data-theme` on `<html>`, saves the choice in `localStorage`, and hits `siteconfig:update_theme` so the preference is stored per user.
3. Each user can manage their theme via **Site Preferences → Theme preference** (light/dark/auto) and enable **High contrast mode** to boost readability. Those values update `DashboardUserPreference` and feed into the admin template via `USER_THEME_PREFERENCE`.

## Site Settings Theme Controls

Site Settings exposes all palette tokens (`admin_sidebar_bg_color`, `admin_sidebar_text_color`, etc.) with color pickers. The **Small screen preview** in the Settings form renders a miniature sidebar/card layout and reacts live to color changes. Because the preview sits next to the pickers, administrators can see how any change behaves at narrow widths before saving.

The form also validates combinations server-side:
* Background/text pairs must meet a 4.5:1 contrast ratio (see `contrast_ratio` in `apps/siteconfig/forms.py`).  
* Invalid hex values are rejected and surface inline errors.  
If you need an even stronger contrast, enable **High contrast mode** in the user preferences to ensure the UI stays legible.

## Responsiveness & Accessibility

The sidebar accordion and footer already include updated focus styles (see `static/css/admin_sidebar_enhanced.css`). The preview component applies the current palette inside a mock device so you can test how cards stack and how colors render on small screens.

## Monitoring & Guardrails

* The `update_theme` endpoint logs each user change (check `apps/siteconfig/dashboard_views.py`).  
* Invalid color submissions are blocked before saving, so the admin always renders with valid CSS variables.

## Walkthrough

1. Open `/admin/siteconfig/sitesettings/`.
2. Adjust the color swatches; the preview updates instantly and warns if contrast is too low.
3. Save, then go to `/siteconfig/preferences/` to pick a default theme and whether you want high contrast.
4. Use the header toggle on any admin page to temporarily switch modes; the change will persist across sessions.
