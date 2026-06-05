#!/usr/bin/env python3
"""
Live HTTP smoke for Operator + Tenant Tools edge-tray (manager /super/, manager /admin/, tenant portal).

Requires Django on VISUAL_QA_PORT (default 8012). Uses Host headers — no /etc/hosts edit required.

Usage:
  python scripts/smoke_operator_tools_tray.py
  python scripts/smoke_operator_tools_tray.py --no-bootstrap
  VISUAL_QA_PORT=8012 E2E_LOGIN_USER=admin E2E_LOGIN_PASSWORD=Sch00l_1234 python scripts/smoke_operator_tools_tray.py
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def _csrf_from_body(body: str) -> str:
    for pattern in (
        r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
        r"name='csrfmiddlewaretoken'\s+value='([^']+)'",
    ):
        match = re.search(pattern, body)
        if match:
            return match.group(1)
    return ""


def _login_surface(
    opener: urllib.request.OpenerDirector,
    base: str,
    host: str,
    username: str,
    password: str,
    *,
    next_path: str,
    label: str,
) -> None:
    login_url = f"{base}/authentication/login/"
    last_code = 0
    last_snippet = ""
    for attempt in range(3):
        code, body, _ = _request(opener, "GET", login_url, host=host)
        if code != 200:
            raise SystemExit(f"FAIL: {label} login page HTTP {code}")
        csrf = _csrf_from_body(body)
        if not csrf:
            raise SystemExit(f"FAIL: could not resolve CSRF token on {label} login page")
        form = urllib.parse.urlencode(
            {
                "username": username,
                "password": password,
                "csrfmiddlewaretoken": csrf,
                "next": next_path,
            }
        ).encode("utf-8")
        last_code, body, _ = _request(
            opener,
            "POST",
            login_url,
            host=host,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_url,
                "X-CSRFToken": csrf,
            },
        )
        last_snippet = body[:240].replace("\n", " ")
        if last_code in (200, 302):
            if "/authentication/login/" in body and (
                "Invalid" in body or "incorrect" in body.lower() or "errorlist" in body
            ):
                raise SystemExit(
                    f"FAIL: {label} login rejected (check credentials or run bootstrap seed)"
                )
            return
        if last_code == 403 and attempt < 2:
            time.sleep(0.35)
            continue
        break
    raise SystemExit(f"FAIL: {label} login POST HTTP {last_code} ({last_snippet})")


def _bootstrap_qa(tenant_slug: str) -> None:
    if tenant_slug == "apple-class-qa":
        script = ROOT / "scripts" / "seed_apple_class_qa.py"
        if script.is_file():
            print(f"bootstrap: {script.name}")
            subprocess.run(
                [sys.executable, str(script)],
                cwd=str(ROOT),
                check=True,
            )
            return
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "manage.py"),
            "seed_demo_tenant_users",
            f"--school-slug={tenant_slug}",
            "--password=Test1234",
            "--username-prefix=demo",
        ],
        cwd=str(ROOT),
        check=True,
    )


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


def _assert_tenant_tray(body: str, label: str) -> None:
    required = (
        'id="page-data-rmc-tenant-tools"',
        "rmc-operator-tools-tray.js",
        "rmc-operator-tools-tray.css",
    )
    forbidden = (
        'id="page-data-rmc-operator-tools"',
        'data-rmc-back-to-top-policy="always"',
    )
    for needle in required:
        if needle not in body:
            raise SystemExit(f"FAIL: {label} missing tenant tools {needle!r}")
    for needle in forbidden:
        if needle in body:
            raise SystemExit(f"FAIL: {label} must not ship {needle!r}")


def _assert_tenant_no_operator_tray(body: str, label: str) -> None:
    if 'id="page-data-rmc-operator-tools"' in body:
        raise SystemExit(f"FAIL: {label} must not ship operator tools page data")


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
    _assert_manager_tray(super_body, "/super/")
    print("OK: manager /super/ ships operator tools island")

    code, admin_body, _ = _request(mgr, "GET", f"{base}/admin/", host=manager_host)
    if code != 200:
        raise SystemExit(f"FAIL: /admin/ HTTP {code}")
    _assert_manager_tray(admin_body, "/admin/")
    print("OK: manager /admin/ ships operator tools island")

    tenant = _build_opener(tenant_host, loopback, port)
    tenant_user = _env("TENANT_SMOKE_USER", "demo.teacher")
    tenant_pass = _env("TENANT_SMOKE_PASSWORD", "Test1234")
    portal_path = "/portal/teacher/"
    _login_surface(
        tenant,
        base,
        tenant_host,
        tenant_user,
        tenant_pass,
        next_path=portal_path,
        label=f"tenant ({tenant_slug})",
    )

    code, tenant_body, _ = _request(tenant, "GET", f"{base}{portal_path}", host=tenant_host)
    if code != 200:
        raise SystemExit(
            f"FAIL: tenant portal HTTP {code} for {tenant_slug} "
            "(set TENANT_SWEEP_SLUG / TENANT_SMOKE_USER/PASSWORD or run bootstrap)"
        )
    _assert_tenant_tray(tenant_body, "tenant portal")
    _assert_tenant_no_operator_tray(tenant_body, "tenant portal")
    print("OK: tenant portal ships tenant tools edge-tray")

    print("OPERATOR_TOOLS_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
