#!/usr/bin/env python3
"""
Verify critical Django middleware ordering (Linux pillar).

Supports both stacks:
  - Single-schema (USE_DJANGO_TENANTS=0): SecurityMiddleware first + TenantMiddleware
  - Schema-per-tenant (USE_DJANGO_TENANTS=1, Render production): TenantMainMiddleware first
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _index(stack: list[str], needle: str) -> int:
    for i, entry in enumerate(stack):
        if needle in entry:
            return i
    return -1


def _calls_get_response(node) -> bool:
    """True if this statement contains a call to ``self.get_response(...)``."""
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get_response"
        ):
            return True
    return False


def has_request_phase(dotted: str) -> bool:
    """Does this middleware do anything BEFORE calling get_response?

    Structural, not a name allowlist, so the next response-only wrapper is legal
    and the next request-phase interloper still fails. Unknown shapes are treated
    as request-phase: this decides whether something may sit ahead of
    SecurityMiddleware, so the safe default is "yes, it does".
    """
    module_path, _, attr = dotted.rpartition(".")
    try:
        obj = getattr(importlib.import_module(module_path), attr)
    except Exception:
        return True
    if hasattr(obj, "process_request") or hasattr(obj, "process_view"):
        return True
    call = getattr(obj, "__call__", None)
    if call is None:
        return True
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(call)))
    except (OSError, TypeError, SyntaxError):
        return True
    fn = tree.body[0]
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return True
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]  # a docstring is not request-phase work
    for position, stmt in enumerate(body):
        if _calls_get_response(stmt):
            return position > 0
    return True  # never delegates: not a passthrough wrapper

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
    # INVERTED 2026-09-03. This asked for IdempotencyKeyMiddleware BEFORE
    # AuthenticationMiddleware ("dedupe before auth mutates request"). Implementing
    # that is a cross-user data leak: the idempotency cache key is built from
    # _user_key(request), which reads request.user and falls back to "anon" when it
    # is absent -- and request.user is exactly what AuthenticationMiddleware sets. Run
    # earlier and every caller keys as global:anon:<method>:<path>:<header>, so two
    # authenticated users sending the same Idempotency-Key to the same path collide
    # and the second is served the first one's cached JSON body. Measured: the two
    # cache keys come back byte-identical. The stack already has this the right way
    # round; the gate did not.
    require_before(
        "AuthenticationMiddleware",
        "IdempotencyKeyMiddleware",
        "the idempotency cache key is user-scoped, so request.user must already be set",
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
    # RELAXED 2026-09-03, in letter but not in intent. This required
    # SecurityMiddleware at index 0 outright, which is incompatible with a
    # RESPONSE-ONLY wrapper -- and one is deliberately in front of it.
    # EdgeHttpsPortRedirectMiddleware rewrites the Location header SecurityMiddleware
    # emits: SECURE_SSL_REDIRECT builds its target from request.get_host() including
    # the port, so a box published on WEB_PORT answers 301 https://<box>:10000/ where
    # nothing speaks TLS, and the browser hangs to ERR_TIMED_OUT. Measured on a live
    # box. Django runs the response phase in reverse, so the fixer MUST be listed
    # earlier. What "first" is really protecting is that no middleware inspects or
    # mutates a REQUEST before the security checks run -- and that is preserved
    # exactly, because a response-only wrapper has no request phase at all.
    security_at = _index(stack, "SecurityMiddleware")
    if security_at < 0:
        errors.append("missing middleware containing 'SecurityMiddleware'")
    else:
        for ahead in stack[:security_at]:
            if has_request_phase(ahead):
                errors.append(
                    f"{ahead} precedes SecurityMiddleware and has request-phase "
                    "behaviour: only response-only middleware may sit ahead of the "
                    "security checks"
                )

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
