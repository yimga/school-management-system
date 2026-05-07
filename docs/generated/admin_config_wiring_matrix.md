# Admin Configuration Wiring Matrix

| Area | Required wiring | Actual wiring | Status |
|---|---|---|---|
| Blueprint composition | Package, workflow packs, dashboard packs, policy bundles, metadata templates, roles, permissions, report templates, offline defaults, billing defaults, implementation checklist | `BlueprintContract` plus preview `package_payload` and `implementation_checklist` include these install units | present |
| Blueprint preview | Pack preview, metadata preview, billing/external dependency check, policy check | `preview_blueprint` calls `preview_pack` for workflow/dashboard/policy refs and preserves `external_required`; metadata/report/billing/offline changes are preview rows | present |
| Blueprint impact | Pack impact, role/permission impact, runtime governance, billing/usage impact | `analyze_blueprint_impact` surfaces roles, workflows, dashboards, policies, billing rules, external dependencies, and confirmation requirements | present |
| Blueprint apply | `BlueprintInstallation`, linked `PackInstallation`, audit, snapshots, tenant scope, external blockers | `apply_blueprint` creates installation records, writes audit, stores rollback snapshot, runs package apply, and calls `apply_pack` for referenced packs | present |
| Blueprint rollback | Pack rollback, rollback snapshot, non-destructive posture, audit | Blueprint rollback uses stored snapshot/audit posture; linked pack rollback is available through `PackInstallation` rollback | present |
| Pack preview | Non-mutating and tenant scoped | `preview_pack` returns payload/conflicts/external blockers; preview mutation tests exist | present |
| Pack simulation | Workflow trigger/condition/action; dashboard role/widgets/actions; policy allow/block/approval | `simulate_pack` is wired into pack apply where required and exposed through `/configuration/*/simulate/` | present |
| Pack apply | `PackInstallation`, audit, snapshots, permissions, tenant boundaries | `apply_pack` blocks failed previews, dependencies, missing simulation, and high-risk unapproved changes; creates installation snapshots | present |
| Pack rollback/deactivate | Non-destructive where possible, audit, health | `rollback_pack_installation` restores snapshot and audits; `deactivate_pack_installation` marks status without destructive deletion | present |
| Configuration change governance | Request, approve/reject, schedule, apply, monitor, rollback | `ConfigurationChangeRequest` routes/services cover request, approval, rejection, scheduling, cancellation, and apply; rollback posture lives in change sets/installations | present |
| `/configuration` hub | All platform configuration domains | `administration_catalog.CONFIGURATION_MODULES` enumerates all required domains and renders links without dummy hrefs | present |
| `/school/settings` hub | Tenant-safe profile, academics, fees, roles, portals, apps, workflows, offline, branding, audit/security | `TENANT_CONFIGURATION_SECTIONS` plus `/school/...` aliases map to existing tenant-safe surfaces | present |

Verdict for wiring: repository wiring is present for the model. Remaining depth is mostly product-detail expansion, not missing control-plane architecture.
