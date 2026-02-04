#!/usr/bin/env python3
"""
Print the SQLite DB path Django uses (no DB connection).
Run from project root: python scripts/show_db_path.py
"""
import os
import sys
from pathlib import Path

# Match config/settings.py logic
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(BASE_DIR / ".env.local")
except Exception:
    pass

sqlite_name = os.getenv("DB_FILE", "db.sqlite3")
if sqlite_name == "db.sqlite3":
    sqlite_name = "db_working.sqlite3"
db_path = BASE_DIR / sqlite_name

print("Django DB path:", db_path.resolve())
print("Exists:", db_path.exists())
sys.exit(0)
