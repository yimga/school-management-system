# Admin: Comprehensive UX Fixes and Improvements

Plan to address: (1) dropdown/primary color aligned to site accent, (2) submit row Back button with referrer behavior and layout, (3) "Is active" toggle red (off) / green (on), (4) other suggested improvements.

---

## Issue 1: Admin primary color (dropdown / focus / buttons) shows blue instead of site accent

**Cause:** Unfold and our CSS use Tailwind-style primary or fallbacks like `#2563eb` / `#3b82f6`. The site accent (purple/pink from design system or SiteSettings) is not applied to form widgets and some links.

**Scope:** All admin change forms (dropdowns, select highlight, focus rings), Unfold helpers (search focus, empty state "Add" button), and any CSS that uses `--color-primary-600` / `-500` with a blue fallback.

### 1.1 Define admin primary CSS variables from site primary

- In **design-tokens.css** or **admin base_site.html**, set in admin context: `--color-primary-500` and `--color-primary-600` to `var(--color-primary)` (or site primary) so existing `var(--color-primary-600, #2563eb)` stops falling back to blue.

### 1.2 Override Unfold Tailwind primary for admin

- In **admin-polish.css** or **admin-flow.css**: override select/dropdown selected and focus rings to use `var(--color-primary)` / `var(--focus-ring-color)`; override search box focus (e.g. `[class*="outline-primary"]`) to use `var(--color-primary)`.

### 1.3 Replace blue fallbacks in our admin CSS

- In **admin-sidebar-backend-inspired.css**, **admin-sidebar-scroll.css**, **admin-color-preview.css**, **color-palette-studio.css**: replace `#2563eb` / `#3b82f6` with `var(--color-primary-600, var(--color-primary))`.

---

## Issue 2: Submit row Back button with "return from where I came" behavior

**Goal:** Add a "Back" control on the **left** of the submit row. Clicking it goes to referrer when same-origin and sensible; otherwise to admin index.

### 2.1 Submit row layout and Back link (injection)

- In **admin/base_site.html** (footer block), add a script that runs on DOMContentLoaded:
  - Find `#content .submit-row`. If not found, exit.
  - Prepend a single "← Back" link as the first child of `.submit-row`.
  - Style the row with `display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;` so existing buttons stay grouped on the right. Layout: `[← Back]  …  [Save and add another] [Save and continue editing] [Save]`.

### 2.2 Back button URL (referrer vs index)

- `referrer = document.referrer`. If empty → `href = admin index`. Else parse with `new URL(referrer)`; if different origin → `href = admin index`. Optional: if `referrer === location.href` → `href = admin index`. Otherwise `href = referrer`.

### 2.3 Styling and scope

- **Back button = secondary style:** Style like "Save and continue editing" (dark background + light border), not the solid purple "Save" button. Use `var(--admin-content-text)`, `var(--admin-content-border)`.
- **Variable buttons:** Row may have 2 or 3 buttons; script adds one Back link and works regardless. Apply on **all** admin change forms that have `.submit-row`. Sticky row on Site settings already includes the injected Back link.

---

## Issue 3: "Is active" toggle – red (off) / green (on)

**Problem:** The "Is active" toggle (and similar boolean toggles) use the framework default teal-blue when on. Agreed convention: **red = inactive/off**, **green = active/on**.

### Fix

- Add CSS in **admin-polish.css** or **admin-flow.css** that targets the toggle/switch used for "Is active":
  - **Unchecked (off / inactive):** Track and/or handle use red: `var(--admin-content-danger)` or `--color-danger` (e.g. `#dc2626`).
  - **Checked (on / active):** Track and/or handle use green: `var(--color-success)` (e.g. `#10b981` / `#16a34a`).
- Target Bootstrap `.form-check-input` (checkbox) or Unfold’s switch component; use `:checked` and `:not(:checked)`.
- If the same component is used for other booleans ("Is published", "Feature enabled"), apply the same red/green convention site-wide, or scope to labels containing "active", "enabled", "published" if only those should be semantic red/green.

---

## Other suggestions and improvements

- **Sidebar user card (white card in dark sidebar):** Style the admin user card at the bottom of the sidebar with theme tokens (e.g. `background: var(--admin-content-surface)` or `--admin-sidebar-*`) so it matches the dark sidebar in dark theme. Target Unfold navigation_user or the wrapper with avatar and "admin" text.

- **Sticky submit row for all change forms:** Consider applying the same sticky rule (position sticky, bottom 0, background, border-top, z-index) to `#content .submit-row` globally in **admin-flow.css** so long forms (User edit, etc.) always show Save at the bottom of the viewport. Avoid double-apply or conflict with the Site settings–specific rule.

- **Breadcrumb and context:** Ensure "Dashboard" or the model list appears in the breadcrumb so Back + breadcrumb give clear exit paths.

- **Other toggles:** After fixing "Is active," audit other checkboxes/switches (e.g. staff flag, is_superuser, feature flags). Use red/green only where the meaning is active/inactive; leave neutral toggles with default or primary if preferred.

- **Focus order and a11y:** Ensure the injected Back link is in the tab order and has an accessible name (e.g. "Back to previous page" or "Back to dashboard").

- **Empty state CTA:** After fixing primary variables (Issue 1), the Unfold "Add" button on empty results will follow the site accent; confirm contrast (white or accent-fg on primary) meets WCAG.

---

## Implementation order

1. **CSS variables:** Set `--color-primary-500` / `--color-primary-600` in admin context from `--color-primary`.
2. **CSS overrides:** Select/dropdown and focus rings; replace blue fallbacks in admin-sidebar and related CSS.
3. **Toggle:** Add red (off) / green (on) for "Is active" and similar toggles.
4. **Back button:** Add injection script and referrer logic in admin base_site.html; style submit row and Back link (secondary style).
5. **Other (optional):** Sidebar user card theme, sticky submit row for all forms, a11y and breadcrumb checks.

---

## Files to touch (summary)

- **design-tokens.css** or **admin base_site.html**: `--color-primary-500` / `--color-primary-600` for admin.
- **admin-polish.css** or **admin-flow.css**: overrides for select/dropdown, focus rings, toggle red/green.
- **admin-sidebar-backend-inspired.css**, **admin-sidebar-scroll.css**, **admin-color-preview.css**, **color-palette-studio.css**: fallbacks to `var(--color-primary)`.
- **admin/base_site.html**: script to inject Back into `.submit-row` + referrer logic; styles for submit row + Back link.
- **templates/unfold/helpers/navigation_user.html** (if overridden): or CSS to theme the sidebar user card.
