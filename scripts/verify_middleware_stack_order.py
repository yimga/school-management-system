#!/usr/bin/env python3
"""
Verify critical Django middleware ordering (Linux pillar).

Supports both stacks:
  - Single-schema (USE_DJANGO_TENANTS=0): SecurityMiddleware first + TenantMiddleware
  - Schema-per-tenant (USE_DJANGO_TENANTS=1, Render production): TenantMainMiddleware first
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _index(stack: list[str], needle: str) -> int:
    for i, entry in enumerate(stack):
        if needle in entry:
            return i
    return -1


def verify_middleware_order(stack: list[str], *, django_tenants_mode: bool) -> list[str]:
    errors: list[str] = []

    def require_before(a: str, b: str, reason: str) -> None:
        ia, ib = _index(stack, a), _index(stack, b)
        if ia < 0:
            errors.append(f"missing middleware containing {a!r}")
            return
        if ib < 0:
            errors.append(f"missing middleware containing {b!r}")
            return
        if ia >= ib:
            errors.append(f"{a} must precede {b}: {reason}")

    tenant_main_markers = ("TenantMainMiddleware", "HealthAwareTenantMainMiddleware")

    def _tenant_main_index() -> int:
        for marker in tenant_main_markers:
            idx = _index(stack, marker)
            if idx >= 0:
                return idx
        return -1

    if django_tenants_mode or _tenant_main_index() >= 0:
        if _tenant_main_index() != 0:
            errors.append(
                "TenantMainMiddleware (or HealthAwareTenantMainMiddleware subclass) "
                "must be first in MIDDLEWARE"
            )
        require_before(
            "HealthAwareTenantMainMiddleware",
            "TenantSchemaSchoolBridgeMiddleware",
            "schema tenant before request.school bridge",
        )
        if _index(stack, "HealthAwareTenantMainMiddleware") < 0:
            require_before(
                "TenantMainMiddleware",
                "TenantSchemaSchoolBridgeMiddleware",
                "schema tenant before request.school bridge",
            )
        require_before(
            "TenantSchemaSchoolBridgeMiddleware",
            "SessionSchoolBindingMiddleware",
            "request.school before session school_id bind",
        )
        require_before(
            "SecurityMiddleware",
            "SessionMiddleware",
            "security headers before session cookies",
        )
        require_before(
            "SessionMiddleware",
            "AuthenticationMiddleware",
            "session before auth",
        )
        return errors

    require_before(
        "SecurityMiddleware",
        "SessionMiddleware",
        "TLS/security headers before session cookie handling",
    )
    require_before(
        "CorsMiddleware",
        "SessionMiddleware",
        "CORS must run before session for preflight OPTIONS",
    )
    require_before(
        "IdempotencyKeyMiddleware",
        "AuthenticationMiddleware",
        "API idempotency dedupe before auth mutates request",
    )
    require_before(
        "SessionMiddleware",
        "TenantMiddleware",
        "session available before host→school resolution",
    )
    require_before(
        "TenantMiddleware",
        "SessionSchoolBindingMiddleware",
        "request.school before session school_id bind",
    )
    require_before(
        "AuthenticationMiddleware",
        "AppApiContextMiddleware",
        "marketplace app API context after user is known",
    )
    if _index(stack, "SecurityMiddleware") != 0:
        errors.append("SecurityMiddleware must be first in MIDDLEWARE")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    stack = list(getattr(settings, "MIDDLEWARE", []))
    tenants_mode = bool(getattr(settings, "USE_DJANGO_TENANTS", False))
    errors = verify_middleware_order(stack, django_tenants_mode=tenants_mode)
    if errors:
        for err in errors:
            print(f"verify_middleware_stack_order: {err}", file=sys.stderr)
        print(
            f"verify_middleware_stack_order: mode={'django-tenants' if tenants_mode else 'single-schema'} "
            f"USE_DJANGO_TENANTS={tenants_mode}",
            file=sys.stderr,
        )
        return 1
    print(
        f"verify_middleware_stack_order: OK "
        f"(mode={'django-tenants' if tenants_mode else 'single-schema'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
