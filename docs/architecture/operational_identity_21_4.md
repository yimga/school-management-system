# Operational Identity (Section 21.4)

Campus model, default workflow/dashboard, and comms/fee pack defaults for a school.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 21.4; phase12.

---

## 1. School model

- **default_workflow_slug:** Default workflow template slug for the school (e.g. from workflow gallery).
- **default_dashboard_slug:** Default dashboard template slug (e.g. by role).
- **Campus:** Where multi-campus is used, Campus model (or equivalent) groups classes/sites; school can have many campuses.

---

## 2. Policy slice: operational_identity

Resolver provides `policy["operational_identity"]` with:

- **default_workflow_slug:** From school or policy (empty string if not set).
- **default_dashboard_slug:** From school or policy.
- **comms_defaults:** Default channel/sender settings for communication.
- **fee_pack_defaults:** Default fee structure or pack reference.

Modules should read these from `get_effective_policy(school)["operational_identity"]` rather than reading `school.default_workflow_slug` directly when policy override is desired. School model remains source of truth for storage; policy merges from bundle/settings.

---

## 3. Implementation status

| Item | Status |
|------|--------|
| School.default_workflow_slug, default_dashboard_slug | Done (migration 0028) |
| policy["operational_identity"] | Done (resolver defaults + merge) |
| Campus model | Existing where used (academics/siteconfig) |
| comms_defaults / fee_pack_defaults wiring | Partial (keys in policy; modules can consume) |
