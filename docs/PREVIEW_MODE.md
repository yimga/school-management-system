# Preview Mode (Config Draft / Sandbox)

Preview mode lets admins **try settings and config changes without affecting what other users see**—**any config**, not only theme or “Theme & Experience.” Changes are stored in your session and applied only for you until you save or clear. The same idea applies to other config UIs (feature toggles, report styles, dashboard layout, etc.) as they adopt the “preview before it goes live” pattern.

## Two parts

### 1. Draft preview (Site Settings form)

- In **Site Settings** → **Preview & Draft** you can enable **Preview mode** and add an optional **Preview note**.
- When you **save** with **Preview mode** enabled, certain fields are **not** written to the database for everyone. Instead they are stored in **your session** only:
  - `site_name`, `tagline`
  - `primary_color`, `accent_color`, `success_color`, `warning_color`, `danger_color`
- The **site settings context processor** (used on every request) overlays these session values onto the `SiteSettings` object for **your** requests only. So you see your draft (e.g. new colors, name), while everyone else still sees the saved DB values.
- To **publish** the draft: turn off **Preview mode** and save again. The form then saves to the database as usual and the session stash is cleared.
- To **discard** the draft: use **Clear preview** (e.g. from User Preferences or the link that clears `site_preview_settings`). That removes the session overlay so you see the real saved settings again.

### 2. Quick toggle (header / session)

- A **Toggle preview** action (e.g. from the dashboard or header) flips a session flag (`admin_preview_mode`) so you can turn “preview on” without opening Site Settings.
- When this flag is on, the context processor still uses any **stashed** values from the form (from when you saved with Preview mode enabled). So the toggle just shows/hides the draft you already saved in session; it does not create new draft values by itself.

## Flow (summary)

1. **Enable draft:** Site Settings → Preview & Draft → check **Preview mode** → Save.  
   → Your submitted values for the listed fields are stored in session; DB is unchanged for others.

2. **See draft:** Every page load for you uses session overlay → you see your draft. Others see DB.

3. **Publish:** Site Settings → uncheck **Preview mode** → Save.  
   → Session stash is cleared; values are written to DB; everyone sees the new settings.

4. **Discard:** Use **Clear preview** (e.g. `/siteconfig/customizer/clear-preview/`).  
   → Session stash is removed; you see the current DB values again.

## Technical notes

- Session keys: `site_preview_settings` (stashed field values), `preview_mode_enabled`, `admin_preview_mode` (toggle).
- Context processor: `apps.siteconfig.context_processors.site_settings` applies `site_preview_settings` to the `site` object and sets `is_preview` when preview is active.
- Templates receive `PREVIEW_MODE_ENABLED`, `PREVIEW_NOTE`, and related variables for banners or labels.
