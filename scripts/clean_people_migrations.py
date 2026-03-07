# Script to scan and clean up invalid migration dependencies in people app
# Run from project root: python scripts/clean_people_migrations.py
import os
import re

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, 'apps', 'people', 'migrations')
INVALID_DEPENDENCIES = [
    "last_migration_name",
    "auto_nullable_specialty_studentprofile"
]

def clean_migration_files():
    for fname in os.listdir(MIGRATIONS_DIR):
        if not fname.endswith('.py') or fname == '__init__.py':
            continue
        fpath = os.path.join(MIGRATIONS_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content
        for dep in INVALID_DEPENDENCIES:
            # Remove any tuple or string referencing the invalid dependency
            content = re.sub(r"\('people', '{}'.*?\),?".format(dep), '', content)
            content = re.sub(r"'{}'".format(dep), '', content)
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Cleaned invalid dependencies from {fname}")

if __name__ == '__main__':
    clean_migration_files()
