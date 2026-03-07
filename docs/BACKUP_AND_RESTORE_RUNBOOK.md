# Backup & Restore Runbook (W12-3)

Single reference for database and media backup/restore procedures. Use this runbook for operational recovery and for checklist items that reference "backup runbooks".

---

## Quick links

| Topic | Document |
|-------|----------|
| **Database recovery** (SQLite corruption, recreate DB) | [DATABASE_RECOVERY_GUIDE.md](DATABASE_RECOVERY_GUIDE.md) |
| **Credentials and restore** (ephemeral disk, Render, reset admin) | [CREDENTIALS_AND_RESTORE.md](CREDENTIALS_AND_RESTORE.md) |

---

## Database backup (manual)

- **SQLite (dev):** Copy `db.sqlite3` (or `$DB_FILE`) to a safe location. No native hot-backup; stop writes or use `sqlite3 .backup` if needed.
- **PostgreSQL (production):** Use `pg_dump` (full or per-schema for multi-tenant). Example:
  ```bash
  pg_dump $DATABASE_URL -Fc -f backup_$(date +%Y%m%d).dump
  ```

---

## Database restore

- **SQLite:** Replace `db.sqlite3` with the backup file, then run `python manage.py migrate` if schema may have changed.
- **PostgreSQL:** `pg_restore` (see PostgreSQL docs). Then run migrations if needed.

---

## Media files

- Back up `media/` (uploaded files, logos, attachments) separately. Restore by copying back to `media/` and ensuring permissions match the app user.

---

## Pre-rollover / pre-release checklist

- Take a DB backup before year-end rollover or major releases.
- Document backup location and retention in your ops playbook.
