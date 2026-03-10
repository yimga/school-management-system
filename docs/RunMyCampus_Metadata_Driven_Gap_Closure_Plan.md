# RunMyCampus Metadata-Driven Gap Closure Plan
## Non-Negotiable Execution Plan to Become the Shopify / Salesforce / AWS of Education

## Mission

RunMyCampus must evolve from a feature-rich multi-tenant education product into a **metadata-governed platform ecosystem** where: metadata is first-class; runtime is the law; tenant behavior is declarative; packs are products; onboarding is guided and low-click; customization is safe, auditable, and rollbackable; APIs and apps extend the platform without breaking the core; every operator task is simpler than on legacy SIS platforms.

---

## 1. The gap we are closing

**Current state:** RunMyCampus already has tenant runtime contracts, dynamic fields/state machines, policies and blueprints, workflow/dashboard packs, registries, marketplace models, migration profiles.

**The actual gap:** The platform is still too mixed between metadata-driven behavior and direct model/global settings behavior — causing sprawl, duplicated logic, hidden precedence, giant config surfaces, weak operator trust, slower onboarding, harder testing and governance.

**Non-negotiable target state:** Metadata-centered, runtime-resolved, pack-deployed, tenant-isolated, audit-safe, preview-first, rollback-capable, low-click by design.

---

## 2. Architecture law

- **Metadata is first-class** — Everything that varies by tenant, region, school type, workflow, dashboard, layout, terminology, or business rule must live in metadata whenever practical.
- **Runtime is the law** — All tenant-facing behavior must be compiled from metadata through the runtime engine; no ad hoc behavior in tenant-facing code.
- **Declarative over imperative** — Different grading rules, attendance workflows, parent portal sections, or role dashboards must be solved by metadata and runtime, not custom code branches.
- **No tenant-specific hardcoding** — No special-case by tenant name, slug, domain, or one-off boolean; all via blueprints, policies, packs, registries, entitlements, runtime overrides.

---

## 3. Target platform architecture (five layers)

1. **Metadata Catalog** — Platform brain (schema, experience, runtime, registry, integration, governance metadata).
2. **Runtime Compiler** — Translation engine (resolves branding, blueprint, policies, packs, entitlements, modules, integrations, locale, role homes per request/tenant/role/route).
3. **Metadata Package Engine** — Export, import, validate, diff, preview impact, sandbox apply, rollback, promote.
4. **Governance and Security Engine** — Who can create/edit/approve/apply/roll back metadata; scope/workflow/registry controls.
5. **Operator Experience Layer** — Setup Studio, Brand Studio, Policy Console, Runtime Console, Marketplace Console, District Control Plane, Migration Cloud, Role Homes.

---

## 4. Required decomposition (siteconfig)

Break siteconfig into seven bounded domains: **brand_experience** (themes, logos, colors, domains, portal/website templates, communication templates); **runtime_blueprints** (blueprint definitions, starter stacks, runtime composition); **policies_rules** (grading, attendance, billing, communication, approval rules, policy bundles); **plans_entitlements** (plans, trials, add-ons, caps, commercial entitlements); **global_registries** (countries, calendars, grade scales, institution types, terminology, compliance); **integrations_marketplace** (providers, scopes, connectors, install/compatibility metadata); **metadata_catalog** (entity dictionary, field catalog, dependency catalog, business glossary, lineage). Shrink SiteSettings to platform defaults only. Break giant files (siteconfig/models, siteconfig/admin, accounts/views, schools/super_views, portal/views, finance/views, api/views_v1) by business domain.

---

## 5. Runtime enforcement

Ban direct singleton/global behavior in tenant flows. Add resolver services (RuntimeResolver, SchemaResolver, LayoutResolver, BrandingResolver, BlueprintResolver, PolicyResolver, WorkflowResolver, DashboardResolver, EntitlementResolver, IntegrationResolver, LocalizationResolver). Define explicit precedence: platform default → regional → blueprint → policy → plan → tenant override → sandbox; implement and test. Add runtime observability (active blueprint, packs, policy bundles, entitlements, locale overlays, branding, integrations, override sources).

---

## 6. Metadata catalog and lineage

Build first-class metadata catalog: entity catalog (student, person, parent, staff, class, attendance, grade, invoice, payment, application, communication, etc.); field catalog (name, entity, type, standard/custom, validation, source package, scope, API/UI exposure, dependency count); dependency catalog (workflows, dashboards, reports, APIs, templates, policies, integrations using each field); business glossary (class/form/homeroom, term/trimester, tuition/levy/fee, guardian/parent/sponsor). **Lineage-first rule:** No important metadata change without showing downstream impact (what breaks? what workflows/dashboards/policies/integrations depend on it?).

---

## 7. Metadata lifecycle and deployment

