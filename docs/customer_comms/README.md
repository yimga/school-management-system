# Customer comms templates

Per-residency / per-language migration notices used by Phase 2 (Organization layer) rollout.

## Audiences

- **Standalone tenants (majority):** "you may now optionally join a group" no-op banner.
- **Existing `parent_school` subtree tenants:** explicit migration notice with opt-out window.
- **`mat_groups` registry users:** unification-into-`Organization` notice with effective date.

## Templates

| File | Audience | Trigger |
|------|----------|---------|
| [`standalone_phase2_no_op.en.md`](standalone_phase2_no_op.en.md) | Standalone tenants | Phase 2 rollout begins |
| [`parent_school_subtree_phase2_migration.en.md`](parent_school_subtree_phase2_migration.en.md) | `parent_school` subtree tenants | Phase 2 rollout begins |
| [`mat_groups_phase2_unification.en.md`](mat_groups_phase2_unification.en.md) | `mat_groups` registry users | Phase 2 rollout begins |

Additional language variants (FR / ES / PT / AR per residency requirement) are produced from the EN templates and stored alongside with the locale suffix. Verifier asserts only the EN baseline; locale variants are reviewed in the LOCALE lane.

## Verifier

[`scripts/verify_customer_comms_templates.py`](../../scripts/verify_customer_comms_templates.py) asserts this directory exists and is reachable from the program register.
