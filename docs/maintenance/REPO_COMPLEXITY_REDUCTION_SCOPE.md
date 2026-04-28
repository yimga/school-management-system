# Repository complexity reduction plan (non-destructive)

## Principles

1. **Classify first** — use `docs/generated/repo_complexity_audit.json` from `scripts/audit_repo_complexity.py`.
2. **No mass deletion** — especially migrations, admin registrations, and legacy URL shims.
3. **Verifier per cleanup type** — each reduction wave must name `verify_*` / `manage.py test` targets.

## Safe cleanup candidates (examples)

- Dead imports / unused variables (Ruff `F401`/`F841`) in test-only files after green CI.
- Duplicate markdown captured by `verify_doc_plan_density_discipline.py` (follow SOT rules before removing).

## Do-not-touch without product sign-off

- `apps/schools/middleware.py` host routing and tenant resolution.
- `apps/platform_runtime/helpers.py` SiteSettings access layer.
- `config/settings.py` INSTALLED_APPS ordering and security defaults.
- Historical migrations.

## Cleanup sequence (suggested)

1. Run `audit_repo_complexity.py` → triage `needs_review` buckets.
2. Pick one app family (e.g. `siteconfig` tests) for Ruff-only cleanup.
3. Re-run full `manage.py test` on a fresh `DJANGO_TEST_DB_FILE` path.
4. Record batch in SOT §11.4.

## Generated audit crosswalk (remediation queues)

Use `docs/generated/*.json` outputs as **queues**, not delete lists:

| Audit script | Generated artifact | Typical triage |
| --- | --- | --- |
| `audit_repo_complexity.py` | `repo_complexity_audit.json` | `except`, `print`, broad patterns |
| `audit_raw_sql_usage.py` | raw SQL inventory | allowlist vs product hotspots |
| `audit_subprocess_usage.py` | subprocess inventory | scripts vs runtime |
| `audit_gilead_references.py` | Gilead residue report | public-facing strings first |
| `audit_security_surface.py` | `security_surface_audit.json` | AllowAny / csrf_exempt / governance tier |
| `audit_admin_gravity.py` | admin surface ledger | routing vs accidental admin-primary UX |
| `audit_sitesettings_python_surface.py` | SiteSettings import map | tenant-safe access paths |

Classify each hit before editing; fix only **safe, public-visible** violations per batch.

## Tests / verifiers per cleanup type

| Cleanup type | Minimum verifiers |
| --- | --- |
| Python style only | `ruff check`, targeted `manage.py test` for touched app |
| Template copy | `verify_shell_surface_inventory.py`, `verify_design_system_phase2.py` |
| URL / middleware | `apps/schools/tests/test_tenant_middleware.py`, control-plane boundary tests |
| Docs only | `verify_doc_plan_density_discipline.py`, `verify_compliance_evidence.py` |
