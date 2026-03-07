# SoR vs Experience (Section 17.1)

**Purpose:** Document the separation between **System of Record (SoR)** and **Experience** so that core data and behaviour are stable and auditable while UI and workflows can vary by tenant and role.

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Section 17; phase14_through_phase20_sections_14_to_26.md (17.1 scoped).

---

## 1. Definitions

| Layer | Meaning | Examples |
|-------|--------|----------|
| **SoR (System of Record)** | Canonical data, lifecycle, audit, policy-driven behaviour. Single source of truth; changes are audited and reversible where specified. | School, StudentProfile, Invoice, Payment; policy from `get_effective_policy(school)`; AuditLog; TenantAdmissionNumberPolicy; workflow template definitions. |
| **Experience** | Themed UI, widgets, dashboards, workflows as presented to a role or tenant. Can vary by blueprint, theme, and role without changing the underlying record. | Dashboard templates, TenantLayoutAssignment, theme (School/policy), workflow overrides (TenantWorkflow), portal shell, widget layout. |

---

## 2. Contract

- **SoR:** All writes to canonical entities go through services or model save with audit where required. Behaviour (e.g. admission number format, grading scale, fee rules) comes from **policy** (get_effective_policy, form_policy), not hardcoded in views. Policy and blueprint are versioned/audited (PolicyBundle, TenantBlueprint).
- **Experience:** Views and templates read from SoR and policy; they render using theme, dashboard resolver, workflow resolver. No business rules in templates; only presentation and layout.

---

## 3. Implementation status

| Item | Status |
|------|--------|
| Policy/blueprint as SoR for behaviour | Done — get_effective_policy, TenantBlueprint, PolicyBundle; no form config in views. |
| AuditLog for core events | Done — compliance app; AuditLog model; export actions. |
| Themed UI and dashboard/workflow from resolver | Done — workflow_resolver, dashboard_resolver; theme from School/policy. |
| Explicit SoR/Experience doc | Done — this doc. |
| Versioned policy (PolicyBundle, rollback) | Done — apply_blueprint_pack, active_bundle, revert. |

---

## 4. References

- policy_injection.md
- phase4_workflow_dashboard_hubs.md
- section_28_data_architecture_and_provisioning.md (brand vs site experience)
