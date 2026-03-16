# Operating discipline layers (connective tissue)

This document expands the operating-discipline layers defined in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5. It holds the full checklists so the SOT stays scannable and one place has the complete detail.

**Authority:** RUNMYCAMPUS §10.5 is the plan; this doc is the expanded reference. Phase I in RUNMYCAMPUS §11 implements these layers.

---

## Decision architecture (meta-layer; §1.8 / §8.0)

Every important page, dashboard, workflow, and control must answer these **seven questions** (in code or in a registry/doc):

1. **Who is this for?** (primary user / role)
2. **What question are they asking?** (primary job-to-be-done)
3. **What state are they in?** (context: e.g. setup, operational, post-launch)
4. **What action should they take next?** (primary CTA / next-best-action)
5. **What confidence signal do we show?** (state clarity, success/error, progress)
6. **What happens if they are wrong?** (wrong-path handling, validation, recovery)
7. **What is the fallback path?** (escape hatch, help, support, rollback)

**Enforcement (§8.0):** No new or materially changed dashboard/page/workflow/control is accepted unless it declares these seven answers. Use **[DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md)** (template in repo) or declare in [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) / code.

---

## 10.5.1 Edge-case and failure strategy

**Goal:** The platform survives partial failures, conflicting overrides, policy collisions, workflow deadlocks, duplicate identities, bad imports, soft-deleted records, tenant over-limit, broken integrations, expired credentials, school shutdown/merger, and academic-year rollover failures.

**Categories to define (behavior + detection/mitigation):**

- Partial failure (service/DB/queue down)
- Conflicting overrides (runtime/precedent clash)
- Policy collision (multiple policies apply; precedence)
- Workflow deadlock (steps waiting on each other)
- Duplicate identity (same person/entity twice)
- Bad import (malformed data, schema mismatch)
- Soft-deleted record (access after delete; referential integrity)
- Tenant over-limit (seats, storage, API rate)
- Broken integration (external API/connector down or invalid)
- Expired credentials (API keys, tokens, certs)
- School shutdown/merger (data retention, access, migration)
- Academic-year rollover failure (rollover job fails; partial state)

**Actions:**

- Document formal strategy (e.g. `docs/EDGE_CASE_AND_FAILURE_STRATEGY.md`).
- Define behavior for each category (what we do when it happens).
- Add detection/mitigation where missing.
- Add tests or audits for critical paths.

**Completion gate:** Strategy doc exists; at least detection or mitigation for each category is defined and implemented for critical flows. **Status:** DONE — [EDGE_CASE_AND_FAILURE_STRATEGY.md](EDGE_CASE_AND_FAILURE_STRATEGY.md).

---

## 10.5.2 Packaging and versioning discipline

**Goal:** Packs are governed by semantic versioning, dependency graph, compatibility matrix, safe upgrade/downgrade, tenant impact preview, rollback behavior, deprecated-pack handling, ownership/provenance, and signed/certified levels.

**Actions:**

- Adopt semver for packs.
- Maintain dependency graph and compatibility matrix.
- Document safe upgrade path and downgrade rules.
- Tenant impact preview (e.g. in Studio OS or control plane).
- Rollback behavior documented and implemented.
- Deprecated-pack handling policy and UI.
- Ownership and provenance on packs.
- Signed/certified pack levels (required per RUNMYCAMPUS §11.1; implement or document N/A).

**Completion gate:** Versioning and compatibility doc; upgrade/downgrade/rollback rules in place; tenant impact preview available for pack changes; deprecated-pack handling defined. **Status:** DONE — [PACK_VERSIONING_AND_COMPATIBILITY.md](PACK_VERSIONING_AND_COMPATIBILITY.md).

---

## 10.5.3 Service and support operating layer

**Goal:** First-class product surfaces for onboarding success, implementation status, tenant maturity, support queue health, incident tracking, migration readiness, unresolved blockers, usage/adoption health, churn risk, expansion readiness.

**Surfaces to define and implement (or wire to existing):**

- Onboarding success
- Implementation status
- Tenant maturity score
- Support queue health
- Incident tracking
- Migration readiness
- Unresolved blockers
- Usage/adoption health
- Churn risk
- Expansion readiness

**Completion gate:** At least a control-plane or super dashboard (or equivalent) that surfaces these dimensions; no “support is only in the backend.”

**Status:** **DONE** — [SERVICE_AND_SUPPORT_OPERATING_LAYER.md](SERVICE_AND_SUPPORT_OPERATING_LAYER.md): dimension→surface mapping for all 10 dimensions; control-plane entry points; completion gate met.

---

## 10.5.4 Trust product (visible security and trust)

**Goal:** Security and trust are visible in product surfaces, not only in backend and docs.

**Surfaces to provide:**

