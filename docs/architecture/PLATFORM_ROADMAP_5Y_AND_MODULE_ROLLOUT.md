# RunMyCampus platform roadmap — 5-year horizon and module-by-module rollout

**Purpose:** Full platform roadmap and module-by-module rollout order, tied directly to the current codebase and refactor phases. Use for planning, prioritisation, and sprint alignment. **Policy: all roadmap items are due today** — see ROADMAP_DUE_TODAY.md for implemented vs deliverable.  
**Sources:** REFINEMENT_AND_IMPLEMENTATION_ORDER.md, REMAINING_PLAN_AUDIT_GAPS.md, RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md (Part D, Section 12, refactor waves), phase11_module_architecture_section_9.md, REMAINING_PHASES_EXECUTION_ORDER.md, ROADMAP_DUE_TODAY.md.

---

## How to use this doc

1. **Strategic planning:** Use the 5-year horizon (Section 2) for themes and major milestones.
2. **Module ownership:** Use the module-by-module rollout (Section 3) to see refactor status and next steps per app.
3. **Sprint backlog:** Use the prioritised backlog (Section 4) and execution order (Section 5) to pull work into sprints; priorities align with REFINEMENT_AND_IMPLEMENTATION_ORDER and REMAINING_PLAN_AUDIT_GAPS.
4. **Checklist alignment:** Every item ties to checklist sections (1–31) or phase docs so implementation can update the main architecture checklist.

---

## 1. Current state (as of roadmap baseline)

- **Runtime constitution:** Done. One tenant runtime object (`request.tenant_runtime`), one blueprint registry, one policy resolver, one injection path. See ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md.
- **Refactor waves 1–8:** Done. Tenancy cleanup → Blueprint foundation → Admissions → Gradebook/attendance → Finance/comms → Dashboard/workflow → Marketplace → Control plane hardening. See refactor_waves_12_7.md.
- **Phases 1–6 (Part D):** Delivered. Registries, control/tenant separation, hardcoding sweep, workflow/dashboard hubs, migration cloud, app and blueprint marketplace.
- **Phases 7 (24.12–24.15), 8 (migration cloud + marketplaces):** Delivered. Deferred refinements in “Deferred and optional items register” and REMAINING_PLAN_AUDIT_GAPS.
- **Remaining work:** REFINEMENT priorities 2–4; REMAINING_PLAN_AUDIT_GAPS (6.3/29.10 tenant app billing, 11.2 tenant-facing Get blueprints, 26.5 UX, 1.8 sandbox hardening, control plane maturity); REMAINING_PHASES_EXECUTION_ORDER Phases 3–24 where not yet closed.

---

## 2. Five-year horizon

| Year | Theme | Key deliverables |
|------|--------|-------------------|
| **Year 1** | Stability and runtime constitution | Runtime constitution done. Close remaining refactor phases (metadata-driven forms, Section 23 audit). Tenant-facing Get blueprints (11.2). UX rules audit and list search/filter/export (26.5). No-hardcoding and provider-abstraction enforcement. |
| **Year 2** | UX, control plane, and gap closure | Control plane maturity (health dashboard, SLOs, rollout/canary, support queue). Tenant app billing wiring (6.3/29.10). Secure app sandbox hardening (1.8) if needed. Parent mobile-first audit. Student 360 UI and immutable transcript (15.1, 26.1). |
| **Year 3** | Student 360, ledger, and integrations | Full Student 360 UI, cross-year archive, transcript. Global ledger (double-entry, payment plans, installments) (15.3). Offline-first and sync engine (16.5). Ed-Fi/CEDS and WebAuthn/passkeys (18.x, 29.1). Preview/release (staging schema, canary) (29.4). |
| **Year 4** | Scale, government, and commercial | Government/district intelligence layer (14.5). Commercial platform (trials, quote-to-contract, partner tooling) (29.10). Metadata-driven data layer / DynamicField (15.2). Multi-region and data residency. |
| **Year 5** | Platform maturity and differentiation | Full roadmap closure; SRE and observability maturity; marketplace and ecosystem growth; optional 5-year refresh of this roadmap. |

---

## 3. Module-by-module rollout order

Order reflects refactor waves (done) and next steps per module. **Refactor status:** Done = policy-only, tenant_runtime-ready where applicable; Next = use tenant_runtime everywhere, UX/audit; Roadmap = new capability or larger scope.

