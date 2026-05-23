# Architecture audit — Local-First Template Marketplace

Generated: 2026-05-23T14:35:23.651549+00:00

## Layering decision

ExperienceTemplate registered as 4th pack_type, composed over existing pack lifecycle.

## Pack types

`dashboard_pack`, `experience_template`, `policy_bundle`, `workflow_pack`

## Lifecycle engine reused (zero new lifecycle code)

- `preview_pack`
- `simulate_pack`
- `analyze_pack_impact`
- `apply_pack`
- `rollback (via packages.engine.rollback)`
- `audit_pack_event`