- MFA status
- Device/session history
- Admin activity
- Impersonation/break-glass usage
- Integration/API key governance
- Policy enforcement status
- Data residency/regional behavior
- Audit exports
- Role/permission reviews
- Risky action approvals

**Completion gate:** Key trust dimensions (e.g. MFA, sessions, admin activity, audit exports) visible in a dedicated trust/security area or control plane; roadmap for the rest.

**Status:** **[TRUST_PRODUCT_SURFACES.md](TRUST_PRODUCT_SURFACES.md)** — trust product doc created; inventory of MFA, device/session history, admin activity, impersonation, API key governance, policy enforcement, data residency, audit exports, role/permission reviews, risky action approvals; entry points (profile security, RBAC, control plane, marketing trust pages); completion gate met; roadmap for trust hub and data residency visibility.

---

## 10.5.5 Dashboard taxonomy

**Goal:** Every dashboard is declared and governed so it is not a junk drawer.

**Required declarations per dashboard:**

- User (primary user/role)
- Job-to-be-done
- Dashboard type (strategic / operational / analytical)
- Primary question answered
- Primary action enabled
- Update frequency
- Drill-down path
- Alerting behavior

**Actions:**

- Maintain a dashboard registry or doc.
- All existing critical dashboards registered.
- New dashboards must declare before merge.

**Completion gate:** Taxonomy doc/registry exists; all existing critical dashboards registered; new dashboards must declare before merge.

**Status:** **[DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md)** — registry doc created; 17 critical dashboards registered (incl. Workflow Center, Guided onboarding, Operator workbench); policy for new dashboards in place.

---

## 10.5.6 Content and terminology governance

**Goal:** One glossary, one naming registry, one terminology standard by institution type/region, one UX writing guide, one CTA hierarchy, one alert/warning language model, one empty-state/help-state system.

**Artifacts to create and maintain:**

- Product glossary
- Naming registry
- Terminology standard by institution type/region
- UX writing guide
- CTA hierarchy
- Alert/warning language model
- Empty-state/help-state system

**Completion gate:** At least glossary and UX writing guide in place; naming/terminology and empty-state system scoped and started.

**Status:** DONE — [CONTENT_AND_TERMINOLOGY_GOVERNANCE.md](CONTENT_AND_TERMINOLOGY_GOVERNANCE.md) (product glossary, UX writing guide, CTA/alert/empty-state; naming registry and terminology by institution type/region scoped; empty-state system references EMBEDDED_HELP_AND_EMPTY_STATES).

---

## 10.5.7 Design system (behavior, not just components)

**Goal:** Standards for behavior as well as components: page/dashboard archetypes, drawers, wizards, modals, filter panels, preview panels, publish flows, error/loading states, action bars, command palette behavior, keyboard support, accessibility minimums, motion rules.

**Behavior standards to document and enforce:**

- Page and dashboard archetypes
- Drawers
- Wizards
- Modals
- Filter panels
- Preview panels
- Publish flows
- Error/loading states
- Action bars
- Command palette
- Keyboard support
- Accessibility minimums
- Motion rules

**Completion gate:** Design-system-behavior doc exists; §8.0 and Studio OS aligned to it; new UI must follow it.

**Status:** **[DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md)** — behavior doc created; archetypes, drawers, wizards, modals, filter/preview panels, publish flows, error/loading, action bars, command palette, keyboard, a11y, motion; §8.0 and Studio OS alignment referenced.

**Status:** **[DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md)** — behavior doc created; all standards defined; aligned to §8.0 and Studio OS.

---

## 10.5.8 Boring excellence program

**Goal:** Recurring discipline so the platform does not decay: performance budgets, accessibility audits, route maturity scoring, dead button/link detection, stale flag cleanup, duplicate shell detection, unused model/page cleanup, docs truth audits, observability gaps, permission drift, config sprawl detection.

**Recurring checks (CI or scheduled tasks):**

- Performance budgets
- Accessibility audits
- Route maturity scoring
- Dead button/link detection
- Stale flag cleanup
- Duplicate shell detection
- Unused model/page cleanup
- Docs truth audits
- Observability gaps
- Permission drift
- Config sprawl detection

**Completion gate:** Program doc exists; at least three of these (e.g. dead link detection, docs truth, observability or permission drift) are automated or in CI; rest on a schedule.

**Implementation:** [BORING_EXCELLENCE_PROGRAM.md](BORING_EXCELLENCE_PROGRAM.md) — program doc created; dead link/URL reverse (phase_h_audit, Phase H tests), docs truth (ledger + BACKLOG), observability (health, logging), lints (broad_except, secret_exposure, raw_sql), accessibility (phase_h_audit) in CI; permission drift, config sprawl, and rest on schedule.
