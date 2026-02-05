# Preview and Draft Patterns – Config Before It Goes Live

**This is not just about theme or “Theme & Experience.”** It is about **settings in general**: giving admins the ability to **preview config before it goes live**—any setting that affects how the site, portal, reports, or dashboards behave or look. Preview, confirm, then apply.

The Site Settings “preview before save” flow is one instance of this **general pattern**. The same idea applies to **all config UIs**: other admin forms, feature toggles, report styles, dashboard layout, and any “see it before you commit it” flow.

---

## 1. When to offer “preview before save”

Use a **preview** (or **draft**) flow whenever:

- A **config/settings form** changes how something is used or rendered (branding, theme, feature flags, report layout, dashboard, visibility rules).
- Users should **confirm the effect** before changes go live.
- The result is **visible or testable** somewhere (site, portal, report PDF, dashboard, API behavior).

**Good candidates in this codebase (config that can be previewed before going live):**

| Area | Config / form | What “preview” could do |
|------|----------------|-------------------------|
| **Site Settings** | SiteSettings (all tabs: branding, theme, features, etc.) | ✅ Done: stash form → open site/backend in new tab with config overlay. |
| **Theme packs** | ThemePack (admin) | Stash pack config → open preview URL that uses that pack for one request or session. |
| **Report card style** | ReportCardStyle | ✅ Report preview exists; add “Preview with current form” from admin so config is previewed before save. |
| **Feature control** | Feature Control panel | Stash toggles in session → open portal in new tab with those toggles applied (config not yet live). |
| **Dashboard layout** | DashboardLayout / widgets | Stash layout config → open backend dashboard with that layout so admin sees it before saving. |
| **Report builder** | Report template / style selection | Preview report with selected style and sample data (partially exists). |
| **Other settings** | Any admin or app form that changes visible/behavioral config | Same pattern: stash → overlay in preview context → open relevant URL; save when confirmed. |

Not every form needs preview—only where **“preview this config before it goes live”** clearly helps.

---

## 2. Reusable “preview config before it goes live” pattern

The same idea works for **any settings/config** (not only theme or one tab):

1. **Endpoint**  
   - POST-only view that:
     - Accepts the same (or a subset of) fields as the form.
     - Validates (optional but recommended).
     - Puts data into **session** (e.g. `request.session["preview_<scope>"]`) or a **per-request override**.
     - Returns JSON `{ "redirect_url": "…" }` or HTML redirect.

2. **Context / template layer**  
   - A context processor or middleware (or view logic) that:
     - Reads that session key (or override).
     - For the **previewed** page only, overlays those values onto the “live” config (e.g. SITE, theme, feature flags).

3. **Button on the form**  
   - “Preview” (or “See how it looks”):
     - Type `button`, not submit.
     - On click: serialize form (e.g. `FormData`), POST to the endpoint with CSRF, then `window.open(data.redirect_url, "_blank")` (or show in iframe/modal).

4. **Banner when preview is active**  
   - On the previewed page: “You’re previewing unsaved changes. [Back to form] [Discard].”  
   - Only show when the preview session key is set (and optionally only for the user who started the preview).

5. **Clear on save**  
   - When the user **saves** the form for real, clear the preview session so the live view matches the DB.

You can **reuse this pattern** for ThemePack, Feature Control, Dashboard layout, etc., by:

- Adding a small view (e.g. `preview_themepack_from_form`, `preview_feature_flags_from_form`).
- Using a dedicated session key per scope (e.g. `site_preview_settings`, `themepack_preview`, `feature_control_preview`).
- Having the relevant context processor or view check that key and overlay values only for the previewed route or user.

---

## 3. Validation and error handling (project-wide)

- **Any** custom POST endpoint that drives UI (preview, apply, export, bulk action) can:
  - Validate input (form or schema).
  - On error: return **400** and JSON `{ "errors": { "field": ["message"] } }` or `{ "errors": ["message"] }`.
- **Front end** (button or form handler):
  - If response is not ok, parse JSON and show errors (toast, inline under button, or next to fields).
  - Don’t open a new tab or follow redirect on error.

Apply this to:

- `preview_from_form` (and any future preview endpoints).
- Other custom admin or app views that return JSON (e.g. “Apply from preview”, “Export”, “Run dry-run”).

---

## 4. Toast / user feedback (project-wide)

- Many places assume `window.showToast(message, type, duration)`.
- **Single place** to define a fallback:
  - In a shared JS file (e.g. used by admin and backend base templates), or in the base template:
    - If `showToast` is not defined, set `window.showToast = function(msg, type, duration) { ... }` (e.g. temporary inline div or `alert()`).
- Then **all** callers (Site Settings preview, Color & harmony, future preview buttons, etc.) get consistent feedback without each one checking for `showToast`.

---

## 5. Accessibility (project-wide)

- **Every** custom action button (Preview, Export, Apply, “Run dry-run”):
  - Use a clear `aria-label` (e.g. “Preview current settings in new tab”).
  - Be focusable and activatable with keyboard (no `div` with click-only).
  - If the button opens a new tab, say so in the label or tooltip.
- **Banners** (preview, maintenance, success):
  - Use a single focusable region (e.g. `role="status"` or `role="alert"`) and ensure contrast and readable text.

This applies to:

- Site Settings Preview button.
- Any new Preview / Apply / Export buttons in admin or app UIs.

---

## 6. Documentation (project-wide)

- **Central list of “preview/draft” flows:**
  - In this doc or in a “Config and preview” section:
    - Site Settings: preview from form → session → open site; clear on save.
    - (Future) ThemePack: preview from form → session → open preview URL.
    - (Future) Feature Control: draft toggles → preview portal.
- **When adding a new preview:**
  - Add one short paragraph: what is previewed, which session key, which URL, and where the “Preview” button lives.
- **Field lists:**
  - For each preview scope, list which fields are in the payload (e.g. `PREVIEW_FROM_FORM_KEYS` for Site Settings). That keeps behavior and docs in sync when new settings are added.

---

## 7. Summary: how this applies more widely

| Suggestion | Scope | How it applies |
|------------|--------|----------------|
| **Preview config before it goes live** | Any settings/config form | Add endpoint (POST → session/override), overlay in context/view, “Preview” button that POSTs form and opens the right URL; clear on save. Applies to **all config**, not only theme or “Theme & Experience.” |
| **Validation + JSON errors** | Any custom POST endpoint | Validate; on error return 400 + `{"errors": ...}`; front end shows errors instead of navigating. |
| **Toast fallback** | Whole project | One shared fallback for `showToast` in base or shared JS so all features get consistent feedback. |
| **Accessibility** | All custom buttons and banners | aria-label, keyboard support, clear wording for “opens in new tab” and alerts. |
| **Docs** | All preview/draft features | One doc (this one) listing each preview flow, its session key, and payload fields; update when adding new ones. |

Using these patterns, the same “preview config before it goes live” capability can be applied consistently to **Site Settings (all tabs)**, ThemePack, Feature Control, dashboard layout, report styles, and any future **settings or config** that affects behavior or appearance.
