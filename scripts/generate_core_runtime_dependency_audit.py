#!/usr/bin/env python3
"""Metadata-only core runtime dependency audit (no secrets, no PII).

Writes:
  docs/generated/core_runtime_dependency_audit.json
  docs/generated/core_runtime_dependency_audit.md

Usage:
  python scripts/generate_core_runtime_dependency_audit.py --write
  python scripts/generate_core_runtime_dependency_audit.py --check
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "core_runtime_dependency_audit.json"
MD_OUT = ROOT / "docs" / "generated" / "core_runtime_dependency_audit.md"


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _redact_env_keys(keys: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in keys:
        raw = os.environ.get(key, "")
        out[key] = "set" if (raw or "").strip() else "unset"
    return out


def _count_shared_tasks() -> dict[str, int]:
    counts: dict[str, int] = {}
    for rel in (
        "apps/automation/tasks.py",
        "apps/events/tasks.py",
        "apps/orchestration/tasks.py",
        "apps/observability/tasks.py",
        "apps/migration_cloud/tasks_audit.py",
    ):
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        counts[rel] = len(re.findall(r"@shared_task", text))
    return counts


def build_audit() -> dict:
    from django.conf import settings

    celery_beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    middleware = list(getattr(settings, "MIDDLEWARE", []))
    installed = list(getattr(settings, "INSTALLED_APPS", []))

    cors_origins = list(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or [])
    cors_regexes = list(getattr(settings, "CORS_ALLOWED_ORIGIN_REGEXES", []) or [])
    csrf_origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])

    simple_jwt = getattr(settings, "SIMPLE_JWT", {}) or {}
    jwt_summary = {
        key: (str(val) if key.endswith("_LIFETIME") else val)
        for key, val in simple_jwt.items()
        if key
        in (
            "ACCESS_TOKEN_LIFETIME",
            "REFRESH_TOKEN_LIFETIME",
            "ROTATE_REFRESH_TOKENS",
            "BLACKLIST_AFTER_ROTATION",
            "UPDATE_LAST_LOGIN",
        )
    }

    runtime_apps = [
        a
        for a in installed
        if any(
            p in a
            for p in (
                "accounts",
                "security",
                "api",
                "apicenter",
                "observability",
                "automation",
                "events",
                "orchestration",
                "platform_runtime",
                "tenancy",
                "otp",
                "celery",
                "channels",
                "simplejwt",
            )
        )
    ]

    channels_layer = getattr(settings, "CHANNEL_LAYERS", None)
    channel_backend = None
    if isinstance(channels_layer, dict):
        channel_backend = (channels_layer.get("default") or {}).get("BACKEND")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "secrets_redacted": True,
        "django": {
            "debug": bool(getattr(settings, "DEBUG", False)),
            "running_tests": bool(getattr(settings, "RUNNING_TESTS", False)),
            "use_django_tenants": bool(getattr(settings, "USE_DJANGO_TENANTS", False)),
            "tenancy_mode": getattr(settings, "TENANCY_MODE", ""),
            "wsgi_application": getattr(settings, "WSGI_APPLICATION", ""),
            "asgi_application": getattr(settings, "ASGI_APPLICATION", None),
        },
        "auth_mfa": {
            "password_hashers": list(getattr(settings, "PASSWORD_HASHERS", [])),
            "otp_apps": [a for a in installed if "otp" in a],
            "require_mfa_middleware": "apps.accounts.middleware.RequireMFAMiddleware"
            in middleware,
            "manager_cookie_isolation": "apps.accounts.middleware.ManagerCookieIsolationMiddleware"
            in middleware,
        },
        "drf_jwt": {
            "default_permission": (
                getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_PERMISSION_CLASSES")
            ),
            "default_authentication": (
                getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_AUTHENTICATION_CLASSES")
            ),
            "simple_jwt": jwt_summary,
            "token_blacklist_installed": "rest_framework_simplejwt.token_blacklist"
            in installed,
        },
        "cors_csrf": {
            "cors_allowed_origins_count": len(cors_origins),
            "cors_origin_regex_count": len(cors_regexes),
            "cors_allow_credentials": bool(getattr(settings, "CORS_ALLOW_CREDENTIALS", False)),
            "cors_allow_all_origins": bool(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)),
            "csrf_trusted_origins_count": len(csrf_origins),
            "csrf_subdomain_wildcards": [
                o for o in csrf_origins if "*" in o
            ],
            "multi_tenant_base_domain": getattr(settings, "MULTI_TENANT_BASE_DOMAIN", ""),
        },
        "async_infrastructure": {
            "redis_url": "set" if (getattr(settings, "REDIS_URL", None) or "").strip() else "unset",
            "celery_broker": "set"
            if (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
            else "unset",
            "celery_result_backend": getattr(settings, "CELERY_RESULT_BACKEND", ""),
            "celery_task_always_eager": bool(
                getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
            ),
            "celery_beat_enabled": bool(getattr(settings, "CELERY_BEAT_ENABLED", True)),
            "celery_beat_schedule_count": len(celery_beat),
            "celery_beat_sample": sorted(celery_beat.keys())[:25],
            "channel_layer_backend": channel_backend,
            "shared_task_counts_by_module": _count_shared_tasks(),
        },
        "runtime_apps": runtime_apps,
        "env_presence": _redact_env_keys(
            [
                "SECRET_KEY",
                "DATABASE_URL",
                "REDIS_URL",
                "CELERY_BROKER_URL",
                "CSRF_TRUSTED_ORIGINS",
                "CORS_ALLOWED_ORIGINS",
                "MIGRATION_CLOUD_AUDIT_SIGNING_KEY",
            ]
        ),
        "honest_limits": [
            "Query counts and sub-millisecond latency are not claimed in this artifact.",
            "Live Render/Redis/Celery worker health requires EXTERNAL infrastructure proof.",
            "Ollama/ASGI long-poll throughput is environment-dependent.",
        ],
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Core runtime dependency audit",
        "",
        f"**Generated:** {data['generated_at']}",
        "",
        "Metadata-only inventory of Django runtime, auth, CORS/CSRF, DRF/JWT, Celery, and Channels.",
        "No secrets, credentials, or tenant-private data.",
        "",
        "## Django runtime",
        "",
    ]
    for key, val in data["django"].items():
        lines.append(f"- **{key}:** `{val}`")
    lines.extend(["", "## Auth / MFA", ""])
    for key, val in data["auth_mfa"].items():
        lines.append(f"- **{key}:** `{val}`")
    lines.extend(["", "## DRF / JWT", ""])
    for key, val in data["drf_jwt"].items():
        lines.append(f"- **{key}:** `{val}`")
    lines.extend(["", "## CORS / CSRF", ""])
    for key, val in data["cors_csrf"].items():
        lines.append(f"- **{key}:** `{val}`")
    lines.extend(["", "## Async (Celery / Channels)", ""])
    for key, val in data["async_infrastructure"].items():
        lines.append(f"- **{key}:** `{val}`")
    lines.extend(["", "## Honest limits", ""])
    for item in data["honest_limits"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.check:
        args.write = True

    _bootstrap_django()
    data = build_audit()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)

    if args.check and JSON_OUT.is_file():
        existing = json.loads(JSON_OUT.read_text(encoding="utf-8"))
        if existing.get("celery_beat_schedule_count") != data["async_infrastructure"][
            "celery_beat_schedule_count"
        ]:
            print("core_runtime_dependency_audit: stale (beat schedule count drift)")
            return 1

    if args.write or args.check:
        JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        MD_OUT.write_text(_write_md(data), encoding="utf-8")
        print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
        print(f"Wrote {MD_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
