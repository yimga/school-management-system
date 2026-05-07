# Admin Configuration Test Coverage Matrix

| Domain | Tests | Proves | Status |
|---|---|---|---|
| Administration model | `apps/platform_runtime/tests/test_administration_model.py` | `/internal-admin` alias and tenant `/configuration/` block | covered |
| Configuration Center | `apps/platform_runtime/tests/test_configuration_center.py` | Required modules render, no dummy hrefs, detail links existing system | covered |
| Tenant School Configuration | `apps/platform_runtime/tests/test_tenant_school_configuration_center.py` | `/school/settings/`, legacy alias, no global registries, `/school/...` route aliases | covered |
| Blueprint Marketplace | Blueprint marketplace, blueprint/pack integration, marketplace rollback ack tests | Preview, impact, apply, rollback posture, audit, pack integration | covered |
| Pack Engines | Pack preview/simulation/impact/apply/rollback/audit and tenant setup tests | Preview, simulation, impact, apply, rollback/deactivate, audit, tenant setup | covered |
| Marketplace / App Catalog | Marketplace governance/install impact and API Center e2e | App catalog route, governance, install impact, scope/billing/audit path | covered |
| Metadata Catalog | Metadata services, lineage API, pack provenance tests | Lineage, pack provenance, downstream impact helpers | covered |
| Runtime and Governance | Runtime truth hub and approval-aware UI tests | Runtime truth and approval-aware apply UI | covered |
| Migration | Super migration cloud/config migration URL tests | Operator route access and migration URLs | covered |
| Security and Trust | Super security hub/surface and procurement trust tests | Platform security ops, security surface, public trust separation | covered |
| Billing / Usage | Billing console and marketplace paid install gate tests | Billing console, paid install gate, external honesty | covered external_required |
| Verifiers | Route, security, tenant isolation, test contract, northstar, kill test scripts | Cross-cutting proof artifacts when run | covered when run |

Coverage gap posture: no critical boundary test gap remains for the administration model after adding the tenant `/school/...` alias test.
