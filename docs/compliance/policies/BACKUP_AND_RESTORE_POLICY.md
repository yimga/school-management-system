# Backup and restore policy (engineering)

## Application data

- Primary persistence: PostgreSQL (production); SQLite used for tests and some local flows (`DJANGO_TEST_DB_FILE`).
- **Backup frequency, retention, and encryption** are environment-specific — document in customer runbooks or `docs/deployment/` where applicable.

## Restore validation

- Maintain at least one documented restore drill per major release (external record).
- Repo gate: `test_db_liveness` and database connectivity checks referenced from release readiness scripts.

## Media / object storage

User uploads and static assets: follow cloud provider lifecycle rules; not fully encoded in this repo.
