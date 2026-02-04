# Preview Before Save – Options (Settings / Config in General)

**Goal:** The ability to **preview config before it goes live**—for **any settings**, not only theme or “Theme & Experience.” See how the site (or backend, portal, reports) will behave with **current form values** before clicking Save; confirm, then apply.

This doc focuses on Site Settings as the first implementation; the same pattern applies to other config UIs (feature toggles, report styles, dashboard layout, etc.). The guide below is aligned with Django Unfold’s patterns (custom action buttons, preview views, draft vs published).

---

## Current behavior vs desired

| Current | Desired |
|--------|---------|
| “Preview mode” = you **Save** with the checkbox on → values go to **session** (not DB). You then see the site with those values. So you must **save first** (to session). | **Preview** = see the effect of **unsaved** form values (no save). When happy, click **Save** to persist to DB. |
| No “Preview” button that means “show me the site with what I’ve typed so far.” | A **Preview** action: “Apply current form to preview only → open site in new tab (or modal). I’ll Save when I’m sure.” |

So the goal is: **preview before applying** (preview = temporary apply for viewing; apply = save to DB).

---

## Option 1: “Preview” button → stash form in session → open site in new tab (recommended)

**Idea:** Add a **Preview** button on the Site Settings change form. On click, send **current form data** to the server (without saving the model). Server validates, puts a subset of fields into the existing session key (`site_preview_settings`), then returns a URL. The button opens that URL (e.g. `/` or `/backend/`) in a **new tab**. The context processor already overlays session preview on `SITE`, so the new tab shows the site as if those settings were saved. You then **Save** in the original tab when you’re happy.

**Flow:**
1. User edits settings/config (e.g. Site Settings: branding, theme, feature toggles, or any other config form).
2. Clicks **Preview** (no Save yet).
3. JS collects current form values → POST to e.g. `/siteconfig/preview-from-form/` (or an admin custom URL).
4. View: validate the submitted data (reuse form validation), build payload for `site_preview_settings`, set session, return JSON `{ "redirect_url": "/backend/" }` (or portal home).
5. JS does `window.open(redirect_url)` so preview opens in a new tab.
6. User sees site/backend with “pending” config (not yet live). When satisfied, goes back to the admin tab and clicks **Save** → config persists to DB and goes live. Clear session preview on save so the live site matches DB.

**Unfold alignment:** Add a custom button (e.g. in the change form template next to Submit row, or via Unfold `@action` if it can trigger a POST with form data). Use `icon="visibility"` or `icon="preview"`, `variant="secondary"`, `target="_blank"`-style behavior (open preview in new tab).

**Pros:** No DB or model change; reuses existing session preview; clear “preview then save” flow.  
**Cons:** Preview is “live” routes with session overlay (not a dedicated preview URL that could show a banner).

---

## Option 2: Dedicated preview URL + banner (“Preview mode” banner)

**Idea:** Same as Option 1, but the redirect goes to a **dedicated preview URL** (e.g. `/siteconfig/preview/` or `/preview/`) that:
- Uses the same session overlay for `SITE`.
- Renders the **same** content as the home or backend (e.g. iframe or server-side include of the real view), or redirects to `/backend/` with a query param `?preview=1`.
- Shows a **banner** at the top: “You are previewing unsaved config. [Apply] [Discard]”. Apply = POST to save config to DB and clear preview. Discard = clear session preview and optionally redirect back to admin.

**Flow:** Same as Option 1 for “Preview” button; redirect URL is `/siteconfig/preview/` (or `/?preview=1`). That page shows the site with session overlay + banner. User then **Apply** (save to DB) or **Discard** (clear session).

**Unfold:** Same button as Option 1; the only difference is where you redirect and that you add a preview-specific template/banner.

**Pros:** Clear “this is a preview” state; explicit Apply/Discard.  
**Cons:** Slightly more work (preview view + banner + Apply/Discard endpoints).

---

## Option 3: Unfold-style “View on site” + custom preview view (get_absolute_url style)

**Idea:** SiteSettings is a singleton, so “view on site” doesn’t map to one object URL. You can still add an Unfold **action** that:
- Either: redirects to a **preview view** that reads from session (after Option 1’s “Preview” has run once). So: first time you must use “Preview” to populate session; then “View preview” just opens that URL.
- Or: the action is the **Preview** button itself: it POSTs the form (or sends form data) to an endpoint that sets session and returns redirect; the action is implemented as a link that triggers a form POST in a new tab (e.g. form `target="_blank"` and a hidden input `name="_preview"`), or via JS as in Option 1.

