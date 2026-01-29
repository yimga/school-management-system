# Backend: Entity Console and Toggle Preview

This document explains **Entity Console** and **Toggle Preview** — how they work and how they fit into the school management system.

## Do you need them?

- **Entity Console**: Optional. Use it if you want to manage students (and related entities) from the portal without opening Django Admin. If you only use `/admin` for that, you can disable it in **Site settings → Backend feature flags → Enable entity console**, or hide the sidebar link by customizing the portal sidebar.
- **Toggle Preview**: Optional. Use it if staff need to preview theme/customizer changes before they go live. If you don’t use the customizer or staged previews, you can ignore it or hide the preview banner via site settings (`preview_toggle_enabled`).

---

## Entity Console

### What it is

**Entity Console** is an admin-only portal page that lets staff manage core entities (e.g. students) from the frontend using headless APIs, without going through Django Admin. It is part of the “backend” operator experience (Backend Console, Workflow Center, Entity Console, Bulk Entity Import).

### How it works

- **Access**: Only users who are staff, superuser, or have role `ADMIN` can open Entity Console. Access is further gated by:
  - **Site settings**: `SiteSettings.backend_feature_flags.enable_entity_console` (default: true). If disabled, the view returns 403.
  - **Allowed roles**: `backend_feature_flags.allowed_roles_entity_console` can restrict which roles see the console (e.g. `["ADMIN", "IT_ADMIN"]`). If set, only those roles (or staff/superuser) are allowed.
- **URL**: `/accounts/backend/entities/` (name: `accounts:backend_entity_console`).
- **Template**: `accounts/entity_console.html`. It includes:
  - Create student form (first name, last name, admission number, status, academic year, classroom).
  - Update / Delete student form (by student ID, status updates, delete).
  - Frontend calls to headless APIs to perform create/update/delete; visibility and actions are RBAC/claims-aware where implemented.
- **Integration**: Linked from the portal sidebar under “Admin Panel” (Entity Console, Bulk Entity Import) and from Django Admin “People & Access” (Entity Console). It uses the same auth and permission model as the rest of the portal; no separate “entity console app.”

### Summary

| Aspect | Detail |
|--------|--------|
| **Purpose** | Manage entities (e.g. students) from the portal via headless APIs, with RBAC. |
| **Who** | Staff / superuser / ADMIN (and optionally other roles via feature flags). |
| **Where** | Portal route `accounts:backend_entity_console`; sidebar and admin links. |
| **Config** | `SiteSettings.backend_feature_flags.enable_entity_console`, `allowed_roles_entity_console`. |

---

## Toggle Preview (Preview / Sandbox mode)

### What it is

**Toggle Preview** (also called “preview” or “sandbox” mode) is a way for staff to **stage changes** (e.g. theme, customizer, report card styles) and see how they look **before** they are applied for everyone. When preview is “on,” the app can show a different state (e.g. staged theme) without persisting it as the live site setting until the operator is satisfied.

### How it works

- **Session flag**: A session key `admin_preview_mode` (in code: `PREVIEW_MODE_SESSION_KEY`) stores whether preview is on or off for the current user.
- **Toggle view**: Staff use the **Toggle preview** (or “Toggle sandbox”) link, which hits `siteconfig:toggle_preview_mode`. That view:
  - Is protected by `@staff_member_required`.
  - Flips the session value: if preview was off, it turns on; if on, it turns off.
  - Redirects to `next` (or referrer, or `/`).
- **Banner**: When preview is **on**, the portal base template shows a warning-style banner: “Preview mode — …” with:
  - **Toggle sandbox**: same URL (`siteconfig:toggle_preview_mode`) to turn preview off (or on again).
  - **Clear preview**: link to `/siteconfig/customizer/clear-preview/` to clear the staged preview state.
- When **preview is off** but the site has “preview ready” (staged changes), an info banner can show “Preview ready — …” with a button whose label comes from `PREVIEW_TOGGLE_LABEL` (e.g. “Toggle preview”) to turn preview on.
- **Middleware**: `PreviewModeMiddleware` runs on each request. It sets:
  - `request.preview_mode_enabled`: true if either the `X-Preview-Mode` header or the session says preview is on.
  - `request.preview_mode_source`: `"header"` or `"session"` (or None).
  - `request.preview_act_as_role`: from session, for “act as role” preview if used.
- **Context**: Templates get `PREVIEW_MODE_ENABLED`, `PREVIEW_TOGGLE_ENABLED`, `PREVIEW_TOGGLE_LABEL`, `PREVIEW_BANNER_TEXT`, etc., so the banner and button text can be customized.

So: **Toggle Preview** = “turn preview/sandbox mode on or off for my session.” When it’s on, you see staged changes; when you’re done, you use Toggle again or Clear preview so changes don’t stay in preview state.

### Summary

| Aspect | Detail |
|--------|--------|
| **Purpose** | Let staff view staged changes (e.g. theme/customizer) before making them live. |
| **Who** | Staff only (`@staff_member_required` on the toggle view). |
| **How** | Session key `admin_preview_mode`; toggle view flips it; middleware sets `request.preview_mode_enabled`. |
| **UI** | Banner when preview is on (or when “preview ready”); “Toggle sandbox” / “Clear preview” links. |
| **URL** | Toggle: `siteconfig:toggle_preview_mode` (e.g. `/siteconfig/preview/toggle/`). |

---

## Relation to the rest of the tool

- **Entity Console** is one of the backend operator pages (with Backend Dashboard, Workflow Center, Bulk Entity Import). It uses the same portal base, auth, and RBAC as the rest of the portal; it does not run as a separate app.
- **Toggle Preview** is a siteconfig feature used wherever “preview” or “sandbox” behavior is implemented (e.g. theme/customizer, report card style preview). The portal base template shows the preview banner and links; views that respect `request.preview_mode_enabled` can serve different content when preview is on.
