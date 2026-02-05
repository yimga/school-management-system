# Fix Database Errors

---

## Error: "database disk image is malformed"

### 🐛 Error
```
sqlite3.DatabaseError: database disk image is malformed
django.db.utils.DatabaseError: database disk image is malformed
```

The SQLite file Django is using is corrupted. Settings use `db_working.sqlite3` by default (or whatever `DB_FILE` is set to in `.env.local`).

### ✅ Quick Fix (one command)

From the **project root**:

```bash
python scripts/reset_local_db.py
```

That removes `db_working.sqlite3` (if present), runs migrations to create a fresh DB, then:

```bash
python manage.py createsuperuser
python manage.py runserver
```

### Manual fix

1. **Stop the dev server** (Ctrl+C).
2. **Delete the corrupted DB file** (so migrate can recreate it):
   ```bash
   rm db_working.sqlite3
   ```
   On Windows (cmd): `del db_working.sqlite3`. In PowerShell: `Remove-Item db_working.sqlite3`.
3. **Unset DB_FILE** if you had set it in the shell (so settings use the default `db_working.sqlite3`):
   ```bash
   unset DB_FILE
   ```
4. **Create a fresh DB:**
   ```bash
   python manage.py migrate
   ```
5. **Create a superuser**, then start the server:
   ```bash
   python manage.py createsuperuser
   python manage.py runserver
   ```

---

## Error: Missing Table

### 🐛 Error
```
django.db.utils.OperationalError: no such table: compliance_ipaccessrule
```

## ✅ Quick Fix

### Step 1: Run Migrations
```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
python manage.py migrate
```

This will create the missing `compliance_ipaccessrule` table.

### Step 2: Restart Server
After migrations complete, restart your dev server:
```bash
python manage.py runserver
```

---

## 🔍 What Happened?

The compliance middleware is trying to check IP access rules, but the database table hasn't been created yet. The migration file exists (`0006_countryaccessrule_ipaccessrule.py`) but needs to be applied.

---

## 🛡️ Safety Fix Applied

I've also updated `apps/compliance/access_control.py` to handle missing tables gracefully:
- If the table doesn't exist, it will allow access (fail open)
- This prevents the server from crashing during development
- Once migrations are run, normal access control will work

---

## 📋 Full Migration Commands

### Check Migration Status
```bash
python manage.py showmigrations compliance
```

### Run All Migrations
```bash
python manage.py migrate
```

### Run Only Compliance Migrations
```bash
python manage.py migrate compliance
```

### Check for Unapplied Migrations
```bash
python manage.py migrate --plan
```

---

## ✅ Verify Fix

After running migrations, you should see:
```
Running migrations:
  Applying compliance.0006_countryaccessrule_ipaccessrule... OK
```

Then restart your server and try accessing `/admin/` again.

---

## 🚀 Quick Command (All-in-One)

```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system" && python manage.py migrate && python manage.py runserver
```
