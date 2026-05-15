# Merge `improvements` into `main`

## Pre-merge checks (done)

- **Django system check:** `python manage.py check` — **passed**
- **Tests:** Full suite can be run with:
  - `python manage.py test apps.accounts apps.evals apps.portal apps.academics apps.people apps.reports apps.siteconfig apps.analytics apps.finance apps.payroll apps.compliance apps.communication apps.requests apps.observability apps.api apps.automation emis`
  - Omit `--parallel` on Windows to avoid encoding issues with root-level scripts; or run from a directory that doesn’t include ad-hoc `test_*.py` in discovery.
  - Allow 3–5+ minutes for test DB creation (SQLite migrations).

## Branch status

- **Branch:** `improvements`
- **Pushed to:** `origin/improvements`
- **Commit:** Enrollment & fee improvements: full plan + verification checklist

## Merge into `main`

### Option A: Local merge, then push

```bash
git fetch origin
git checkout main
git pull origin main
git merge improvements -m "Merge improvements: enrollment & fee plan complete"
git push origin main
```

### Option B: GitHub PR

1. Open: https://github.com/yimga/school-management-system/compare/main...improvements
2. Create a Pull Request from `improvements` into `main`
3. Review and merge (squash or merge commit as preferred)

## After merge

- Optionally delete the branch: `git push origin --delete improvements` (or keep for reference).
- On local: `git checkout main && git pull origin main`.
