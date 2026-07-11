# Django Admin Canvas Render Gap Closure Prompt

Use this prompt when Django admin, tenant backend, Studio configuration, or live-preview surfaces look unchanged after a claimed platform-wide UI rollout.

## Mission

Audit, fix, render, validate, and repeat until the approved full-canvas Django admin contract is actually visible on operator and tenant pages. Do not accept file presence, CSS tokens, or unrendered previews as proof. Browser-rendered DOM and screenshots are the proof.

## Approved Contract

The approved surface is represented by `var/design-previews/django-admin-canvas-intelligent-revamp.html` and must map into real Django admin templates:

- Full-width canvas between sidebars.
- Command band at the top of form and list surfaces.
- Balanced form panel with responsive field columns.
- Native full-width changelist table with horizontal scroll only when needed.
- Context rail for boundary, page sections, and quick actions.
- Static save action row inside the workbench, never floating over content or footer.
- Preview-heavy surfaces use drawer, modal, popout, or new-tab preview when inline preview would be cramped.
- Same contract applies to operator `/admin/` and tenant `/admin/` without operator/tenant co-mingling.

## Required File-Level Checks

Fail the audit unless all are true:

- `templates/admin/base.html` has:
  - `data-rmc-admin-canvas-contract="intelligent-full-width"`
  - `data-rmc-admin-canvas-host="{% if is_manager_host %}operator{% else %}tenant{% endif %}"`
  - `data-rmc-admin-content="canvas-first"`
- `templates/admin/base_site.html` loads `css/rmc-admin-django-canvas-contract.css` with the current cache key and loads it late enough to win.
- `templates/admin/change_form.html` has:
  - `data-rmc-django-workspace="change-form"`
  - `data-rmc-django-command-band="change-form"`
  - `rmc-django-form-panel`
  - `data-rmc-django-form-body="1"`
  - `data-rmc-admin-form-scope="{% if is_manager_host %}operator{% else %}tenant{% endif %}"`
- `templates/admin/change_list.html` has:
  - `data-rmc-django-workspace="change-list"`
  - `data-rmc-django-command-band="change-list"`
  - `data-rmc-django-table-panel="1"`
  - `data-rmc-admin-table-contract="native-table-scroll"`
- `templates/admin/includes/admin_change_form_rail.html` has `data-rmc-django-side-panel="1"`.
- `templates/admin/submit_line.html` has `data-rmc-django-actions="static"`.
- `static/css/rmc-admin-django-canvas-contract.css` contains the structural closure selectors for all of those hooks.

## Render Audit Loop

1. Start from a clean worktree at latest `origin/main`.
2. Run `python scripts/audit_django_admin_canvas_contract.py`.
3. Render or browser-smoke both operator and tenant examples:
   - `/admin/auth/user/`
   - `/admin/auth/user/add/`
   - `/admin/auth/user/<id>/change/`
   - tenant `/admin/` equivalents
   - tenant Studio Experience, Automation, Outputs, Launch, Control
   - report card builder
   - feature controls
   - dashboard previews and theme/customizer pages
4. In rendered DOM, verify the structural markers above exist.
5. In screenshots, verify:
   - no narrow center column on wide screens
   - no overlapping save bar
   - no stacked mobile-style changelist rows on desktop
   - no large unused right void when a table or form could expand
   - previews are readable or intentionally opened as drawer/modal/popout/new tab
6. Fix any failed surface at the shared template/CSS contract first. Only add model-specific fixes where the page has a genuinely unique DOM.
7. Re-run the audit and render checks.
8. Commit only after the file audit and browser/render audit both pass or any local-environment blocker is documented with exact exception text.

## Deployment Proof

After pushing:

- Confirm deployed commit SHA equals the pushed commit.
- Confirm the HTML source loads the new `rmc-admin-django-canvas-contract.css` cache key.
- Confirm browser devtools network did not serve an older static asset.
- Confirm screenshots from production show the command band and full-canvas layout on operator and tenant admin.

## Non-Negotiables

- Do not mark this complete because a CSS file exists.
- Do not mark this complete because a design preview exists.
- Do not mark this complete without checking both operator and tenant admin.
- Do not allow tenant routes to redirect to operator admin unless the route is explicitly operator-only.
- Do not allow live preview surfaces to stay cramped inline; use drawer, modal, popout, or new tab fallback.
