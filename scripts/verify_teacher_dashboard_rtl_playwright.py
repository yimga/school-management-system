#!/usr/bin/env python3
"""Glocal 1537 — teacher dashboard RTL Playwright spec scaffold (+ optional live run)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests/e2e/teacher-dashboard-rtl-mobile.spec.js"


def _scaffold_checks() -> list[str]:
    findings: list[str] = []
    if not SPEC.is_file():
        findings.append("missing tests/e2e/teacher-dashboard-rtl-mobile.spec.js")
        return findings
    text = SPEC.read_text(encoding="utf-8")
    for needle in (
        "390",
        "dir",
        "rtl",
        "data-rmc-cp-scroll",
        "canvas",
        "tenantLogin",
        "dashboard-page-teacher",
        "horizontalOverflowPx",
    ):
        if needle not in text:
            findings.append(f"teacher-dashboard-rtl-mobile.spec.js missing {needle!r}")
    helper = ROOT / "tests/e2e/helpers/tenant-login.js"
    if not helper.is_file():
        findings.append("missing tests/e2e/helpers/tenant-login.js")
    return findings


def _playwright_env(*, spawn_server: bool = False) -> dict[str, str]:
    import shutil
    from urllib.parse import urlparse

    env = os.environ.copy()
    port = env.get("VISUAL_QA_PORT", "8000")
    if spawn_server and "VISUAL_QA_PORT" not in os.environ:
        port = "8011"
    env["VISUAL_QA_PORT"] = port
    base = (env.get("TENANT_BASE_URL") or f"http://127.0.0.1:{port}").rstrip("/")
    parsed = urlparse(base)
    slug = env.get("TENANT_SLUG", "gilead-school")
    env.setdefault("TENANT_SLUG", slug)
    env.setdefault("VISUAL_QA_PORT", str(parsed.port or port))
    if spawn_server and "TENANT_ROUTING" not in os.environ:
        env["TENANT_ROUTING"] = "host"
    else:
        env.setdefault("TENANT_ROUTING", "path")
    env.setdefault("E2E_USERNAME", "teacher1")
    env.setdefault("E2E_PASSWORD", "Sch00l_1234")
    env.setdefault(
        "PLAYWRIGHT_HOST_RULES",
        "MAP gilead-school.runmycampus.com 127.0.0.1,"
        "MAP demo-school.runmycampus.com 127.0.0.1,"
        "MAP apple-class-qa.runmycampus.com 127.0.0.1,"
        "MAP manager.runmycampus.com 127.0.0.1,"
        "MAP *.runmycampus.com 127.0.0.1",
    )
    if env.get("TENANT_ROUTING") == "host":
        env["TENANT_BASE_URL"] = f"http://{slug}.runmycampus.com:{env['VISUAL_QA_PORT']}"
    elif parsed.hostname in {"127.0.0.1", "localhost"}:
        env.setdefault("TENANT_BASE_URL", f"http://127.0.0.1:{env['VISUAL_QA_PORT']}")
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        env["_RMC_NPM_CMD"] = npm_cmd
    return env


def _probe_server(base: str, timeout: float = 2.0, *, slug: str = "gilead-school") -> bool:
    """Health probe — tenant login paths often 301 off-host; use /healthz/ for readiness."""
    del slug  # reserved for future tenant-scoped health checks
    parsed = urlparse(base)
    hostname = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loopback = hostname in {"127.0.0.1", "localhost"} or hostname.endswith(
        ".runmycampus.com"
    )
    probe_origin = (
        f"http://127.0.0.1:{port}"
        if loopback and not hostname.startswith("127.")
        else base.rstrip("/")
    )
    headers: dict[str, str] = {}
    if probe_origin != base.rstrip("/"):
        headers["Host"] = hostname
    for path in ("/healthz/", "/"):
        try:
            req = urllib.request.Request(
                f"{probe_origin}{path}",
                method="GET",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= int(resp.status) < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if 200 <= int(exc.code) < 500:
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def _wait_for_server(
    base: str, *, slug: str = "gilead-school", timeout_sec: float = 120.0
) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _probe_server(base, timeout=5.0, slug=slug):
            return True
        time.sleep(3.0)
    return False


def _spawn_django(port: str) -> tuple[subprocess.Popen[bytes], Path]:
    env = os.environ.copy()
    env["SECURITY_ENFORCE_MINIMUM_STRENGTH"] = "0"
    env["USE_FILE_LOGGING"] = "0"
    log_path = ROOT / "var" / "evidence" / "teacher-rtl-playwright-runserver.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return proc, log_path


def _run_playwright(env: dict[str, str]) -> tuple[bool, str]:
    npm_cmd = env.get("_RMC_NPM_CMD")
    if not npm_cmd:
        return False, "npm not found on PATH"
    proc = subprocess.run(
        [npm_cmd, "run", "test:e2e:teacher:rtl-mobile"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=420,
        env=env,
        shell=os.name == "nt",
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-1200:]
    return proc.returncode == 0, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute Playwright against TENANT_BASE_URL (Lane 2; needs live Django).",
    )
    parser.add_argument(
        "--spawn-server",
        action="store_true",
        help="With --run: start manage.py runserver (SECURITY_ENFORCE_MINIMUM_STRENGTH=0) if down.",
    )
    args = parser.parse_args()

    findings = _scaffold_checks()
    if findings:
        print("verify_teacher_dashboard_rtl_playwright: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    if not args.run:
        print("verify_teacher_dashboard_rtl_playwright: TEACHER_DASHBOARD_RTL_PLAYWRIGHT_SCAFFOLD_PASS")
        return 0

    env = _playwright_env(spawn_server=args.spawn_server)
    base = (env.get("TENANT_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
    server_proc: subprocess.Popen[bytes] | None = None
    spawn_log: Path | None = None
    spawned = False
    slug = env.get("TENANT_SLUG", "gilead-school")

    try:
        if args.spawn_server:
            port = env.get("VISUAL_QA_PORT", "8011")
            if env.get("TENANT_ROUTING") == "host":
                base = f"http://{slug}.runmycampus.com:{port}"
            else:
                base = f"http://127.0.0.1:{port}"
            env["TENANT_BASE_URL"] = base
            env["VISUAL_QA_PORT"] = port
            server_proc, spawn_log = _spawn_django(port)
            spawned = True
            if not _wait_for_server(base, slug=slug, timeout_sec=420.0):
                tail = ""
                if spawn_log and spawn_log.is_file():
                    tail = spawn_log.read_text(encoding="utf-8", errors="replace")[-600:]
                print(
                    "verify_teacher_dashboard_rtl_playwright: FAIL (runserver did not become ready)",
                    file=sys.stderr,
                )
                if tail:
                    print(tail, file=sys.stderr)
                return 1
        elif not _probe_server(base):
            print(
                "verify_teacher_dashboard_rtl_playwright: SKIP live run "
                f"(server unreachable at {base}; pass --spawn-server to auto-start)",
                file=sys.stderr,
            )
            print(
                "verify_teacher_dashboard_rtl_playwright: "
                "TEACHER_DASHBOARD_RTL_PLAYWRIGHT_SCAFFOLD_PASS"
            )
            return 0

        ok, tail = _run_playwright(env)
        if not ok:
            print("verify_teacher_dashboard_rtl_playwright: FAIL (playwright run)", file=sys.stderr)
            print(tail, file=sys.stderr)
            return 1
        mode = "live" + ("+spawn" if spawned else "")
        print(f"verify_teacher_dashboard_rtl_playwright: TEACHER_DASHBOARD_RTL_PLAYWRIGHT_PASS ({mode})")
        return 0
    finally:
        if server_proc is not None and spawned:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
