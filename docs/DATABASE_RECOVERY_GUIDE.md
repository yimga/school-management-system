# SQLite Database Recovery Guide

## Problem

You're encountering: `sqlite3.DatabaseError: database disk image is malformed`

This means your SQLite database file (`db.sqlite3`) has become corrupted, likely due to:
- Unexpected shutdown during write operation
- Disk issues
- File system errors
- Concurrent access issues

## Solutions

### Option 0: Use a Different DB File (No Replace, No Data Loss)

If you already have a working SQLite file (e.g. `db_fresh.sqlite3`) and don't want to touch the corrupted `db.sqlite3` (e.g. it's locked or you'll fix it later):

**Windows (cmd):**
```cmd
set DB_FILE=db_fresh.sqlite3
python manage.py runserver
```

**Windows (PowerShell):**
```powershell
$env:DB_FILE="db_fresh.sqlite3"; python manage.py runserver
```

**Bash / Git Bash:**
```bash
export DB_FILE=db_fresh.sqlite3
python manage.py runserver
```

Or add to your `.env` or `.env.local`:
```
DB_FILE=db_fresh.sqlite3
```
(Requires that your settings load env from that file for `DB_FILE`; `config/settings.py` uses `os.getenv("DB_FILE", "db.sqlite3")`.)

This uses the alternate file only for this process; nothing is overwritten.

---

### Option 1: Recreate Database (Recommended for Development)

**⚠️ WARNING: This will delete all data in the database!**

If this is a development database and you don't need the data:

```bash
# 1. Delete the corrupted database
rm db.sqlite3

# 2. Delete migration history (optional - only if you want fresh start)
# Or just recreate migrations

# 3. Run migrations to create fresh database
python manage.py migrate

# 4. Create superuser (if needed)
python manage.py createsuperuser
```

### Option 2: Try to Recover Data

If you have important data you need to keep:

```bash
# 1. Backup the corrupted database first
cp db.sqlite3 db.sqlite3.backup

# 2. Try to dump data using SQLite's recovery mode
sqlite3 db.sqlite3 ".recover" | sqlite3 db_recovered.sqlite3

# 3. If that works, replace the corrupted file
mv db_recovered.sqlite3 db.sqlite3

# 4. Run integrity check
sqlite3 db.sqlite3 "PRAGMA integrity_check;"

# 5. If integrity check passes, try migrations again
python manage.py migrate
```

### Option 3: Use SQLite's Built-in Recovery

```bash
# 1. Try to repair using .dump and .read
sqlite3 db.sqlite3 ".dump" > dump.sql
sqlite3 db_new.sqlite3 < dump.sql

# 2. Replace old database
mv db.sqlite3 db_corrupted.sqlite3
mv db_new.sqlite3 db.sqlite3

# 3. Run migrations
python manage.py migrate
```

### Option 4: Check Database Integrity

First, let's see how bad the corruption is:

```bash
sqlite3 db.sqlite3 "PRAGMA integrity_check;"
```

If it returns "ok", the database might be recoverable. If it returns errors, you may need to recreate.

## Prevention

To prevent future corruption:

1. **Use PostgreSQL in Production**: SQLite is not recommended for production
2. **Proper Shutdown**: Always stop Django server gracefully (Ctrl+C, not force kill)
3. **Backup Regularly**: Keep backups of your database
4. **Use WAL Mode**: SQLite WAL mode is more resilient (Django uses this by default)

## Quick Fix Script

I can create a management command to help with this. Would you like me to create one?

---

**For Production**: If you're using PostgreSQL (via DATABASE_URL), this error won't occur. This is only for local SQLite development databases.
