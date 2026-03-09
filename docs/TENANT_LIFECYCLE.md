# Tenant (School) Lifecycle: Suspend, Archive, and Automation

**Purpose:** Document and standardise tenant lifecycle actions beyond provision. Used by control-plane and support.

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
