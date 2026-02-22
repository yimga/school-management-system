# Titan SMS Execution Plan (Sprint-Based)

## Scope
This plan executes the import backlog in `docs/execution/TITAN_SMS_BACKLOG_IMPORT.csv`.
Goal: deliver region auto-build + tenant-level configurability while closing global compliance, interop, finance, and security gaps.

## Planning Assumptions
- Sprint length: 2 weeks
- Horizon: 6 sprints (12 weeks)
- Team shape (minimum):
  - 2 Backend Engineers
  - 1 Platform/Interop Engineer
  - 1 Finance Engineer
  - 1 Security Engineer
  - 1 QA Engineer (shared)
- Effective capacity target: 36-42 SP per sprint (cross-functional)
- Release model: no region launch before S6 exit gates are green

## Delivery Lanes
- Lane A: Compliance + Regional Config
- Lane B: Interop + Identity
- Lane C: Finance + Academic Depth
- Lane D: Security + Guardrails + QA

## Critical Path
1. `P0-001` + `P0-002` + `P0-008`
2. `CFG-101` -> `CFG-102` -> `CFG-103` -> `CFG-104`
3. `INT-201` + `INT-202` + `INT-205`
4. `SEC-601` + `SEC-602`
5. Regional launch readiness (`SEC-607`, `SEC-608`)

## Sprint Plan

### Sprint 1 (Stabilize P0 Runtime)
Target tickets:
- `P0-001`, `P0-002`, `P0-005`, `P0-006`, `P0-007`, `P0-009`

Objectives:
- Remove stub/placeholder risk from compliance and payments.
- Close immediate public endpoint abuse and disbursement defect.

Exit criteria:
- DSAR portability and erasure workflows execute end-to-end.
- MTN/Orange adapters pass callback signature + idempotency tests.
- Lead capture endpoint enforces throttling with 429 behavior.
- No known P0 runtime defect remains open in this group.

### Sprint 2 (Interop and Structural Cleanup)
Target tickets:
- `P0-003`, `P0-004`, `P0-010`, `P0-011`, `P0-012`, `INT-201`, `INT-202`

Objectives:
- Stand up real interoperability baseline.
- Remove architectural ambiguity around integration and payment factories.

Exit criteria:
- LTI baseline launch and SCIM/OIDC core flows operational.
- Interop stubs removed from production routes.
- Factory override and duplicated model ownership risk addressed.

### Sprint 3 (Configuration Compiler and Standards Depth)
Target tickets:
- `P0-008`, `CFG-101`, `CFG-102`, `CFG-103`, `INT-203`, `INT-204`, `INT-205`

Objectives:
- Deliver deterministic regional/tenant config resolution.
- Expand enterprise standards support (SAML, OneRoster, LTI AGS/NRPS).

Exit criteria:
- Effective configuration compiler resolves precedence and lock state.
- Regional pack versioning works for US/EU/Brazil/Africa presets.
- OneRoster and LTI advanced capabilities pass integration tests.

### Sprint 4 (Tenant Auto-Build + Governance)
Target tickets:
- `CFG-104`, `CFG-105`, `CFG-106`, `CFG-107`, `CFG-108`, `INT-206`

Objectives:
- Automate tenant provisioning from region packs.
- Implement tenant override governance and data residency enforcement.

Exit criteria:
- New tenant bootstrap fully automated from selected region pack.
- Locked vs editable controls enforced with approval workflow.
- Outbound webhooks have retry ledger and dead-letter path.

### Sprint 5 (Domain Depth: Academics + Finance)
Target tickets:
- `EDU-301`, `EDU-302`, `EDU-303`, `EDU-304`, `FIN-401`, `FIN-402`, `FIN-403`, `FIN-404`, `FIN-405`

Objectives:
- Replace simplified degree audit with solver-grade capability.
- Deliver finance architecture required for global multi-tenant operations.

Exit criteria:
- Degree solver handles prerequisites, waivers, transfer credit.
- Aid/tuition flows enforce balanced ledger behavior.
- Multi-currency/tax/split-billing scenarios pass regression suite.

### Sprint 6 (Sovereign AI + Security Launch Gates)
Target tickets:
- `AI-501`, `AI-502`, `AI-503`, `SEC-601`, `SEC-602`, `SEC-603`, `SEC-604`, `SEC-605`, `SEC-606`, `SEC-607`, `SEC-608`

Objectives:
- Complete sovereign AI readiness with safe fallback behavior.
- Enforce hard security and compliance launch gates.

Exit criteria:
- AI provider abstraction, circuit breaker, and schema-validated outputs are live.
- IDOR, RLS, and throttling suites are green.
- Transcript hash verification is implemented.
- Compliance evidence pack and SLO dashboard are available for audit and go-live.

## Release Gates (Must Pass Before Regional Rollout)
- Gate 1: CI integrity
  - Migration check, tenant audit, smoke suites, critical integration suites
- Gate 2: Compliance runtime
  - DSAR export + erasure execution by region profile
- Gate 3: Interop readiness
  - SCIM, OIDC/SAML, OneRoster, LTI AGS/NRPS
- Gate 4: Finance reliability
  - Payment callback authenticity, idempotency, reconciliation
- Gate 5: Security hardening
  - IDOR, RLS/search_path invariants, prompt-injection tests, public endpoint rate limits

## Risk Register
- High: External provider onboarding delays (IdP, payment rails)
  - Mitigation: provider sandbox contracts in Sprint 1, parallel adapter test harness
- High: Scope creep in config compiler
  - Mitigation: freeze schema and precedence contract at start of Sprint 3
- Medium: Data migration complexity for identity consolidation
  - Mitigation: staged migration with shadow writes and rollback checkpoints
- Medium: Test runtime explosion
  - Mitigation: classify suites (blocking vs nightly) and parallelize CI jobs

## Operating Cadence
- Weekly architecture review: dependency drift and critical path check
- Twice-weekly risk burn-down: unresolved blockers and vendor dependencies
- End-of-sprint hard gate: only done tickets with passing tests and documented rollback

## Definition of Done (Global)
- Ticket acceptance criteria met
- Automated tests added/updated and green
- Tenant isolation and audit implications verified
- Observability hooks added for operationally critical paths
- Documentation updated in `docs/execution`
