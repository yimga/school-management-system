# Phase 4 — Control plane operator UX — checklist

**SOT:** ZIP Phase 3 — **COMPLETE**.

## Python

- [x] `apps/siteconfig/control_outcome_center.py` — `OUTCOME_GROUP_SPECS`, builders
- [x] `apps/siteconfig/views.py` (or related) — `console_domains_hub` context
- [x] `apps/studio_os/views.py` — control mode, `control_outcome_sections`, operator model
- [x] `apps/siteconfig/tests/test_control_outcome_center.py`

## Templates

- [x] `templates/siteconfig/console_domains_hub_control_plane.html`
- [x] `templates/siteconfig/partials/configuration_control_center_operator_model.html` (and `configuration_control_center_outcomes.html`)
- [x] `templates/studio_os/partials/control_mode_canvas.html`
- [x] `templates/studio_os/modes/control.html`

## Routes (verify names resolve on manager)

- [x] `super:` names + root names per `test_control_outcome_center.py`

## Validation

- [x] `python -m pytest apps/siteconfig/tests/test_control_outcome_center.py`

## Acceptance

- [x] Outcome grouping (9 groups) + operator model (6 steps) + why-enabled + stability badges
