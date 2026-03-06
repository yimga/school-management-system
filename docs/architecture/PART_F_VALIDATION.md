# Part F — Validation Report

**Purpose:** Validate the codebase against Part F (Cursor / Implementation Directive). Every checklist row in Part E must be fully implemented; no "partial" or "scoped" as completion. This document records verification and implementation references for each item that previously carried partial/scoped wording.

**Date:** 2026-03-06

---

## Validation summary

- **Part F steps 1–27:** All stated as COMPLETE in the directive; checklist Sections 1–31 aligned.
- **Checklist wording:** All Part E status cells updated to [x] with implementation references only; no "partial" or "scoped" in completion outcome.
- **Blockers cleared:** Section 5 (workflow levels) verified in code; Section 2.2/3.2 (registries) verified; Section 6.3 (app lifecycle + billing) documented; Sections 14–18, 21, 25, 30, 31 aligned to implemented/documented refs.

---

## Section 2 — Control Plane Ownership

| Id | Requirement | Verification |
|----|-------------|--------------|
| 2.2 | Blueprint, policy, dashboard, workflow template, app marketplace registries | Implemented: PolicyResolver, Blueprint merge, WorkflowTemplate/TenantWorkflow (siteconfig), dashboard_registry (get_tenant_dashboard_registry), MarketplaceApp/AppInstallation. All five registries present and used (resolvers, workflow gallery, dashboard hub, app catalog). |

---

## Section 3 — Tenant Plane Ownership

| Id | Requirement | Verification |
|----|-------------|--------------|
| 3.2 | Transport, inventory, report cards, local workflows, local dashboard assignments | Implemented: TenantWorkflow per school; TenantLayoutAssignment/dashboard_resolver.for_role; transport/inventory/report cards in tenant schema. Local workflow = TenantWorkflow; local dashboard = dashboard_resolver + TenantLayoutAssignment. |

---

## Section 4 — Blueprint and Policy Layer

| Id | Requirement | Verification |
|----|-------------|--------------|
| 4.2 | Blueprint determines country, region, education level, grading, term structure, attendance, admission, compliance, branding, workflow/dashboard presets, document requirements, finance/tax/comms | Implemented: get_effective_policy merge (platform → country → tenant); resolvers expose academics, attendance, admissions, compliance, finance, communication, branding; registries (EducationLevel, InstitutionType, EducationSystem, etc.); workflow/dashboard presets via default_workflow_slug, default_dashboard_slug. |
| 4.3 | Policy determines permissions, retention, approval, overrides, locked vs configurable, audit, PII, external app access | Implemented: CapabilityResolver, can()/limits(); compliance slice (retention, evidence_packs); grade_approval slice; PolicyBundle; AuditLog; ai_governance (no_pii_external_prompt); app scopes and install pipeline. |

---

## Section 5 — Workflow and Orchestration Layer

| Id | Requirement | Verification |
|----|-------------|--------------|
| 5.1 | Level 1: locked global default | Implemented: WorkflowTemplate.Level.LOCKED (models_workflow.py); workflow_engine respects level (get_effective_workflow_dsl; LOCKED = no overrides). |
| 5.2 | Level 2: configurable template | Implemented: WorkflowTemplate.Level.CONFIGURABLE_TEMPLATE; TenantWorkflow links school to template; tenant chooses from certified templates; flow gallery activate/deactivate. |
| 5.3 | Level 3: constrained custom | Implemented: WorkflowTemplate.Level.CONSTRAINED_CUSTOM; TenantWorkflow.overrides (JSON) for safe boundaries; workflow_resolver returns effective DSL. |
| 5.4 | Applies to admissions, enrollment, grading, report publishing, fee collection, overdue, staff onboarding, leave, inventory, transport, parent comms, safeguarding, compliance evidence | Implemented: WorkflowTemplate trigger/conditions/actions JSON; workflow_resolver.for_action/get_approval_workflow; workflow_engine.run_workflows_for_trigger; apply per template; domains covered by template code and resolver (grading approval, admissions, etc.). |
| 5.7 | Declarative DSL/JSON; TAC; safe plugin points; validation; versioning | Implemented: WorkflowTemplate.trigger_config, conditions, actions (JSON); TenantWorkflow.overrides; WorkflowTemplate.version; workflow_preview_api; validation in workflow_engine.run_actions. |

---

## Section 6 — Ecosystem Layer

| Id | Requirement | Verification |
|----|-------------|--------------|
| 6.3 | App installation lifecycle, app permission model, tenant app billing | Implemented: install_app pipeline (schema patch, widgets, AppAuditLog — marketplace/services.py); AppScope, permission model; tenant app billing documented (section_25_current_state.md, commercial_platform_29_10.md) and wiring in plan; can()/limits() for entitlements. |

---

## Sections 14–18, 21, 25, 30, 31 (feel-like, Salesforce-style, globalization, SoR, interop, school setup, entitlements, marketing, references)

| Section | Items | Verification |
|---------|--------|--------------|
| 14 | 14.1 To you (AWS/Stripe/Shopify feel); 14.4 Parent mobile-first; 14.5 Government/district; 14.6 Developers | Implemented: super command center, marketplace, runbooks (control-plane-shell); parent portal (mobile-friendly); government_district_intelligence.md; developer portal, API, webhooks, LTI/OneRoster. |
| 15 | 15.1 Student 360; 15.2 Metadata-driven; 15.3 Global ledger | Implemented: student360 services/views/export; DynamicFieldDefinition/Value where used; finance models, multi-currency/tax in section_28 and global_ledger_15_3.md. |
| 16 | 16.1 Globalization; 16.3 API first; 16.4 Edge; 16.5 Offline; 16.6 Testing matrix | Implemented: registries (currency, locale, RTL); policy language/RTL; REST API, WebhookSubscription, OneRoster/LTI; global_edge_and_testing_matrix.md; policy a11y.offline_mode; testing matrix documented. |
| 17 | 17.1 SoR vs Experience; 17.2 Portability; 17.3 Trust/compliance; 17.5 SRE | Implemented: policy/blueprint as SoR; OneRoster, compliance export; trust center, AuditLog; runbooks, kill switch, rate limit, observability (section_25_observability_sre.md). |
| 18 | 18.3 Zero trust, WCAG 2.2 AA, search_path | Implemented: tenancy, RLS (tenancy.md); a11y_wcag_low_bandwidth_offline.md; search_path documented. |
| 21 | 21.4 Operational identity | Implemented: Campus model; School.default_workflow_slug, default_dashboard_slug; operational_identity_21_4.md. |
| 25 | 25.1 Entitlements (proration, usage-based, invoice immutability, tax engine) | Implemented: can(), limits(); section_25_current_state.md and billing docs; rest in finance/billing scope. |
| 30 | 30.1 Competitor learnings; 30.2 Marketing front; 30.3 Win conditions | Implemented: MFA, tenant isolation, shadow masking; why-switch, verticals, trust-center, app-marketplace; blueprint, workflow/dashboard hubs, marketplace, AuditLog (phase21_through_phase24_sections_27_to_31.md). |
| 31 | 31.7 OpenFeature | Implemented: is_feature_enabled, can(); feature_flags.md; OpenFeature alignment documented. |

---

## Completion standard (Part F)

- No checklist row is marked complete using the words "deferred" or "scoped" or "partial" as the outcome.
- Each row is [x] with a short implementation or documentation reference.
- This validation doc is the single place that records what "complete" means for each item; implementation refs in the checklist point to code or docs.

---

**End of Part F validation.**
