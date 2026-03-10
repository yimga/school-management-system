# Fix SQLite Migration Error

## 🐛 Error
```
sqlite3.OperationalError: no such table: pg_indexes
```

## 🔍 Problem
Migration `0024_alter_payment_options_and_more.py` uses PostgreSQL-specific SQL (`pg_indexes`) but your database is SQLite.

## ✅ Fix Applied

I've updated the migration to be database-agnostic:

1. **Fixed `remove_indexes_if_exist` function:**
   - Now detects database vendor (`postgresql` vs `sqlite`)
   - Uses `pg_indexes` for PostgreSQL
   - Uses `sqlite_master` for SQLite
   - Falls back gracefully for other databases

2. **Fixed `handle_id_field_alteration` function:**
   - Checks database vendor before running PostgreSQL-specific SQL
   - Skips database operations for SQLite (only updates Django state)
   - PostgreSQL-specific code only runs on PostgreSQL

## 🚀 Run Migrations Again

```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
python manage.py migrate
```

The migration should now work with SQLite!

---

## 📋 What Changed

**Before:**
- Hardcoded PostgreSQL SQL (`pg_indexes`)
- Would fail on SQLite

**After:**
- Database vendor detection
- SQLite-compatible queries (`sqlite_master`)
- PostgreSQL code only runs on PostgreSQL
- SQLite skips database operations (updates state only)

---

## ✅ Verify Fix

After running migrations, you should see:
```
Running migrations:
  Applying finance.0024_alter_payment_options_and_more... OK
  ...
```

No more `pg_indexes` errors!

---

**The migration is now database-agnostic and should work!** 🎉
