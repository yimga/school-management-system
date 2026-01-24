# Script to remove lingering migration record from the database
import sqlite3

DB_PATH = 'db.sqlite3'
MIGRATION_NAME = 'auto_nullable_specialty_studentprofile'
APP_NAME = 'people'

def remove_migration():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM django_migrations WHERE app = ? AND name = ?", (APP_NAME, MIGRATION_NAME))
    conn.commit()
    print(f"Removed migration {MIGRATION_NAME} from {APP_NAME} app.")
    conn.close()

if __name__ == '__main__':
    remove_migration()
