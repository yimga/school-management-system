# RunMyCampus Pack Installation Model

This repo-scope slice makes workflow packs, dashboard packs, and policy bundles previewable, simulatable, impact-analyzed, installable, auditable, deactivatable, and rollback-aware.

## Contract

`apps/platform_runtime/pack_contract.py` defines `PackContract` for:

- `workflow_pack`
- `dashboard_pack`
- `policy_bundle`

Each pack declares identity, target roles, school types, owner, version, included items, prerequisites, external dependencies, tenant scope, safety level, preview/simulation/apply/rollback availability, and audit requirements.

## Preview

`pack_preview.py` is non-mutating and tenant-scoped. It returns included changes, prerequisites, conflicts, warnings, external required items, affected roles, affected workflows/dashboards/policies, rollback posture, and `can_apply`.

## Simulation

`pack_simulation.py` performs dry-run simulation only:

- workflow packs show trigger, conditions, actions, messages, escalations, and audit events that would be emitted
- dashboard packs show layout, widgets, actions, empty states, role visibility, and mobile behavior
- policy bundles show allowed/blocked/requires-approval posture and audit requirements

## Impact

`pack_impact.py` classifies impact as low, medium, high, destructive, external required, approval required, tenant blocked, or platform only. It lists affected roles, routes, dashboards, workflows, policies, billing posture, rollback coverage, and audit coverage.

## Apply

`pack_apply.py` requires successful preview, simulation for high-risk packs, confirmation for medium/high/destructive packs, tenant scope, and audit. It creates `PackInstallation`, records snapshots, delegates package metadata to the existing package engine, and keeps PSP/live external dependencies as blockers rather than completed readiness.

## Deactivate And Rollback

`pack_rollback.py` supports deactivation and rollback. Rollback restores captured school settings posture and deactivates the package-engine marker when present. It avoids destructive school-data deletion.

## Tenant Boundaries

`/configuration/...` is control-plane only. `/school/setup/packs/` exposes tenant-safe packs only and scopes every apply/deactivate/rollback to the request tenant school.

## Blueprint Integration

Blueprint preview now includes pack preview summaries, simulation readiness, pack impact summaries, install blockers, and rollback posture. Blueprint apply creates linked `PackInstallation` rows through the pack apply engine.

## Audit Events

Pack lifecycle events include preview, simulation, impact, apply requested, applied, apply failed, deactivated, rollback requested, rolled back, and rollback failed.

## External Honesty

No pack completes PSP/live settlement readiness. External requirements remain explicit blockers until proven outside this repo.
# Governance Expansion

Pack installation now participates in Configuration Change Governance. High-risk or platform-only pack applies require a `ConfigurationChangeRequest`, approval by a platform operator, and a fresh change set before apply.

The pack contract includes dependency metadata:

- `requires_packs`
- `requires_modules`
- `requires_roles`
- `requires_features`
- `recommends_packs`
- `conflicts_with_packs`
- `conflicts_with_blueprints`
- `blocked_by_external`
- `blocked_by_plan`
- `blocked_by_missing_setup`

`PackInstallation` stores installed version, available version, upgrade state, previous version, upgrade preview, and upgrade impact. Installation health is calculated through `calculate_pack_installation_health`.

External PSP/payment readiness is never marked complete by pack apply. It remains an external blocker until integration proof exists.
