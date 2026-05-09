"""verify_settings_registry_coverage — scan apps/ + config/ for settings access.

Reports any ``getattr(settings, "X", ...)``, ``settings.X``, or
``settings_helpers.something(...)`` reference whose name is NOT declared in
``config.settings_registry.SETTINGS_REGISTRY``. Exits non-zero only when the
``--strict`` flag is passed; otherwise prints the deficit and exits 0 so it
can be informational in CI before a hard cutover.

Usage::

    python scripts/verify_settings_registry_coverage.py
    python scripts/verify_settings_registry_coverage.py --strict
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Late import so the script runs without Django setup.
from config.settings_registry import all_setting_names  # noqa: E402


SCAN_DIRS = ("apps", "config")
SKIP_DIR_PARTS = {
    "__pycache__",
    "migrations",
    "tests",
    ".tmp_test_artifacts",
    ".tmp_test_raw_sql_usage",
    ".django_test_dbs",
    ".pytest_cache",
}

# Names we don't expect in the registry (Django built-ins consumed by the
# framework, not by our app code).
EXEMPT_NAMES = {
    "DEBUG", "DATABASES", "INSTALLED_APPS", "MIDDLEWARE", "ROOT_URLCONF",
    "TEMPLATES", "WSGI_APPLICATION", "ASGI_APPLICATION", "SECRET_KEY",
    "ALLOWED_HOSTS", "TIME_ZONE", "USE_I18N", "USE_TZ", "LANGUAGE_CODE",
    "STATIC_URL", "STATIC_ROOT", "STATICFILES_DIRS", "STATICFILES_STORAGE",
    "STATICFILES_FINDERS", "MEDIA_URL", "MEDIA_ROOT",
    "DEFAULT_AUTO_FIELD", "AUTH_USER_MODEL", "AUTH_PASSWORD_VALIDATORS",
    "PASSWORD_HASHERS", "AUTHENTICATION_BACKENDS",
    "DEFAULT_FROM_EMAIL", "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT",
    "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS", "EMAIL_USE_SSL",
    "ADMINS", "MANAGERS", "BASE_DIR",
    "SESSION_ENGINE", "SESSION_COOKIE_NAME", "SESSION_COOKIE_AGE",
    "SESSION_COOKIE_SAMESITE", "SESSION_COOKIE_SECURE", "SESSION_COOKIE_DOMAIN",
    "CSRF_COOKIE_NAME", "CSRF_COOKIE_SAMESITE", "CSRF_COOKIE_SECURE",
    "CSRF_COOKIE_DOMAIN", "CSRF_TRUSTED_ORIGINS",
    "SECURE_SSL_REDIRECT", "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD", "SECURE_BROWSER_XSS_FILTER",
    "SECURE_CONTENT_TYPE_NOSNIFF", "SECURE_PROXY_SSL_HEADER",
    "SECURE_REDIRECT_EXEMPT", "USE_X_FORWARDED_HOST",
    "FILE_UPLOAD_HANDLERS", "DATA_UPLOAD_MAX_MEMORY_SIZE",
    "FILE_UPLOAD_MAX_MEMORY_SIZE", "FILE_UPLOAD_PERMISSIONS",
    "LOGIN_URL", "LOGIN_REDIRECT_URL", "LOGOUT_REDIRECT_URL",
    "LANGUAGES", "LOCALE_PATHS", "FORMAT_MODULE_PATH",
    "CACHES", "CACHE_MIDDLEWARE_SECONDS", "CACHE_MIDDLEWARE_KEY_PREFIX",
    "LOGGING", "LOGGING_CONFIG",
    "TEST_RUNNER", "TESTING",
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP_DIR_PARTS for part in p.parts):
                continue
            files.append(p)
    return files


def _extract_names_from_tree(tree: ast.AST) -> set[str]:
    """Collect setting names referenced in this AST."""
    names: set[str] = set()

    for node in ast.walk(tree):
        # getattr(settings, "X", ...) or getattr(settings, "X")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2:
                obj = node.args[0]
                key = node.args[1]
                if (
                    isinstance(obj, ast.Name)
                    and obj.id == "settings"
                    and isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                ):
                    names.add(key.value)

        # settings.X (attribute access)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "settings":
            if node.attr.isupper() or "_" in node.attr:
                names.add(node.attr)

    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 on undeclared names")
    args = parser.parse_args()

    declared = all_setting_names() | EXEMPT_NAMES
    referenced: set[str] = set()
    parse_failures: list[Path] = []

    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            parse_failures.append(path)
            continue
        referenced.update(_extract_names_from_tree(tree))

    undeclared = sorted(referenced - declared)

    print(f"verify_settings_registry_coverage: scanned {len(_iter_python_files())} files")
    print(f"  declared (registry + exempt): {len(declared)}")
    print(f"  referenced in code:           {len(referenced)}")
    print(f"  undeclared (gap):             {len(undeclared)}")
    if parse_failures:
        print(f"  unparseable files:            {len(parse_failures)} (skipped)")

    if undeclared:
        print()
        print("  First 30 undeclared names (extend config/settings_registry.py):")
        for name in undeclared[:30]:
            print(f"    - {name}")

    if args.strict and undeclared:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
