# Backend Entity Console & Toggle Preview

## Entity Console

**What it is:** The Entity Console (`/authentication/backend/entities/` or `accounts:backend_entity_console`) is an admin-only, beta UI for managing core entities (e.g. students, teachers, classrooms) via a form/table interface instead of the Django admin.

**How it works:**
- Access is restricted to staff/superuser or users with role `ADMIN`. It can be further limited or disabled via **Site Settings → backend_feature_flags**:
  - `enable_entity_console`: turn the feature on/off (default: true).
  - `allowed_roles_entity_console`: list of roles that may access it (e.g. `["ADMIN","IT_ADMIN"]`).
- The view renders `accounts/entity_console.html`, which can list and edit entities (students, teachers, etc.) in a day-to-day backend style, separate from the full Django admin.
- **Integration:** It sits under the **Backend Dashboard** in the sidebar (Admin Panel → Entity Console). Use it for quick entity management; use **Admin Interface** for full config/setup.

## Toggle Preview (Sandbox / Staged changes)

**What it is:** A “preview mode” that lets staff stage theme/palette/site changes without applying them to the live site. The blue banner (“Preview ready - Staged changes can be viewed…”) appears when this mode is active.

**How it’s configured:**
- **URL:** `siteconfig:toggle_preview_mode` — toggles preview on/off; optional `?next=<path>` redirects after toggle.
- **Clear preview:** `/siteconfig/customizer/clear-preview/` — clears staged preview and returns to live.
- **Context:** `SITE.is_preview` (or equivalent) is set when preview is on; templates (e.g. `portal_base.html`, `base.html`, admin base) show the banner and “Toggle preview” / “Toggle sandbox” / “Clear preview” buttons.
- **Behaviour:** Changes made in preview (e.g. in Site Settings customizer) are stored in a sandbox; they only go live when you exit preview or apply them. This keeps config/setup safe before publishing.

## Chathead & Messaging

- **Messages** are under **Communication** in the sidebar only (removed from Account). Unread count badge appears next to “Messages” where that link is shown.
- A **chathead** (floating button for staff to open messaging) can be added in the portal base template: a fixed-position button that links to `accounts:user_messages` and optionally opens a small messaging panel. Implementation would go in `templates/partials/portal_sidebar.html` or `portal_base.html` as a floating element.

## My Profile (password, picture, etc.)

- **My Profile** is under **Account** in the sidebar and points to `accounts:user_profile`.
- Ensure the profile view and template support: change password (Django auth), profile picture upload (if using a user/profile model with avatar), and any other self-service fields. These are typically handled in `apps/accounts/views.py` (`user_profile`) and the profile template.
