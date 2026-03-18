#!/usr/bin/env python
"""
Create a fresh SQLite DB and teacher/parent accounts (password Test1234).
Run from project root: python scripts/create_fresh_db_and_accounts.py

Use when the current DB is corrupted (database disk image is malformed).
1. Stop runserver first (it may lock the DB file).
2. Uses db_clean.sqlite3 (new file; nothing has it open).
3. Run this script, then set DB_FILE=db_clean.sqlite3 in .env.local and start runserver.
"""

import os
import sys
from pathlib import Path

# Project root (parent of config/)
BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

# Use a NEW filename so we never touch a file that runserver might have open
FRESH_DB_NAME = "db_clean.sqlite3"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DB_FILE"] = FRESH_DB_NAME

db_path = BASE_DIR / FRESH_DB_NAME
if db_path.exists():
    try:
        db_path.unlink()
        print("Removed existing", FRESH_DB_NAME)
    except OSError as e:
        print("Warning: could not remove", db_path, "-", e)
        print("Stop runserver and run this script again, or use a different DB_FILE.")
        sys.exit(1)

import django

django.setup()

from django.core.management import call_command
from django.conf import settings

db_name = settings.DATABASES["default"]["NAME"]
print("Using database:", db_name)

# Migrate
print("Running migrations...")
call_command("migrate", "--noinput", verbosity=1)

# Ensure superuser (optional; skip if you already have one)
call_command("ensure_superuser", "--no-input", verbosity=1)

# Create teacher and parent with password Test1234
call_command("create_teacher_parent_accounts", "--password", "Test1234", verbosity=1)

print("\nDone. Set DB_FILE=db_clean.sqlite3 in .env.local and start runserver.")
print("Log in: teacher / Test1234  or  parent / Test1234")
