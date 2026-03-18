# Migration CSV diff (BR-04)

## Product

**Control plane:** `/super/migration/csv-diff/` — upload **baseline** + **candidate** CSV (same header row). Response: row counts, keys only in A, only in B, value diffs for shared keys.

**Key column:** First column default, or `?key_column=student_id` in POST field.

## Shadow period (operational)

1. Export from legacy SIS (nightly).
2. Export from RunMyCampus.
3. Run diff in UI; investigate **only in B** / **value mismatch** rows.
4. Repeat 30 days; go-live when diff &lt; threshold.

## Connectors

- PowerSchool / IC / Skyward: use district **export** CSV until API connectors ship; document export recipes in district runbook.
