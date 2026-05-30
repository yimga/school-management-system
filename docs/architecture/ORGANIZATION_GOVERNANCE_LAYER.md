# Organization Governance Layer

Phase 2 architectural canon for the optional organization overlay above the `School` tenant boundary.

## Non-negotiable principle

- `School` remains the tenant boundary (isolation, billing, data residency).
- `Organization` is an **overlay**, not a replacement. Schools can run standalone with `organization=NULL` indefinitely.
- All group features (rollups, cross-tenant HR, consolidated billing, EMIS aggregation) sit behind feature flags that default off.
- No country or sector hardcodes a group-only path. Country matrix recommends a default operating mode; the tenant overrides.

## Models

| Model | Responsibility |
|-------|---------------|
| `Organization` | Legal owner type (proprietor, corporation, diocese, ministry, NGO, franchise). Optional FK from `School`. |
| `GovernanceNode` | Optional tree (diocese office, LGA, MAT central, state dept). |
| `OrgMembership` | `User` x `Organization` x role (`owner`, `group_admin`, `inspector`, `superintendent`). |
| `Employment` | Employer relationship (org-level or school-level). |
| `SchoolAssignment` | Deployment of an `Employment` to a specific `School`. Powers transfer workflows. |
| `OrganizationLifecycleEvent` | Immutable, signed event row for split / merge / dissolve / change-of-control / school-moves-org / bankruptcy / regulator-export. |
| `OrganizationControlChange` | Chain of custody for change-of-control events; references the prior controller and the incoming. |

## Operating modes per `School`

| Mode | Meaning |
|------|---------|
| `standalone` | Full local management, no org membership required. Default. |
| `group_member` | Member of an `Organization`; configurable per-domain inheritance (`governance_inherit` JSON). |
| `group_member_sovereign` | In a group but per-domain opt-out of central control. |

The mode is `RuntimeDefaults` -> `School.settings` driven. No hard-coded country branch.

## Lifecycle event contract

Every state mutation on `Organization` (or the `Organization` <-> `School` link) MUST produce a row in `OrganizationLifecycleEvent`. Direct UPDATE without an event is a verifier failure under [`scripts/verify_org_lifecycle_events.py`](../../scripts/verify_org_lifecycle_events.py).

| Event | Required payload | Notification target |
|-------|------------------|---------------------|
| `org.split` | source_org_id, child_org_ids[], reassignment_rule | regulator per residency |
| `org.merge` | source_org_ids[], target_org_id, inheritance_reconcile_map | regulator per residency |
| `org.dissolve` | org_id, terminal_date, residual_school_disposition | regulator + counsel signoff |
| `org.change_of_control` | org_id, prior_controller_ref, incoming_controller_ref, sale_doc_hash | varies by statute |
| `school.move_org` | school_id, from_org_id, to_org_id, inheritance_reset_map | none statutory; tenant comms required |
| `org.bankruptcy_winddown` | org_id, retention_countdown_starts_at, locked_writes_at | records authority signoff |
| `org.regulator_export_request` | org_id, requesting_authority, court_order_hash | cryptographic chain-of-custody |

## Inheritance map (per domain)

`School.settings["governance_inherit"]` is a domain -> mode map. Domains: `curriculum`, `fees`, `hr`, `branding`, `emis`, `integrations`. Modes per domain: `inherit`, `local`, `hybrid`.

Idempotence rule (verified by property tests in [`apps/governance/tests/test_governance_property_invariants.py`](../../apps/governance/tests/test_governance_property_invariants.py)): applying the same inherit map twice equals applying once.

## Anti-patterns (banned)

- Forcing group membership at signup.
- Hardcoding `if country == "US": district_employer` branches in views.
- Collapsing `parent_school` into `Organization` (those are separate concepts).
- Mutating `Organization` without a `OrganizationLifecycleEvent` row.

## Cross-references

- Plan: [`global_governance_audit_582fd47d.plan.md` Phase 2](../../.cursor/plans/global_governance_audit_582fd47d.plan.md)
- Verifier: [`scripts/verify_org_lifecycle_events.py`](../../scripts/verify_org_lifecycle_events.py)
- Verifier: [`scripts/verify_school_operating_modes.py`](../../scripts/verify_school_operating_modes.py)
