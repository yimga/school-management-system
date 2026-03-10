# Phases 11–25 implementation summary

This document records the implementation status and references for Master Platform Checklist phases 11–25. All items are non-negotiable; each section points to docs, code, or UX already in place or to the checklist section that defines the requirement.

---

## Phase 11: In-product trust center (§14.5)

- **Requirement:** Audit viewer; active app scopes; metadata change log; impersonation logs; integration permissions dashboard; policy history; backup/export controls; privacy/compliance posture.
- **Implementation:** Control-plane and tenant audit flows; impersonation logging (ImpersonationLog where present); integration governance (Integration model, API Center); policy in runtime inspector. Trust center UX: document in control_plane_access_and_roles.md; implement viewer pages incrementally.

## Phase 12: Platform health per tenant (§15.3)

- **Requirement:** Track failed jobs, stale integrations, broken workflows, unread alerts, migration warnings, dashboard failures, data quality issues, permission anomalies.
- **Implementation:** Observability app (SLO dashboard, health); migration visibility at /super/migration/; Integration.health_status; workflow/dashboard resolution errors in runtime. Per-tenant health view: extend observability or control-plane tenant health page.

## Phase 13: Setup Studio (§8)

- **Requirement:** One unified Setup Studio: Create school → Choose plan → Apply blueprint → Branding → Starter stack → Data path → Preview by role → Launch checklist. Branding assistant; setup guidance; fewer-click standard.
- **Implementation:** Document flow in this doc and §8; onboarding wizard and control-plane school creation exist; extend to unified Setup Studio flow and click metrics (store in siteconfig or analytics).

## Phase 14: Design system enforcement (§9)

- **Requirement:** Page archetypes; role-native homes; action engine; visual design system; premium UI rule.
- **Implementation:** docs/architecture/ux_rules_audit_26_5.md, design-tokens.css, form-system.css, table-system.css, card-grammar.css; page families and shell map. Enforcement: lint or design-token usage; component preview (Phase 21).

## Phase 15: Workflow reduction metrics (§18.2)

- **Requirement:** UX metrics: clicks to launch school, apply branding, install starter stack, publish results, create invoice batch, install pack.
- **Implementation:** §18.2 defines the metrics; store in FeatureUsage or analytics; dashboard for reduction over time. governor_limits and event catalog support measurement.

## Phase 16: Migration programs per competitor (§12.1)

- **Requirement:** PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, generic CSV/API/export — each with source detection, known mappings, validation guide, parity checklist, operator checklist, rollback readiness.
- **Implementation:** docs/architecture and migration app; MigrationRun, orchestration_layer.md. Per-competitor playbooks: document in migration docs; implement source detection and playbooks incrementally.

## Phase 17: Marketplace seeding and listing (§11)

- **Requirement:** Marketplace categories; listing quality; 25+ first-party apps, 25+ blueprint packs, 30+ workflow packs, etc.; partner platform.
- **Implementation:** apps/marketplace (models, services, views); siteconfig metadata_catalog and blueprint/workflow registries. Seeding: management commands and fixture data; partner platform (developer portal) documented in architecture.

## Phase 18: Release governance (§15.4)

- **Requirement:** Release trains; feature flags; beta channels; staged rollouts; rollback plans; metadata rollout gates.
- **Implementation:** Feature flags (backend_feature_flags, runtime flags); orchestration rollback (MigrationRun.trigger_rollback); pre_deploy_gate.sh as merge gate. Document release process in this doc and §15.4.

## Phase 19: Performance in CI (§15.1–15.2)

- **Requirement:** Query budgets; response-time budgets; N+1 detection; index audit; pagination; cache strategy.
- **Implementation:** pre_deploy_gate can run lint_mega_files, check_repo_hygiene, lint_bounded_context_imports; add pytest markers or CI job for query count / response time on critical paths. Performance budgets documented in PERFORMANCE_BUDGETS_ARCHITECTURE.md.

## Phase 20: Search and command

- **Requirement:** Global search and command palette (e.g. Cmd+K) for navigation, actions, entities.
- **Implementation:** docs/architecture/SEARCH_ARCHITECTURE.md; implement search/command API and frontend incrementally; scope to control-plane and tenant.

## Phase 21: Internal DX and contract testing (§17)

- **Requirement:** Architecture maps; ownership maps; local setup; test fixtures; seeded sandbox; runtime inspection; component preview; contract testing (runtime, event, API, integration).
- **Implementation:** runtime_inspector.py; bounded_contexts.md; platform_runtime tests; event catalog; API versioning. Contract tests: add pytest contracts for runtime, events, critical APIs.

## Phase 22: Tenant maturity model

- **Requirement:** Model tenant maturity (onboarding stage, adoption, health) for prioritization and success.
- **Implementation:** Define stages in this doc and §18; store maturity score or stage in tenant/school or analytics; use in control-plane and support.

## Phase 23: Platform narrative in product (§20)

- **Requirement:** Team mantra and narrative visible in product (e.g. footer, about, help): Simplify architecture, runtime as law, metadata-first, productize packs, migration as killer feature, remove clicks.
- **Implementation:** Add narrative/mantra to portal_base or control_plane_base template and/or help/about page.

## Phase 24: Success metrics (§18)

- **Requirement:** Platform, UX, product, and trust metrics (§18.1–18.4) defined and tracked.
- **Implementation:** §18 checkboxes; governor_limits; event catalog; observability; store metrics in analytics or FeatureUsage; dashboard for success metrics.

## Phase 25: Final non-negotiable rule and merge gate (§19)

- **Requirement:** No new feature merged unless it reduces/justifies complexity, respects runtime-first and metadata-first, preserves tenant isolation, improves operator clarity, fits archetypes, supports auditability, avoids sprawl. Merge/PR gate enforces.
- **Implementation:** scripts/pre_deploy_gate.sh (repo hygiene, bounded context imports, optional lint_tenant_settings, lint_mega_files); PR checklist or GitHub Actions that runs pre_deploy_gate; rule documented in MASTER_PLATFORM_CHECKLIST.md §19 and §20.
