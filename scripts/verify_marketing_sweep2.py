#!/usr/bin/env python3
"""Sweep 2 gate — responsive/theme matrix + LCP/CLS artifacts; optional live run."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

ARTIFACTS = (
    "tests/e2e/marketing-theme-contrast.spec.js",
    "tests/e2e/marketing-impact-responsive.spec.js",
    "tests/e2e/marketing-gear2-a11y.spec.js",
    "tests/e2e/marketing-pricing-i18n.spec.js",
    "scripts/verify_marketing_lighthouse_budget.py",
    "scripts/verify_marketing_lighthouse_budget.mjs",
)

ARTIFACT_SNIPPETS: tuple[tuple[str, str, str], ...] = (
    ("tests/e2e/marketing-theme-contrast.spec.js", "mobile:", "mobile viewport in theme matrix"),
    ("tests/e2e/marketing-theme-contrast.spec.js", "390", "iPhone-scale viewport width"),
    ("tests/e2e/marketing-impact-responsive.spec.js", "data-mkt-bell-clock", "bell clock responsive test"),
    ("tests/e2e/marketing-impact-responsive.spec.js", "data-mkt-day-role", "day|role responsive flow"),
    ("tests/e2e/marketing-impact-responsive.spec.js", "overflowX", "horizontal scroll guard"),
    ("tests/e2e/marketing-impact-responsive.spec.js", "mkt-lane-academics", "academics lane layout gate"),
    ("tests/e2e/marketing-gear2-a11y.spec.js", "data-mkt-day-role", "gear2 day|role axe scope"),
    ("tests/e2e/marketing-gear2-a11y.spec.js", "AxeBuilder", "gear2 axe integration"),
    ("scripts/verify_marketing_lighthouse_budget.mjs", "MKT_LIGHTHOUSE_MAX_LCP_MS", "LCP budget env"),
    ("scripts/verify_marketing_lighthouse_budget.mjs", "MKT_LIGHTHOUSE_MAX_CLS", "CLS budget env"),
    ("scripts/verify_marketing_lighthouse_budget.mjs", "2500", "LCP 2.5s threshold"),
    ("scripts/verify_marketing_lighthouse_budget.mjs", "0.1", "CLS 0.1 threshold"),
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


def _server_up(host: str, port: str) -> bool:
    url = f"http://{host}:{port}/"
    req = urllib.request.Request(url, headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    errors: list[str] = []
    host = os.environ.get("MKT_LIGHTHOUSE_HOST", "runmycampus.com")
    port = os.environ.get("MKT_LIGHTHOUSE_PORT", "8000")
    run_live = os.environ.get("MKT_RUN_SWEEP2_LIVE", "").strip() in ("1", "true", "yes")

    for rel in ARTIFACTS:
        if not (REPO / rel).is_file():
            errors.append(f"missing sweep2 artifact: {rel}")

    for rel, needle, label in ARTIFACT_SNIPPETS:
        if not (REPO / rel).is_file():
            continue
        if needle not in _read(rel):
            errors.append(f"{label}: expected `{needle}` in {rel}")

    theme = REPO / "tests/e2e/marketing-theme-contrast.spec.js"
    if theme.is_file() and not re.search(r"width:\s*390", theme.read_text(encoding="utf-8")):
        errors.append("theme matrix missing 390px mobile viewport")

    if run_live or _server_up(host, port):
        if not run_live:
            print(f"verify_marketing_sweep2: server up at {host}:{port} — running live LCP/CLS", file=sys.stderr)
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_lighthouse_budget.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
            env={**os.environ, "MKT_LIGHTHOUSE_STRICT": "1", "MKT_LIGHTHOUSE_HOST": host, "MKT_LIGHTHOUSE_PORT": port},
        )
        if proc.returncode != 0:
            errors.append(f"verify_marketing_lighthouse_budget.py failed:\n{proc.stderr or proc.stdout}")

        if shutil_which("npx"):
            e2e_env = {
                **os.environ,
                "MARKETING_BASE_URL": f"http://{host}:{port}",
                "PLAYWRIGHT_HOST_RULES": f"MAP {host} 127.0.0.1",
            }
            for spec in (
                "tests/e2e/marketing-impact-responsive.spec.js",
                "tests/e2e/marketing-gear2-a11y.spec.js",
                "tests/e2e/marketing-pricing-i18n.spec.js",
            ):
                try:
                    e2e = subprocess.run(
                        ["npx", "playwright", "test", spec, "--reporter=line"],
                        cwd=REPO,
                        capture_output=True,
                        text=True,
                        env=e2e_env,
                    )
                except FileNotFoundError:
                    print(
                        "verify_marketing_sweep2: npx/playwright unavailable — skipping live E2E",
                        file=sys.stderr,
                    )
                    break
                if e2e.returncode != 0:
                    errors.append(f"{spec} failed:\n{e2e.stderr or e2e.stdout}")
    else:
        print(
            "verify_marketing_sweep2: structural OK (set MKT_RUN_SWEEP2_LIVE=1 with Django on runmycampus.com:8000 for live LCP/CLS)",
            file=sys.stderr,
        )

    if errors:
        print("verify_marketing_sweep2: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("verify_marketing_sweep2: OK")
    return 0


def shutil_which(cmd: str) -> bool:
    from shutil import which

    return which(cmd) is not None


if __name__ == "__main__":
    raise SystemExit(main())
