# Tenant Option A Palette, Lifecycle, And Blueprint Audit Prompt

Use this prompt when implementing the approved tenant-only Option A direction.

## Scope

- Focus on tenant-wide surfaces only.
- Include signup, email verification, login/MFA, first-login setup, Setup Studio, blueprint setup, import/migration, Theme & Experience, Money Center, dashboard, messages, academics, reports, workflow center, feature controls, launch readiness, and daily school operations.
- Do not redesign operator surfaces in this pass except to verify tenant/operator separation.

## Audit First

1. Build a tenant route and template inventory for the scope above.
2. Identify pages using sparse text layouts, cramped forms, broken preview surfaces, excessive vertical length, or non-tenant destinations.
3. Identify all tenant live-preview surfaces and classify preview delivery as inline, sidecar, modal, popout, or new tab fallback.
4. Trace signup to daily operation:
   signup -> email verification -> tenant host login -> MFA/profile -> setup -> blueprint -> import -> brand/theme -> readiness -> daily school dashboard.
5. Audit tenant-safe blueprints with `preview_blueprint(..., platform_operator=False)` and fail on `pack_not_found`.
6. Verify no tenant route links to `/super/` or operator-only `/admin/` for tenant configuration work.

## Design Contract

- Apply Option A warm command workspace where the current tenant page is sparse, cramped, or hard to act on.
- Use the full available canvas intelligently; no narrow centered columns for operational work.
- Use bounded scroll inside long panels and progressive sections for long forms.
- Keep page actions close to the work and never hidden behind large empty areas.
- Use color meaningfully across header, sidebar active state, hero, buttons, status pills, charts, tables, alerts, and form focus states.
- Preserve accessibility and contrast; color cannot be the only signal.

## Theme And Palette Contract

- Palette cards must preview more than swatches.
- Every palette preview must show:
  - tenant header accent
  - sidebar active state
  - primary and secondary buttons
  - success, warning, danger, info
  - card and table accents
  - chart colors
  - role dashboard preview
- Theme & Experience must offer a reliable live preview path:
  - inline preview only if it fits without crowding
  - sidecar/drawer for complex pages
  - popout or new tab if iframe/frame rendering is blocked
  - clear status when preview is using draft values versus saved values

## Blueprint Contract

- Tenant admins must see tenant-safe blueprints only.
- Each blueprint row must show preview and current readiness.
- Selected blueprint must show `Apply tenant blueprint`, `Request approval`, or `Resolve blockers before apply`.
- Blockers must show human-readable reasons.
- External blockers must remain honest and must not be hidden.
- Platform-only blueprint management links must not appear on tenant pages.

## Validation

- Run focused tenant tests for:
  - tenant blueprint setup
  - tenant onboarding links
  - tenant lifecycle
  - theme and experience
  - operational workbench surfaces
- Run `python manage.py check`.
- Run a direct blueprint preview audit for all tenant-safe blueprints.
- Re-run the route/template inventory and close remaining gaps before commit.