| Module | Apps / touchpoints | Refactor status | Next steps | Roadmap year |
|--------|--------------------|-----------------|------------|--------------|
| **Tenancy / Platform runtime** | tenancy, platform_runtime, schools (middleware) | Done | Keep as single source of identity + policy; no change. | — |
| **Policies / Blueprint** | policies (resolver, resolvers, context_processors, form_policy, blueprint_services) | Done | Optional: more forms via apply_form_policy (Phase 3). | — |
| **Siteconfig** | siteconfig (workflow_resolver, dashboard_resolver, tenant_config, workflow hub, dashboard hub) | Done | Tenant-facing Get blueprints entry (11.2). | Y1 |
| **Admissions** | people (StudentProfile, admission number), portal (onboarding, link_child) | Done | UX: list search/filter/export; form autosave for onboarding if critical. | Y1–Y2 |
| **Evals / Gradebook** | evals, academics (courses, syllabus) | Done | All views use request.tenant_runtime where possible; UX on marksheet/list. | Y1 |
| **Finance** | finance (gateways, models, views) | Done (policy + tenant_runtime.policy in gateways) | Tenant app billing wiring (6.3/29.10). Global ledger extension (15.3). | Y1–Y3 |
| **People** | people, accounts | Done (policy for admissions/RBAC) | UX: staff list search/filter/export. WebAuthn/passkeys (29.1). | Y2–Y3 |
| **Portal** | portal (dashboard, forms, parent/student views) | Done (policy, dashboard_resolver, workflow) | Parent mobile-first audit (14.4). Student 360 UI (15.1, 26.1). | Y2 |
| **Reports** | reports | Done (policy for labels, grading_scale) | Report list/search/export; BI/export enhancements. | Y1–Y2 |
| **Communication** | communication | Done (policy slice) | Channel/provider abstraction; messaging UX. | Y2 |
| **Compliance** | compliance (audit, evidence, consent) | Done (policy, AuditLog) | Retention/export refinements; inspector portal. | Y2 |
| **Marketplace** | marketplace (catalog, install, sandbox) | Done (install pipeline, governance) | Tenant app billing (6.3); sandbox hardening (1.8). | Y1–Y2 |
| **Billing** | billing (platform billing, processors) | Done (Stripe processor, subscriptions) | Tenant app billing line items; proration for app installs. | Y1–Y2 |
| **Student 360** | student360 (services, export) | Partial (services exist) | Full 360 UI, timeline, immutable transcript, cross-year archive (15.1, 26.1). | Y2–Y3 |
| **Events / Webhooks** | events (DomainEvent, WebhookDelivery) | Done | Use event backbone for more domain events; optional event catalog UI. | Y2–Y3 |
| **Interop** | interop (oneroster, lti, edfi, ceds) | Done (adapters, APIs) | Ed-Fi/CEDS depth; optional LTI 1.3 Advantage extensions. | Y3 |
| **Observability / SRE** | observability, control plane runbooks | Done (request_id, tenant_id, metrics) | Health dashboard, SLOs, canary (29.4); control plane maturity. | Y1–Y2 |
| **Metadata (custom attributes)** | metadata | **Done** | DynamicFieldDefinition, DynamicFieldValue, services, admin (15.2). API/UI extensions per product. | — |
| **Government / District** | — | Roadmap | EMIS, secure aggregation (14.5). | Y4 |

---

## 4. Prioritised backlog (by source)

Mapped from REFINEMENT_AND_IMPLEMENTATION_ORDER and REMAINING_PLAN_AUDIT_GAPS into this roadmap.

### From REMAINING_PLAN_AUDIT_GAPS

| Gap | Goal | Next step | Target year |
|-----|------|-----------|-------------|
| 6.3 / 29.10 Tenant app billing | Wire app installs to billing (proration, invoice line) | Billing event on install; subscription line per app; proration. | Y1–Y2 |
| 11.2 Tenant-facing Get blueprints | Tenant backend entry for blueprint discovery/request | Add “Get blueprints” or blueprint gallery in tenant backend; link from siteconfig/settings. | Y1 |
| 26.5 UX rules | Search/filters/export on key lists; autosave/draft on critical forms | Audit students, staff, invoices; add search/filter/export; autosave for application/report config. | Y1–Y2 |
| 1.8 Secure app sandbox | Harden iframe/CSP; postMessage contract; embed audit | Security pass on sandbox_embed and all embed points; document contract. | Y2 |
| Control plane maturity | “AWS console for schools” (health, rollout, support) | Health dashboard (SLOs, incidents); rollout/canary; support queue; runbooks linked from super. | Y1–Y2 |

