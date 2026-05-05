# Release Clean Archive

Use `git archive` for release/source sharing. Do not create release ZIPs by manually compressing the working tree.

## Clean ZIP Command

```bash
git archive --format=zip --output ../runmycampus-clean-main.zip HEAD
```

For an exact pushed commit:

```bash
git archive --format=zip --output ../runmycampus-clean-40179942.zip 40179942d1082039b0ad8887f3467638cc00128d
```

## Forbidden In Release Source Archives

- `.env` and local secret files
- SQLite databases and database journals
- logs
- caches and `__pycache__`
- `.django_test_dbs`
- local screenshots, videos, and Playwright traces
- `artifacts/db_snapshots`
- local media/debug dumps

Visual QA screenshots and generated browser evidence may be useful, but package them as a separate evidence archive instead of mixing them into the production source ZIP.

## Working Tree Scan

```bash
git ls-files | grep -E '(\.env$|\.sqlite3$|\.sqlite3-journal$|\.log$|(^|/)__pycache__/|^\.django_test_dbs/|^tmp/screenshots/|^artifacts/db_snapshots/)'
```

## Archive Scan

```bash
unzip -l ../runmycampus-clean-main.zip | grep -E '(\.env|sqlite3|\.log|__pycache__|\.django_test_dbs|tmp/screenshots|artifacts/db_snapshots)' || true
```

The expected result is no matches. If matches appear, remove them from Git tracking or add an `export-ignore` rule before sharing the archive.
