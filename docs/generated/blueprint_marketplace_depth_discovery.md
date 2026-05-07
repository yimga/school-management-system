# Blueprint Marketplace Depth Discovery

Status: discovery_complete

Scope: repo

Finding: Blueprint Marketplace depth should extend existing runtime_blueprints, packages, marketplace, SiteConfig, metadata, automation, dashboard, policy, billing, and audit primitives instead of creating a duplicate installer.

| Existing primitive | File/module | Purpose | Reusable? | Missing behavior | Risk | Recommended reuse path |
|---|---|---:|---:|---|---|---|
| runtime_blueprints proxy owner models | `apps/runtime_blueprints/models.py` | Bounded-context facade over legacy BlueprintPack, TenantBlueprint, dashboard packs, workflow packs, and report templates. | yes | No single preview/apply/rollback contract. | Duplicate blueprint ownership. | Keep owner facade; add platform runtime orchestration. |
| package engine | `apps/packages/engine.py` | Validate, preview, apply, promote, and rollback package payloads. | yes | Blueprint-specific confirmation gate. | Blind install if exposed directly. | Blueprint apply stores installation state and calls package engine with a blueprint payload marker. |
| InstalledPackage / PackageChangeLog | `apps/packages/models.py` | Tenant package lineage and rollback evidence. | yes | Blueprint preview and settings snapshot. | Package logs alone do not explain operating-model intent. | Use minimal `BlueprintInstallation` for blueprint state. |
| marketplace pack registry | `apps/marketplace/pack_registry.py` | Static workflow, dashboard, theme, policy, and app catalog metadata. | yes | Cross-domain blueprint composition. | Catalog-only marketplace. | Blueprint contract references packs by stable names and external blockers. |
| automation workflow galleries | `apps/automation/*gallery*.py` | Workflow templates and playbook definitions. | yes | Blueprint-level impact summary. | Workflow activation without operator awareness. | Preview and impact list workflow packs and require confirmation. |
| dashboard/workflow packs | `apps/siteconfig` models via `apps/runtime_blueprints` | Dashboard/workflow pack assignments and tenant workflows. | yes | Installer orchestration. | Manual configuration drift. | BlueprintInstallation records intended pack set for later deep assignment. |
| metadata usage registry | `apps/metadata/usage_registry.py` | Metadata lineage and blast-radius helpers. | yes | Blueprint metadata-template wording. | Metadata templates without lineage. | Reuse package engine payload preview. |
| PlatformEventLog | `apps/platform_runtime/events.py` and `models.py` | Append-only audit trail. | yes | Blueprint event catalog entries. | Installer actions without tenant/actor audit. | Emit blueprint preview, impact, apply, fail, rollback events. |
| tenant settings / SiteConfig | `apps/schools/models.py`, `apps/siteconfig/` | Tenant-scoped settings and configuration. | yes | Blueprint marker and rollback snapshot. | Cross-tenant mutation. | Write only target school settings and store rollback snapshot. |
| configuration center facade | `apps/platform_runtime/views_administration.py` | `/configuration/` control-plane facade. | yes | Blueprint depth routes. | Dummy links or blind apply. | Extend `/configuration/blueprints/`. |
| tenant configuration center | `config/tenant_urls.py` | `/school/settings/` tenant configuration. | yes | Tenant-safe blueprint setup. | Tenant exposure to platform registries. | Add `/school/setup/blueprints/` with tenant-safe blueprints only. |
