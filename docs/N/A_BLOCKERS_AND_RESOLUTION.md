# N/A Blockers and Resolution

**Purpose:** For each SOT item left as N/A (deferred), this doc records **what is blocking** it and **how to unblock** so we can resolve, remove, or implement when prioritized. See [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) and [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Owner/date default:** product 2026-03-12 unless otherwise noted.

**How to use:** When you prioritize an item, find its row below; follow "Unblock by" and the concrete steps in §"Concrete unblock steps" so the item can be implemented without going in circles.

---

## Blocked by: No plan / product model

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §4.5 | Select plan (plan picker in setup) | No plan model productized; plans not yet first-class in setup flow | (1) Add plan/entitlement model and UI if missing. (2) Add "Select plan" to Launch Studio rail in `studio_os/views.py` launch_rail; add step to `get_setup_studio_payload`; link from Launch mode template. (3) Mark SOT §4.5 [x]. |
| §5.3 | Report style inheritance/versioning | Not in current scope; Report Platform evolution | (1) Agree design in Report Platform roadmap. (2) Add style/version fields to ReportPack or report template model; wire in report_library and Output Studio. (3) Mark SOT §5.3 style [x]. |
| §5.4 | Document & Compliance Platform | Large scope; not in current phase | (1) Break into BACKLOG items (lifecycle UI, compliance views, retention dashboard). (2) Implement per PATH_TO_100 Phase IV §5.4. (3) Mark SOT §5.4 [x]. |

---

## Blocked by: UX / design / product scope

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §5.1 | Move ownership; Unify visual systems | Design and ownership model not finalized | (1) Get design sign-off. (2) Move theme/experience models and resolvers to brand_experience per domain_ownership.md §5; unify tokens in static/css (design-tokens, portal, dashboard). (3) Mark SOT §5.1 [x]. |
| §5.5 | Design Studio split, layout, section/block, preview, versioning, publish/rollback | UX and scope deferred | (1) Prioritize in backlog. (2) Implement per SOT §5.5 order: split Document vs Experience design surfaces; add layout/section/block models and UI; responsive preview; versioning; publish/rollback. (3) Mark each [x] in SOT. |
| §5.7 | Workflows simulation, visual builder, AI, dependency, conflict, staged, replay, health | Scope beyond current workflow toolset | (1) Add to BACKLOG with owner. (2) Implement per PATH_TO_100 §5.7: simulation (orchestration/runners dry run), visual builder UI, AI workflow generation, dependency graph (automation_dependency_graph exists), conflict detection, staged activation, replay/rollback (automation_replay_rollback exists), health (automation_workflow_health exists). (3) Mark SOT §5.7 [x]. |
| §5.8 | AI permissions/audit, Use AI, API Center governance, contract tests | Product/security scope | (1) Define scope in AI_audit_trail_and_permissions.md and apicenter_integration_governance.md. (2) Extend ai_permissions matrix and audit log; add AI to setup/workflow/migration flows; API Center UI per doc; add contract tests (test_runtime_contract exists). (3) Mark SOT §5.8 [x]. |
| §5.9 | Total decomposition; Reclassify; preview/diff/rollback | Large metadata/blueprint scope | (1) Break into backlog. (2) Add bounded consoles per BOUNDED_CONSOLES_INVENTORY.md; reclassify per site_settings_usage_inventory; add preview/diff/rollback in Configuration Control Center. (3) Mark SOT §5.9 [x]. |
| §6.6 | Absorb real ownership from siteconfig (theme/experience) | Product decision to keep siteconfig as source for now | (1) Decide to move. (2) Migrate theme/experience fields to brand_experience models; siteconfig becomes legacy data source; update get_effective_site_settings/resolvers. (3) Mark SOT §6.6 [x]. |
| §6.7–§6.10 | Registry UI, marketplace, preview/sandbox, trust/scope (various) | Product deferral of registry/marketplace UX | (1) Pick item from PATH_TO_100 Phase III §6.7–6.10. (2) Implement: registry list/detail UI (metadata_lineage_graph exists); marketplace screenshot/trust/scope per MARKETPLACE_LISTING_METADATA.md; blueprint sandbox/versioning. (3) Mark corresponding SOT [x]. |
| §6.11–§6.23 | Policies sandbox/graph, accounts onboarding, portal actions, finance/analytics/people/360/reports/automation/communication/observability | Each deferred per product; see SOT inline | (1) Add specific item to sprint. (2) Implement per PATH_TO_100 Phase III table for that section (file refs in plan). (3) Mark SOT [x]. |
| §6.24 | Harden auth/signature/rate limiting (beyond current) | manual_review_required items deferred to security review | (1) In public_endpoint_audit.md §6, for each manual_review_required endpoint get security sign-off. (2) Add signature/replay per doc; add tests; update ledger. (3) Mark SOT §2.4 [x]. |
| §6.24 | API Center governance; Interop validation; Contract tests | Product/scope deferral | (1) Implement per docs/apicenter_integration_governance.md. (2) Add interop validation view/script; extend contract tests (apps.platform_runtime.tests.test_runtime_contract). (3) Mark SOT §6.24 [x]. |

---

## Blocked by: Out of current scope / manual phase

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §11 Phase H | Go through entire codebase (links, UX, responsive, framing) | Manual phase; automation slice exists | (1) Run `bash scripts/run_phase_h_verification.sh` and fix failures. (2) Run PHASE_H_MANUAL_CHECKLIST.md; record in PHASE_H_EXECUTION_LOG.md. (3) Mark SOT §11 Phase H first bullet [x]. |
| §11 Phase H | Ensure after deployment changes visibly seen | Staging/release process | (1) Deploy to staging; verify key flows per RELEASE_CHECKLIST and CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md. (2) Record in PHASE_H_EXECUTION_LOG "After deployment" and RELEASE_CHECKLIST sign-off. (3) Mark SOT §11 Phase H second bullet [x]. |
| §11 Phase H | Run full test suite and smoke/E2E | No blocker — automation in place | Run `bash scripts/pre_deploy_gate.sh`; fix any failures. Mark third bullet [x] when gate passes and full suite run is recorded. |

---

## Concrete unblock steps (by category)

Use these when you prioritize an N/A item so implementation can continue without going in circles.

| Category | First step | Key files / commands |
|----------|------------|----------------------|
| **§4.5 Select plan** | Productize plan model | apps/plans_entitlements (or equivalent); studio_os/views.py launch_rail; get_setup_studio_payload |
| **§5.1 Theme/Experience ownership** | Design sign-off | domain_ownership.md §5; brand_experience models; static/css design-tokens |
| **§5.3 Report Platform** | Report style/version design | reports/report_packs.py; report_library view; Output Studio |
| **§5.4 Document & Compliance** | Backlog breakdown | DOCUMENT_LIFECYCLE_*; document_library; BACKLOG_AND_DEFERRED_CLOSURE |
| **§5.5 Design Studio** | Backlog order | SOT §5.5 Actions; layout/section/block models |
| **§5.7 Workflows** | Per-item backlog | orchestration/runners; studio_os automation_* views; PATH_TO_100 §5.7 |
| **§5.8 AI/API** | Scope in docs | AI_audit_trail_and_permissions.md; apicenter_integration_governance.md; apps.platform_runtime.tests.test_runtime_contract |
| **§5.9 Configuration Control Center** | Bounded consoles + reclassify | BOUNDED_CONSOLES_INVENTORY.md; site_settings_usage_inventory |
| **§6.6 brand_experience ownership** | Product decision | brand_experience resolvers; get_effective_site_settings |
| **§6.7–6.10 Registry/marketplace** | Per PATH_TO_100 row | MARKETPLACE_LISTING_METADATA.md; metadata_lineage_graph; NA_REGISTER |
| **§6.11–6.23 App-by-app** | Pick section in PATH_TO_100 | PATH_TO_100_PERCENT_EXECUTION_PLAN.md Phase III table; SOT §6 |
| **§6.24 Auth/signature** | public_endpoint_audit §6 | docs/public_endpoint_audit.md; add HMAC/nonce per endpoint |
| **§11 Phase H manual** | Run scripts + manual checklist | `bash scripts/run_phase_h_verification.sh`; `bash scripts/pre_deploy_gate.sh`; PHASE_H_MANUAL_CHECKLIST.md; PHASE_H_EXECUTION_LOG.md |
| **Release sign-off (plan done)** | Staging 10-point + sign-off | launch_studio_checklist.md §4; RELEASE_CHECKLIST.md "Release sign-off" section |

---

## Resolved (no longer N/A)

| SOT ref | Item | Resolution |
|---------|------|------------|
| §5.2 | Add owner/expiry/source/scope to flags | **Done** — FeatureToggleDefinition has owner, source; scope on Definition; FeatureToggleState has expires_at; migration 0158; admin + feature_control_ledger. |
| §6.24 | Classify endpoints | **Done** — public_endpoint_audit.md has Classification column (public\|tenant\|admin) on all csrf_exempt and AllowAny rows. |

---

*Cross-reference: [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md).*
