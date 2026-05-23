# Live Preview Engine Audit

Generated: 2026-05-23T14:09:48.833174+00:00

## Engine

apps.platform_runtime.pack_preview.preview_pack

## Routes

### Operator
- `configuration:experience_template_preview`
- `configuration:experience_template_simulation`
- `configuration:experience_template_impact`

### Tenant
- `template_marketplace:preview`
- `template_marketplace:compare (live iframe)`

## Boundary enforcement

- Tenant views call `_gate_operator_only()` before calling any pack lifecycle function — 404 on operator-only template keys.
- No cross-tenant data leakage — preview_pack receives the resolved tenant school as scope.
