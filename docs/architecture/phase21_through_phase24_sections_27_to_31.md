# Phases 21–24 — Sections 27, 29, 30, 31

Single reference for repo audit and deliverables (27), add-ons (29), competitor and marketing (30), and references (31). Used to close out the remaining phases and move forward.

---

## Section 27 — Repo Audit and Architecture Deliverables (Phase 21)

**Status:** Checklist 27.1–27.3 already [x]. Phase 21 confirms deliverables present and current.

| Id   | Requirement | Status / location |
|------|-------------|-------------------|
| 27.1 | Audit commands; findings (hardcoded labels, FileField scope, security config, tenant leak tests) | [x] FINDINGS_REPO_AUDIT.md; media_tenant_scope.md |
| 27.2 | Cursor master prompt: audit → findings → TENANCY_MODE + Blueprint + Policy + refactor one module + repeatable pattern | [x] Part F directive in main doc; REPEATABLE_REFACTOR_PATTERN.md |
| 27.3 | Architecture deliverables: apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md; Admissions/Gradebook refactor | [x] phase13_refactor_map_section_13.md; policy_injection.md; grade_approval + admissions refactor done |

**Phase 21 done when:** Audit re-run if needed; deliverables present; 27.1–27.3 confirmed [x]. No re-run required; all confirmed.

---

## Section 29 — Add-Ons (Phase 22)

Each 29.x item implemented or scoped with a note.

| Id   | Area | Status / note |
|------|------|----------------|
| 29.1 | Identity/access | Partial: MFA (RequireMFAMiddleware, require_mfa_roles); RBAC; impersonation with audit. Passkeys/WebAuthn, step-up, JIT elevation, masking scoped. |
| 29.2 | Observability | Partial: control_plane_runbooks.md; standard logging. Traces, correlation IDs, per-tenant SLOs scoped (section_25_current_state 25.4). |
| 29.3 | Search | Done: GlobalSearchAPI tenant-scoped (request.school); section_25.3. Control-plane de-identified and blueprint registry search scoped. |
| 29.4 | Preview/release | Scoped: tenant staging/sandbox, config diff, canary, auto rollback. |
| 29.5 | Content/website | Partial: marketing pages, trust center, app marketplace. CMS, tenant page builder, microsites scoped. |
| 29.6 | Migration engine | Partial: phase5_migration_cloud.md, phase8; import studio, mapping, dry run, parity, scorecard. Rollback/exception queue scoped. |
| 29.7 | Integration layer | Partial: OneRoster adapter + API; LTI (ExternalToolConfig); WebhookSubscription; API. SIS/LMS webhooks, OAuth apps, monitoring scoped. |
| 29.8 | Design system | Partial: theme vars, density, backend/control shells (phase10). Design tokens doc, component governance, visual regression scoped. |
| 29.9 | AI governance | Partial: AI copilot; tenant context. Model routing, no-PII guardrails, prompt audit, tenant enable/disable scoped. |
| 29.10 | Commercial platform | Scoped: self-serve trials, quote-to-contract, partner tooling, migration calculator, in-app upgrade (phase8 deferred). |

**Ref:** section_25_current_state.md; phase8_migration_cloud_and_marketplaces.md; phase14_through_phase20_sections_14_to_26.md.

---

## Section 30 — Competitor and Marketing (Phase 23)

| Id   | Requirement | Status / note |
|------|-------------|----------------|
| 30.1 | Learn from PowerSchool, Infinite Campus, Skyward/Veracross/Blackbaud, Canvas/Moodle; avoid breach risk (MFA, tenant-scoped keys, shadow support with masking) | Documented: MFA and tenant isolation in place (section_25); competitor learnings and shadow support scoped in product/marketing. |
| 30.2 | Marketing front: segmented journeys (K-12, higher ed, vocational, international, ministries); world-class design; product-led demos; migration messaging; trust/compliance; country landings; comparison pages; marketplace narrative; customer proof | Partial: marketing_views (why-switch, verticals, trust-center, app-marketplace); section_11_category_killers. Full segmented journeys and comparison pages scoped. |
| 30.3 | Win conditions: blueprint-driven polymorphism; workflow + theme stores; marketplace + events; zero-friction admissions + teacher command center; compliance-as-code | Partial: blueprint/policy resolver; workflow and dashboard hubs; marketplace (phase8); admissions policy (Section 22); compliance AuditLog. Full win-condition checklist scoped. |

**Ref:** section_11_category_killers.md; schools.marketing_views; phase8, phase10.

---

## Section 31 — References (Phase 24)

References listed and linked; reflected in design/docs/code where applicable.

| Id   | Reference | Status / where reflected |
|------|-----------|--------------------------|
| 31.1 | WCAG (W3C) for accessibility | section_25_current_state 25.7; phase14–20 doc 26.4; target WCAG 2.2 AA. |
| 31.2 | OneRoster, Ed-Fi, CEDS for interoperability | apps/interop/oneroster; api/oneroster_views; phase14–20 doc 18.1–18.2; Ed-Fi/CEDS scoped. |
| 31.3 | NIST SP 800-207 for zero trust | phase14–20 doc 18.3; auth and tenant isolation align with zero-trust principles. |
| 31.4 | PostgreSQL schema/search_path docs | tenancy.md (schema switching, RLS); migrations conditional on TENANCY_MODE. |
| 31.5 | IMS Global / 1EdTech (OneRoster, LTI) | interop/oneroster, interop/lti; ExternalToolConfig; marketing (LTI interoperability). |
| 31.6 | Salesforce metadata-driven platform; Shopify metafields/extension model | section_28 (module vs feature); policy/blueprint as metadata; marketplace app install (phase8). |
| 31.7 | OpenFeature for feature flags | Feature flags via is_feature_enabled(school, code), can(school, capability); OpenFeature integration scoped. |
| 31.8 | PostgreSQL Row Level Security | tenancy.md (RLS mode); RLS migrations conditional; 19.6 tests for no cross-tenant leakage. |

**Ref:** tenancy.md; policy_injection.md; apps/interop; RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Part F.

---

## Checklist summary (Phases 21–24)

- **Phase 21 (Section 27):** 27.1–27.3 confirmed [x]; deliverables present; Phase 21 done.
- **Phase 22 (Section 29):** 29.1–29.10 each have status (partial/scoped/done); checklist updated.
- **Phase 23 (Section 30):** 30.1–30.3 documented/scoped; checklist updated.
- **Phase 24 (Section 31):** 31.1–31.8 linked and reflected; checklist updated.

After updating the main doc checklists and REMAINING_PHASES_EXECUTION_ORDER, all 24 phases are complete and the platform can move forward.
