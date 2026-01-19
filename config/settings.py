from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    # Admin theme (must be first)
    "unfold",

    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Project apps
    "apps.accounts",
    "apps.evals",
    "apps.portal",
    "apps.academics",
    "apps.people",
    "apps.reports",
    "apps.siteconfig",
    "apps.analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.siteconfig.middleware.MaintenanceModeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
                "apps.siteconfig.context_processors.site_settings",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---

import os
import dj_database_url

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
    # ✅ Local fallback (no DATABASE_URL) = sqlite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_USER_MODEL = "accounts.User"

# --- Static / Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ---
LOGIN_URL = "/authentication/login/"
LOGIN_REDIRECT_URL = "/authentication/redirect/"
LOGOUT_REDIRECT_URL = "/authentication/login/"

# --- Site behavior ---
MAINTENANCE_MODE = False

# --- Admin theme (Unfold) ---
# Docs: https://unfoldadmin.com/docs/configuration/settings/
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": "Gilead School Admin",
    "SITE_HEADER": "Gilead School Management",
    "SITE_SUBHEADER": "Gilead Tech High School",
    "SITE_URL": "/",

    # Icon/branding (32px height works best)
    "SITE_ICON": lambda request: static("images/logo.png"),

    # Small UX improvements
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,

    # Titles
    "ENVIRONMENT": "Development" if DEBUG else "Production",

    # You can expand this later into a full sidebar definition,
    # but keeping defaults is safest during the migration.
}

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

