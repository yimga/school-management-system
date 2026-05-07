# Admin Configuration Domain Route Matrix

| Domain | Expected route | Actual route(s) | Status | Permission boundary |
|---|---|---|---|---|
| Blueprint Marketplace | `/configuration/blueprints/` | `/configuration/blueprints/`, `/school/setup/blueprints/`, `/super/marketplace/blueprints/`, `/super/blueprints/` | present | Control-plane for platform; tenant setup requires tenant context/operator eligibility. |
| App Catalog | `/configuration/app-catalog/` | `/configuration/app-catalog/`, `/school/apps/`, `/settings/app-catalog/`, `/super/marketplace/apps/` | present alias | Super marketplace governance; tenant catalog remains tenant URLConf/login scoped. |
| Package Rollout | `/configuration/packages/` | `/configuration/packages/`, `/super/marketplace/package-rollout/`, `/school/billing/`, `/school/money/`, `/finance/` | present alias | Platform rollout is super/control-plane; tenant finance is tenant scoped. |
| Workflow Pack | `/configuration/workflow-packs/` | `/configuration/workflow-packs/`, `/school/setup/packs/`, `/school/workflows/`, `/studio/automation/`, `/super/workflow-packs/` | present | Platform configuration is control-plane; tenant pack setup is tenant scoped. |
| Dashboard Pack | `/configuration/dashboard-packs/` | `/configuration/dashboard-packs/`, `/super/dashboard-packs/`, `/siteconfig/school-configuration/` | present | Platform dashboard packs require control-plane; tenant settings remain scoped. |
| Policy Bundles | `/configuration/policy-bundles/` | `/configuration/policy-bundles/`, `/super/policies/`, `/school/security/`, `/school/audit/`, `/compliance/` | present alias | Platform policies require control-plane; tenant audit/security routes stay tenant scoped. |
| Metadata Catalog | `/configuration/metadata/` | `/configuration/metadata/`, `/super/metadata-catalog/`, `/api/internal/metadata/` | present | Platform metadata is control-plane; tenant settings do not expose global registries. |
| Registries | `/configuration/registries/` | `/configuration/registries/`, `/super/registries/` | present | Control-plane only. |
| Runtime and Governance | `/configuration/runtime/` | `/configuration/runtime/`, `/super/runtime-truth-hub/`, `/super/runtime-inspector/` | present | Control-plane only. |
| Migration | `/configuration/migrations/` | `/configuration/migrations/`, `/super/migration/`, `/super/migration/registry/`, `/super/migration/rollback/<run_id>/` | present | Fleet migration is control-plane; tenant imports remain tenant scoped. |
| Integration and API Center | `/configuration/integrations/` | `/configuration/integrations/`, `/api-center/`, `/developer/`, `/super/marketplace/apps/` | present | API Center distinguishes platform/tenant access; marketplace review is super scoped. |
| Compliance and Audit | `/configuration/compliance/` | `/configuration/compliance/`, `/super/compliance/`, `/super/trust/export/`, `/school/audit/`, `/compliance/` | present | Platform audit is control-plane; tenant audit is tenant scoped. |
| Security and Trust Center | `/configuration/security/` | `/trust/`, `/configuration/security/`, `/super/security/`, `/school/security/`, `/compliance/` | present separated | Public trust, platform security ops, and tenant security are separate surfaces. |
| Billing / Subscription / Usage | `/configuration/billing/` | `/configuration/billing/`, `/super/billing/`, `/super/usage/`, `/school/billing/`, `/school/money/`, `/finance/` | present external_required | Platform billing is control-plane; tenant finance is tenant scoped. |
| UX/UI / Experience | `/configuration/experience/` | `/configuration/experience/`, `/studio/experience/`, `/school/settings/` | present | Platform experience is control-plane; tenant branding/theme stays scoped. |
| `/super` | `/super/` | `/super/` | present | `require_super_access_with_host`. |
| `/configuration` | `/configuration/` | `/configuration/` | present | `require_control_plane_access`; tenant URLConf returns 403. |
| `/school/settings` | `/school/settings/` | `/school/settings/`, `/siteconfig/school-configuration/` | present | Login, `request.school`, and `tenant_operator_hub_eligible`. |
| `/internal-admin` | `/internal-admin/` | `/internal-admin/`, `/internal-admin/<path>` | present alias | Redirects to `/admin/`; admin permissions remain on admin site. |
| `/admin` compatibility | `/admin/` | `/admin/` | present | Split platform/tenant admin sites and Django admin permissions. |

Recommended route action: keep `/configuration/` and `/super/` platform-only, keep `/school/...` tenant-safe aliases, and do not point product navigation to raw `/admin/`.
