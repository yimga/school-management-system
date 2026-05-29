# MAT Group Hub — Operator Guide

**Wave J + Wave P-A · v3.95.1 · 2026-05-26**

The MAT (Multi-Academy Trust / district / school network) Group Hub gives a group operator a single cross-tenant rollup view: total students, staff, admissions pipeline, attendance, pass rate — aggregated across all member schools, **without breaking tenant isolation**.

## Pages

| URL | Purpose |
|---|---|
| `/super/mat-hub/` | All groups + summary cards |
| `/super/mat-hub/edit/` | Create a new MAT group in the registry |
| `/super/mat-hub/<group_id>/edit/` | Edit an existing group's members and metadata |
| `/super/mat-hub/<group_id>/` | One group's per-member detail |
| `/super/mat-hub/<group_id>/api/` | JSON endpoint for the rollup |

All pages require `staff_member_required`.

## Registry

MAT groups live in the **operator-side** `SiteSettings` (the control-plane singleton, `school=None`) under `cockpit_payload["mat_groups"]`:

```python
{
  "trust-greenwich": {
    "display_name": "Greenwich Academy Trust",
    "operator_email": "ops@greenwich.example",
    "region": "UK-London",
    "members": [
      {"tenant_slug": "greenwich-park", "display_name": "Greenwich Park School", "region": "UK-London"},
      {"tenant_slug": "greenwich-meridian", "display_name": "Meridian Primary", "region": "UK-London"}
    ]
  }
}
```

The parser is at [apps/schools/mat_group_hub.py:parse_mat_registry](beta/school-management-system/apps/schools/mat_group_hub.py).

**Phase 2 (global governance):** Optional `apps/governance.Organization` FK on `School` complements this operator registry — MAT hub remains the control-plane rollup surface; member schools with `governance_operating_mode=group_member` link to an `Organization` when customers opt into the org overlay.

## Tenant isolation

The aggregator NEVER runs a cross-tenant queryset. Instead:

1. The view builds a `tenant_scope_runner` closure that hits each member's School-scoped models one tenant at a time.
2. `aggregate_group_kpis` calls the runner per member and **sums the returned dicts in Python**.
3. The `scan_tenant_queryset_safety` scanner stays at baseline 0.

A failed member doesn't abort the rollup — that tenant gets recorded in `snapshot.failed_members` and rendered with a `FAIL` badge. Operators see partial data, never blank.

## KPIs per member

The default runner (`_runner_from_real_models` in [views_mat_group_hub.py](beta/school-management-system/apps/schools/views_mat_group_hub.py)) returns:

- `students` — count of `apps.people.Student` for the member
- `staff` — count of `apps.people.Staff`
- `admissions_pipeline` — 0 (stub; Wave P-A+1 ships)
- `fees_collected_minor` / `fees_outstanding_minor` — 0 (stub; needs finance integration)
- `attendance_rate_pct` / `pass_rate_pct` — 0.0 (stub)

Operators can override by injecting a richer runner; see the kernel docstring for the contract.

## Adding a group

1. Open Django admin → SiteSettings (the entry with `school=None`).
2. Edit `cockpit_payload` JSON to add a `mat_groups` block (shape above).
3. Save. The dashboard picks up the new group on next page load.

## Tests

- [apps/schools/tests/test_mat_group_hub.py](beta/school-management-system/apps/schools/tests/test_mat_group_hub.py) — 14 unit tests on the kernel.
