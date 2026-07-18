# Django admin gap analysis — 2026-07-17 (post batch 1761)

**Design SOT:** `var/design-previews/django-admin-canvas-intelligent-revamp.html`  
**Static gates:** all PASS (canvas / platformwide / scroll / shell / backoffice / live soft)  
**Honesty rule:** green audits prove markers + scroll/layout contract, not full pixel parity.

## Closed

| Area | Status |
|------|--------|
| Full-width canvas (no form cap) | DONE |
| Tenant scroll = manager canvas scroll | DONE (1759) |
| Fluid shell / blank-until-click / reveal strand | DONE (1759) |
| Command band + Form/Preview/Audit toggle | DONE |
| Two-pane workbench + changelist rail | DONE |
| Static save (no FAB) | DONE |
| **G1** Field-level smart grid (`.form-rows` half/wide) | DONE (1760) |
| **G2** Save nested inside form panel | DONE (1760) |
| **G5** Conflicting auto-fit form-body recipe | DONE (1760) |
| **G3** Preview-card stage in rail + Preview mode + drawer mount | DONE (1761) |
| **G8** Operator index context rail (shared partial) | DONE (1761) |
| **G4** Workspace-head + metrics strip on change surfaces | DONE (1761) |
| **G6** Changelist pagination inside table panel | DONE (1761) |
| **G7** 48px workspace tools column | DONE (1761) |
| **G9** Operator change/list duplicate H1 → toolbar-only | DONE (1761) |
| Tenant intelligent index catalog | DONE |
| Nested 68vh table trap | DONE |

## Still open / operator-gated

| ID | Severity | Gap |
|----|----------|-----|
| **G10** | P1 | Live Playwright screenshots soft without running server (`verify_django_admin_canvas_live.py --strict`) |

## Recommended next slice

**G10** live `--strict` screenshots with healthy Django + login, or tenant abrupt-end / exception program rows outside this Django canvas track.

## Batch 1761 proof

- `DJANGO_ADMIN_CANVAS_CONTRACT_PASS`
- Cache `20260717-parity-close`
- SW `sms-v4.05.134-django-admin-parity-close-2026-07-17`
