# Premium UX manual pass (BR-13)

## Checklist (each page)

- [ ] `data-page-archetype` present
- [ ] Studio OS page_header where applicable
- [ ] No broken placeholder copy
- [ ] Focus visible / keyboard
- [ ] Responsive ≤768px
- [ ] ≤3 clicks for task (see TOP_20_LOW_CLICK_TASKS)

## Touring

- **Super (control plane):** **Page tour** on `/super/trust/`, `/super/migration/csv-diff/`, `/super/tools/governed-query/` → `siteconfig:tour_steps_api?context=super_trust|super_migration|super_governed` + `static/js/control-plane-tour.js`.
- **Tenant backend:** `tour_steps_api?context=backend_dashboard` + first-login tour (unchanged).
- **Setup Studio** linked from System config outcome banner (`console_domains_hub`).

## Sign-off

Product + design **date + initials** on release.

**Per release (non-automated):** Complete this checklist before tagging; CI does not replace this pass.
