"""
One-off settings to create a fresh SQLite DB (db_fresh.sqlite3).
Usage: DJANGO_SETTINGS_MODULE=config.settings_freshdb python manage.py migrate
Then set DB_FILE=db_fresh.sqlite3 in .env.local and restart runserver.
"""
from pathlib import Path

from .settings import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent
# Use a dedicated file so we never touch a corrupted db_working / db_new
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db_fresh.sqlite3",
    }
}
if "preview" in DATABASES:
    DATABASES["preview"] = DATABASES["default"].copy()
