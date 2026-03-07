# Theme JSON Schema (Export / Figma / Tools)

Structure for exporting or importing theme data (SiteSettings / ThemePack) as JSON, and for design tools (e.g. Figma) to target the same structure. Supports the standard: *"Export/Save: Use JSON or CSS files for easy integration."*

---

## Site-level theme (minimal)

Matches **SiteSettings** palette and typography:

```json
{
  "primary_color": "#0d6efd",
  "accent_color": "#198754",
  "success_color": "#22c55e",
  "warning_color": "#fbbf24",
  "danger_color": "#ef4444",
  "brand_font": "Inter, system-ui, sans-serif",
  "use_dark_mode": false,
  "theme_brightness": "system"
}
```

---

## Theme pack (named pack)

Matches **ThemePack** (primary, accent, background, font, palette JSON):

```json
{
  "name": "School Brand",
  "slug": "school-brand",
  "primary_color": "#0d6efd",
  "accent_color": "#198754",
  "background_color": "#ffffff",
  "font_family": "Inter, system-ui, sans-serif",
  "palette": { "gradient": ["#0d6efd", "#198754"] },
  "logo_opacity": 0.3,
  "logo_background_mode": "contain"
}
```

---

## CSS variables emitted

Templates inject these from the active theme:

- **Portal / base:** `--school-primary`, `--school-accent`, `--school-font`
- **Backend dashboard:** `--brand-primary`, `--brand-accent`, plus admin vars
- **Admin:** `--admin-sidebar-*`, optional `--brand-primary` when "use site primary" is on

Export logic can serialize SiteSettings/ThemePack to the JSON above; import can validate and write back to the DB. See [THEME_COLOR_STYLE_ASSESSMENT.md](./THEME_COLOR_STYLE_ASSESSMENT.md) for full standard compliance.
