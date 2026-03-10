# RunMyCampus Metadata-Driven Platform Codex
## Non-Negotiable Architecture Mandate

**Purpose:** This codex defines the non-negotiable architecture rules for RunMyCampus to become a metadata-driven, multitenant, extensible, governable education platform (Salesforce/Shopify/AWS standard). It overrides convenience-based development patterns.

---

## 1. Core platform law

RunMyCampus must behave as: a multitenant runtime platform; a metadata-driven product system; a governed configuration and pack marketplace; a low-click operator environment; a secure and auditable control plane. It must not drift toward: hardcoded tenant features, giant singleton settings objects, module-owned ad hoc configuration, per-tenant code paths, settings landfill sprawl, unmanaged metadata changes.

## 2. Metadata-first architecture is mandatory

**2.1 Metadata is a first-class asset** — All significant customization and tenant behavior must be represented as metadata where practical (schema extensions, dynamic fields, layouts, page composition, navigation, dashboard/workflow/policy definitions, blueprint/pack assignments, branding, communication templates, integration mappings, entitlements, regional definitions).

**2.2 Metadata must be governed like code** — Versioning, audit logging, diffing, validation, preview, rollback, environment promotion, ownership.

**2.3 No tenant-specific hardcoding** — No branching on tenant names/slug/domain; no tenant-only code paths; no ad hoc "just for this customer" flags outside formal metadata/entitlement systems. All tenant-specific behavior via runtime, blueprints, packs, policies, registries, entitlements, metadata overrides.

## 3. Centralized metadata model

The platform must maintain a formal metadata catalog (single source of truth) covering six families: **Schema** (entities, fields, validation, state machines); **Experience** (layouts, forms, role homes, themes, dashboard definitions, communication templates); **Runtime** (blueprints, workflow/dashboard packs, policy bundles, tenant overrides, entitlements, module composition); **Registry** (countries, locales, calendars, terminology, grading scales, institution types, compliance packs); **Integration** (providers, scopes, webhooks, sync mappings); **Governance** (ownership, scope, version, lifecycle state, approval, compatibility, rollback). Every metadata item must declare: type, scope, source, owner, version, lifecycle state, compatibility, security classification, preview-required, rollback-supported.

## 4. Runtime is the law

All tenant-facing behavior must be runtime-resolved. No direct global config access in tenant flows. Resolvers mandatory: RuntimeResolver, SchemaResolver, LayoutResolver, PolicyResolver, BlueprintResolver, EntitlementResolver, WorkflowResolver, DashboardResolver, BrandingResolver, IntegrationResolver. Runtime must be observable (inspection tools) and testable (resolution order, fallbacks, precedence, tenant isolation).

## 5. Metadata precedence and multitenant isolation

Every metadata item must have explicit scope (platform-global, region, blueprint, pack, plan, tenant, sandbox). Effective precedence chain: (1) platform default (2) regional/registry default (3) blueprint default (4) policy bundle (5) plan/entitlement constraint (6) tenant override (7) sandbox/staged override. Tenant isolation mandatory; every request/event/job/workflow/metadata resolution/data mutation anchored to tenant identity where applicable.

## 6. Declarative over imperative

Prefer declarative metadata for validations, workflows, role home composition, dashboard composition, form composition, labels, regional behavior, approval rules, feature availability. Operators solve problems by configuration, not engineering tickets. Declarative changes must support preview, impact analysis, dependency checks, simulation where applicable, rollback.

## 7. Metadata as code and metadata lifecycle

Pack-level and environment-level metadata must be version-controlled. Metadata package engine must support: export, import, validate, compare, preview impact, sandbox apply, rollback, promote across environments. No major metadata change relying solely on manual click-only configuration.

## 8. Active metadata, lineage, and data dictionary

RunMyCampus must maintain a business-first metadata catalog answering: what is this object/field? who owns it? who uses it? what workflows/dashboards/reports/APIs/templates/policies/integrations depend on it? Dependency and lineage tracking mandatory. Business glossary (education terms → technical metadata) must exist and be metadata.

## 9. Security and access control metadata

Metadata changes require metadata governance. Roles (minimum): Platform Config Admin, Runtime Steward, Policy Steward, Registry Steward, Marketplace Governor, Migration Operator, Implementation Specialist, District Operator, Tenant Admin, Support Read-Only, Break-Glass. Sensitive metadata changes require preview, audit, approval where needed, rollback. Every privileged metadata mutation must log: actor, old value, new value, scope, impacted tenant(s), timestamp, reason/ticket, rollback reference.

## 10. Governor limits and platform safety

Enforceable limits for: workflow execution volume, API throughput, dashboard refresh cost, migration concurrency, app scope usage, AI invocation volume, dynamic field counts, pack complexity. Limits must not fail silently; produce clear operator messages, deferred execution where possible, audit logs, admin visibility.

## 11. Low-click operator standard

Metadata and runtime must simplify UX: fewer clicks, clearer defaults, more reusable templates, safer defaults, faster outcomes. Every major operator task must have a guided path. Present outcomes, not internal jargon ("Standardize grading" not "Apply policy bundle"). Every major metadata operation preview-first.

## 12. Non-negotiable implementation mandates

Decompose siteconfig; make runtime the law; build formal Metadata Catalog; build Metadata Package Engine; build Setup Studio; productize packs (preview, compare, compatibility, rollback, recommendation); add metadata governance and security roles; add lineage and dependency visibility; add architecture enforcement in CI.

## 13. CI and review gates

Pipeline must fail when: direct singleton/global settings access is added to tenant-facing code; forbidden metadata bypasses are introduced; large unbounded config files are introduced; broad `except Exception` appears in sensitive flows without approved justification; privileged metadata mutations lack audit hooks; high-risk metadata changes lack tests; pack/policy/runtime precedence tests are missing.

## 14. Definition of done

RunMyCampus reaches this standard only when: metadata is centralized enough to be discoverable and governed; tenant behavior is runtime-resolved, not ad hoc; packs and policies are packageable and rollbackable; metadata changes are versioned, previewed, and auditable; lineage and dependency visibility exist; multitenant isolation is explicit and tested; operator UX is simpler because of metadata; system config is decomposed and no longer a giant sprawl zone.

## 15. Final non-negotiable statement

RunMyCampus will not drift into a hardcoded, sprawl-heavy, settings-landfill architecture. It will become a metadata-driven, runtime-governed, multitenant education platform where metadata is first-class, runtime is the law, packs are products, configuration is governed, security is metadata-aware, and operators achieve more with fewer clicks — easier to extend, localize, govern, and harder to replace.
