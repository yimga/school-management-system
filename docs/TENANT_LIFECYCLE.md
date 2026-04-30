# Tenant (School) Lifecycle: Suspend, Archive, and Automation

**Purpose:** Document and standardise tenant lifecycle actions beyond provision. Used by control-plane and support.

---

## Customer lifecycle phases (product scale)

Canonical phases for onboarding, retention analytics, and automation at 1000+ schools (derived read model — **no duplicate writes** to `School`; composed from billing, onboarding checklist, health, and activity signals):

| Phase | Meaning |
|-------|---------|
| **trial** | Free trial / trialing subscription (`FREE_TRIAL` billing type or `TenantSubscription.Status.TRIALING`). |
| **onboarding** | Tenant active but activation checklist **&lt; 85%** (`get_school_onboarding_progress`). |
| **active** | Healthy engagement and checklist largely complete. |
| **at_risk** | Billing/frozen risk, low customer-health score, stale login activity, or billing exception. |
| **churned** | Tenant deactivated (`is_active=False`) — no login; data retained per policy. |

**Implementation:** `apps.platform_runtime.tenant_lifecycle_engine` — `resolve_lifecycle_phase(school)`, `compute_health_dimensions(school)`, `validate_phase_transition(from, to)`, `get_inactivity_alert(school)`, `get_retention_recommendations`, `get_success_automation_nudges`.

**Health scoring (0–100 pillars):** feature usage depth (students/teachers/reports), login recency (`School.last_activity` + staff `last_login`), payment/subscription posture (`TenantSubscription` + billing type), onboarding **completion_pct** (same as CCC checklist). Composite is a weighted blend for digests and automation.

**Onboarding engine:** Unchanged — continues to use `SchoolOnboardingProgress`, `get_school_onboarding_steps`, and siteconfig onboarding URLs; the lifecycle engine **reads** that progress.

**Retention / nudges:** `get_inactivity_alert` for stale tenants; recommendations reuse `get_school_health_recommendations` with lifecycle-aware extras.

---

## Implemented lifecycle actions

| Action | Effect | API |
|--------|--------|-----|
| **approve** | Set `school.is_approved = True`. | `POST /super/api/schools/<id>/lifecycle/` with `{"action": "approve"}` |
| **unapprove** | Set `school.is_approved = False`. | Same |
| **activate** | Set `school.is_active = True`. | Same |
| **deactivate** | Set `school.is_active = False`. Tenant cannot log in. | Same |
| **freeze** | Set `school.is_frozen = True`; reason `STORAGE` or `BILLING`. Subscription set to SUSPENDED when BILLING. | Same with `{"action": "freeze", "reason": "BILLING"}` |
| **unfreeze** | Clear `school.is_frozen` and `frozen_reason`. | Same |

**Operator UX (control plane):** On **School 360**, a top banner with **Unfreeze school — restore access** appears when frozen. **Schools list** (`/super/schools/`) supports **`?frozen=1`** and **Frozen only** in filters, highlights frozen rows, and adds a green **Unfreeze** button per row (one POST). **School Health** links to the frozen list and adds **Unfreeze** next to **360** when the tenant is frozen.
| **suspend** | **Alias for freeze.** Use for “suspend tenant” in UI/runbooks. | Same as freeze |
| **set_trial_end** | Set trial end date. | Same with `trial_end_date` |
| **clear_trial** | Clear trial; set billing to REGULAR. | Same |

---

## Archive (documented; automate when required)

- **Semantics:** Archive = tenant is deactivated and retained for compliance/history. No login; data retained.
- **Current:** Use **deactivate** to stop access. For “archive” in UI/runbooks, use **deactivate** and document retention policy. Optional future: add `School.is_archived` and an **archive** action that sets `is_active=False` and `is_archived=True`, and exclude archived schools from default listings.
- **Automation:** Lifecycle actions are applied via `apply_school_lifecycle_action()` in `apps.schools.control_plane_lifecycle`. To automate (e.g. auto-suspend after trial end): add a scheduled task that calls `apply_school_lifecycle_action(school, action="freeze", reason="BILLING")` for schools past trial end with no subscription.

---

## Suspend alias in code

The lifecycle handler accepts **suspend** as an alias for **freeze** so runbooks and UI can use “Suspend” consistently. Implemented in control_plane_lifecycle.

---

**See also:** `apps.schools.control_plane_lifecycle`, `api_school_lifecycle` in super_views, `SCHOOL_TENANT_CAMPUS_CANONICAL.md`.
