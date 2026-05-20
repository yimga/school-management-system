#!/usr/bin/env python3
"""Tenant kernel architecture discovery artifact (metadata-only, PII-free).

Writes:
  docs/generated/tenant_kernel_architecture_review.json
  docs/generated/tenant_kernel_architecture_review.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "tenant_kernel_architecture_review.json"
MD_OUT = ROOT / "docs" / "generated" / "tenant_kernel_architecture_review.md"


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def build_review() -> dict:
    from django.conf import settings
    from django.db import connection

    middleware = list(getattr(settings, "MIDDLEWARE", []))
    tenant_mw = [m for m in middleware if "Tenant" in m or "tenant" in m.lower()]

    rls_migrations = sorted(
        p.name
        for p in (ROOT / "apps").rglob("migrations/*rls*.py")
        if p.is_file()
    )
    force_rls = (ROOT / "apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py").is_file()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "tenancy": {
            "tenancy_mode": getattr(settings, "TENANCY_MODE", None),
            "use_django_tenants": bool(getattr(settings, "USE_DJANGO_TENANTS", False)),
            "database_vendor": connection.vendor,
            "rls_active_on_engine": connection.vendor == "postgresql"
            and not getattr(settings, "USE_DJANGO_TENANTS", False),
            "force_rls_migration_present": force_rls,
            "rls_policy_migration_count": len(rls_migrations),
        },
        "host_routing": {
            "multi_tenant_base_domain": getattr(settings, "MULTI_TENANT_BASE_DOMAIN", ""),
            "manager_urlconf": "config.manager_urls",
            "tenant_urlconf": "config.tenant_urls",
        },
        "middleware_tenant_stack": tenant_mw,
        "session_isolation": {
            "manager_session_cookie": getattr(settings, "MANAGER_SESSION_COOKIE_NAME", None),
            "impersonation_token_max_age": getattr(
                settings, "IMPERSONATION_TOKEN_MAX_AGE_SECONDS", None
            ),
            "impersonation_require_justification": bool(
                getattr(settings, "IMPERSONATION_REQUIRE_JUSTIFICATION", True)
            ),
            "jit_impersonation_require_consent": bool(
                getattr(settings, "JIT_IMPERSONATION_REQUIRE_CONSENT", True)
            ),
        },
        "proof_differences": {
            "sqlite": "RLS session GUCs are no-ops; isolation relies on queryset scoping + middleware.",
            "postgresql_rls": "app.current_school_id + FORCE RLS bind tenant rows when TENANCY_MODE=RLS.",
            "postgresql_schema": "django-tenants schema routing when USE_DJANGO_TENANTS=True.",
        },
        "target_apps": [
            "schools",
            "tenancy",
            "customers",
            "accounts",
            "siteconfig",
            "platform_runtime",
            "security",
            "compliance",
        ],
    }


def _write_md(data: dict) -> str:
    t = data["tenancy"]
    lines = [
        "# Tenant kernel architecture review",
        "",
        f"**Generated:** {data['generated_at']}",
        "",
        "## Mode",
        "",
        f"- **TENANCY_MODE:** `{t['tenancy_mode']}`",
        f"- **USE_DJANGO_TENANTS:** `{t['use_django_tenants']}`",
        f"- **DB vendor:** `{t['database_vendor']}`",
        f"- **RLS active (engine):** `{t['rls_active_on_engine']}`",
        f"- **FORCE RLS migration:** `{t['force_rls_migration_present']}`",
        "",
        "## Proof differences",
        "",
    ]
    for key, note in data["proof_differences"].items():
        lines.append(f"- **{key}:** {note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    _ = parser.parse_args()
    _bootstrap_django()
    data = build_review()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
