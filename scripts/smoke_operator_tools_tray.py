#!/usr/bin/env python3
"""
Live HTTP smoke for Operator Tools edge-tray (manager /super/, manager /admin/, tenant exclusion).

Requires Django on VISUAL_QA_PORT (default 8012). Uses Host headers — no /etc/hosts edit required.

Usage:
  python scripts/smoke_operator_tools_tray.py
  VISUAL_QA_PORT=8012 E2E_LOGIN_USER=admin E2E_LOGIN_PASSWORD=admin python scripts/smoke_operator_tools_tray.py
"""

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


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip()


def _build_opener(host_header: str, loopback: str, port: str) -> urllib.request.OpenerDirector:
    jar = CookieJar()

    class _HostPreservingRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parsed = urllib.parse.urlparse(newurl)
            if parsed.hostname and parsed.hostname not in (loopback, "localhost", "127.0.0.1"):
                newurl = urllib.parse.urlunparse(
                    parsed._replace(netloc=f"{loopback}:{port}")
                )
            new_req = urllib.request.Request(
                newurl,
                data=req.data,
                headers=dict(req.header_items()),
                method=req.get_method(),
            )
            new_req.add_header("Host", host_header)
            return new_req

    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        _HostPreservingRedirectHandler(),
    )


def _request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    *,
    host: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, str, dict[str, str]]:
    hdrs = {"Host": host, "User-Agent": "rmc-operator-tools-smoke/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, dict(exc.headers)


def _wait_ready(base: str, host: str, loopback: str, port: str, max_secs: int) -> None:
    opener = _build_opener(host, loopback, port)
    for _ in range(max_secs):
        try:
            code, _, _ = _request(opener, "GET", f"{base}/ready/", host=host, timeout=3.0)
            if code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL: server not ready at {base}/ready/ (Host: {host}) within {max_secs}s")


def _csrf_from_cookies(opener: urllib.request.OpenerDirector) -> str:
    for cookie in opener.handlers[0].cookiejar:  # type: ignore[attr-defined]
        if cookie.name in ("csrftoken", "csrfmiddlewaretoken"):
            return cookie.value
    return ""


def _csrf_from_body(body: str) -> str:
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', body)
    return match.group(1) if match else ""


def _login_manager(
    opener: urllib.request.OpenerDirector,
    base: str,
    host: str,
    username: str,
    password: str,
) -> None:
    code, body, _ = _request(opener, "GET", f"{base}/authentication/login/", host=host)
    if code != 200:
        raise SystemExit(f"FAIL: login page HTTP {code}")
    csrf = _csrf_from_body(body) or _csrf_from_cookies(opener)
    if not csrf:
        raise SystemExit("FAIL: could not resolve CSRF token on manager login page")
    form = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": csrf,
            "next": "/super/",
        }
    ).encode("utf-8")
    code, body, _ = _request(
        opener,
        "POST",
        f"{base}/authentication/login/",
        host=host,
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base}/authentication/login/",
            "X-CSRFToken": csrf,
        },
    )
    if code not in (200, 302):
        raise SystemExit(f"FAIL: manager login POST HTTP {code}")
    if "/authentication/login/" in body and "Invalid" in body:
        raise SystemExit("FAIL: manager login rejected (check E2E_LOGIN_USER/PASSWORD)")


def _assert_manager_tray(body: str, label: str) -> None:
    required = (
        'id="page-data-rmc-operator-tools"',
        "rmc-operator-tools-tray.js",
        "rmc-operator-tools-tray.css",
    )
    forbidden = ('data-rmc-back-to-top-policy="always"',)
    for needle in required:
        if needle not in body:
            raise SystemExit(f"FAIL: {label} missing {needle!r}")
    for needle in forbidden:
        if needle in body:
            raise SystemExit(f"FAIL: {label} still has {needle!r}")


def _assert_tenant_no_tray(body: str, label: str) -> None:
    forbidden = (
        'id="page-data-rmc-operator-tools"',
        "rmc-operator-tools-tray.js",
        "rmc-operator-tools-tray.css",
    )
    for needle in forbidden:
        if needle in body:
            raise SystemExit(f"FAIL: {label} must not ship operator tools ({needle!r})")


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
    _assert_manager_tray(super_body, "/super/")
    print("OK: manager /super/ ships operator tools island")

    code, admin_body, _ = _request(mgr, "GET", f"{base}/admin/", host=manager_host)
    if code != 200:
        raise SystemExit(f"FAIL: /admin/ HTTP {code}")
    _assert_manager_tray(admin_body, "/admin/")
    print("OK: manager /admin/ ships operator tools island")

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
                    "next": backend_path.replace(base, ""),
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
        raise SystemExit(
            f"FAIL: tenant backend HTTP {code} for {tenant_slug} "
            "(set TENANT_SWEEP_SLUG / TENANT_SMOKE_USER/PASSWORD)"
        )
    _assert_tenant_no_tray(tenant_body, "tenant backend")
    print("OK: tenant backend excludes operator tools tray")

    print("OPERATOR_TOOLS_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
