# Preview System – Platform-Wide Live Preview (Site Settings & Configuration Control Center)

This is the **platform-wide Live Preview** system for site settings and system configuration. Any section can participate (see **`docs/PLATFORM_LIVE_PREVIEW.md`** for the single contract and how report/Setup Studio previews fit in). The following describes how full-page config preview works and how to extend it for any site-setting or system-config section. Preview is heavily used when editing **Site Settings** (header, footer, theme, branding, etc.) so admins can see exactly which parts of the site their changes affect.

---

## Overview

| Piece | Location | Purpose |
|-------|----------|---------|
| **Preview from form** | `siteconfig.views.preview_from_form` | Accepts POST (form data + `preview_section`), enables session preview, redirects to portal with `?preview_section=...` so the page can scroll and highlight. |
| **Redirect + params** | `accounts.views.redirect_view` | Preserves `preview_section` (and other GET params) when redirecting so the final page receives the param. |
| **Highlight script** | `templates/portal_base.html` (inside `{% if SITE.is_preview %}`) | Reads `preview_section`, scrolls to the right place, and highlights **specific configurable areas** with color-coded outlines and labels. |
| **Preview targets** | Footer: `templates/components/dashboard_footer.html`<br>Header: `templates/portal_base.html` (nav) | DOM elements with `id="preview-{section}-*"` and `data-preview-label="..."` so the script knows what to highlight and what to call each area. |
| **Small-screen preview** | `templates/admin/components/theme_preview_section.html` | Inline mini preview on Theme & Experience / color forms; updates as you change colors (JS). |

---

## How It Works End-to-End

1. **User edits a section** (e.g. Footer, Header & branding, Theme & Experience) in Site Settings or the Theme & Experience page.
2. **User clicks “Preview” / “Live preview”** – the form POSTs to `siteconfig:preview_from_form` with `preview_section` set (e.g. `footer`, `header`, `theme-experience`).
3. **Backend** turns on preview mode in session and redirects to the portal (e.g. dashboard) with `?preview_section=footer` (or `header`, `theme`).
4. **Portal page** loads with unsaved settings applied (via `SITE.is_preview`). The script in `portal_base.html` runs only when `SITE.is_preview` is true.
5. **Script** reads `preview_section`, scrolls to the right container (footer, header, etc.), then finds all elements that are **preview targets** for that section and highlights each with a colored outline and a small label (from `data-preview-label`). After a few seconds, highlights and labels are removed.

So the user is taken to the right place and sees **exactly which parts** of the page their current section's settings affect — not just one big block.

---

## Supported Sections (preview_section)

| Value in URL | Scroll to | What gets highlighted | Typical use |
|--------------|-----------|------------------------|-------------|
| `footer` | Footer | All elements with `id^="preview-footer-"` inside `#dashboardFooter` (footer bar, brand card, help card, meta). | Footer content, colors, accreditation, support hours. |
| `header` | Header | All elements with `id^="preview-header-"` inside `#portalHeader` (header bar, brand, actions). | Header colors, logo, site name, search/controls. |
| `theme` | Header (then footer in view) | Header and footer preview targets, both with theme color. | Theme & Experience (colors, theme pack) affecting header and footer. |

Mapping from **form** to **URL** is done in `apps/siteconfig/views.py` in `preview_from_form` (e.g. `footer-content` → `footer`, `theme-experience` → `theme`, `branding` → `header`).

---

## Adding a New Preview Section (e.g. Login, Sidebar, Another Page)

Preview is **not** limited to footer/header/theme. Use the same pattern for any site-setting or system-config area.

### 1. Mark the DOM (where settings apply)

In the template that renders that part of the site:

- Give the **scroll container** a stable `id` (e.g. `id="loginPage"` or reuse an existing one).
- For each **configurable area** that the user's settings affect, add:
  - `id="preview-{section}-{area}"`  
    Use a single `{section}` name for this feature (e.g. `preview-login-form`, `preview-login-brand`).
  - `data-preview-label="Short label for this area"`  
    This is the text shown in the small label above the highlight.

Example for a hypothetical “Login” section:

```html
<main id="loginPage">
  <div id="preview-login-brand" data-preview-label="Logo and site name">...</div>
  <form id="preview-login-form" data-preview-label="Login form and layout">...</form>
</main>
```

Use **one** `preview-{section}-*` prefix per section so the script can find all targets with one selector.

### 2. Register the section in the highlight script

In `static/js/preview-highlights.js`, extend the `config` object (or set `window.PREVIEW_SECTION_CONFIG` before the script runs):

```javascript
var config = {
  footer: { scrollTo: 'dashboardFooter', container: 'dashboardFooter', selector: '[id^="preview-footer-"]', class: 'preview-highlight-footer', sectionKey: 'footer' },
  header: { scrollTo: 'portalHeader', container: 'portalHeader', selector: '[id^="preview-header-"]', class: 'preview-highlight-header', sectionKey: 'header' },
  theme: { ... },
  login: { scrollTo: 'loginPage', container: 'loginPage', selector: '[id^="preview-login-"]', class: 'preview-highlight-login', sectionKey: 'login' }
};
```

Add a CSS class and (optional) label style:

- In the same `<style>` block:  
  `.preview-highlight-login { --preview-highlight-color: rgba(16, 185, 129, 0.95); }`  
  `.preview-changes-label[data-preview-section="login"] { background: #10b981; }`

If the section spans **multiple containers** (like theme with header + footer), use the `theme`-style config: `scrollTo`, `containers` (array of IDs), and `selectors` (object: containerId → selector).

### 3. Map form / admin section to URL param

