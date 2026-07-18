# Django admin tenant scroll parity (batch 1759)

## Problem (live screenshots 2026-07-17)

Tenant `/admin/` was unscrollable with a large blank void; catalog/content appeared only after clicking the blank surface. Sidebar text overlapped main chrome.

## Root cause

1. Tenant shell used `rmc-app-shell--fluid` (flex column) → sidebar stacked over canvas.
2. Tenant never set `data-rmc-cp-scroll="canvas"`; only manager got `#cp-main-content` as scroller.
3. Nested `overflow: clip/hidden` + 68vh changelist panes trapped content.
4. `rmc-reveal` could leave page-explain at opacity:0 when scroll root was wrong.

## Fix

- Same grid + canvas scroll as manager (`cp-admin-canvas-main`, `data-rmc-cp-scroll=canvas`).
- `rmc-backoffice-scroll-10x.css` covers `admin-premium-shell`.
- Terminal overflow:visible on large surfaces; changelist no nested max-height.
- Admin shells: immediate reveal; paginator skips bounded zones.
- Cache bust `20260717-tenant-scroll-parity`; SW `sms-v4.05.132`.

## Proof

- `DJANGO_ADMIN_CANVAS_CONTRACT_PASS`
- `DJANGO_SURFACE_PLATFORMWIDE_CONTRACT_PASS`
- `TENANT_SURFACE_SCROLL_CONTRACT_PASS`
- `SHELL_SCROLL_CONTRACT_AUDIT_PASS`
- `BACKOFFICE_SCROLL_AFFORDANCE_PASS`
- `DJANGO_ADMIN_CANVAS_LIVE_SOFT_PASS` (live screenshots need running server)

## Operator action

Hard-refresh tenant `/admin/` (and any open changelist/change-form) after deploy so SW + CSS bust apply.
