#!/usr/bin/env python3
"""Live smoke for nav sidebar rail + resize on operator and tenant shells."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

# Reuse operator-tools smoke transport helpers (stdlib-only).
from smoke_operator_tools_tray import (  # noqa: E402
    _build_opener,
    _csrf_from_body,
    _csrf_from_cookies,
    _env,
    _login_manager,
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
    args = parser.parse_args()

    port = _env("VISUAL_QA_PORT", "8012")
    loopback = _env("VISUAL_QA_LOOPBACK", "127.0.0.1")
    manager_host = _env("VISUAL_QA_MANAGER_HOST", "manager.runmycampus.com")
    tenant_slug = _env("TENANT_SWEEP_SLUG", "apple-class-qa")
    tenant_host = _env("VISUAL_QA_TENANT_HOST", f"{tenant_slug}.runmycampus.com")
    base = _env("MANAGER_BASE_URL", f"http://{loopback}:{port}")
    username = _env("E2E_LOGIN_USER", "admin")
    password = _env("E2E_LOGIN_PASSWORD", "Sch00l_1234")

    _wait_ready(base, manager_host, loopback, port, args.wait_secs)

    mgr = _build_opener(manager_host, loopback, port)
    _login_manager(mgr, base, manager_host, username, password)

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
    tenant_user = _env("TENANT_SMOKE_USER", "teacher")
    tenant_pass = _env("TENANT_SMOKE_PASSWORD", "Test1234")
    login_path = f"{base}/t/{tenant_slug}/authentication/login/"
    backend_path = f"{base}/t/{tenant_slug}/authentication/backend/"
    code, body, _ = _request(tenant, "GET", login_path, host=tenant_host)
    if code == 200:
        csrf = _csrf_from_body(body) or _csrf_from_cookies(tenant)
        if csrf:
            form = urllib.parse.urlencode(
                {
                    "username": tenant_user,
                    "password": tenant_pass,
                    "csrfmiddlewaretoken": csrf,
                    "next": backend_path,
                }
            ).encode("utf-8")
            _request(
                tenant,
                "POST",
                login_path,
                host=tenant_host,
                data=form,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": login_path,
                    "X-CSRFToken": csrf,
                },
            )
    code, tenant_body, _ = _request(tenant, "GET", backend_path, host=tenant_host)
    if code != 200:
        raise SystemExit(f"FAIL: tenant backend HTTP {code}")
    _assert_nav_sidebar(tenant_body, "tenant backend", manager=False)
    print("OK: tenant portal ships nav sidebar contract")

    print("NAV_SIDEBAR_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        raise SystemExit(f"FAIL: network error — {exc}") from exc
