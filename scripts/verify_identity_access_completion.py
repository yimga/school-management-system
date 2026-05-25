#!/usr/bin/env python3
"""Dual-plane identity completion gate — operator + tenant hubs green."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    if proc.returncode != 0:
        print(f"FAIL {script}")
        if tail:
            print(tail)
        return proc.returncode
    for line in (proc.stdout or "").splitlines():
        if line.endswith("_PASS"):
            print(line.strip())
    return 0


def main() -> int:
    checks = [
        "verify_operator_identity_hub.py",
        "verify_tenant_identity_hub.py",
        "verify_super_platform_scope_coverage.py",
        "verify_iam_identity_10x.py",
        "verify_iam_rebac_offline.py",
    ]
    for script in checks:
        code = _run(script)
        if code:
            print("IDENTITY_ACCESS_COMPLETION_FAIL")
            return code
    iam = ROOT / "apps/accounts/iam_localization.py"
    if not iam.is_file():
        print("IDENTITY_ACCESS_COMPLETION_FAIL missing iam_localization.py")
        return 1
    tenant_urls = (ROOT / "apps/accounts/urls.py").read_text(encoding="utf-8")
    if "tenant_identity_regulator_grant" not in tenant_urls:
        print("IDENTITY_ACCESS_COMPLETION_FAIL missing tenant regulator URL")
        return 1
    super_urls = (ROOT / "apps/schools/super_urls.py").read_text(encoding="utf-8")
    if "operator_team_suspend" not in super_urls:
        print("IDENTITY_ACCESS_COMPLETION_FAIL missing operator suspend URL")
        return 1
    print("IDENTITY_ACCESS_COMPLETION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
