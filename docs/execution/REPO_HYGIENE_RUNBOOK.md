# Repo Hygiene Runbook (Plan Workstream A1)

**Due today, non-negotiable.** Keeps the repo fit for a platform that competes with PowerSchool/Blackbaud/Salesforce/Shopify.

## Done this session

- Removed merge conflict artifact: `apps/billing/services_HY-OFFICE_Mar-07-222520-2026_Conflict.py`
- Updated `.gitignore`: added `/backups/`, `db_working.sqlite3`, `db_*.sqlite3`, `*.sqlite3.malformed`, `*.sqlite3.corrupted`, `data/db_live.sqlite3`, `db_fresh.sqlite3`, `db_buea_seed.sqlite3`, `db_step4.sqlite3`, `*_Conflict.py`, `*Conflict*.py`

## One-time cleanup (run when needed)

1. **Conflict files:** `git status` and `find . -name '*Conflict*' -o -name '*_Conflict.py'` — delete or resolve; do not commit.
2. **Sqlite/DB in repo:** Ensure no `*.sqlite3`, `*.db` (except in tests/fixtures if allowed) are tracked. Use `git rm --cached` if already committed, then add to `.gitignore`.
3. **Backup/debug junk:** Remove `backups/` from tracking if present; keep in `.gitignore`.
4. **Gilead residue:** `grep -ri "Gilead" --include="*.py" --include="*.md" --include="*.json" .` in docs/config/fixtures; replace with "RunMyCampus" or generic wording in non-archival areas. Archive old audits to `docs/archive/`.
5. **Root markdown:** Move stray root-level `.md` into `docs/` by category (runbooks, architecture, audits); minimal README at root.

## CI

- `scripts/lint_tenant_settings.py --check-get-solo-only` must pass (no `SiteSettings.get_solo()` in tenant apps).
- No new `*_Conflict.py` or `*Conflict*.py` committed.
