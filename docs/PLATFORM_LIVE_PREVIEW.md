# Platform-Wide Live Preview

Live preview is a **platform-wide capability**, not limited to one section or page. Any system-config or content surface can offer "Live preview" so users see changes before saving.

---

## One contract, many surfaces

| Mode | Entry point | Use |
|------|-------------|-----|
| **Config / full-page** | `siteconfig:preview_from_form` | Theme & Experience, Site Settings (header, footer, login, sidebar). Form POSTs with `preview_section`; user is redirected to portal (or login) with unsaved settings applied and section highlighted. |
| **Report / embed** | `siteconfig:reportcard_style_embed_preview`, `reportcard_style_live_preview` | Report Card Builder: iframe or new-tab preview of report style with sample student. |
| **Setup Studio** | Guided onboarding "Live preview workspace" + 6-role preview cards | Onboarding: preview by role (website, admin, teacher, parent, etc.) before go-live. |

Same idea everywhere: **preview before save**, with the right context (section highlight, embed, or role). The Site Settings admin change form uses this same contract via its dynamic Preview button (active section from the sidebar is sent as `preview_section`).

---

## How to add a new section (config/full-page)

1. **Mark the DOM** in the template where the settings apply: `id="preview-{section}-*"` and `data-preview-label="..."` on each configurable area.
2. **Register the section** in `static/js/preview-highlights.js` (scroll target, container, selector, highlight class).
3. **Map section name** in `apps/siteconfig/views.preview_from_form`: add your form’s `preview_section` value to the `section_map` (and optionally handle a login redirect if the section is on the login page).
4. **Add a Live preview button** on the form: use the reusable `{% include "components/live_preview_button.html" with preview_section="your-section" %}` (inside the form), or wire your own button to POST the form to `preview_from_form` with `preview_section` and open the returned `redirect_url` in a new tab.

Detail: **`docs/PREVIEW_SYSTEM.md`** (scroll/highlight, supported sections, adding login/sidebar, tests).

---

## Reusable Live preview button

Any form that submits fields accepted by `preview_from_form` can use the platform button:

```django
{% include "components/live_preview_button.html" with preview_section="theme-experience" %}
```

Optional variables: `form_id` (default: closest parent form), `show_keep_checkbox=True`, `button_label="Live preview"`. The include must be **inside** the form (or you pass `form_id`).

---

## Supported sections (preview_section)

| Form value | URL param | Where it scrolls/highlights |
|------------|-----------|-----------------------------|
| `theme-experience`, `theme` | `theme` | Header + footer (theme colors) |
| `footer`, `footer-content` | `footer` | Footer |
| `header`, `branding`, `login-header-layout` | `header` or `login` | Header or login page |
| `login`, `login-layout` | `login` | Login page |
| `sidebar` | `sidebar` | Sidebar/nav |

Multiple sections: send `preview_section=footer,header` (comma-separated). Optional `preview_keep=1` keeps highlights until the user dismisses.

---

## Report and Setup Studio

- **Report Card Builder**: Live preview is iframe-based (embed endpoint) and/or new-tab (live_preview endpoint). Same "platform live preview" idea: preview style and data before saving. See `templates/siteconfig/partials/mock_reportcard_preview.html` and `siteconfig:reportcard_style_embed_preview`.
- **Setup Studio**: 6-role preview cards and "Live preview workspace" are the onboarding flavour of platform live preview (preview by role before launch). See `templates/customersuccess/guided_onboarding.html` and Setup Studio payload (`preview_workspace`, `preview_cards`).

---

## Summary

- **Platform-wide** = one conceptual contract: "Live preview" anywhere means "see effect before save" (full-page highlight, embed, or role preview).
- **Config sections** use `preview_from_form` + section map + highlight script; **report** uses embed/live_preview endpoints; **Setup Studio** uses role preview cards and workspace.
- New sections (config) register in the section map and DOM/JS; new pages can use the shared `live_preview_button.html` include so Live preview stays consistent across the platform.
