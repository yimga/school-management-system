#!/usr/bin/env python3
"""Post-deploy smoke: manager /health/ + Workflow Progress Bus surface on Render.

Runs locally against any manager base URL (default production manager host).
Exits 0 with RENDER_WORKFLOW_PROGRESS_SMOKE_PASS when checks pass.

Usage:
  python scripts/smoke_render_workflow_progress_deploy.py
  python scripts/smoke_render_workflow_progress_deploy.py --base-url https://manager.runmycampus.com
  python scripts/smoke_render_workflow_progress_deploy.py --offline-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_runtime_posture(base_url: str, timeout: float) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_render_runtime_posture.py"),
            "--base-url",
            base_url.rstrip("/"),
            "--timeout",
            str(timeout),
        ],
        cwd=str(ROOT),
    )
    return int(proc.returncode)


def _run_local_bus_smoke() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "smoke_workflow_progress_bus.py")],
        cwd=str(ROOT),
    )
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="https://manager.runmycampus.com",
        help="Manager host (no trailing slash)",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Skip live HTTP; run in-repo workflow bus smoke only",
    )
    args = parser.parse_args()

    failures: list[str] = []

    if _run_local_bus_smoke() != 0:
        failures.append("smoke_workflow_progress_bus.py failed")

    if not args.offline_only:
        if _run_runtime_posture(args.base_url, args.timeout) != 0:
            failures.append(
                f"verify_render_runtime_posture.py failed for {args.base_url}"
            )

    if failures:
        print("RENDER_WORKFLOW_PROGRESS_SMOKE_FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("RENDER_WORKFLOW_PROGRESS_SMOKE_PASS")
    if args.offline_only:
        print("  mode: offline-only (local bus smoke)")
    else:
        print(f"  live: {args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
