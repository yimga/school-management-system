# RunMyCampus Configuration Change Governance

RunMyCampus configuration changes now use a governed rollout layer for blueprints and packs:

`request -> approval -> scheduled rollout -> dry-run -> apply -> monitor -> rollback -> audit`

## Change Requests

`ConfigurationChangeRequest` is the approval envelope for blueprint apply, blueprint rollback, pack apply, pack rollback, pack deactivate, and pack upgrade actions. It stores tenant scope, request type, target key/type/version, requester, status, reason, preview/simulation/impact snapshots, rollback plan, external blockers, approval metadata, scheduling metadata, audit reference, and idempotency key.

High-risk and platform-only changes cannot be blindly applied. Tenant school admins can request governed changes, but platform approval is required for platform-only or high-risk rollouts.

## Change Sets

`configuration_change_set.py` formalizes preview, simulation, and impact output into a non-mutating dry-run contract. A change set includes target version, tenant, preview summary, simulation summary, impact summary, dependencies, conflicts, warnings, external blockers, rollback coverage, apply eligibility, approval requirement, confirmation requirement, risk level, generation time, and generator.

Change sets are version-bound. Apply rejects stale change sets when the blueprint or pack version has changed since generation.

## Approvals And Scheduling

Approved requests can be applied immediately or scheduled with `scheduled_at`, `scheduled_by`, `schedule_status`, and `execution_window`. Scheduled requests do not apply early. Rejected and cancelled requests are terminal for apply.

All transitions emit `PlatformEventLog` audit events.

## Dependency Graph

`pack_dependency_graph.py` adds deterministic package-manager behavior:

- required packs block apply when missing
- recommended packs create warnings
- conflicting packs or blueprints block apply
- external dependencies remain explicit external blockers
- installation planning is deterministic

Pack and blueprint contracts now expose dependency metadata: required packs/modules/roles/features, recommendations, conflicts, external blockers, plan blockers, and missing setup blockers.

## Versioning And Upgrades

Blueprint and pack installations now track installed version, available version, upgrade availability, upgrade status, previous version, upgrade preview snapshot, and upgrade impact snapshot.

Upgrade previews are non-mutating. Medium/high/destructive/external-risk upgrades require approval. External readiness cannot be upgraded to live without proof.

## Tenant Boundaries

Tenant school admins can preview and request tenant-safe changes. They cannot approve platform-only or high-risk requests. Tenant-scoped views use the current school context and do not expose global registry internals or other tenants' requests.

Platform operators can approve, reject, schedule, cancel, and apply governed requests through `/configuration/change-requests/`.

## Installation Health

Installation health reports:

- healthy
- pending_approval
- scheduled
- partially_applied
- needs_attention
- external_blocked
- rollback_available
- rollback_required
- failed

Health is exposed on installation detail surfaces and can be reused by configuration center and tenant setup pages.

## Rollback And Audit

Apply remains idempotent and rollback-aware. Rollback coverage is part of the change set and installation health. External PSP/payment readiness remains an external blocker unless proof is supplied by the appropriate integration path.
