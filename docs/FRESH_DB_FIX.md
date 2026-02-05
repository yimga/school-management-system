# Fix: "database disk image is malformed" and "no such table: django_session"

## Cause

- The SQLite file in use was corrupted (two processes using it at once, cloud sync, antivirus, or disk issues).
- That leads to `database disk image is malformed` on migrate and `no such table: django_session` on admin login.

## Fix (do in order)

### 1. Stop the dev server

Stop **all** `python manage.py runserver` processes (Ctrl+C in every terminal).  
No Django process should use the DB while you run the next steps.

### 2. Use a DB file outside the project (recommended)

`.env.local` is set to:

```env
DB_FILE=%TEMP%\gilead_db.sqlite3
```

So the DB lives in your **Windows temp folder** (e.g. `C:\Users\<you>\AppData\Local\Temp\gilead_db.sqlite3`). That avoids:

- Cloud sync (OneDrive, Dropbox, etc.) touching the file
- Antivirus scanning the project folder while SQLite is writing
- Partial/corrupt files if migrate is interrupted

Settings expand `%TEMP%` automatically. No need to create the folder.

### 3. Remove old DB if it exists (optional)

If you previously used `data/db_live.sqlite3` or another path, you can delete that file so it’s not used by mistake. The app now uses `%TEMP%\gilead_db.sqlite3` while this is set in `.env.local`.

To remove the temp DB and start completely fresh:

- Windows (PowerShell): `Remove-Item -Force $env:TEMP\gilead_db.sqlite3 -ErrorAction SilentlyContinue`
- Git Bash: `rm -f "$TEMP/gilead_db.sqlite3"`

### 4. Create DB and tables (with server still stopped)

From the **project root** (the folder that contains `manage.py`):

```bash
cd "c:/Users/yimga/Documents/HY_DOC_MAINPC/Docs for Others_Friends_family/Gilead Tech High/beta/school-management-system"
python manage.py migrate
```

If you still see "database disk image is malformed", ensure no `runserver` or other Django process is running, then delete the temp DB (step 3) and run `migrate` again.

### 5. Create a superuser

```bash
python manage.py createsuperuser
```

Enter username, email (optional), and password.

### 6. Start the server

```bash
python manage.py runserver
```

Then open **http://127.0.0.1:8000/admin/** and log in with the superuser.

## Summary

1. Stop `runserver` everywhere.
2. `.env.local` has `DB_FILE=%TEMP%\gilead_db.sqlite3` (DB outside project).
3. (Optional) Remove `%TEMP%\gilead_db.sqlite3` for a clean start.
4. From project root: `python manage.py migrate`
5. `python manage.py createsuperuser`
6. `python manage.py runserver` and use `/admin/`.
