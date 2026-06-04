#!/usr/bin/env python3
"""Bundle gate: platform /admin/ gear-up contracts (steering, render, page-fold)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, env=env or os.environ
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode


def main() -> int:
    index = ROOT / "templates/admin/index_superadmin.html"
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    fold_ok = (
        'data-rmc-page-fold-nav="required"' in index_text
        and "rmc-page-fold-nav" in index_text
        and 'data-rmc-scroll-policy="paginate"' in index_text
    )
    if not fold_ok:
        print("FAIL: index_superadmin.html missing page-fold markers", file=sys.stderr)
        return 1

    full = os.environ.get("ADMIN_RENDER_FULL", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if full:
        render_cmd = [
            sys.executable,
            "scripts/verify_admin_changelist_render_contract.py",
            "--write",
        ]
        render_env = {**os.environ, "ADMIN_RENDER_FULL": "1"}
    else:
        render_cmd = [
            sys.executable,
            "scripts/verify_admin_changelist_render_contract.py",
        ]
        render_env = {**os.environ, "ADMIN_RENDER_SAMPLE_MAX": "32"}

    steps: list[tuple[list[str], dict[str, str] | None]] = [
        ([sys.executable, "scripts/verify_admin_steering_strip_contract.py"], None),
        (render_cmd, render_env),
    ]
    for cmd, env in steps:
        if _run(cmd, env) != 0:
            return 1
    if _run([sys.executable, "scripts/verify_admin_playwright_sweep_audit.py"], None) != 0:
        return 1
    print("verify_admin_platform_gear_up_bundle: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