Package types: blueprint packs, workflow packs, dashboard packs, policy bundles, theme packs, communication template packs, dynamic field sets, state machine bundles, migration packs. Every package: versioning, export/import, validation, compatibility checks, preview, sandbox apply, rollback, environment promotion. Metadata as code: exportable to source control, testable in CI, reviewable in PRs, auditable across environments. No major metadata change only as manual click configuration.

---

## 8. Multitenant isolation and safety

Every relevant record and request must carry tenant context (request, jobs, events, webhook handlers, workflow runs, metadata resolution, data writes). Scope every metadata object (global, regional, blueprint, pack, tenant, sandbox). Tenant-isolation tests: tenant metadata does not leak; overrides do not mutate global defaults; pack installs correctly scoped. Governor limits: workflow volume, API throughput, dashboard refresh cost, migration concurrency, app scope usage, AI invocation volume, dynamic field counts, pack complexity.

---

## 9. Security and metadata governance

Define metadata roles (Platform Config Admin, Runtime Steward, Policy Steward, Registry Steward, Marketplace Governor, Migration Operator, Implementation Specialist, District Operator, Tenant Admin, Support Read-Only, Break-Glass). Sensitive metadata changes (policy, plan/entitlement, workflow activation, scope grants, migration profile, registry, break-glass, AI permissions) must require preview, audit, approval where needed, rollback. Audit trail mandatory: actor, old/new value, scope, tenant(s) affected, timestamp, reason/ticket, rollback reference.

---

## 10. Low-click Setup Studio

One unified flow: (1) Create school — name, country, institution type, size, current system, admin identity. (2) Choose plan — free trial, starter, growth, enterprise/district. (3) Apply recommended blueprint. (4) Import or create branding (upload logo/colors, import website, choose template). (5) Choose starter stack (core operations, admissions, parent engagement, finance, analytics, district governance, international school). (6) Choose data path (vendor migration, CSV, directory sync, sample/demo). (7) Preview by role (admin, teacher, parent, student, website/portal). (8) Launch checklist (branding, users, dashboards, workflows, migration validation, first reports). Brand import assistant (URL → logo, favicon, colors, title, contact, social links, template recommendation). Setup health score (branding, user, workflow, dashboard, data, migration readiness).

---

## 11. Pack productization

Blueprints as institution design kits (structure, calendars, labels, modules, starter dashboards, recommended workflows, compatible policies, theme starter; compare, preview, sandbox, rollback, version notes). Workflow packs as installable automation (problem solved, triggers, roles, actions, simulation, compatibility, rollback). Dashboard packs as role-native control centers (role, KPIs, widgets, sample data preview, mobile view, compatibility). Policy bundles: diff, impact preview, sandbox apply, rollback, dependency warnings.

---

## 12. Marketplace and ecosystem

Seed targets: 25+ first-party apps, 25+ blueprint packs, 30+ workflow packs, 20+ dashboard packs, 15+ policy bundles, rich migration packs by vendor/region. Every listing: screenshots/previews, compatibility, region support, plan requirements, scopes/permissions, trust/compliance notes, sandbox support, version history. Partner/developer ecosystem: API portal, SDKs, webhook docs, sandbox tenants, app certification, scope review, partner analytics.

---

## 13. CI and architecture enforcement

CI must fail when: direct singleton/global config access is added to tenant-facing code; forbidden metadata bypasses are introduced; giant unbounded config files are added; privileged metadata changes lack audit hooks; high-risk runtime/precedence changes lack tests; broad `except Exception` in sensitive flows without approved justification.

---

## 14. Definition of done

RunMyCampus reaches the required standard only when: metadata is centralized, governed, and discoverable; runtime is the universal behavior engine; packs are packageable and rollbackable; metadata changes are versioned and previewable; lineage and dependency visibility exist; multitenant isolation is explicit and tested; system configuration is decomposed; onboarding is unified and low-click; operator UX is simpler because of metadata, not more complex.

---

## 15. Final command for engineering

RunMyCampus will not drift into a hardcoded, sprawl-heavy, settings-landfill architecture. It will become a metadata-driven, runtime-governed, multitenant education platform where metadata is first-class, runtime is the law, packs are products, configuration is governed, tenant isolation is explicit, security is metadata-aware, and operators achieve more with fewer clicks — easier to extend, localize, govern, and harder to replace.

---

## Shortest blunt answer — five things in sequence

1. **Decompose siteconfig and stop configuration sprawl**
2. **Make runtime the only legal source of tenant behavior**
3. **Build a formal metadata catalog with lineage and governance**
4. **Turn blueprints/workflows/dashboards/policies into real deployable metadata packages**
5. **Use all of that to make onboarding, configuration, and daily operations dramatically lower-click than competitors**

That is how you move from "metadata-aware" to metadata-driven platform law.
