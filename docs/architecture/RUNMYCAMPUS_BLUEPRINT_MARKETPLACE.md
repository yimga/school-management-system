# RunMyCampus Blueprint Marketplace

The Blueprint Marketplace turns school setup into a governed operating-model installer. A blueprint does not replace SiteConfig, Studio OS, packages, marketplace, automation, metadata, billing, compliance, or audit systems. It coordinates them through a preview-first contract.

## Contract

Blueprints are defined in `apps/platform_runtime/blueprint_contract.py`.

Each blueprint declares identity, target school type, region, maturity, owner, status, scope, modules, roles, permissions, dashboard packs, workflow packs, policy bundles, metadata templates, report templates, billing defaults, offline defaults, implementation checklist, integrations, external dependencies, safety flags, and evidence links.

Baseline blueprints:

- Private Primary School
- Private Secondary School
- Cameroon GCE School
- Bilingual School
- Boarding School
- International School
- Multi-campus Network
- Low-connectivity School

## Preview

`apps/platform_runtime/blueprint_preview.py` computes changes without mutating data. Preview returns modules, roles, permissions, dashboard packs, workflow packs, policies, metadata templates, report templates, billing posture, offline defaults, conflicts, warnings, external requirements, rollback plan, and audit summary.

Preview blocks unsafe apply when a tenant is missing, a platform operator is required, or the blueprint is not installable.

## Impact Analysis

`apps/platform_runtime/blueprint_impact.py` converts preview into impact categories: low, medium, high, destructive, external_required, tenant_blocked, and platform_only.

Impact answers what changes, who is affected, which roles gain access, which workflows activate, which dashboards change, which policies become active, which billing/package rules change, which external dependencies remain, what can be rolled back, and what cannot.

## Apply

`apps/platform_runtime/blueprint_apply.py` requires a successful preview and explicit confirmation for medium/high-risk blueprints. Apply is tenant-scoped, idempotency-key aware, audited, and records `BlueprintInstallation`.

Apply writes only a target-school blueprint marker in `School.settings`, stores a rollback snapshot, and calls the existing package engine with a blueprint payload marker. It does not enable PSPs, settlement, live payment readiness, or external certification.

## Rollback

`apps/platform_runtime/blueprint_rollback.py` requires confirmation and an existing applied installation. Rollback restores the settings snapshot and deactivates package markers through the package engine. It prefers disable/deactivate behavior and does not delete school operational data.

## Audit

Blueprint actions emit `PlatformEventLog` events:

- `blueprint_previewed`
- `blueprint_impact_viewed`
- `blueprint_apply_requested`
- `blueprint_applied`
- `blueprint_apply_failed`
- `blueprint_rollback_requested`
- `blueprint_rolled_back`
- `blueprint_rollback_failed`

Each event carries actor, tenant/school, blueprint key, result, reason, and installation id where available.

## Tenant Boundaries

Platform blueprint management is under `/configuration/blueprints/` and requires control-plane access. Tenant setup is under `/school/setup/blueprints/` and lists tenant-safe blueprints only. Platform-only or operator-required blueprints are hidden or blocked for tenant users.

## External Honesty

Blueprints may declare PSP, settlement, multi-currency, or certification dependencies. These remain `external_required` until externally proven. No blueprint marks live settlement or PSP readiness complete.

## Future Marketplace Path

The current repo-scope slice establishes the installer contract, preview, impact, apply, rollback, audit, and tenant setup. Future depth can bind package payloads to concrete dashboard/workflow/policy assignments, add richer diff visualizations, and connect implementation checklists to onboarding progress.
# Governance Expansion

Blueprint Marketplace apply now has a formal governance layer:

`preview -> impact -> change set -> request -> approval -> schedule -> apply -> monitor -> rollback -> audit`

Blueprint contracts expose dependency metadata for required packs/modules/roles/features, recommended packs, conflicts, external blockers, plan blockers, and missing setup blockers.

`BlueprintInstallation` now tracks installed version, available version, upgrade availability, upgrade status, previous version, upgrade preview, and upgrade impact. High-risk or platform-only blueprint changes require approval before apply.

Tenant school admins can preview tenant-safe blueprints and submit change requests. Platform operators approve, reject, schedule, cancel, and apply through the configuration change request queue.
