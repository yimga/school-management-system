# N/A Blockers and Resolution

**Purpose:** For each SOT item left as N/A (deferred), this doc records **what is blocking** it and **how to unblock** so we can resolve, remove, or implement when prioritized. See [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) and [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Owner/date default:** product 2026-03-12 unless otherwise noted.

---

## Blocked by: No plan / product model

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §4.5 | Select plan (plan picker in setup) | No plan model productized; plans not yet first-class in setup flow | Productize plans (plan model, entitlements, UI); then add "select plan" step to setup/onboarding |
| §5.3 | Report style inheritance/versioning | Not in current scope; Report Platform evolution | Prioritize in Report Platform roadmap; implement when design agreed |
| §5.4 | Document & Compliance Platform | Large scope; not in current phase | Break into backlog items; implement per BACKLOG_AND_DEFERRED_CLOSURE when prioritized |

---

## Blocked by: UX / design / product scope

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §5.1 | Move ownership; Unify visual systems | Design and ownership model not finalized | Design sign-off; then implement ownership migration and visual system unification |
| §5.5 | Design Studio split, layout, section/block, preview, versioning, publish/rollback | UX and scope deferred | Prioritize Design Studio roadmap; implement in order per SOT |
| §5.7 | Workflows simulation, visual builder, AI, dependency, conflict, staged, replay, health | Scope beyond current workflow toolset | Prioritize workflow items in backlog; implement per BACKLOG_AND_DEFERRED_CLOSURE |
| §5.8 | AI permissions/audit, Use AI, API Center governance, contract tests | Product/security scope | Define AI governance and API Center scope; implement per plan |
| §5.9 | Total decomposition; Reclassify; preview/diff/rollback | Large metadata/blueprint scope | Break into backlog; implement when prioritized |
| §6.6 | Absorb real ownership from siteconfig (theme/experience) | Product decision to keep siteconfig as source for now | Decide to move ownership to brand_experience; then migrate models/resolvers |
| §6.7–§6.10 | Registry UI, marketplace, preview/sandbox, trust/scope (various) | Product deferral of registry/marketplace UX | Prioritize registry/marketplace; implement per execution plan |
| §6.11–§6.23 | Policies sandbox/graph, accounts onboarding, portal actions, finance workflows/analytics, academics/people/student360/reports/automation/communication/analytics/observability (specific unchecked items) | Each deferred per product; see SOT inline | Unblock per item: implement when added to sprint/backlog |
| §6.24 | Harden auth/signature/rate limiting (beyond current) | manual_review_required items deferred to security review | Implement per public_endpoint_audit.md §6 when security review specifies |
| §6.24 | Reduce public/exempt exposure; API Center as integration governance; Interop validation workbench; Contract tests | Product/scope deferral | Prioritize apicenter_integration_governance.md and interop; implement per plan |

---

## Blocked by: Out of current scope / manual phase

| SOT ref | Item | Blocked by | Unblock by |
|---------|------|------------|------------|
| §11 Phase H | Go through entire codebase (links, UX, responsive, framing) | Manual phase; automation slice exists (phase_h_audit, run_phase_h_verification.sh) | Run Phase H audit when scheduling full UX pass; use scripts to narrow scope |
| §11 Phase H | Ensure after deployment changes visibly seen | Staging/release process | Use RELEASE_CHECKLIST and staging verification when deploying |
| §11 Phase H | Run full test suite and smoke/E2E | Already in pre_deploy_gate + phase_h_verification | No blocker — run as part of release |

---

## Resolved (no longer N/A)

| SOT ref | Item | Resolution |
|---------|------|------------|
| §5.2 | Add owner/expiry/source/scope to flags | **Done** — FeatureToggleDefinition has owner, source; scope on Definition; FeatureToggleState has expires_at; migration 0158; admin + feature_control_ledger. |
| §6.24 | Classify endpoints | **Done** — public_endpoint_audit.md has Classification column (public\|tenant\|admin) on all csrf_exempt and AllowAny rows. |

---

*Cross-reference: [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md).*
