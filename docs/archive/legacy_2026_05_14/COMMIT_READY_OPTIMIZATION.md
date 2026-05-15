# Commit-ready: Optimization, recommendations, and testing

## Checks run before commit

| Check | Result |
|-------|--------|
| `python scripts/check_image_dimensions.py` | OK – no `<img>` missing width/height |
| `python manage.py check` | OK – no issues (0 silenced) |
| `python manage.py test apps.evals...` | **Evals migrations fixed** – 0019, 0020, 0021 now use `connection.vendor` and SQLite `PRAGMA table_info` so they run on SQLite. Full test suite can still fail on **finance** app (`table finance_paymentmethod already exists` – duplicate/merge migrations); that is pre-existing and outside this optimization batch. |

## What’s in this batch (ready to commit)

1. **Optimization (responsive, perf, theme)**  
   Sticky header, aria-labels, search/topbar visibility, theme visibility (badges, focus), overlay tokens, footer mobile accordion (`open` by default), breakpoint tokens (`--bp-*`), image dimensions/lazy loading across templates, fonts (display=swap, preconnect), PERFORMANCE_BUDGET.md, FRONTEND_IMAGE_GUIDELINES.md, `npm run perf`, `npm run check:images`.

2. **Recommendations implemented**  
   - Cursor rule: `.cursor/rules/images.mdc` (width/height, loading, decoding, alt).  
   - Evals: removed duplicate `GradeApprovalRequest` class in `apps/evals/models.py` (was defined twice; kept the full definition with `mark_reviewed`, `mark_bypassed`, `is_overdue`).  
   - Lighthouse CI: `lighthouserc.js` (LCP, CLS, performance/accessibility assertions), `npm run lighthouse` (run after starting dev server).

3. **Lighthouse CI**  
   `lighthouserc.js` (LCP, CLS, performance/accessibility assertions), `npm run lighthouse` (run after dev server). PERFORMANCE_BUDGET.md updated.

4. **Evals**  
   Removed duplicate `GradeApprovalRequest` in models.py. Migrations 0019, 0020, 0021: SQLite-safe (PRAGMA table_info, vendor-specific DROP COLUMN).

5. **Docs**  
   OPTIMIZATION_PLAN_RESPONSIVE_PERF_THEME.md, PERFORMANCE_BUDGET.md (updated), FRONTEND_IMAGE_GUIDELINES.md, COMMIT_READY_OPTIMIZATION.md (this file).

## Suggested commit message

```
Optimization: responsive, theme, perf, and recommendations

- Portal: sticky header, aria-labels, search/topbar visibility, theme visibility
- Footer: mobile accordion (open by default), breakpoint tokens in CSS
- Design tokens: overlay vars, --bp-* breakpoints; use in portal_base, responsive-performance, dashboard-responsive, footer
- Images: dimensions + loading/decoding across templates; FRONTEND_IMAGE_GUIDELINES.md
- Fonts: Inter display=swap, preconnect (portal_base)
- Performance: PERFORMANCE_BUDGET.md, npm run perf, check:images; Lighthouse CI (lighthouserc.js, npm run lighthouse)
- Evals: remove duplicate GradeApprovalRequest in models.py; migrations 0019/0020/0021 SQLite-safe (PRAGMA table_info, vendor DROP COLUMN)
- Cursor rule: .cursor/rules/images.mdc for image guidelines
- Docs: OPTIMIZATION_PLAN, COMMIT_READY_OPTIMIZATION
```

## Note on tests

- **Evals**: Migrations 0019, 0020, 0021 were updated to support SQLite (PRAGMA table_info + vendor-specific DROP COLUMN). They apply cleanly on SQLite test DB.
- **Finance**: Full test suite may fail with `table "finance_paymentmethod" already exists` due to duplicate/merge migrations in the finance app. That is pre-existing; fix separately if you run full tests on SQLite.
