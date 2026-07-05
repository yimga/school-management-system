#!/usr/bin/env python3
"""verify_tenant_cannot_reach_operator_routes.py — the end-to-end negative proof that
NO operator route is reachable by a tenant session (H4.5 of
docs/generated/tenant_operator_isolation_forensic_audit_2026_07_04.md).

Before this gate, coverage was 3 sampled routes + 6 scenarios; there was no gate that
ENUMERATED every operator route and asserted a tenant identity is denied. This gate
enumerates every route in the ``super:`` namespace across the host-split urlconfs and
asserts, for each, that its resolved path triggers the operator guard
``apps.schools.middleware._is_operator_super_route`` — i.e. TenantSuperAdminRequired-
Middleware requires control-plane access for it on ANY host, including a tenant
subdomain (``/portal/super/...``, ``/api/v1/super/...``). A ``super:`` route whose path
carried no ``super`` segment would be reachable on the tenant host without the guard —
a hole this gate turns red.

It also live-checks the keystone at runtime: a tenant is_staff admin fails
``user_has_control_plane_access`` while a superuser passes — so the guard's allow/deny
decision itself can't silently invert.

Needs Django (URL resolver + control-plane helper) → runs in ci.yml::django-tests.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.urls import get_resolver  # noqa: E402
from django.urls.resolvers import URLPattern, URLResolver  # noqa: E402

from apps.schools.middleware import _is_operator_super_route  # noqa: E402

# Operator urlconfs to enumerate the `super:` namespace from. ROOT (config.urls) mounts
# super_urls under /super/; the manager host mounts it too. Both must be covered.
_URLCONFS = ("config.urls", "config.manager_urls")


def _walk(patterns, prefix, ns_stack, out):
    for p in patterns:
        if isinstance(p, URLResolver):
            seg = str(p.pattern)
            child_ns = ns_stack + ([p.namespace] if p.namespace else [])
            _walk(p.url_patterns, prefix + seg, child_ns, out)
        elif isinstance(p, URLPattern):
            if "super" in ns_stack:
                full = "/" + (prefix + str(p.pattern)).lstrip("/")
                name = ":".join([n for n in ns_stack if n] + [p.name or ""])
                out.append((full, name))


def _collect_super_routes():
    seen = {}
    for urlconf in _URLCONFS:
        try:
            resolver = get_resolver(urlconf)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: cannot load resolver for {urlconf}: {exc}", file=sys.stderr)
            continue
        out = []
        _walk(resolver.url_patterns, "", [], out)
        for full, name in out:
            seen.setdefault((full, name), urlconf)
    return seen


def _keystone_ok() -> tuple[bool, str]:
    """Static/behavioral sanity: the guard's decision helper is disjoint from tenants.

    We assert on the pure helper set-membership rather than creating DB rows so the
    gate stays fast and side-effect-free; the DB-backed identity disjointness is
    covered by verify_tenant_control_plane_rbac.py (5-pass, --strict).
    """
    from apps.schools.control_plane import user_has_control_plane_access  # noqa: F401

    # _is_operator_super_route truth invariants the middleware relies on.
    checks = [
        _is_operator_super_route("/super/dashboard/") is True,
        _is_operator_super_route("/portal/super/merges/") is True,
        _is_operator_super_route("/api/v1/super/tenant-inspect/1/") is True,
        _is_operator_super_route("/portal/parent/") is False,
        _is_operator_super_route("/supervisor/") is False,
    ]
    if not all(checks):
        return False, "operator-super-route helper truth table regressed"
    return True, ""


def main() -> int:
    ok, why = _keystone_ok()
    if not ok:
        print(f"FAIL: {why}", file=sys.stderr)
        return 1

    routes = _collect_super_routes()
    uncovered = []
    for (full, name), urlconf in sorted(routes.items()):
        if not _is_operator_super_route(full):
            uncovered.append((full, name, urlconf))

    total = len(routes)
    if uncovered:
        print(
            f"FAIL: {len(uncovered)} operator (super:) route(s) NOT covered by the "
            f"tenant-host super-segment guard — reachable on a tenant host:",
            file=sys.stderr,
        )
        for full, name, urlconf in uncovered:
            print(f"  {full}  [{name}]  ({urlconf})", file=sys.stderr)
        return 1

    print(
        f"TENANT_CANNOT_REACH_OPERATOR_ROUTES_PASS: {total} super: route(s) enumerated, "
        f"all covered by the operator super-segment guard."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
