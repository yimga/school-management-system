# Theme & Experience Combined Page – Revised Plan

## Goal

One **combined page** at `/siteconfig/theme-colors/` that gives:

- **Left column:** Color & harmony tools (picker, harmony type, Apply palette, presets, optional Color combinations reference).
- **Right column:** Full **Theme & Experience** form (all fields from admin “Theme & Experience” section) so the user can pick colors and edit settings side by side with a single Save.

No sidebars on this page (full-width layout). Back button (top and bottom) returns to where the user came from (e.g. Site Settings).

---

## 1. URL and entry

- **Keep** `/siteconfig/theme-colors/` as the combined page URL (name: `theme_colors`).
- Entry from admin: “Open Color & harmony” (or “Theme & experience”) link in Site Settings → Theme & Experience tab. Link should include `?next=/admin/siteconfig/sitesettings/1/change/#section-theme-experience` so the Back button returns there.

---

## 2. No sidebars (full-width layout)

- When this page is open, **hide the main app sidebar** so the two columns have maximum horizontal space.
- **Implementation:** Use a body class (e.g. `theme-experience-full-width`) on this page. CSS hides `.portal-sidebar-col`, `.portal-resize-handle`, and makes `.portal-main-col` full width. Mobile offcanvas sidebar can be hidden or kept for “Menu” if needed; for simplicity, hide sidebar entirely on this page.
- Optional: use a minimal top bar (logo + Back + user/logout only) so the page feels like a dedicated “Theme & experience editor” without the full backend nav.

---

## 3. Back button (top and bottom)

- **Top:** “Back to Site Settings” (or “Back”) in the header row.
- **Bottom:** Same back link in the action row (already present).
- **URL for back:** Prefer `request.GET.get('next')`, then `request.META.get('HTTP_REFERER')`, then fallback to admin Site Settings change URL (`admin_change_url`). Pass `back_url` (or keep `admin_change_url` and add `back_url`) to the template so both buttons use it.
- Admin link to this page: build URL with `?next={{ request.get_full_path }}` (or the current admin change form URL) so Back returns to the same tab.

---

## 4. Left column: Color & harmony

- **Base color** + **Harmony type** + **Apply palette** (and “Apply to Primary / Accent / …” if present).
- **Quick presets** and **Color combinations reference** in a compact or **collapsible** block so the left column doesn’t dominate.
- Optional: **very compact** “Small screen preview” (e.g. small mock or collapsible) if desired; otherwise it can live at the bottom or be omitted to keep the page shorter.
- “Apply palette” (and any “Apply to …” actions) must **write into the right-column form inputs** (same field names: `primary_color`, `accent_color`, etc.) so the form and tools stay in sync. Existing Color Palette Studio JS already targets inputs by name in the form; ensure the right-column inputs use the same `name` attributes.

---

## 5. Right column: Theme & Experience form

- **All fields** from the admin “Theme & Experience” fieldset (except the link block):
  - **Colors:** `primary_color`, `accent_color`, `header_bg_color`, `footer_bg_color`, `success_color`, `warning_color`, `danger_color`
  - **Theme:** `theme_brightness`, `use_dark_mode`, `admin_theme_pack`, `admin_use_site_primary`, `backend_console_theme`
  - **Typography:** `secondary_font`, `use_secondary_font_for_headings`, `base_font_size`
  - **Dashboard / reports:** `default_widgets_per_role`, `report_downloads_enabled`, `default_dashboard_view`, `default_refresh_rate`, `default_term_report_style`, `default_annual_report_style`
- Rendered as **normal form inputs** (text, select, checkbox) so they’re visible and editable next to the color tools.
- **One Save button** at the bottom (and optionally in a sticky bar) submits this form; the view updates `SiteSettings` and redirects back or shows success.
- No iframe and no “open Site Settings in another tab to fill the form.”

---

## 6. Behavior and wiring

- **Apply palette** (and “Apply to Primary/Accent/…”) updates the right-column inputs by name; form and color studio share the same form element (same `id="theme-colors-form"` or equivalent) so existing JS keeps working.
- **Revert to saved:** restores current DB values into the form (already implemented).
- **Live preview:** POSTs current form data to `preview_from_form`, opens site in new tab with optional section scroll/highlight (already implemented).
- **Save:** single POST; view validates and saves all Theme & Experience fields to `SiteSettings`; then redirect to same page with success message or to `back_url` if desired.