### From REFINEMENT_AND_IMPLEMENTATION_ORDER (Priority 2–4)

| Priority | Item | Section | Next step | Target year |
|----------|------|---------|-----------|-------------|
| 2 | UX rules (list search/filters/export, form autosave) | 26.5 | See 26.5 above. | Y1–Y2 |
| 2 | Parent mobile-first | 14.4 | Audit parent portal; viewport, touch targets, responsive layout. | Y2 |
| 3 | Ed-Fi adapter | 18.1 | Interop adapter; map canonical → Ed-Fi; optional API. | Y3 |
| 3 | CEDS for reporting (US) | 18.2 | CEDS mapping and translation layer. | Y3 |
| 3 | WebAuthn / Passkeys | 29.1 | Add passkey option alongside TOTP. | Y3 |
| 4 | Student 360 / timeline / transcript | 15.1, 26.1 | Full 360 UI; immutable transcript; cross-year archive. | Y2–Y3 |
| 4 | Metadata-driven data layer (DynamicField) | 15.2 | Design and implement DynamicFieldDefinition/Value. | Y4 |
| 4 | Global ledger (double-entry, payment plans) | 15.3 | Extend finance; payment plans and installments. | Y3 |
| 4 | Offline first + sync engine | 16.5 | Offline-capable flows; sync engine and conflict resolution. | Y3 |
| 4 | Preview/release (staging, canary) | 29.4 | Staging schema; config diff; canary by tenant/country/plan. | Y3 |
| 4 | Government/district intelligence | 14.5 | EMIS/reporting; secure aggregation; product roadmap. | Y4 |
| 4 | Commercial platform (trials, quote-to-contract) | 29.10 | Self-serve trials; quote-to-contract; partner tooling. | Y4 |

---

## 5. Execution order (phases tied to roadmap)

Remaining phases from REMAINING_PHASES_EXECUTION_ORDER; map to years for planning. Phases 1–2 already done.

| Phase | Scope | When (roadmap) |
|-------|--------|----------------|
| 3 | Section 24.8: metadata-driven config (remaining forms, POLICY_USE_BUNDLES/CACHE) | Y1 |
| 4 | Workflow and dashboard hubs — full UI and flows (already largely done; verify and doc) | Y1 |
| 5 | Section 23: policy/blueprint injection audit and fix | Y1 |
| 6+ | Section 25 (entitlements, isolation, observability, security, governance, a11y) — refinements | Y1–Y2 |
| … | Sections 26–31 and remaining phases per REMAINING_PHASES_EXECUTION_ORDER | Y2–Y5 |

Use REMAINING_PHASES_EXECUTION_ORDER.md for the full ordered list (Phases 3–24). This roadmap assigns target years; sprint planning should still follow phase order within each year.

---

## 6. Summary table: Year → focus areas

| Year | Focus areas |
|------|-------------|
| **Y1** | Runtime constitution done. Close Phase 3–5. Tenant Get blueprints (11.2). UX rules audit and list search/filter/export (26.5). No-hardcoding and provider audit. Control plane health/SLOs. Tenant app billing start (6.3/29.10). |
| **Y2** | Control plane maturity. Tenant app billing complete. Sandbox hardening (1.8). Parent mobile-first. Student 360 UI and transcript. UX autosave/draft where critical. |
| **Y3** | Student 360 full; global ledger; offline + sync engine. Ed-Fi/CEDS; WebAuthn/passkeys. Preview/release (canary). |
| **Y4** | Government/district layer. Commercial platform (trials, quote-to-contract). DynamicField (metadata-driven attributes). |
| **Y5** | Platform maturity; roadmap refresh; differentiation and scale. |

---

## References

- RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md (Part D, Part E, Part F)
- REFINEMENT_AND_IMPLEMENTATION_ORDER.md
- REMAINING_PLAN_AUDIT_GAPS.md
- REMAINING_PHASES_EXECUTION_ORDER.md
- refactor_waves_12_7.md
- phase11_module_architecture_section_9.md
- ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md