**Unfold:** Use `@action(description=_("Preview"), icon="visibility", attrs={"target": "_blank"})` on `SiteSettingsAdmin`. The action method can’t see unsaved form data in a GET request, so the “Preview” that uses **current form** must either:
- Submit the form (e.g. to current change URL) with a flag and handle in `response_change` (see Option 4), or
- Be implemented as a custom button that uses JS to POST form to an endpoint (Option 1).

So Option 3 is “use Unfold action for the same behavior as Option 1 or 2”: button opens preview in new tab; under the hood you still need the “stash form → session → redirect” endpoint.

---

## Option 4: “Save and preview” vs “Preview only” in submit row

**Idea:** Two submit buttons:
- **Preview** – POST the form to the **same** change URL with e.g. `name="preview"` (or `_preview=1`). Override `response_change` (or the change_view) so that when `request.POST.get("preview")`:
  - Run form validation (don’t save model).
  - If valid: build preview payload from `form.cleaned_data`, set `request.session[SESSION_KEY]`, redirect to `/backend/` (or preview URL) with `target="_blank"` by returning a response that the front end opens in a new tab (e.g. return JSON `{"redirect": "..."}` and have the Preview button submit via JS/fetch and then `window.open`).
  - If invalid: re-render change form with errors (in same tab).
- **Save** – normal save to DB; optionally clear session preview.

**Unfold:** Add a secondary button in the submit row (e.g. “Preview”, variant secondary). The trick is that a normal submit would replace the current tab. So either:
- Preview submits via JS (fetch) with form data, server returns redirect URL, JS opens in new tab; or
- Form has two submit buttons; one has `formtarget="_blank"` so the POST goes to the same URL but the response opens in the new tab (preview in new tab, admin stays in current tab). Then the server must detect preview and return redirect in that response.

**Pros:** No new URL for “preview from form”; everything goes through the change view.  
**Cons:** Change view and possibly form handling get a bit more complex; need to avoid saving on preview.

---

## Option 5: Draft vs published (separate storage)

**Idea:** Store “pending” settings in a **draft** (e.g. a `SiteSettingsDraft` model per user, or a JSON field on the user/session). Preview = a view that renders the site using **draft** when present. “Apply” = copy draft to live `SiteSettings` and clear draft.

**Unfold:** “Implement a Draft system” as in the guide: a view that renders the object (or the site) in draft status; Preview button links to that view.

**Pros:** Clear draft vs live separation; can support “last saved” vs “current draft” in UI.  
**Cons:** More model/DB work; two sources of truth; need to define which fields are draftable.

---

## Recommendation and next steps

- **Best fit for “preview before applying” with minimal change:** **Option 1** (Preview button → POST current form to endpoint → stash in session → open site in new tab). Reuses your existing session preview; no new models; clear UX.
- **If you want an explicit “You are previewing” state:** Add **Option 2** (dedicated preview URL + Apply/Discard banner) on top of Option 1.
- **Unfold integration:** Add a **Preview** button (Unfold-style: icon `visibility`, variant secondary, opens in new tab) that triggers the Option 1 flow (JS POST form to `/siteconfig/preview-from-form/`, then `window.open(redirect_url)`).

**Concrete steps for Option 1:**
1. Add a view (e.g. `preview_from_form`) that accepts POST with the same fields as the Site Settings form (or a subset). Validate (e.g. with `SiteSettingsForm` or a slim form), build `site_preview_settings` payload, set session, return JSON `{ "redirect_url": "/backend/" }`.
2. Add URL for that view (e.g. `/siteconfig/preview-from-form/`).
3. In Site Settings change form template (or via Unfold component): add a **Preview** button. On click: serialize form (or submit a copy of the form via fetch), POST to the new URL, then `window.open(data.redirect_url)`.
4. Optionally: on **Save** in admin, clear `request.session[SESSION_KEY]` so that after save, the live site matches DB (already done when “Preview mode” is unchecked).
5. (Optional) Add a small “Previewing unsaved settings” banner on the backend/portal when `request.session.get(SESSION_KEY)` is set, with link “Back to Site Settings” or “Discard preview”.

This gives you a real “preview before apply” flow and fits the Unfold pattern of a custom preview action that opens the result in a new tab.
