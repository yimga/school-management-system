# Sections 14–26 — Differentiators (Student 360, events, design system, UX rules)

## Student 360 (15.1, 26.1)

- **Implemented:** `apps/student360`: `get_student_360_summary(school_id, student_id, ...)`, `get_student_timeline_feed(school_id, student_id, limit)`. Reads from DomainEvent and linked domains (academic, finance, attendance, etc.). Permission-gated views: `student_360_page`, `student_360_export` at `/portal/student/<id>/360/` and `/360/export/`. Export pack (JSON) for data portability.
- **Remaining (optional):** Full 360 UI polish, immutable transcript view, cross-year archive UI.

## Event backbone (26.2)

- **Implemented:** `apps/events.models`: `DomainEvent` (school_id, event_type, payload, schema_version). `apps/events.services`: `emit_event(event_type, payload, school_id=..., schema_name=...)`. `apps/siteconfig.models`: `WebhookDelivery` (retries, signatures). Workflow engine action `emit_event`; student360 timeline reads from DomainEvent. Emit from service layer only; no direct DB from views.
- **Schema versioning:** DomainEvent can carry schema_version; WebhookDelivery records delivery and retries.

## Design system (26.4)

- **Implemented:** `static/css/design-tokens.css` and `design-system-unified.css`: tokens for spacing, colors, focus ring; `--school-primary` and SITE override for tenant brand. Bootstrap vars (`--bs-*`) and token layer. Theme engine (tenant brand + density) in siteconfig/school theme. Three density modes documented or applied where theme supports.
- **WCAG-aligned:** Focus states and tokens referenced in design-system-unified.css; visual regression optional in CI.

## UX rules (26.5)

- **No empty pages:** Prefer empty states with clear CTA (e.g. "Add your first student") rather than blank content.
- **Lists:** Search, filters, saved views, export, bulk actions — implement per list (backend student list, evals, etc.); document in this file or per-module UX checklist.
- **Forms:** Autosave/draft, validation, explainers — apply where implemented (e.g. report builder, onboarding).
- **Workflows:** Progress, audit trail, "why did this happen?" — workflow engine logs WorkflowRunLog; approval flows show history. Document as standard for new workflows.

## References

- Student 360: `apps/student360/services.py`, `apps/student360/views.py`, `apps/portal/urls.py`.
- Events: `apps/events/models.py`, `apps/events/services.py`, `apps/siteconfig/workflow_engine.py` (emit_event action).
- Design: `static/css/design-tokens.css`, `static/css/design-system-unified.css`, theme_root_variables and school branding.
