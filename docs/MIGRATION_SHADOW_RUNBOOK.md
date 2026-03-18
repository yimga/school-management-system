# Migration shadow period + diff (BR-04)

1. **Export baseline** from legacy SIS (CSV).
2. **Export target** from RunMyCampus after seed/import.
3. **Diff:** `POST /api/internal/br/migration-diff-preview/` with `{"csv_a": "...", "csv_b": "..."}` — row counts, header match.
4. **Shadow:** Run parallel read-only for 2–4 weeks; compare attendance/grade samples daily.
5. **Rollback:** Keep legacy export + rollback playbook; freeze writes on cutover window.
6. **Connectors:** Document PowerSchool / Infinite Campus / iSAMS export paths in partner runbooks.

*§0.4.1 implementation and migration safety.*
