# Script to clean up all test/rollback artifacts from people migrations
# Run from project root: python scripts/clean_people_migration_artifacts.py
import os
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, "apps", "people", "migrations")
REMOVE_FILES = [
    "0016_alter_studentprofile_specialty_nullable.py",
    "auto_nullable_specialty_studentprofile.py",
]


def clean_migration_artifacts():
    for fname in REMOVE_FILES:
        fpath = os.path.join(MIGRATIONS_DIR, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            print(f"Deleted {fname}")
    # Remove all .pyc files in migrations and __pycache__
    for root, dirs, files in os.walk(MIGRATIONS_DIR):
        for file in files:
            if file.endswith(".pyc"):
                pyc_path = os.path.join(root, file)
                os.remove(pyc_path)
                print(f"Deleted {pyc_path}")
        for dir in dirs:
            if dir == "__pycache__":
                shutil.rmtree(os.path.join(root, dir))
                print(f"Deleted {os.path.join(root, dir)}")


if __name__ == "__main__":
    clean_migration_artifacts()
