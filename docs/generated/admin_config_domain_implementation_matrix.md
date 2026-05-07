# Admin Configuration Implementation Matrix

| Domain | Code primitive | View/template | Model/registry | Test coverage | Gap |
|---|---|---|---|---|---|
| Blueprint Marketplace | `blueprint_contract`, `blueprint_preview`, `blueprint_impact`, `blueprint_apply`, `blueprint_rollback` | `views_administration` blueprint views and `templates/platform_runtime/blueprint_*.html` | `BlueprintInstallation`, `PlatformEventLog` | Blueprint marketplace and blueprint/pack integration tests | closed |
| App Catalog | Marketplace governance/lifecycle and integrations marketplace | Super marketplace views and tenant app catalog views | `MarketplaceApp`, `AppInstallation`, scopes, app audit | Marketplace governance/install impact and API Center e2e | partial external blocker |
| Package Rollout | `apps.packages.engine` | Package rollout, super billing, tenant finance | `InstalledPackage`, `PackageChangeLog`, `TenantSubscription` | Package rollback and marketplace impact tests | closed |
| Workflow Pack | `pack_preview`, `pack_simulation`, `pack_impact`, `pack_apply`, `pack_rollback` | Configuration pack views/templates | `PackInstallation` | Pack preview/simulation/apply/rollback and tenant pack setup tests | closed |
| Dashboard Pack | Pack engine with `dashboard_pack` type | Configuration dashboard pack routes and super dashboard catalog | `PackInstallation`, dashboard registries | Pack and dashboard shell tests | closed |
| Policy Bundles | Pack engine with `policy_bundle` type | Configuration policy bundle routes and super policy catalog | `PackInstallation`, policy bundle models | Pack and super policy tests | closed |
| Metadata Catalog | Metadata models/services/usage registry/lineage | Metadata governance/lineage and super metadata catalog | Entity catalog, dependencies, change logs | Metadata service/lineage/provenance tests | closed |
| Registries | `administration_catalog.REGISTRIES` plus app registries | Configuration module detail and super registry overview | Dashboard/workflow/integration/billing/brand/pack/usage registries | Registry center and shell inventory tests | closed |
| Runtime and Governance | Runtime defaults/inspector/resolver and change requests | Runtime truth/inspector and change request templates | `ConfigurationChangeRequest`, runtime defaults, fleet changes | Runtime truth, approval-aware UI, configuration center tests | closed |
| Migration | Super migration views and sync repair | Migration cloud, profile registry, rollback/quarantine templates | Migration run/quarantine/audit state | Super migration and URL tests | closed |
| Integration and API Center | API Center, integrations marketplace, OAuth urls | API Center dashboard and developer surfaces | Integration, API audit, OAuth/webhook models | API Center governance and developer e2e tests | closed |
| Compliance and Audit | Compliance app, audit middleware, platform events | Super compliance/audit export and tenant compliance | Audit logs, platform events, export/hash logs | Security, report export, pack/blueprint audit tests | closed |
| Security and Trust Center | Public trust, super security hub, enterprise security middleware | Marketing trust and super security templates | Security/audit generated ledgers | Super security, procurement trust, security verifier | closed |
| Billing / Subscription / Usage | Billing app, package rollout, usage registry | Super billing and tenant finance | Subscriptions, billing accounts, usage registry | Billing console and paid install gate tests | partial external blocker |
| UX/UI / Experience | Studio OS, brand experience, dashboard packs | Studio experience and configuration center | Theme/experience/dashboard config models | Theme studio, design system, premium shell audits | closed |

The implementation model is mostly repository-complete. The meaningful non-repo blockers are external billing/PSP/settlement proof and any live provider certifications.
