# Apply / Customize / Rollback Audit

Generated: 2026-05-23T14:09:48.833174+00:00

## Apply

- Operator: `configuration:experience_template_apply (reuses pack_apply_view)`
- Tenant: `template_marketplace:apply (delegates to apply_pack)`

## Customize

- Tenant: `template_marketplace:customize (edits TemplateAssignment.customizations JSON)`
- Audit event: `template.customized`

## Rollback

- Tenant: `template_marketplace:rollback (delegates to packages.engine.rollback)`
- Audit event: `template.rolled_back`

## Audit model

apps.brand_experience.models_template.TemplateAuditEvent (append-only, sanitized payload)
