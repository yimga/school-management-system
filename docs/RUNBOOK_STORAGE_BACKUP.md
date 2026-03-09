# Runbook: Storage and backup (required when S3/production media used)

When using S3-compatible or production file storage, backup and recovery are required. This runbook is non-optional for production.

## What it is

- **Abstraction:** All programmatic file access via `apps.platform_runtime.storage` (save_to_storage, get_storage_url, delete_from_storage, storage_exists).
- **Backend:** Django `DEFAULT_FILE_STORAGE` (local `MEDIA_ROOT` or S3-compatible).
- **Tenant paths:** Prefer `tenants/{school_id}/...` for tenant-scoped files.

## When using local MEDIA_ROOT

- **Backup:** Include `MEDIA_ROOT` in daily/weekly backups (e.g. tar or rsync to backup volume).
- **Restore:** Restore the same path; ensure app has read/write permissions.

## When using S3-compatible storage

- **Backup:** Enable bucket versioning and/or lifecycle rules; use provider backup (e.g. AWS Backup, MinIO mirror) or periodic sync to another bucket/region.
- **Restore:** Restore from backup bucket or version history; point `DEFAULT_FILE_STORAGE` to restored bucket if needed.
- **Credentials:** Rotate `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or equivalent) on schedule; update settings and restart app.

## Health check

- **Local:** Ensure `MEDIA_ROOT` exists and is writable (e.g. deploy check or health endpoint).
- **S3:** Test write/read (e.g. save a small file and read it back) in health check or preflight.

## References

- `apps/platform_runtime/storage.py`
- `docs/architecture/storage_and_search.md`
- `config/settings.py` — `MEDIA_ROOT`, `DEFAULT_FILE_STORAGE`
