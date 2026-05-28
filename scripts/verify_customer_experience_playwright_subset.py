#!/usr/bin/env python3
"""CEZGP optional Playwright subset (local server on runmycampus.com:8000)."""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Playwright host-rules map runmycampus.com → 127.0.0.1; probe loopback with Host header.
BASE = os.environ.get("MARKETING_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MARKETING_HOST = os.environ.get("MARKETING_TEST_HOST", "runmycampus.com")
TENANT_LOGIN_PATH = os.environ.get(
    "TENANT_LOGIN_PATH", "/authentication/login/"
)
_TENANT_HOST_CANDIDATES = (
    "demo-school.runmycampus.com",
    "apple-class-qa.runmycampus.com",
)


def _resolve_tenant_host() -> str:
    explicit = os.environ.get("TENANT_TEST_HOST", "").strip()
    if explicit:
        return explicit
    for host in _TENANT_HOST_CANDIDATES:
        if _probe(TENANT_LOGIN_PATH, host):
            return host
    return _TENANT_HOST_CANDIDATES[0]

MARKETING_SPECS = (
    "tests/e2e/marketing-visual-engine.spec.js",
    "tests/e2e/help-ai-center-a11y.spec.js",
)
TENANT_SPECS = ("tests/e2e/parent-identity-cezgp-lane2.spec.js",)


def _probe(path: str, host: str, *, allow_redirect: bool = True) -> bool:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        req = urllib.request.Request(
            f"{BASE}{path}",
            headers={"Host": host},
            method="GET",
        )
        with opener.open(req, timeout=12) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 200:
            return True
        if not allow_redirect or exc.code not in (301, 302, 303, 307, 308):
            return False
        location = (exc.headers.get("Location") or "").lower()
        if "school-not-found" in location:
            return False
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _server_up(tenant_host: str) -> bool:
    return _probe("/", MARKETING_HOST, allow_redirect=True) and _probe(
        TENANT_LOGIN_PATH, tenant_host, allow_redirect=True
    )


def main() -> int:
    tenant_host = _resolve_tenant_host()
    if not _server_up(tenant_host):
        print(
            "verify_customer_experience_playwright_subset: SKIP "
            f"(no server at {BASE}; start Django and re-run)",
            file=sys.stderr,
        )
        return 0

    marketing_base = os.environ.get(
        "MARKETING_BASE_URL", f"http://{MARKETING_HOST}:8000"
    ).rstrip("/")
    tenant_base = os.environ.get(
        "PLAYWRIGHT_TENANT_BASE_URL", f"http://{tenant_host}:8000"
    ).rstrip("/")
    print(f"  tenant host: {tenant_host}")

    def _run_specs(specs: tuple[str, ...], env_extra: dict[str, str]) -> int:
        env = {**os.environ, **env_extra}
        for spec in specs:
            proc = subprocess.run(
                f'npx playwright test "{spec}" --reporter=line',
                cwd=REPO,
                env=env,
                shell=True,
                timeout=600,
            )
            if proc.returncode != 0:
                print(
                    f"verify_customer_experience_playwright_subset: FAIL ({spec})",
                    file=sys.stderr,
                )
                return 1
            print(f"  OK: {spec}")
        return 0

    if _run_specs(
        MARKETING_SPECS,
        {
            "MARKETING_BASE_URL": marketing_base,
            "BASE_URL": marketing_base,
        },
    ):
        return 1
    if _run_specs(
        TENANT_SPECS,
        {
            "PLAYWRIGHT_TENANT_BASE_URL": tenant_base,
            "PLAYWRIGHT_BASE_URL": tenant_base,
            "BASE_URL": tenant_base,
            "TENANT_LOGIN_PATH": TENANT_LOGIN_PATH,
        },
    ):
        return 1

    print("CUSTOMER_EXPERIENCE_PLAYWRIGHT_SUBSET_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
