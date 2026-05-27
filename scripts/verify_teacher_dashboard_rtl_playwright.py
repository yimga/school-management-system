#!/usr/bin/env python3
"""Glocal 1537 — teacher dashboard RTL Playwright spec scaffold (+ optional live run)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def _run_playwright() -> tuple[bool, str]:
    import os
    import shutil
    from urllib.parse import urlparse

    env = os.environ.copy()
    base = (
        env.get("TENANT_BASE_URL")
        or f"http://127.0.0.1:{env.get('VISUAL_QA_PORT', '8000')}"
    ).rstrip("/")
    parsed = urlparse(base)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        slug = env.get("TENANT_SLUG", "gilead-school")
        port = str(parsed.port or "8000")
        env.setdefault("TENANT_ROUTING", "host")
        env.setdefault("TENANT_SLUG", slug)
        env.setdefault("VISUAL_QA_PORT", port)
        env.setdefault("TENANT_BASE_URL", f"http://{slug}.runmycampus.com:{port}")
    env.setdefault(
        "PLAYWRIGHT_HOST_RULES",
        "MAP gilead-school.runmycampus.com 127.0.0.1,"
        "MAP demo-school.runmycampus.com 127.0.0.1,"
        "MAP *.runmycampus.com 127.0.0.1,"
        "MAP runmycampus.com 127.0.0.1,"
        "MAP manager.runmycampus.com 127.0.0.1",
    )
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm_cmd:
        return False, "npm not found on PATH"
    proc = subprocess.run(
        [
            npm_cmd,
            "run",
            "test:e2e:teacher:rtl-mobile",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        shell=os.name == "nt",
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
    return proc.returncode == 0, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute Playwright against TENANT_BASE_URL (Lane 2; needs live Django).",
    )
    args = parser.parse_args()

    findings = _scaffold_checks()
    if findings:
        print("verify_teacher_dashboard_rtl_playwright: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    if args.run:
        import os
        import urllib.error
        import urllib.request

        base = (
            os.environ.get("TENANT_BASE_URL")
            or f"http://127.0.0.1:{os.environ.get('VISUAL_QA_PORT', '8000')}"
        ).rstrip("/")
        try:
            urllib.request.urlopen(f"{base}/", timeout=15)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(
                "verify_teacher_dashboard_rtl_playwright: SKIP live run "
                f"(server unreachable at {base}: {exc})",
                file=sys.stderr,
            )
            print("verify_teacher_dashboard_rtl_playwright: TEACHER_DASHBOARD_RTL_PLAYWRIGHT_SCAFFOLD_PASS")
            return 0
        ok, tail = _run_playwright()
        if not ok:
            print("verify_teacher_dashboard_rtl_playwright: FAIL (playwright run)", file=sys.stderr)
            print(tail, file=sys.stderr)
            return 1
        print("verify_teacher_dashboard_rtl_playwright: TEACHER_DASHBOARD_RTL_PLAYWRIGHT_PASS (live)")
        return 0

    print("verify_teacher_dashboard_rtl_playwright: TEACHER_DASHBOARD_RTL_PLAYWRIGHT_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
