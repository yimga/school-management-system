# Powerhouse Wave 0 Baseline and Gate

This document operationalizes Wave 0 of the Powerhouse plan:

- Baseline snapshot and rollback point
- Quality gates for migration drift, tenant audit, RBAC, and smoke
- Clear command set for local and CI execution

## 1. Baseline Snapshot

Create a snapshot before any wave implementation:

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release/create_baseline_snapshot.ps1
```

Bash:

```bash
bash scripts/release/create_baseline_snapshot.sh
```

Artifacts are written under `backups/phase0/`:

- `backups/phase0/db/*.sqlite3` (when local sqlite db exists)
- `backups/phase0/ui_config/ui_config_*.json`
- `backups/phase0/snapshot_meta_*.txt`

## 2. Wave 0 Strict Gate

Run strict gate manually:

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release/powerhouse_wave0_gate.ps1
```

Bash:

```bash
bash scripts/release/powerhouse_wave0_gate.sh
```

What it enforces:

1. `python manage.py check`
2. `python manage.py makemigrations --check --dry-run`
3. `python manage.py audit_tenant_models --strict`
4. Targeted RBAC + smoke tests
5. `python manage.py seed_compliance_baseline` on isolated strict-gate DB
6. `python manage.py compliance_auditor --strict --min-score 70`
7. `python manage.py verify_access_control` (fails if unresolved issues are reported)
8. Startup script sanity in `render.yaml` and `Procfile`

Notes:

- Compliance and access-control checks run against an isolated sqlite file in local temp/appdata (generated uniquely per run). This avoids false failures from stale or cloud-synced local DB state.
- Override the isolated DB path with `POWERHOUSE_WAVE0_DB_FILE`.

## 3. CI Integration

Existing `scripts/pre_deploy_gate.sh` supports optional strict mode:

```bash
POWERHOUSE_WAVE0_STRICT=1 bash scripts/pre_deploy_gate.sh
```

Default behavior remains unchanged when strict mode is not enabled.

## 4. Exit Criteria for Wave 0

Wave 0 is complete only when:

- Baseline snapshot is captured and stored.
- Strict gate passes on the target commit.
- Rollback artifacts are available and documented.
- Subsequent waves start from this baseline.