---

## 7. Responsive (stack on small screens)

- On narrow viewports (e.g. &lt; 992px), switch to **one column**: Color & harmony first, then Theme & Experience form below.
- Use CSS grid or flex with `grid-template-columns: 1fr 1fr` on large, `1fr` on small.

---

## 8. Layout: 50/50 + Small screen preview + Compact form

**50/50 vertical space**

- Two columns share the page **50% width each** (already in place).
- **Vertical balance:** Give the two-column grid a **fixed or min height** (e.g. `min-height: 70vh` or `height: 80vh`) and set **`overflow-y: auto`** on each column so:
  - Left column: color tools scroll inside their half if needed.
  - Right column: Theme & Experience form + Small screen preview scroll inside their half if needed.
- Result: the page doesn’t grow endlessly; each column scrolls independently and uses ~50% of the viewport height (or equal space).

**Small screen preview**

- **Placement:** In the **right column**, **under** the “Theme & Experience settings” form card.
- Order: (1) Theme & Experience settings card, (2) Small screen preview (inline mock that updates as you change colors).
- Keeps preview next to the form and avoids making the left column too long.

**Fit horizontally (compact form)**

- **Form in the right column:** Use horizontal space so the page isn’t unnecessarily long:
  - **Denser grid:** 3–4 fields per row for colors/selects (e.g. primary, accent, header, footer in one row; success, warning, danger in one; theme brightness, backend theme, admin pack in one).
  - **Checkboxes in one row:** use_dark_mode, admin_use_site_primary, report_downloads_enabled, use_secondary_font_for_headings in a single horizontal row (flex-wrap).
  - **Smaller inputs:** `form-control-sm` / `form-select-sm` and tighter spacing (`g-1` / `mb-1` or `mb-2`) so the form is more compact vertically.
- Optional: collapsible sections for “Typography” and “Dashboard & reports” to shorten the initial view.

**Summary**

- 50/50: two columns, equal width; equal/min height with overflow scroll so each column scrolls inside its area.
- Preview: right column, under Theme & Experience settings.
- Compact form: denser grid, checkboxes in one row, smaller controls, tighter spacing (and optionally collapsible sections).

---

## 9. Implementation checklist

| # | Task | Notes |
|---|------|--------|
| 1 | **Form** | Extend `ThemeColorsForm` (or create `ThemeExperienceForm`) to include all Theme & Experience fields with correct widgets (text, select, checkbox). Exclude `theme_color_tools_link_block`. |
| 2 | **View** | Use the expanded form in `theme_colors_page`; pass `back_url` (from `next`, referer, or admin change URL). On POST, save form and redirect. |
| 3 | **Layout** | Add body class `theme-experience-full-width` in template; add CSS (inline or static) to hide sidebar and make main content full width. |
| 4 | **Template** | Two-column layout: left = Color & harmony (palette studio, presets, color combinations ref collapsible), right = form (all fields visible). One form, one Save. Back button top and bottom using `back_url`. |
| 5 | **Back URL** | View: `back_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or admin_change_url`. Admin link: add `?next=<current admin URL>` when opening theme-colors. |
| 6 | **Apply palette** | Ensure Color Palette Studio (and any “Apply to …” buttons) target form inputs by name; right-column inputs must be part of the same form and use the same names. |
| 7 | **Responsive** | Media query: single column on small screens (color tools above, form below). |
| 8 | **Optional** | Compact or collapsible “Small screen preview” in left column or at bottom; optional “Live preview” button kept as is. |

---

## 9. Summary

- **One page:** `/siteconfig/theme-colors/`.
- **No sidebars** on this page → full width for two columns.
- **Left:** Color & harmony (picker, harmony, Apply palette, presets, color combinations ref).
- **Right:** Full Theme & Experience form (all fields, one Save); below it, Small screen preview.
- **Back button** top and bottom → `next`, referer, or Site Settings.
- **Apply palette** writes into the form; single form, single Save.
- **Stack** to one column on small screens.
