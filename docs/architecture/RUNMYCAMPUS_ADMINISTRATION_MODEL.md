# RunMyCampus Administration Model

Status: `ADMINISTRATION MODEL READY - REPO SCOPE`

RunMyCampus separates platform operation, platform configuration, tenant school configuration, role workspaces, and raw technical administration.

## `/super/`

Platform Command Center.

Used by RunMyCampus operators to operate the platform: tenant registry, tenant 360, implementation pipeline, support, billing oversight, marketplace governance, developer ecosystem oversight, external dependency command, security, trust, compliance, system health, and proof ledger.

## `/configuration/`

Platform Configuration Center.

Used by platform admins and configuration operators to configure platform behavior without duplicating existing systems. This surface is a facade over SiteConfig, Studio OS, metadata, runtime blueprints, packages, marketplace, integrations, automation, API center, billing, finance, compliance, platform runtime, and enterprise security.

Modules:

- Blueprint Marketplace
- App Catalog
- Package Rollout
- Workflow Packs
- Dashboard Packs
- Policy Bundles
- Metadata Catalog
- Registry Center
- Runtime + Governance
- Migration Center
- Integration + API Center
- Compliance + Audit Configuration
- Security + Trust Configuration
- Billing / Subscription / Usage Rules
- UX/UI Experience Configuration

Every module exposes purpose, owner, scope, status, primary action, existing route, and proof link. External payment and marketplace monetization rows remain `external_required` until provider and settlement proof exists.

## Tenant School Configuration

Tenant schools use `/school/settings/` or `/siteconfig/school-configuration/`.

The School Configuration Center is tenant-scoped only. It covers School Profile, Academic Year / Term, Classes / Subjects, Grading Rules, Report Templates, Fees, Roles / Permissions, Parent Portal, Teacher Portal, Apps, Workflows, Offline Settings, Branding / Theme, and Security / Audit.

Tenants do not see platform global registries, system closure maps, global external dependency command, cross-tenant billing ledgers, platform app review, or raw platform models.

## Role Workspaces

Teacher, parent, and student workspaces remain role-specific operational surfaces. They are not platform configuration surfaces.

## `/admin/` And `/internal-admin/`

`/admin/` remains compatible and split by host:

- manager/root host: `platform_admin_site`
- tenant host: `tenant_admin_site`

`/internal-admin/` is an explicit technical fallback alias that redirects to the current host's canonical `/admin/` mount. It avoids duplicate admin namespace registration while making raw admin intent clear.

Raw admin is not the primary product UX. Product workflows should use `/super/`, `/configuration/`, and tenant School Configuration Center.

## Boundary Rules

- Platform-only configuration requires control-plane access.
- Tenant school configuration requires tenant school access.
- Tenant hosts return 403 for `/configuration/`.
- `/configuration/` does not expose secrets.
- External dependencies remain `external_required` unless verified by external evidence.
- `/admin/` compatibility is preserved.
