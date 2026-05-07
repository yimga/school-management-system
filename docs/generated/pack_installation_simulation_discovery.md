# Pack Installation Simulation Discovery

| Existing primitive | File/module | Pack type | Reuse | Missing behavior | Risk | Recommended reuse |
| --- | --- | --- | --- | --- | --- | --- |
| Package engine | `apps/packages/engine.py` | workflow/dashboard/policy | preview/apply/rollback | pack-specific simulation and UI contract | duplicate installs if callers bypass idempotency | wrap with `PackInstallation` |
| Workflow catalog | `apps/siteconfig/models_workflow.py` | workflow pack | catalog/assignment | governed lifecycle | unsafe activation | require preview/simulation/confirmation |
| Workflow engine | `apps/siteconfig/workflow_engine.py` | workflow pack | simulation semantics | pack output contract | live mutation during dry-run | dry-run only actions list |
| Dashboard catalog | `apps/siteconfig/models_dashboard.py` | dashboard pack | widgets/layout/role visibility | installation history | unauthorized widgets | role-aware contract and tenant marker |
| Policy bundles | `apps/policies/models.py` | policy bundle | snapshots/rules | policy decision simulation | audit bypass | simulate allowed/blocked/approval |
| Marketplace registry | `apps/marketplace/pack_registry.py` | workflow/dashboard/theme | discovery/entitlement hints | lifecycle | catalog mistaken for install | installer writes applied state |
| Blueprint contract | `apps/platform_runtime/blueprint_contract.py` | pack references | composition | live pack integration | descriptive-only blueprints | preview/apply delegates to pack engines |
| Platform events | `apps/platform_runtime/events.py` | all | audit | pack event names | untraceable install | pack lifecycle events |

Discovery result: pack installation should be a governed facade over the existing package engine, workflow/dashboard/policy registries, marketplace catalog, and platform event log.
