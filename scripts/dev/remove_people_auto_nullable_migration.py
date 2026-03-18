# Script to remove lingering migration record from the database
# Run from project root: python scripts/dev/remove_people_auto_nullable_migration.py
import os
import sqlite3

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_script_dir, "..", ".."))
DB_PATH = os.path.join(_project_root, "db.sqlite3")
MIGRATION_NAME = "auto_nullable_specialty_studentprofile"
APP_NAME = "people"


def remove_migration():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM django_migrations WHERE app = ? AND name = ?",
        (APP_NAME, MIGRATION_NAME),
    )
    conn.commit()
    print(f"Removed migration {MIGRATION_NAME} from {APP_NAME} app.")
    conn.close()


if __name__ == "__main__":
    remove_migration()
