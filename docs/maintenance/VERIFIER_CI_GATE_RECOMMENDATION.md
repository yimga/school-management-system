# Verifier CI gate recommendation

This document recommends how to wire **repository verifiers** into CI. It is guidance only until your pipeline implements it.

## Required local release gates

Run before tagging or shipping a release (adjust for your cadence):

- `python scripts/verify_doc_plan_density_discipline.py`
- `python scripts/verify_sot_pillar_evidence.py`
- `python scripts/verify_compliance_evidence.py`
- `python scripts/audit_admin_gravity.py --strict`
- `python scripts/audit_sitesettings_python_surface.py`
- `python scripts/verify_shell_surface_inventory.py`
- `python scripts/verify_phase2_authenticated_shell_conformance.py`
- `python scripts/verify_design_system_phase2.py`

These enforce **documentation discipline**, **governance crosswalks**, **evidence paths**, **admin/control-plane gravity**, **SiteSettings surface**, and **shell/design** contracts.

## Optional / external gates

- Full `python manage.py test` (or staged slices) — required for quality; may be split across parallel jobs by time budget.
- `python scripts/verify_phases_3_11_gates.py` (if used in your release process) — bundles multiple checks; confirm runtime in CI.

Anything that needs **secrets**, **network**, or **live infrastructure** should stay **manual** or run in a dedicated staging job, not default PR gates.

## Enterprise hardening gates (batch 1102 family)

Recommended for **main** / **release** branches or weekly scheduled jobs:

| Script | Suggest blocking? | Notes |
| --- | --- | --- |
| `verify_compliance_evidence.py` | **Yes** for release | Fails only on missing ledger files/policies |
| `audit_security_surface.py` | Advisory | Exit 0; archive JSON as artifact |
| `audit_tenant_isolation.py` | Advisory | Same |
| `audit_query_hotspots.py` | Advisory | Same |
| `audit_repo_complexity.py` | Advisory | Same |
| `audit_raw_sql_usage.py` | Advisory | Same |
| `audit_subprocess_usage.py` | Advisory | Same |
| `audit_gilead_references.py --strict-public` | **Yes** if customer-facing branding is a contract item | Fails on public UI legacy hits when strict |
| `audit_admin_usage_extended.py` | Advisory | Large output; trend over time |

## Which scripts should block PRs

**Strong candidates:**

- Doc/governance: `verify_doc_plan_density_discipline.py`, `verify_sot_pillar_evidence.py`, `verify_compliance_evidence.py`
- Product invariants already in use: `verify_design_system_phase2.py`, `verify_shell_surface_inventory.py`, `verify_phase2_authenticated_shell_conformance.py` (if PRs touch UI/shell)
- `audit_admin_gravity.py --strict` when admin routes or registrations change frequently

**PR scope–dependent:** run targeted `manage.py test` for touched apps.

## Advisory-only (typical PR)

- `audit_security_surface.py`, `audit_tenant_isolation.py`, `audit_query_hotspots.py`, `audit_repo_complexity.py`, `audit_raw_sql_usage.py`, `audit_subprocess_usage.py`, `audit_admin_usage_extended.py`

Rationale: these are **visibility** tools; blocking on every heuristic would slow iteration. Promote individual checks to blocking when fixing a known class of defect (e.g., a security regression wave).

## Artifacts to retain

Store under CI artifacts or a docs bucket:

- `docs/generated/*.json` outputs from audits (or re-run audits in CI and upload JSON).
- Verifier stdout for `verify_compliance_evidence`, `audit_gilead_references --strict-public` when used as a gate.

## Staged tightening

To increase enforcement without boiling the ocean:

1. Block `verify_compliance_evidence` on **main** first.
2. Add `audit_gilead_references.py --strict-public` on **main** if rebranding is a release criterion.
3. Schedule full audit bundle **nightly** with diff alerts on JSON changes.
