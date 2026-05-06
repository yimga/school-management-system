# Administration Surface Map

Classification: `ADMINISTRATION MODEL READY - REPO SCOPE`

This map records the administration and configuration fronts created for the current repo state. The model does not duplicate existing systems; it organizes SiteConfig, Studio OS, runtime blueprints, packages, marketplace, integrations, automation, metadata, API center, billing, finance, compliance, platform runtime, and security behind a governed facade.

| Surface | Belongs to | Current user | Status | Recommended action |
| --- | --- | --- | --- | --- |
| `/super/` | `/super` | RunMyCampus platform operator | ready | Keep as Platform Command Center |
| `/configuration/` | `/configuration` | Platform configuration operator | ready | Use as governed configuration facade |
| `/configuration/blueprints/` | `/configuration` | Platform configuration operator | ready | Preview-first blueprint marketplace |
| `/configuration/packages/` | `/configuration` | Package operator | ready | Package rollout facade |
| `/configuration/workflow-packs/` | `/configuration` | Automation operator | ready | Workflow packs with simulation |
| `/configuration/dashboard-packs/` | `/configuration` | Experience operator | ready | Dashboard packs with permissions and mobile posture |
| `/configuration/policy-bundles/` | `/configuration` | Policy operator | ready | Auditable and reversible policy bundles |
| `/configuration/registries/` | `/configuration` | Runtime operator | ready | Registry Center with owner, scope, route, proof, and drift posture |
| `/school/settings/` | `/school` | Tenant school admin | ready | Tenant-scoped School Configuration Center |
| `/siteconfig/school-configuration/` | `/school` | Tenant school admin | ready | Alias to School Configuration Center |
| `/internal-admin/` | `/internal-admin` | Technical admin | ready | Redirect alias to split `/admin/` raw admin |
| `/admin/` | `/internal-admin` | Technical admin | ready | Keep compatible; do not promote as product UX |

External blockers remain: `global_payments`, `marketplace_monetization`.

Boundary tests added:

- `apps.platform_runtime.tests.test_administration_model`
- `apps.platform_runtime.tests.test_configuration_center`
- `apps.platform_runtime.tests.test_internal_admin_alias`
- `apps.platform_runtime.tests.test_blueprint_marketplace_foundations`
- `apps.platform_runtime.tests.test_pack_libraries`
- `apps.platform_runtime.tests.test_registry_center`
- `apps.platform_runtime.tests.test_tenant_school_configuration_center`
