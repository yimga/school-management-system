#!/usr/bin/env python3
"""
Verify critical Django middleware ordering (Linux pillar).

Fails when security/session/tenant/CORS/idempotency layers drift out of the
documented positions in config.settings.MIDDLEWARE.
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


def verify_middleware_order(stack: list[str]) -> list[str]:
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
    errors = verify_middleware_order(stack)
    if errors:
        for err in errors:
            print(f"verify_middleware_stack_order: {err}", file=sys.stderr)
        return 1
    print("verify_middleware_stack_order: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