In `apps/siteconfig/views.py`, in `preview_from_form`, map the value your form sends to the URL param:

```python
elif preview_section in ("login-layout", "login"):
    redirect_url += "&" if "?" in redirect_url else "?"
    redirect_url += "preview_section=login"
```

In the Site Settings (or other) form, when the user clicks Preview, send that value (e.g. `preview_section: "login"` or `"login-layout"`) in the POST so the redirect gets `?preview_section=login`.

---

## Conventions (for the whole codebase)

- **Preview targets**: `id="preview-{section}-{area}"` and `data-preview-label="..."` so the script can both find and label each area.
- **One prefix per section**: Use a single `preview-{section}-` prefix per feature so one selector (e.g. `[id^="preview-footer-"]`) is enough.
- **Scroll container**: Each section config has a `scrollTo` ID so the page scrolls to the right place before highlighting.
- **Color-coding**: Each section has its own highlight class and label background (footer = blue, header = amber, theme = purple, etc.) so users can tell sections apart.
- **Site Settings / system config**: This flow is intended for any part of the system that is configured in Site Settings or similar (header, footer, theme, login, branding, etc.) — not just one page or one section.

---

## Files Reference

| File | Role |
|------|------|
| **`docs/PLATFORM_LIVE_PREVIEW.md`** | **Platform-wide live preview:** one contract; config, report, Setup Studio; how to add sections; reusable button. |
| **`templates/components/live_preview_button.html`** | **Reusable Live preview button** for any form using `preview_from_form`; pass `preview_section`, optional `form_id`, `show_keep_checkbox`. |
| `apps/siteconfig/views.py` | `preview_from_form`: reads `preview_section`, appends it to redirect URL. |
| `apps/accounts/views.py` | `redirect_view`: preserves GET params (e.g. `preview_section`) to final URL. |
| `templates/portal_base.html` | Loads `preview-highlights.css` and `preview-highlights.js` when `SITE.is_preview`; banner with Save / Back / Discard. |
| `templates/components/dashboard_footer.html` | Footer preview targets: `preview-footer-bg`, `preview-footer-brand`, `preview-footer-help`, `preview-footer-meta`. |
| `templates/admin/siteconfig/sitesettings/change_form.html` | Preview button that POSTs with `preview_section` from current fieldset/section. |
| `templates/siteconfig/theme_colors.html` | Live preview button for Theme & Experience; sends `preview_section: 'theme-experience'`. |
| `templates/admin/components/theme_preview_section.html` | Inline small-screen preview on color/theme forms. |
| `static/css/preview-highlights.css` | Full-page preview: highlight/label colors, dismiss button, print hide, scroll-margin. |
| `static/js/preview-highlights.js` | Section config, multi-section, `preview_keep`, scroll + highlight logic; used by portal_base and base (login). |
| `static/css/site-settings-preview.css` | Styling for the inline theme preview card. |

---

## Inline vs Full-Page Preview

- **Inline (small-screen preview)**  
  Shown on the form (e.g. Theme & Experience). Updates as you change fields (JS). Good for quick feedback on colors/layout in one place.

- **Full-page preview (open in new tab)**  
  Real portal page with unsaved settings and `?preview_section=...`. Scrolls to the section and highlights **specific configurable areas** with labels. Use this whenever you want to show "this is exactly what will change" for header, footer, theme, or any other site-setting section across the app.

This doc emphasizes **full-page preview** and **site settings / system configuration** so the same pattern can be reused for the entire codebase wherever config drives the UI.

---

## Implemented Improvements

All suggested improvements are in place:

| Improvement | Status |
|-------------|--------|
| **Dismiss highlights** | Button clears highlights and labels immediately. |
| **Hide on print** | `@media print` hides highlights and labels. |
| **aria-live on labels** | Labels have `aria-live="polite"` for screen readers. |
| **Login section** | Add `preview-login-*` targets and a `login` section so “Login & branding” preview works on the login page. |
| **Sidebar section** | `preview-sidebar-*` (header + nav) in `portal_sidebar.html`; config in JS. |
| **Multiple sections** | `preview_section=footer,header` supported; backend normalizes and passes through. |
| **“What changed” per area** | Optional backend-driven tooltip per highlight (e.g. “Footer bg color, accreditation text”) so users see which settings map to each area. |
| **Persist until dismiss** | Option to keep highlights until the user clicks “Dismiss” (or closes the tab) instead of a fixed 7s timeout. |
| **Preview banner** | In the “You're previewing unsaved Site Settings” banner, add a primary “Save” link that goes straight to the Site Settings save form. |
| **Central config** | Move section config (scrollTo, selector, class) into a small JS module or `data-` attribute so new sections don't require editing the inline script block. |
| **Reusable CSS** | `static/css/preview-highlights.css` for highlight/label/dismiss/print. |
| **Tests** | `test_preview.py`: POST required (GET -> 400 when logged in), redirect for footer, header, theme, login, sidebar, multiple sections, `preview_keep`. |
| **Redirect chain** | `redirect_view` preserves GET params; login-only preview uses login URL with params. |
| **Mobile scroll** | Use `scroll-margin` or scroll to the first highlighted element so small screens don't leave the target off-screen. |


---

## Running the tests

Preview tests live in `apps/siteconfig/tests/test_preview.py`. They cover redirect URL params (footer, header, theme, login, sidebar), multiple sections, `preview_keep`, and that GET returns 400 when authenticated.

```bash
python manage.py test apps.siteconfig.tests.test_preview -v 2
```

For faster reruns (reuse test DB; skip recreating it and re-running migrations), use `--keepdb`:

```bash
python manage.py test apps.siteconfig.tests.test_preview -v 2 --keepdb
```
