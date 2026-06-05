#!/usr/bin/env python3
"""Live smoke for nav sidebar rail + resize on operator and tenant shells."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error

# Reuse operator-tools smoke transport helpers (stdlib-only).
from smoke_operator_tools_tray import (  # noqa: E402
    _bootstrap_qa,
    _build_opener,
    _env,
    _login_surface,
    _request,
    _wait_ready,
)


def _assert_nav_sidebar(body: str, label: str, *, manager: bool = True) -> None:
    required = (
        'id="page-data-rmc-nav-sidebar"',
        "rmc-nav-sidebar.js",
        "rmc-nav-sidebar.css",
        "rmc-nav-sidebar__toggle",
        "rmc-nav-sidebar__resize-handle",
    )
    for needle in required:
        if needle not in body:
            raise SystemExit(f"FAIL: {label} missing {needle!r}")
    if manager:
        if 'id="cp-sidebar-col"' not in body:
            raise SystemExit(f"FAIL: {label} missing cp-sidebar-col mount")
    else:
        if 'id="portal-sidebar-col"' not in body:
            raise SystemExit(f"FAIL: {label} missing portal-sidebar-col mount")
    if "portal-resize-handle" in body:
        raise SystemExit(f"FAIL: {label} still ships legacy portal-resize-handle")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-secs", type=int, default=int(_env("SMOKE_WAIT_SECS", "120")))
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Skip QA seed (seed_apple_class_qa or seed_demo_tenant_users)",
    )
    args = parser.parse_args()

    port = _env("VISUAL_QA_PORT", "8012")
    loopback = _env("VISUAL_QA_LOOPBACK", "127.0.0.1")
    manager_host = _env("VISUAL_QA_MANAGER_HOST", "manager.runmycampus.com")
    tenant_slug = _env("TENANT_SWEEP_SLUG", "apple-class-qa")
    tenant_host = _env("VISUAL_QA_TENANT_HOST", f"{tenant_slug}.runmycampus.com")
    base = _env("MANAGER_BASE_URL", f"http://{loopback}:{port}")
    username = _env("E2E_LOGIN_USER", "admin")
    password = _env("E2E_LOGIN_PASSWORD", "Sch00l_1234")

    bootstrap = not args.no_bootstrap and _env("SMOKE_BOOTSTRAP", "1") != "0"
    if bootstrap:
        _bootstrap_qa(tenant_slug)

    _wait_ready(base, manager_host, loopback, port, args.wait_secs)

    mgr = _build_opener(manager_host, loopback, port)
    _login_surface(
        mgr,
        base,
        manager_host,
        username,
        password,
        next_path="/super/",
        label="manager",
    )

    code, super_body, _ = _request(mgr, "GET", f"{base}/super/", host=manager_host)
    if code != 200:
        raise SystemExit(f"FAIL: /super/ HTTP {code}")
    _assert_nav_sidebar(super_body, "/super/", manager=True)
    print("OK: manager /super/ ships nav sidebar contract")

    code, zero_body, _ = _request(mgr, "GET", f"{base}/siteconfig/super/zero-ticket/", host=manager_host)
    if code == 200:
        _assert_nav_sidebar(zero_body, "zero-ticket hub", manager=True)
        print("OK: zero-ticket hub ships nav sidebar contract")

    code, admin_body, _ = _request(mgr, "GET", f"{base}/admin/", host=manager_host)
    if code != 200:
        raise SystemExit(f"FAIL: /admin/ HTTP {code}")
    _assert_nav_sidebar(admin_body, "/admin/", manager=True)
    print("OK: manager /admin/ ships nav sidebar contract")

    tenant = _build_opener(tenant_host, loopback, port)
    tenant_user = _env("TENANT_SMOKE_USER", "demo.teacher")
    tenant_pass = _env("TENANT_SMOKE_PASSWORD", "Test1234")
    backend_path = "/authentication/backend/"
    _login_surface(
        tenant,
        base,
        tenant_host,
        tenant_user,
        tenant_pass,
        next_path=backend_path,
        label=f"tenant ({tenant_slug})",
    )

    code, tenant_body, _ = _request(tenant, "GET", f"{base}{backend_path}", host=tenant_host)
    if code != 200:
        raise SystemExit(
            f"FAIL: tenant backend HTTP {code} for {tenant_slug} "
            "(set TENANT_SWEEP_SLUG / TENANT_SMOKE_USER/PASSWORD or run bootstrap)"
        )
    _assert_nav_sidebar(tenant_body, "tenant backend", manager=False)
    print("OK: tenant backend ships nav sidebar contract")

    print("NAV_SIDEBAR_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        raise SystemExit(f"FAIL: network error — {exc}") from exc
